"""Authentication routes.

Response bodies are deliberately uninformative about *why* a sign-in failed. For this
product that is not box-ticking: an abusive ex-partner probing whether their former
spouse has an account is a realistic use of a chatty login endpoint (CLAUDE.md §3).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.api.cases import Store
from app.api.deps import AuthenticatedSession, CurrentUser, DbSession, JwtSecret
from app.auth.deletion import collect_storage_keys, delete_account, purge_objects
from app.auth.mfa_service import is_mfa_active, verify_code_for_login
from app.auth.passwords import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    WeakPasswordError,
    verify_password_against,
)
from app.auth.service import (
    AuthenticationError,
    EmailAlreadyRegisteredError,
    InvalidRefreshTokenError,
    IssuedSession,
    MfaRequired,
    RateLimitedError,
    authenticate,
    refresh_session,
    register_account,
    revoke_session,
)
from app.models.session import UserSession

router = APIRouter(prefix="/auth", tags=["auth"])

INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
)
INVALID_REFRESH = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is no longer valid"
)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    display_name: str | None = Field(default=None, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(max_length=512)


class MfaChallengeResponse(BaseModel):
    """Returned instead of tokens when a second factor is owed."""

    mfa_required: bool = True
    challenge_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    # The OAuth2 token_type literal, not a credential.
    token_type: str = "bearer"  # noqa: S105


class AccountResponse(BaseModel):
    id: str
    email: str
    display_name: str | None


def _tokens(issued: IssuedSession) -> TokenResponse:
    return TokenResponse(access_token=issued.access_token, refresh_token=issued.refresh_token)


@router.post("/register", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, session: DbSession) -> AccountResponse:
    try:
        account = await register_account(
            session,
            email=body.email,
            password=body.password,
            display_name=body.display_name,
        )
    except WeakPasswordError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except EmailAlreadyRegisteredError as exc:
        # 409 rather than a 200 that pretends to have registered: this endpoint is
        # already an enumeration surface by nature (the user must be told the address
        # is taken), so the mitigation belongs in rate limiting, not in a fiction that
        # would leave a real user unable to explain why they cannot sign in.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email is already registered"
        ) from exc

    return AccountResponse(
        id=str(account.id), email=account.email, display_name=account.display_name
    )


@router.post("/login", response_model=TokenResponse | MfaChallengeResponse)
async def login(
    body: LoginRequest, session: DbSession, secret: JwtSecret
) -> TokenResponse | MfaChallengeResponse:
    try:
        issued = await authenticate(
            session,
            email=body.email,
            password=body.password,
            secret=secret,
            now=datetime.now(UTC),
        )
    except RateLimitedError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many sign-in attempts. Try again later.",
            headers={"Retry-After": str(int(exc.retry_after.total_seconds()))},
        ) from exc
    except AuthenticationError as exc:
        raise INVALID_CREDENTIALS from exc

    if isinstance(issued, MfaRequired):
        # A correct password alone yields no credentials — only a short-lived
        # challenge, which no other route accepts.
        return MfaChallengeResponse(challenge_token=issued.challenge_token)
    return _tokens(issued)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, session: DbSession, secret: JwtSecret) -> TokenResponse:
    try:
        issued = await refresh_session(
            session, refresh_token=body.refresh_token, secret=secret, now=datetime.now(UTC)
        )
    except InvalidRefreshTokenError as exc:
        raise INVALID_REFRESH from exc
    return _tokens(issued)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(auth: AuthenticatedSession, session: DbSession) -> Response:
    """End the session behind the presented access token.

    Idempotent: revoking an already-revoked session is not an error, so a client
    retrying a logout it never saw succeed does not get a confusing failure.
    """
    await revoke_session(session, session_id=auth.session_id, now=datetime.now(UTC))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=AccountResponse)
async def me(account: CurrentUser) -> AccountResponse:
    return AccountResponse(
        id=str(account.id), email=account.email, display_name=account.display_name
    )


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_everywhere(account: CurrentUser, session: DbSession) -> Response:
    """Revoke every session for the account.

    Belongs in the first auth release rather than a later one: "someone else may be in
    my account" is a safety question for this user base, and the answer has to be one
    action, available immediately.
    """
    now = datetime.now(UTC)
    sessions = (
        await session.execute(
            select(UserSession).where(
                UserSession.user_id == account.id, UserSession.revoked_at.is_(None)
            )
        )
    ).scalars()
    for user_session in sessions:
        user_session.revoked_at = now
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class DeleteAccountRequest(BaseModel):
    """Re-authentication for an irreversible action.

    The password is required even though the caller already holds a session, and the
    MFA code is required when MFA is on: destroying the account is exactly what someone
    who found an unlocked phone would do, and it is the one action with no undo.
    """

    password: str = Field(max_length=MAX_PASSWORD_LENGTH)
    mfa_code: str | None = Field(default=None, max_length=64)
    acknowledge: bool = Field(
        description="Must be true. Forces the client to show what is about to be lost."
    )


class DeletionSummaryResponse(BaseModel):
    cases_deleted: int
    documents_deleted: int
    objects_removed: int


@router.post("/me/delete", response_model=DeletionSummaryResponse)
async def delete_own_account(
    body: DeleteAccountRequest,
    account: CurrentUser,
    session: DbSession,
    store: Store,
) -> DeletionSummaryResponse:
    """Permanently destroy this account and every case it owns.

    A hard app-store requirement for any app collecting user data, and the right
    default regardless: someone who no longer wants their family court file held by a
    third party should not have to ask permission to remove it.
    """
    if not body.acknowledge:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Confirm that you understand this cannot be undone.",
        )

    if not verify_password_against(body.password, account.password_hash):
        raise INVALID_CREDENTIALS

    if await is_mfa_active(session, user_id=account.id):
        from app.core.config import settings

        if body.mfa_code is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="A verification code is required to delete your account.",
            )
        try:
            await verify_code_for_login(
                session,
                account=account,
                code=body.mfa_code,
                key=settings.mfa_encryption_key,
                now=datetime.now(UTC),
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid verification code",
            ) from exc

    keys = await collect_storage_keys(session, user_id=account.id)
    summary = await delete_account(session, store, account=account)
    # Blobs are removed after the row deletion, so a database failure leaves
    # unreferenced objects rather than records pointing at absent bytes.
    removed = await purge_objects(store, keys)

    return DeletionSummaryResponse(
        cases_deleted=summary.cases,
        documents_deleted=summary.documents,
        objects_removed=removed,
    )
