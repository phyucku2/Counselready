"""MFA end to end.

The property that matters: once MFA is on, a correct password alone must not produce
credentials. Everything else here supports that or protects the recovery path.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pyotp
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.mfa import TOTP_INTERVAL_SECONDS, generate_encryption_key
from app.core.config import settings
from app.db.session import get_session
from app.main import app

PASSWORD = "correct-horse-battery-staple"
SECRET = "SYNTHETIC_SIGNING_KEY_LONG_ENOUGH_FOR_HS256"


@pytest_asyncio.fixture()
async def client(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncClient]:
    async def _session_override() -> AsyncSession:
        return session

    monkeypatch.setattr(settings, "mfa_encryption_key", generate_encryption_key())
    app.dependency_overrides[get_session] = _session_override
    app.state.jwt_secret = SECRET
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as async_client:
            yield async_client
    finally:
        app.dependency_overrides.clear()


def _email() -> str:
    return f"user-{uuid.uuid4().hex[:10]}@example.com"


def _secret_from_uri(uri: str) -> str:
    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(uri).query)["secret"][0]


def _code(secret: str, *, offset: int = 0) -> str:
    import time

    return pyotp.TOTP(secret, interval=TOTP_INTERVAL_SECONDS).at(
        int(time.time()) + offset * TOTP_INTERVAL_SECONDS
    )


async def _account(client: AsyncClient) -> tuple[str, dict[str, str]]:
    email = _email()
    registered = await client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert registered.status_code == 201, registered.text
    tokens = (await client.post("/auth/login", json={"email": email, "password": PASSWORD})).json()
    return email, {"Authorization": f"Bearer {tokens['access_token']}"}


async def _enrol(client: AsyncClient) -> tuple[str, dict[str, str], str, list[str]]:
    """Register, log in, and complete MFA enrolment. Returns the TOTP secret too."""
    email, headers = await _account(client)
    setup = await client.post("/auth/mfa/setup", headers=headers)
    assert setup.status_code == 200, setup.text
    body = setup.json()
    secret = _secret_from_uri(body["provisioning_uri"])

    # Confirm with a code from the PREVIOUS step, so the current step is still
    # unused and tests can spend it. Confirming records the step it consumed —
    # reusing that same code afterwards is correctly refused as a replay.
    confirmed = await client.post(
        "/auth/mfa/confirm", json={"code": _code(secret, offset=-1)}, headers=headers
    )
    assert confirmed.status_code == 204, confirmed.text
    return email, headers, secret, body["recovery_codes"]


async def test_enrolment_returns_a_provisioning_uri_and_recovery_codes(
    client: AsyncClient,
) -> None:
    _, headers = await _account(client)
    response = await client.post("/auth/mfa/setup", headers=headers)

    body = response.json()
    assert body["provisioning_uri"].startswith("otpauth://totp/")
    assert "CounselReady" in body["provisioning_uri"]
    assert len(body["recovery_codes"]) == 10
    assert len(set(body["recovery_codes"])) == 10


async def test_mfa_is_not_active_until_a_code_is_confirmed(client: AsyncClient) -> None:
    """Activating on issue would lock out anyone whose QR scan silently failed."""
    email, headers = await _account(client)
    await client.post("/auth/mfa/setup", headers=headers)

    status_response = await client.get("/auth/mfa/status", headers=headers)
    assert status_response.json()["enabled"] is False

    # Login still returns tokens, because MFA is not active yet.
    login = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert "access_token" in login.json()


async def test_confirming_with_a_wrong_code_leaves_mfa_off(client: AsyncClient) -> None:
    _, headers = await _account(client)
    await client.post("/auth/mfa/setup", headers=headers)

    rejected = await client.post("/auth/mfa/confirm", json={"code": "000000"}, headers=headers)
    assert rejected.status_code == 401
    assert (await client.get("/auth/mfa/status", headers=headers)).json()["enabled"] is False


async def test_a_correct_password_alone_no_longer_yields_a_session(
    client: AsyncClient,
) -> None:
    """The whole point. A stolen password must buy nothing but a challenge."""
    email, _, _, _ = await _enrol(client)

    login = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    body = login.json()

    assert login.status_code == 200
    assert body["mfa_required"] is True
    assert "access_token" not in body
    assert "refresh_token" not in body


async def test_the_challenge_cannot_be_used_as_an_access_token(
    client: AsyncClient,
) -> None:
    """A challenge is not a session. Presenting it to an authenticated route must fail,
    or the second factor would be trivially bypassed."""
    email, _, _, _ = await _enrol(client)
    challenge = (
        await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    ).json()["challenge_token"]

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {challenge}"})
    assert response.status_code == 401


async def test_a_valid_code_exchanges_the_challenge_for_a_session(
    client: AsyncClient,
) -> None:
    email, _, secret, _ = await _enrol(client)
    challenge = (
        await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    ).json()["challenge_token"]

    verified = await client.post(
        "/auth/mfa/verify", json={"challenge_token": challenge, "code": _code(secret)}
    )
    assert verified.status_code == 200
    tokens = verified.json()

    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == email


async def test_a_wrong_code_does_not_yield_a_session(client: AsyncClient) -> None:
    email, _, _, _ = await _enrol(client)
    challenge = (
        await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    ).json()["challenge_token"]

    rejected = await client.post(
        "/auth/mfa/verify", json={"challenge_token": challenge, "code": "000000"}
    )
    assert rejected.status_code == 401


async def test_a_code_cannot_be_replayed_within_its_own_window(
    client: AsyncClient,
) -> None:
    """Without replay protection, a code glimpsed over a shoulder stays usable for up
    to ninety seconds."""
    email, _, secret, _ = await _enrol(client)
    code = _code(secret)

    first_challenge = (
        await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    ).json()["challenge_token"]
    first = await client.post(
        "/auth/mfa/verify", json={"challenge_token": first_challenge, "code": code}
    )
    assert first.status_code == 200

    second_challenge = (
        await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    ).json()["challenge_token"]
    replay = await client.post(
        "/auth/mfa/verify", json={"challenge_token": second_challenge, "code": code}
    )
    assert replay.status_code == 401


async def test_a_forged_challenge_is_refused(client: AsyncClient) -> None:
    from datetime import UTC, datetime

    from app.auth.tokens import issue_mfa_challenge

    forged = issue_mfa_challenge(
        user_id=uuid.uuid4(),
        secret="SYNTHETIC_ATTACKER_KEY_ALSO_LONG_ENOUGH_256",
        now=datetime.now(UTC),
    )
    response = await client.post(
        "/auth/mfa/verify", json={"challenge_token": forged, "code": "000000"}
    )
    assert response.status_code == 401


async def test_an_access_token_cannot_be_used_as_a_challenge(client: AsyncClient) -> None:
    """The `typ` claim is checked in both directions."""
    _, headers = await _account(client)
    access = headers["Authorization"].removeprefix("Bearer ")

    response = await client.post(
        "/auth/mfa/verify", json={"challenge_token": access, "code": "000000"}
    )
    assert response.status_code == 401


async def test_a_recovery_code_works_when_the_authenticator_is_gone(
    client: AsyncClient,
) -> None:
    """The lost-device path. Without it, losing a phone loses the account."""
    email, _, _, recovery_codes = await _enrol(client)
    challenge = (
        await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    ).json()["challenge_token"]

    verified = await client.post(
        "/auth/mfa/verify",
        json={"challenge_token": challenge, "code": recovery_codes[0]},
    )
    assert verified.status_code == 200
    assert "access_token" in verified.json()


async def test_a_recovery_code_is_single_use(client: AsyncClient) -> None:
    email, _, _, recovery_codes = await _enrol(client)

    for expected in (200, 401):
        challenge = (
            await client.post("/auth/login", json={"email": email, "password": PASSWORD})
        ).json()["challenge_token"]
        response = await client.post(
            "/auth/mfa/verify",
            json={"challenge_token": challenge, "code": recovery_codes[0]},
        )
        assert response.status_code == expected


async def test_a_recovery_code_is_accepted_without_its_separators(
    client: AsyncClient,
) -> None:
    """People retype these from paper; formatting must not reject a correct code."""
    email, _, _, recovery_codes = await _enrol(client)
    challenge = (
        await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    ).json()["challenge_token"]

    response = await client.post(
        "/auth/mfa/verify",
        json={"challenge_token": challenge, "code": recovery_codes[0].replace("-", "").lower()},
    )
    assert response.status_code == 200


async def test_using_a_recovery_code_reduces_the_remaining_count(
    client: AsyncClient,
) -> None:
    email, headers, _, recovery_codes = await _enrol(client)
    assert (await client.get("/auth/mfa/status", headers=headers)).json()[
        "recovery_codes_remaining"
    ] == 10

    challenge = (
        await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    ).json()["challenge_token"]
    await client.post(
        "/auth/mfa/verify", json={"challenge_token": challenge, "code": recovery_codes[0]}
    )

    assert (await client.get("/auth/mfa/status", headers=headers)).json()[
        "recovery_codes_remaining"
    ] == 9


async def test_disabling_requires_both_the_password_and_a_code(
    client: AsyncClient,
) -> None:
    """Someone at an unlocked laptop must not be able to strip the second factor."""
    _, headers, secret, _ = await _enrol(client)

    no_password = await client.post(
        "/auth/mfa/disable",
        json={"password": "wrong-password-entirely", "code": _code(secret)},
        headers=headers,
    )
    assert no_password.status_code == 401

    no_code = await client.post(
        "/auth/mfa/disable", json={"password": PASSWORD, "code": "000000"}, headers=headers
    )
    assert no_code.status_code == 401

    assert (await client.get("/auth/mfa/status", headers=headers)).json()["enabled"] is True


async def test_disabling_with_both_factors_turns_mfa_off(client: AsyncClient) -> None:
    email, headers, secret, _ = await _enrol(client)

    disabled = await client.post(
        "/auth/mfa/disable",
        json={"password": PASSWORD, "code": _code(secret, offset=1)},
        headers=headers,
    )
    assert disabled.status_code == 204
    assert (await client.get("/auth/mfa/status", headers=headers)).json()["enabled"] is False

    # Login returns tokens directly again.
    login = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert "access_token" in login.json()


async def test_disabling_destroys_the_recovery_codes(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Leaving them behind would let an old code bypass a later re-enrolment."""
    _, headers, secret, _ = await _enrol(client)
    await client.post(
        "/auth/mfa/disable",
        json={"password": PASSWORD, "code": _code(secret, offset=1)},
        headers=headers,
    )

    remaining = (await session.execute(text("SELECT count(*) FROM recovery_code"))).scalar_one()
    assert remaining == 0


async def test_the_totp_secret_is_encrypted_at_rest(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Plaintext here would make a database disclosure enough to generate valid codes
    forever — the second factor would be decorative."""
    _, _, secret, _ = await _enrol(client)

    stored = (await session.execute(text("SELECT encrypted_secret FROM user_mfa"))).scalar_one()
    assert secret not in stored
    assert stored.startswith("gAAAAA")  # Fernet's version prefix


async def test_recovery_codes_are_not_stored_in_usable_form(
    client: AsyncClient, session: AsyncSession
) -> None:
    _, _, _, recovery_codes = await _enrol(client)

    digests = list((await session.execute(text("SELECT digest FROM recovery_code"))).scalars())
    for code in recovery_codes:
        assert all(code not in digest for digest in digests)
        assert all(code.replace("-", "") not in digest for digest in digests)


async def test_mfa_status_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get("/auth/mfa/status")).status_code == 401


async def test_setup_is_refused_once_mfa_is_active(client: AsyncClient) -> None:
    """Re-running setup on an active enrolment would silently rotate the secret out
    from under a working authenticator."""
    _, headers, _, _ = await _enrol(client)
    assert (await client.post("/auth/mfa/setup", headers=headers)).status_code == 409


async def test_restarting_an_unconfirmed_setup_is_allowed(client: AsyncClient) -> None:
    """A user whose first scan failed must be able to start over unaided."""
    _, headers = await _account(client)
    first = (await client.post("/auth/mfa/setup", headers=headers)).json()
    second = (await client.post("/auth/mfa/setup", headers=headers)).json()

    assert first["provisioning_uri"] != second["provisioning_uri"]

    # Only the newest secret works.
    stale = await client.post(
        "/auth/mfa/confirm",
        json={"code": _code(_secret_from_uri(first["provisioning_uri"]))},
        headers=headers,
    )
    assert stale.status_code == 401

    current = await client.post(
        "/auth/mfa/confirm",
        json={"code": _code(_secret_from_uri(second["provisioning_uri"]))},
        headers=headers,
    )
    assert current.status_code == 204
