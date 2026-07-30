"""Account and data deletion.

A hard app-store requirement, and the right default regardless: someone who no longer
wants a third party holding their family court file should not have to ask.

The tests that matter are the completeness ones — nothing case-related may survive —
and the one proving the audit trail outlives the account, anonymized.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pyotp
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.mfa import TOTP_INTERVAL_SECONDS, generate_encryption_key
from app.core.config import settings
from app.db.session import get_session
from app.main import app
from app.storage.local import LocalObjectStore
from tests.pdf_builder import make_pdf

PASSWORD = "correct-horse-battery-staple"
SECRET = "SYNTHETIC_SIGNING_KEY_LONG_ENOUGH_FOR_HS256"
LINE = "Petitioner requests modification of timesharing."


@pytest_asyncio.fixture()
async def store(tmp_path: Path) -> LocalObjectStore:
    return LocalObjectStore(tmp_path / "objects")


@pytest_asyncio.fixture()
async def client(
    session: AsyncSession, store: LocalObjectStore, monkeypatch: Any
) -> AsyncIterator[AsyncClient]:
    async def _session_override() -> AsyncSession:
        return session

    monkeypatch.setattr(settings, "mfa_encryption_key", generate_encryption_key())
    app.dependency_overrides[get_session] = _session_override
    app.state.jwt_secret = SECRET
    app.state.object_store = store
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as async_client:
            yield async_client
    finally:
        app.dependency_overrides.clear()


async def _account_with_a_document(client: AsyncClient) -> tuple[str, dict[str, str], str]:
    email = f"user-{uuid.uuid4().hex[:10]}@example.com"
    await client.post("/auth/register", json={"email": email, "password": PASSWORD})
    tokens = (await client.post("/auth/login", json={"email": email, "password": PASSWORD})).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    case_id = (await client.post("/cases", json={"title": "My Matter"}, headers=headers)).json()[
        "id"
    ]
    await client.post(
        f"/cases/{case_id}/documents",
        files={"file": ("filing.pdf", make_pdf([LINE]), "application/pdf")},
        headers=headers,
    )
    return email, headers, case_id


async def _delete(client: AsyncClient, headers: dict[str, str], **overrides: Any) -> Any:
    body: dict[str, Any] = {"password": PASSWORD, "acknowledge": True}
    body.update(overrides)
    return await client.post("/auth/me/delete", json=body, headers=headers)


async def test_deletion_removes_the_account_and_its_case_material(
    client: AsyncClient, session: AsyncSession
) -> None:
    _, headers, _ = await _account_with_a_document(client)

    response = await _delete(client, headers)
    assert response.status_code == 200, response.text
    assert response.json()["cases_deleted"] == 1
    assert response.json()["documents_deleted"] == 1

    for table in ("user_account", '"case"', "document", "document_page", "passage"):
        remaining = (await session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()  # noqa: S608
        assert remaining == 0, f"{table} still holds rows after deletion"


async def test_deletion_removes_the_stored_bytes(
    client: AsyncClient, store: LocalObjectStore, session: AsyncSession
) -> None:
    """Erasing the record without erasing the blob would leave the documents intact on
    disk — the opposite of what the user asked for."""
    _, headers, _ = await _account_with_a_document(client)
    key = (await session.execute(text("SELECT storage_key FROM document"))).scalar_one()
    assert await store.get(key)

    response = await _delete(client, headers)
    assert response.json()["objects_removed"] == 1

    from app.storage.base import ObjectNotFoundError

    try:
        await store.get(key)
        raise AssertionError("the document bytes survived deletion")
    except ObjectNotFoundError:
        pass


async def test_sessions_passkeys_and_mfa_are_destroyed_with_the_account(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Anything left behind is a credential belonging to an account that no longer
    exists."""
    _, headers, _ = await _account_with_a_document(client)
    setup = (await client.post("/auth/mfa/setup", headers=headers)).json()
    secret = __import__("urllib.parse", fromlist=["parse_qs"]).parse_qs(
        __import__("urllib.parse", fromlist=["urlparse"]).urlparse(setup["provisioning_uri"]).query
    )["secret"][0]
    totp = pyotp.TOTP(secret, interval=TOTP_INTERVAL_SECONDS)
    import time

    await client.post(
        "/auth/mfa/confirm",
        json={"code": totp.at(int(time.time()) - TOTP_INTERVAL_SECONDS)},
        headers=headers,
    )

    response = await _delete(client, headers, mfa_code=totp.at(int(time.time())))
    assert response.status_code == 200, response.text

    for table in ("user_session", "user_mfa", "recovery_code", "passkey"):
        remaining = (await session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()  # noqa: S608
        assert remaining == 0, f"{table} survived account deletion"


async def test_the_audit_trail_survives_anonymized(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Erasing the account erases its contents and its identity, not the record that
    the system was used."""
    _, headers, _ = await _account_with_a_document(client)
    await _delete(client, headers)

    rows = (await session.execute(text("SELECT count(*) FROM case_audit_event"))).scalar_one()
    orphaned = (
        await session.execute(
            text("SELECT count(*) FROM case_audit_event WHERE actor_user_id IS NOT NULL")
        )
    ).scalar_one()
    assert rows > 0
    assert orphaned == 0


async def test_deletion_requires_the_password(client: AsyncClient, session: AsyncSession) -> None:
    _, headers, _ = await _account_with_a_document(client)

    response = await _delete(client, headers, password="wrong-password-entirely")
    assert response.status_code == 401
    assert (await session.execute(text('SELECT count(*) FROM "case"'))).scalar_one() == 1


async def test_deletion_requires_an_explicit_acknowledgement(client: AsyncClient) -> None:
    """Forces the client to show what is about to be lost rather than offering a bare
    button."""
    _, headers, _ = await _account_with_a_document(client)
    assert (await _delete(client, headers, acknowledge=False)).status_code == 422


async def test_deletion_requires_the_second_factor_when_mfa_is_on(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Destroying the account is exactly what someone who found an unlocked phone would
    do, and it is the one action with no undo."""
    _, headers, _ = await _account_with_a_document(client)
    setup = (await client.post("/auth/mfa/setup", headers=headers)).json()
    import time
    from urllib.parse import parse_qs, urlparse

    secret = parse_qs(urlparse(setup["provisioning_uri"]).query)["secret"][0]
    totp = pyotp.TOTP(secret, interval=TOTP_INTERVAL_SECONDS)
    await client.post(
        "/auth/mfa/confirm",
        json={"code": totp.at(int(time.time()) - TOTP_INTERVAL_SECONDS)},
        headers=headers,
    )

    assert (await _delete(client, headers)).status_code == 401
    assert (await _delete(client, headers, mfa_code="000000")).status_code == 401
    assert (await session.execute(text('SELECT count(*) FROM "case"'))).scalar_one() == 1


async def test_deletion_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/me/delete", json={"password": PASSWORD, "acknowledge": True}
    )
    assert response.status_code == 401


async def test_another_accounts_data_is_untouched(
    client: AsyncClient, session: AsyncSession
) -> None:
    _, mine, _ = await _account_with_a_document(client)
    _, theirs, _ = await _account_with_a_document(client)

    await _delete(client, mine)

    assert (await session.execute(text('SELECT count(*) FROM "case"'))).scalar_one() == 1
    assert (await session.execute(text("SELECT count(*) FROM document"))).scalar_one() == 1
    assert (await client.get("/cases", headers=theirs)).status_code == 200


async def test_the_session_stops_working_after_deletion(client: AsyncClient) -> None:
    _, headers, _ = await _account_with_a_document(client)
    await _delete(client, headers)

    assert (await client.get("/auth/me", headers=headers)).status_code == 401
