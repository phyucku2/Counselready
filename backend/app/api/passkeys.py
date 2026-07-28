"""Passkey routes.

Registration requires an existing session, so a passkey is added by someone who has
already proved who they are. Sign-in exchanges an assertion for tokens — and when the
account also has TOTP, a passkey satisfies the second factor on its own, because
`user_verification=REQUIRED` means the authenticator already confirmed the human.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, JwtSecret
from app.auth.passkeys import (
    PasskeyVerificationError,
    RelyingParty,
    authentication_options,
    decode_challenge,
    encode_challenge,
    new_challenge,
    registration_options,
    verify_authentication,
    verify_registration,
)
from app.auth.service import complete_mfa_login, normalize_email
from app.models.passkey import Passkey, PasskeyChallenge
from app.models.user import UserAccount

router = APIRouter(prefix="/auth/passkeys", tags=["auth"])

CHALLENGE_TTL = timedelta(minutes=5)

INVALID = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Passkey could not be verified"
)


def relying_party(request: Request) -> RelyingParty:
    from app.core.config import settings

    return RelyingParty(
        rp_id=settings.webauthn_rp_id, name="CounselReady", origin=settings.webauthn_origin
    )


class RegisterBeginResponse(BaseModel):
    options: dict[str, object]


class CredentialRequest(BaseModel):
    credential: dict[str, object]
    label: str | None = Field(default=None, max_length=120)


class LoginBeginRequest(BaseModel):
    email: EmailStr


class PasskeyResponse(BaseModel):
    id: str
    label: str | None
    backed_up: bool
    last_used_at: datetime | None


async def _store_challenge(
    session: DbSession, *, user_id: uuid.UUID | None, challenge: bytes
) -> None:
    session.add(
        PasskeyChallenge(
            user_id=user_id,
            challenge=encode_challenge(challenge),
            expires_at=datetime.now(UTC) + CHALLENGE_TTL,
        )
    )
    await session.flush()


async def _consume_challenge(session: DbSession, *, credential: dict[str, object]) -> bytes:
    """Take the challenge this response answers, deleting it so it cannot serve twice."""
    from webauthn.helpers import base64url_to_bytes

    try:
        client_data = json.loads(
            base64url_to_bytes(str(credential["response"]["clientDataJSON"]))  # type: ignore[index]
        )
        presented = str(client_data["challenge"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise INVALID from exc

    record = (
        await session.execute(
            select(PasskeyChallenge).where(PasskeyChallenge.challenge == presented)
        )
    ).scalar_one_or_none()
    if record is None or record.expires_at <= datetime.now(UTC):
        raise INVALID

    await session.delete(record)
    await session.flush()
    return decode_challenge(presented)


@router.get("", response_model=list[PasskeyResponse])
async def list_passkeys(account: CurrentUser, session: DbSession) -> list[PasskeyResponse]:
    passkeys = list(
        (await session.execute(select(Passkey).where(Passkey.user_id == account.id))).scalars()
    )
    return [
        PasskeyResponse(
            id=str(passkey.id),
            label=passkey.label,
            # Surfaced on purpose: a synced passkey lives wherever that Apple or Google
            # account is signed in, which the user may not have thought about.
            backed_up=passkey.backed_up,
            last_used_at=passkey.last_used_at,
        )
        for passkey in passkeys
    ]


@router.post("/register/begin", response_model=RegisterBeginResponse)
async def register_begin(
    account: CurrentUser, session: DbSession, request: Request
) -> RegisterBeginResponse:
    existing = [
        passkey.credential_id
        for passkey in (
            await session.execute(select(Passkey).where(Passkey.user_id == account.id))
        ).scalars()
    ]
    challenge = new_challenge()
    await _store_challenge(session, user_id=account.id, challenge=challenge)

    options = registration_options(
        party=relying_party(request),
        user_id=account.id.bytes,
        user_name=account.email,
        display_name=account.display_name,
        challenge=challenge,
        existing_credentials=existing,
    )
    return RegisterBeginResponse(options=json.loads(options))


@router.post("/register/complete", status_code=status.HTTP_201_CREATED)
async def register_complete(
    body: CredentialRequest, account: CurrentUser, session: DbSession, request: Request
) -> Response:
    challenge = await _consume_challenge(session, credential=body.credential)
    try:
        registered = verify_registration(
            party=relying_party(request),
            credential_json=json.dumps(body.credential),
            challenge=challenge,
        )
    except PasskeyVerificationError as exc:
        raise INVALID from exc

    session.add(
        Passkey(
            user_id=account.id,
            credential_id=registered.credential_id,
            public_key=registered.public_key,
            sign_count=registered.sign_count,
            backed_up=registered.backed_up,
            label=body.label,
        )
    )
    await session.flush()
    return Response(status_code=status.HTTP_201_CREATED)


@router.post("/login/begin")
async def login_begin(
    body: LoginBeginRequest, session: DbSession, request: Request
) -> dict[str, object]:
    """Options for signing in with a passkey.

    A challenge is returned whether or not the account exists, and the credential list
    is empty for an unknown one — the same non-disclosure rule as password login.
    """
    account = (
        await session.execute(
            select(UserAccount).where(UserAccount.email == normalize_email(body.email))
        )
    ).scalar_one_or_none()

    allowed: list[bytes] = []
    if account is not None and account.active:
        allowed = [
            passkey.credential_id
            for passkey in (
                await session.execute(select(Passkey).where(Passkey.user_id == account.id))
            ).scalars()
        ]

    challenge = new_challenge()
    await _store_challenge(
        session, user_id=account.id if account is not None else None, challenge=challenge
    )
    options = authentication_options(
        party=relying_party(request), challenge=challenge, allowed_credentials=allowed
    )
    return dict(json.loads(options))


@router.post("/login/complete")
async def login_complete(
    body: CredentialRequest, session: DbSession, secret: JwtSecret, request: Request
) -> dict[str, str]:
    """Exchange an assertion for a session.

    A passkey satisfies both factors at once: the authenticator required user
    verification, so possession and the human were both proved before we saw anything.
    """
    challenge = await _consume_challenge(session, credential=body.credential)

    from webauthn.helpers import base64url_to_bytes

    try:
        credential_id = base64url_to_bytes(str(body.credential["id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise INVALID from exc

    passkey = (
        await session.execute(select(Passkey).where(Passkey.credential_id == credential_id))
    ).scalar_one_or_none()
    if passkey is None:
        raise INVALID

    account = (
        await session.execute(select(UserAccount).where(UserAccount.id == passkey.user_id))
    ).scalar_one_or_none()
    if account is None or not account.active:
        raise INVALID

    try:
        new_count = verify_authentication(
            party=relying_party(request),
            credential_json=json.dumps(body.credential),
            challenge=challenge,
            public_key=passkey.public_key,
            stored_sign_count=passkey.sign_count,
        )
    except PasskeyVerificationError as exc:
        raise INVALID from exc

    now = datetime.now(UTC)
    passkey.sign_count = new_count
    passkey.last_used_at = now
    await session.flush()

    issued = await complete_mfa_login(session, account=account, secret=secret, now=now)
    return {
        "access_token": issued.access_token,
        "refresh_token": issued.refresh_token,
        "token_type": "bearer",
    }


@router.delete("/{passkey_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_passkey(
    passkey_id: uuid.UUID, account: CurrentUser, session: DbSession
) -> Response:
    """Remove a passkey. Scoped to the owner, so another account's id is a 404."""
    passkey = (
        await session.execute(
            select(Passkey).where(Passkey.id == passkey_id, Passkey.user_id == account.id)
        )
    ).scalar_one_or_none()
    if passkey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Passkey not found")

    await session.delete(passkey)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
