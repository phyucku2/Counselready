"""Authentication end to end: real HTTP, real PostgreSQL.

Driven through `httpx.ASGITransport` rather than `TestClient` on purpose. TestClient
runs the app in its own event loop, so the asyncpg session these tests share with the
routes would be used from two loops and fail. ASGITransport keeps the app, the test,
and the transaction in one loop.

The lifespan does not run under ASGITransport, so the fixture supplies the signing key
the same way startup would.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import MAX_FAILED_LOGINS
from app.db.session import get_session
from app.main import app

PASSWORD = "correct-horse-battery-staple"
SECRET = "SYNTHETIC_SIGNING_KEY_LONG_ENOUGH_FOR_HS256"


@pytest_asyncio.fixture()
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def _session_override() -> AsyncSession:
        return session

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


async def _register(client: AsyncClient, email: str, password: str = PASSWORD) -> None:
    response = await client.post(
        "/auth/register", json={"email": email, "password": password, "display_name": "Pat"}
    )
    assert response.status_code == 201, response.text


async def _login(client: AsyncClient, email: str, password: str = PASSWORD) -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    tokens: dict[str, str] = response.json()
    return tokens


def _auth(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_register_then_login_then_read_own_account(client: AsyncClient) -> None:
    email = _email()
    await _register(client, email)
    tokens = await _login(client, email)

    response = await client.get("/auth/me", headers=_auth(tokens))
    assert response.status_code == 200
    assert response.json()["email"] == email


async def test_the_registration_response_never_contains_a_password_or_hash(
    client: AsyncClient,
) -> None:
    response = await client.post("/auth/register", json={"email": _email(), "password": PASSWORD})
    assert PASSWORD not in response.text
    assert "argon2" not in response.text.lower()
    assert "password" not in response.json()


async def test_a_duplicate_registration_is_refused(client: AsyncClient) -> None:
    email = _email()
    await _register(client, email)
    duplicate = await client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert duplicate.status_code == 409


async def test_email_case_and_whitespace_do_not_create_a_second_account(
    client: AsyncClient,
) -> None:
    """Two accounts differing only in capitalization would be a way to shadow someone
    else's address."""
    email = _email()
    await _register(client, email)
    response = await client.post(
        "/auth/register", json={"email": f"  {email.upper()}  ", "password": PASSWORD}
    )
    assert response.status_code in (409, 422)


async def test_login_with_a_different_case_email_succeeds(client: AsyncClient) -> None:
    email = _email()
    await _register(client, email)
    response = await client.post("/auth/login", json={"email": email.upper(), "password": PASSWORD})
    assert response.status_code == 200


async def test_a_short_password_is_refused_at_registration(client: AsyncClient) -> None:
    response = await client.post("/auth/register", json={"email": _email(), "password": "short"})
    assert response.status_code == 422


async def test_a_wrong_password_and_an_unknown_email_are_indistinguishable(
    client: AsyncClient,
) -> None:
    """The response to a probe must not reveal whether the account exists."""
    email = _email()
    await _register(client, email)

    wrong = await client.post("/auth/login", json={"email": email, "password": "wrong-password-x"})
    unknown = await client.post("/auth/login", json={"email": _email(), "password": PASSWORD})

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


async def test_an_unauthenticated_request_is_refused(client: AsyncClient) -> None:
    assert (await client.get("/auth/me")).status_code == 401


async def test_a_garbage_bearer_token_is_refused(client: AsyncClient) -> None:
    response = await client.get("/auth/me", headers={"Authorization": "Bearer nonsense"})
    assert response.status_code == 401


async def test_a_token_signed_with_the_wrong_key_is_refused(client: AsyncClient) -> None:
    from datetime import UTC, datetime

    from app.auth.tokens import issue_access_token

    forged = issue_access_token(
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        secret="SYNTHETIC_ATTACKER_KEY_ALSO_LONG_ENOUGH_256",
        now=datetime.now(UTC),
    )
    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


async def test_a_validly_signed_token_for_no_real_session_is_refused(
    client: AsyncClient,
) -> None:
    """Signature alone is not enough — the session must still exist and be live."""
    from datetime import UTC, datetime

    from app.auth.tokens import issue_access_token

    orphan = issue_access_token(
        user_id=uuid.uuid4(), session_id=uuid.uuid4(), secret=SECRET, now=datetime.now(UTC)
    )
    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {orphan}"})
    assert response.status_code == 401


async def test_refreshing_rotates_the_token_and_keeps_the_session(
    client: AsyncClient,
) -> None:
    email = _email()
    await _register(client, email)
    tokens = await _login(client, email)

    response = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 200
    rotated = response.json()
    assert rotated["refresh_token"] != tokens["refresh_token"]
    assert (await client.get("/auth/me", headers=_auth(rotated))).status_code == 200


async def test_replaying_a_rotated_refresh_token_kills_the_whole_session(
    client: AsyncClient,
) -> None:
    """Replay is the signature of a stolen token. We cannot tell the thief from the
    legitimate holder, so both lose the session — the safe outcome."""
    email = _email()
    await _register(client, email)
    tokens = await _login(client, email)

    rotated = (
        await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    ).json()

    replay = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert replay.status_code == 401

    # The rotated token dies with the session, and so does its access token.
    followup = await client.post("/auth/refresh", json={"refresh_token": rotated["refresh_token"]})
    assert followup.status_code == 401
    assert (await client.get("/auth/me", headers=_auth(rotated))).status_code == 401


async def test_an_unknown_refresh_token_is_refused(client: AsyncClient) -> None:
    response = await client.post("/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert response.status_code == 401


async def test_logging_out_immediately_invalidates_the_access_token(
    client: AsyncClient,
) -> None:
    """The access token has not expired; it must stop working anyway, or logout is
    cosmetic until the token lapses."""
    email = _email()
    await _register(client, email)
    tokens = await _login(client, email)

    assert (await client.post("/auth/logout", headers=_auth(tokens))).status_code == 204
    assert (await client.get("/auth/me", headers=_auth(tokens))).status_code == 401
    stale = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert stale.status_code == 401


async def test_logging_out_everywhere_ends_every_session(client: AsyncClient) -> None:
    """'Someone else may be in my account' needs one action that works immediately."""
    email = _email()
    await _register(client, email)
    first = await _login(client, email)
    second = await _login(client, email)

    assert (await client.post("/auth/logout-all", headers=_auth(first))).status_code == 204
    assert (await client.get("/auth/me", headers=_auth(first))).status_code == 401
    assert (await client.get("/auth/me", headers=_auth(second))).status_code == 401


async def test_one_session_ending_leaves_the_other_alive(client: AsyncClient) -> None:
    """Signing out on a phone must not sign the user out on their laptop."""
    email = _email()
    await _register(client, email)
    phone = await _login(client, email)
    laptop = await _login(client, email)

    assert (await client.post("/auth/logout", headers=_auth(phone))).status_code == 204
    assert (await client.get("/auth/me", headers=_auth(laptop))).status_code == 200


async def test_repeated_failures_are_rate_limited(client: AsyncClient) -> None:
    email = _email()
    await _register(client, email)

    for _ in range(MAX_FAILED_LOGINS):
        failed = await client.post(
            "/auth/login", json={"email": email, "password": "wrong-password-x"}
        )
        assert failed.status_code == 401

    limited = await client.post(
        "/auth/login", json={"email": email, "password": "wrong-password-x"}
    )
    assert limited.status_code == 429
    assert limited.headers["Retry-After"]

    # The limit holds even with the right password, so guessing cannot be confirmed by
    # a lucky attempt inside a throttled window.
    correct = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert correct.status_code == 429


async def test_throttling_one_account_does_not_lock_out_another(client: AsyncClient) -> None:
    """The limiter is per identity; one targeted account must not deny service to
    everyone else."""
    victim, bystander = _email(), _email()
    await _register(client, victim)
    await _register(client, bystander)

    for _ in range(MAX_FAILED_LOGINS + 1):
        await client.post("/auth/login", json={"email": victim, "password": "wrong-password-x"})

    response = await client.post("/auth/login", json={"email": bystander, "password": PASSWORD})
    assert response.status_code == 200


async def test_a_deactivated_account_cannot_sign_in(
    client: AsyncClient, session: AsyncSession
) -> None:
    email = _email()
    await _register(client, email)
    await session.execute(
        text("UPDATE user_account SET active = false WHERE email = :email"), {"email": email}
    )
    await session.flush()

    response = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 401


async def test_a_password_is_never_written_to_the_database_in_plaintext(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Proven by absence, over the actual stored row."""
    email = _email()
    await _register(client, email)

    stored = (
        await session.execute(
            text("SELECT password_hash FROM user_account WHERE email = :email"), {"email": email}
        )
    ).scalar_one()
    assert PASSWORD not in stored
    assert stored.startswith("$argon2id$")


async def test_a_refresh_token_is_never_stored_in_usable_form(
    client: AsyncClient, session: AsyncSession
) -> None:
    """A database disclosure must not hand over working sessions."""
    email = _email()
    await _register(client, email)
    tokens = await _login(client, email)

    digests = list(
        (await session.execute(text("SELECT refresh_digest FROM user_session"))).scalars()
    )
    assert digests
    assert all(tokens["refresh_token"] not in digest for digest in digests)
