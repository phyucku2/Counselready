"""Passkeys end to end, driven by a software authenticator.

A real Face ID prompt cannot be automated, so these tests implement the authenticator
side in Python: an ES256 key pair, a signed attestation, and signed assertions. That
exercises the actual WebAuthn verification path rather than mocking it — the parts a
mock would hide (signature checks, origin binding, challenge consumption) are exactly
the parts worth testing.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import uuid
from collections.abc import AsyncIterator
from typing import Any

import cbor2
import pytest_asyncio
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.main import app

PASSWORD = "correct-horse-battery-staple"
SECRET = "SYNTHETIC_SIGNING_KEY_LONG_ENOUGH_FOR_HS256"
RP_ID = "localhost"
ORIGIN = "http://localhost:5173"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


class SoftwareAuthenticator:
    """A minimal FIDO2 authenticator: enough to produce responses we actually verify."""

    def __init__(self) -> None:
        self.credential_id = os.urandom(32)
        self._key = ec.generate_private_key(ec.SECP256R1())
        self.sign_count = 0

    def _cose_key(self) -> dict[int, Any]:
        numbers = self._key.public_key().public_numbers()
        return {
            1: 2,  # kty: EC2
            3: -7,  # alg: ES256
            -1: 1,  # crv: P-256
            -2: numbers.x.to_bytes(32, "big"),
            -3: numbers.y.to_bytes(32, "big"),
        }

    def _authenticator_data(self, *, attested: bool) -> bytes:
        # UP (user present) | UV (user verified) | BE | BS, and AT when attesting.
        # UV set is what `require_user_verification=True` checks — it is the bit that
        # says a human was confirmed by Face ID, fingerprint, or PIN.
        flags = 0b0101_1101 if attested else 0b0001_1101
        data = hashlib.sha256(RP_ID.encode()).digest() + bytes([flags])
        data += struct.pack(">I", self.sign_count)
        if attested:
            data += bytes(16)  # AAGUID
            data += struct.pack(">H", len(self.credential_id))
            data += self.credential_id
            data += cbor2.dumps(self._cose_key())
        return data

    def _client_data(self, *, challenge: str, ceremony: str) -> bytes:
        return json.dumps(
            {"type": ceremony, "challenge": challenge, "origin": ORIGIN, "crossOrigin": False},
            separators=(",", ":"),
        ).encode()

    def register(self, challenge: str) -> dict[str, Any]:
        client_data = self._client_data(challenge=challenge, ceremony="webauthn.create")
        attestation = cbor2.dumps(
            {"fmt": "none", "attStmt": {}, "authData": self._authenticator_data(attested=True)}
        )
        return {
            "id": _b64url(self.credential_id),
            "rawId": _b64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": _b64url(client_data),
                "attestationObject": _b64url(attestation),
            },
            "clientExtensionResults": {},
        }

    def assert_(self, challenge: str) -> dict[str, Any]:
        self.sign_count += 1
        client_data = self._client_data(challenge=challenge, ceremony="webauthn.get")
        authenticator_data = self._authenticator_data(attested=False)
        signature = self._key.sign(
            authenticator_data + hashlib.sha256(client_data).digest(),
            ec.ECDSA(hashes.SHA256()),
        )
        return {
            "id": _b64url(self.credential_id),
            "rawId": _b64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": _b64url(client_data),
                "authenticatorData": _b64url(authenticator_data),
                "signature": _b64url(signature),
                "userHandle": None,
            },
            "clientExtensionResults": {},
        }


@pytest_asyncio.fixture()
async def client(session: AsyncSession, monkeypatch: Any) -> AsyncIterator[AsyncClient]:
    async def _session_override() -> AsyncSession:
        return session

    monkeypatch.setattr(settings, "webauthn_rp_id", RP_ID)
    monkeypatch.setattr(settings, "webauthn_origin", ORIGIN)
    app.dependency_overrides[get_session] = _session_override
    app.state.jwt_secret = SECRET
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as async_client:
            yield async_client
    finally:
        app.dependency_overrides.clear()


async def _signed_in(client: AsyncClient) -> tuple[str, dict[str, str]]:
    email = f"user-{uuid.uuid4().hex[:10]}@example.com"
    await client.post("/auth/register", json={"email": email, "password": PASSWORD})
    tokens = (await client.post("/auth/login", json={"email": email, "password": PASSWORD})).json()
    return email, {"Authorization": f"Bearer {tokens['access_token']}"}


async def _enrol_passkey(
    client: AsyncClient, headers: dict[str, str], label: str = "iPhone"
) -> SoftwareAuthenticator:
    options = (await client.post("/auth/passkeys/register/begin", headers=headers)).json()
    challenge = options["options"]["challenge"]
    authenticator = SoftwareAuthenticator()

    completed = await client.post(
        "/auth/passkeys/register/complete",
        json={"credential": authenticator.register(challenge), "label": label},
        headers=headers,
    )
    assert completed.status_code == 201, completed.text
    return authenticator


async def test_registering_a_passkey_then_signing_in_with_it(client: AsyncClient) -> None:
    email, headers = await _signed_in(client)
    authenticator = await _enrol_passkey(client, headers)

    options = (await client.post("/auth/passkeys/login/begin", json={"email": email})).json()
    tokens = await client.post(
        "/auth/passkeys/login/complete",
        json={"credential": authenticator.assert_(options["challenge"])},
    )
    assert tokens.status_code == 200, tokens.text

    me = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {tokens.json()['access_token']}"}
    )
    assert me.json()["email"] == email


async def test_registration_requires_an_existing_session(client: AsyncClient) -> None:
    """A passkey is added by someone who has already proved who they are."""
    assert (await client.post("/auth/passkeys/register/begin")).status_code == 401


async def test_a_challenge_cannot_be_used_twice(client: AsyncClient) -> None:
    """Replay protection: a captured assertion must not sign in a second time."""
    email, headers = await _signed_in(client)
    authenticator = await _enrol_passkey(client, headers)

    options = (await client.post("/auth/passkeys/login/begin", json={"email": email})).json()
    credential = authenticator.assert_(options["challenge"])

    first = await client.post("/auth/passkeys/login/complete", json={"credential": credential})
    assert first.status_code == 200

    replay = await client.post("/auth/passkeys/login/complete", json={"credential": credential})
    assert replay.status_code == 401


async def test_an_assertion_for_an_unissued_challenge_is_refused(
    client: AsyncClient,
) -> None:
    _, headers = await _signed_in(client)
    authenticator = await _enrol_passkey(client, headers)

    invented = _b64url(os.urandom(32))
    response = await client.post(
        "/auth/passkeys/login/complete",
        json={"credential": authenticator.assert_(invented)},
    )
    assert response.status_code == 401


async def test_an_unregistered_authenticator_cannot_sign_in(client: AsyncClient) -> None:
    email, headers = await _signed_in(client)
    await _enrol_passkey(client, headers)

    options = (await client.post("/auth/passkeys/login/begin", json={"email": email})).json()
    stranger = SoftwareAuthenticator()

    response = await client.post(
        "/auth/passkeys/login/complete",
        json={"credential": stranger.assert_(options["challenge"])},
    )
    assert response.status_code == 401


async def test_login_begin_does_not_disclose_whether_an_account_exists(
    client: AsyncClient,
) -> None:
    """Same non-disclosure rule as password login — an unknown address still gets a
    well-formed challenge."""
    unknown = await client.post("/auth/passkeys/login/begin", json={"email": "nobody@example.com"})
    assert unknown.status_code == 200
    assert unknown.json()["challenge"]
    assert unknown.json()["allowCredentials"] == []


async def test_a_registered_passkey_is_listed_with_its_sync_state(
    client: AsyncClient,
) -> None:
    """Sync state is surfaced because a synced passkey lives wherever that Apple or
    Google account is signed in."""
    _, headers = await _signed_in(client)
    await _enrol_passkey(client, headers, label="Pat's iPhone")

    listed = (await client.get("/auth/passkeys", headers=headers)).json()
    assert len(listed) == 1
    assert listed[0]["label"] == "Pat's iPhone"
    assert "backed_up" in listed[0]


async def test_passkeys_are_listed_per_account(client: AsyncClient) -> None:
    _, mine = await _signed_in(client)
    _, theirs = await _signed_in(client)
    await _enrol_passkey(client, mine)

    assert len((await client.get("/auth/passkeys", headers=mine)).json()) == 1
    assert (await client.get("/auth/passkeys", headers=theirs)).json() == []


async def test_deleting_another_accounts_passkey_is_a_404(client: AsyncClient) -> None:
    _, mine = await _signed_in(client)
    _, theirs = await _signed_in(client)
    await _enrol_passkey(client, mine)
    passkey_id = (await client.get("/auth/passkeys", headers=mine)).json()[0]["id"]

    assert (await client.delete(f"/auth/passkeys/{passkey_id}", headers=theirs)).status_code == 404
    assert len((await client.get("/auth/passkeys", headers=mine)).json()) == 1


async def test_a_deleted_passkey_can_no_longer_sign_in(client: AsyncClient) -> None:
    email, headers = await _signed_in(client)
    authenticator = await _enrol_passkey(client, headers)
    passkey_id = (await client.get("/auth/passkeys", headers=headers)).json()[0]["id"]

    assert (await client.delete(f"/auth/passkeys/{passkey_id}", headers=headers)).status_code == 204

    options = (await client.post("/auth/passkeys/login/begin", json={"email": email})).json()
    response = await client.post(
        "/auth/passkeys/login/complete",
        json={"credential": authenticator.assert_(options["challenge"])},
    )
    assert response.status_code == 401


async def test_no_biometric_data_is_stored(client: AsyncClient, session: AsyncSession) -> None:
    """What we hold is a public key. The biometric never leaves the device, which is
    why this adds no biometric-privacy obligations."""
    _, headers = await _signed_in(client)
    await _enrol_passkey(client, headers)

    columns = (
        await session.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = 'passkey'")
        )
    ).scalars()
    names = set(columns)
    assert "public_key" in names
    assert not {name for name in names if "biometric" in name or "face" in name}
