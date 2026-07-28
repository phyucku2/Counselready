"""Multi-factor routes.

Enrolment is deliberately two steps: setup issues a secret, confirm activates it only
once the user has produced a working code. Activating on issue would lock out anyone
whose QR scan silently failed — with no second device and no support desk, that is an
unrecoverable account.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, JwtSecret
from app.auth.mfa import MfaNotConfiguredError, SecretDecryptionError
from app.auth.mfa_service import (
    InvalidMfaCodeError,
    MfaAlreadyEnrolledError,
    MfaNotEnrolledError,
    confirm_enrolment,
    disable_mfa,
    is_mfa_active,
    remaining_recovery_codes,
    start_enrolment,
    verify_code_for_login,
)
from app.auth.passwords import MAX_PASSWORD_LENGTH, verify_password_against
from app.auth.service import complete_mfa_login
from app.auth.tokens import InvalidChallengeError, decode_mfa_challenge
from app.models.user import UserAccount

router = APIRouter(prefix="/auth/mfa", tags=["auth"])

INVALID_CODE = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid verification code"
)
NOT_ENROLLED = HTTPException(
    status_code=status.HTTP_409_CONFLICT, detail="Multi-factor authentication is not enabled"
)
MFA_UNAVAILABLE = HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    detail="Multi-factor authentication is not configured on this server",
)


def encryption_key(request: Request) -> str | None:
    from app.core.config import settings

    return settings.mfa_encryption_key


class CodeRequest(BaseModel):
    # Wide enough for a recovery code with its separators; a TOTP code is six digits.
    code: str = Field(min_length=6, max_length=64)


class VerifyRequest(CodeRequest):
    challenge_token: str = Field(max_length=2048)


class DisableRequest(CodeRequest):
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class SetupResponse(BaseModel):
    """Shown once. The client renders the URI as a QR code locally — no image is
    generated server-side, so the secret never passes through an image pipeline."""

    provisioning_uri: str
    recovery_codes: list[str]


class StatusResponse(BaseModel):
    enabled: bool
    recovery_codes_remaining: int


@router.get("/status", response_model=StatusResponse)
async def mfa_status(account: CurrentUser, session: DbSession) -> StatusResponse:
    enabled = await is_mfa_active(session, user_id=account.id)
    return StatusResponse(
        enabled=enabled,
        recovery_codes_remaining=(
            await remaining_recovery_codes(session, user_id=account.id) if enabled else 0
        ),
    )


@router.post("/setup", response_model=SetupResponse)
async def setup(account: CurrentUser, session: DbSession, request: Request) -> SetupResponse:
    try:
        pending = await start_enrolment(session, account=account, key=encryption_key(request))
    except MfaNotConfiguredError as exc:
        raise MFA_UNAVAILABLE from exc
    except MfaAlreadyEnrolledError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Multi-factor authentication is already enabled",
        ) from exc

    return SetupResponse(
        provisioning_uri=pending.provisioning_uri, recovery_codes=pending.recovery_codes
    )


@router.post("/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm(
    body: CodeRequest, account: CurrentUser, session: DbSession, request: Request
) -> Response:
    try:
        await confirm_enrolment(
            session,
            account=account,
            code=body.code,
            key=encryption_key(request),
            now=datetime.now(UTC),
        )
    except MfaNotConfiguredError as exc:
        raise MFA_UNAVAILABLE from exc
    except MfaNotEnrolledError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Start setup before confirming"
        ) from exc
    except MfaAlreadyEnrolledError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Multi-factor authentication is already enabled",
        ) from exc
    except (InvalidMfaCodeError, SecretDecryptionError) as exc:
        raise INVALID_CODE from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/verify")
async def verify(
    body: VerifyRequest, session: DbSession, secret: JwtSecret, request: Request
) -> dict[str, str]:
    """Exchange a login challenge plus a code for a session."""
    try:
        user_id = decode_mfa_challenge(body.challenge_token, secret=secret)
    except InvalidChallengeError as exc:
        raise INVALID_CODE from exc

    account = (
        await session.execute(select(UserAccount).where(UserAccount.id == user_id))
    ).scalar_one_or_none()
    if account is None or not account.active:
        raise INVALID_CODE

    now = datetime.now(UTC)
    try:
        await verify_code_for_login(
            session, account=account, code=body.code, key=encryption_key(request), now=now
        )
    except MfaNotConfiguredError as exc:
        raise MFA_UNAVAILABLE from exc
    except (InvalidMfaCodeError, MfaNotEnrolledError, SecretDecryptionError) as exc:
        raise INVALID_CODE from exc

    issued = await complete_mfa_login(session, account=account, secret=secret, now=now)
    return {
        "access_token": issued.access_token,
        "refresh_token": issued.refresh_token,
        "token_type": "bearer",
    }


@router.post("/disable", status_code=status.HTTP_204_NO_CONTENT)
async def disable(
    body: DisableRequest, account: CurrentUser, session: DbSession, request: Request
) -> Response:
    """Turn MFA off. Requires the password *and* a current code.

    Both are demanded on purpose: someone who has walked up to an unlocked laptop
    should not be able to strip the second factor off the account.
    """
    if not verify_password_against(body.password, account.password_hash):
        raise INVALID_CODE

    try:
        await verify_code_for_login(
            session,
            account=account,
            code=body.code,
            key=encryption_key(request),
            now=datetime.now(UTC),
        )
        await disable_mfa(session, account=account)
    except MfaNotConfiguredError as exc:
        raise MFA_UNAVAILABLE from exc
    except MfaNotEnrolledError as exc:
        raise NOT_ENROLLED from exc
    except (InvalidMfaCodeError, SecretDecryptionError) as exc:
        raise INVALID_CODE from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
