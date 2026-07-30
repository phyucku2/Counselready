"""Authentication service.

Every function takes `now` explicitly. Expiry, rotation, and rate-limit windows are all
time-dependent, and reading the clock inside them would make the behaviour untestable
without sleeping and flaky depending on when CI happened to run.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.mfa_service import is_mfa_active
from app.auth.passwords import hash_password, needs_rehash, verify_password_against
from app.auth.tokens import (
    generate_refresh_token,
    hash_refresh_token,
    issue_access_token,
    issue_mfa_challenge,
    refresh_expiry,
)
from app.models.audit import AuthEvent, AuthEventType
from app.models.session import UsedRefreshToken, UserSession
from app.models.user import UserAccount

# Deliberately generous enough not to lock out a person mistyping a password on a phone,
# tight enough to make online guessing useless.
MAX_FAILED_LOGINS = 10
LOGIN_WINDOW = timedelta(minutes=15)


class AuthenticationError(Exception):
    """Credentials were not accepted.

    Raised identically for an unknown email, a wrong password, and a deactivated
    account. The caller must not distinguish them: which one it was is exactly the
    information an attacker probing for an ex-partner's account wants.
    """


class RateLimitedError(Exception):
    """Too many failed attempts for this identity in the current window."""

    def __init__(self, retry_after: timedelta) -> None:
        super().__init__("too many failed sign-in attempts")
        self.retry_after = retry_after


class EmailAlreadyRegisteredError(Exception):
    """An account already exists for this email."""


class InvalidRefreshTokenError(Exception):
    """The refresh token is unknown, expired, revoked, or already used."""


@dataclass(frozen=True)
class MfaRequired:
    """The password was accepted; a second factor is still owed.

    Deliberately not a session: no tokens exist yet, so a stolen password alone buys
    an attacker nothing but a five-minute challenge.
    """

    challenge_token: str
    user_id: uuid.UUID


@dataclass(frozen=True)
class IssuedSession:
    access_token: str
    refresh_token: str
    session_id: uuid.UUID
    user: UserAccount


def normalize_email(email: str) -> str:
    """Casefold and trim. Emails are compared case-insensitively in practice, and two
    accounts differing only in capitalization would be a confusing security hazard."""
    return email.strip().casefold()


async def register_account(
    session: AsyncSession, *, email: str, password: str, display_name: str | None = None
) -> UserAccount:
    """Create an account. Raises `WeakPasswordError` before touching the database."""
    password_hash = hash_password(password)
    account = UserAccount(
        email=normalize_email(email), display_name=display_name, password_hash=password_hash
    )
    session.add(account)
    try:
        await session.flush()
    except IntegrityError as exc:
        # Uniqueness is enforced by the database rather than a prior SELECT: a
        # check-then-insert races two concurrent signups into a duplicate.
        await session.rollback()
        raise EmailAlreadyRegisteredError(email) from exc
    return account


async def _failed_attempts_since(session: AsyncSession, *, email: str, since: datetime) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(AuthEvent)
            .where(
                AuthEvent.email == email,
                AuthEvent.event_type == AuthEventType.login_failed,
                AuthEvent.created_at >= since,
            )
        )
    ).scalar_one()


async def authenticate(
    session: AsyncSession, *, email: str, password: str, secret: str, now: datetime
) -> IssuedSession | MfaRequired:
    """Verify credentials and issue a session.

    Failures are recorded so the rate limiter has something to count, and so an account
    holder can later be shown where sign-in attempts came from.
    """
    normalized = normalize_email(email)

    attempts = await _failed_attempts_since(session, email=normalized, since=now - LOGIN_WINDOW)
    if attempts >= MAX_FAILED_LOGINS:
        raise RateLimitedError(LOGIN_WINDOW)

    account = (
        await session.execute(select(UserAccount).where(UserAccount.email == normalized))
    ).scalar_one_or_none()

    # Runs the hash even when the account is missing, so timing does not disclose
    # whether the email is registered.
    stored_hash = account.password_hash if account is not None else None
    matched = verify_password_against(password, stored_hash)

    if account is None or not matched or not account.active:
        session.add(
            AuthEvent(
                email=normalized,
                user_id=account.id if account is not None else None,
                event_type=AuthEventType.login_failed,
            )
        )
        await session.flush()
        raise AuthenticationError("invalid credentials")

    if needs_rehash(account.password_hash or ""):
        # Migrate the stored hash forward now that we hold the plaintext.
        account.password_hash = hash_password(password)

    if await is_mfa_active(session, user_id=account.id):
        # No session yet. The password alone must not produce credentials, or MFA
        # would be advisory.
        await session.flush()
        return MfaRequired(
            challenge_token=issue_mfa_challenge(user_id=account.id, secret=secret, now=now),
            user_id=account.id,
        )

    issued = await _issue_session(session, account=account, secret=secret, now=now)
    session.add(
        AuthEvent(email=normalized, user_id=account.id, event_type=AuthEventType.login_succeeded)
    )
    await session.flush()
    return issued


async def _issue_session(
    session: AsyncSession, *, account: UserAccount, secret: str, now: datetime
) -> IssuedSession:
    refresh_token = generate_refresh_token()
    user_session = UserSession(
        user_id=account.id,
        refresh_digest=hash_refresh_token(refresh_token),
        expires_at=refresh_expiry(now),
        last_used_at=now,
    )
    session.add(user_session)
    await session.flush()

    return IssuedSession(
        access_token=issue_access_token(
            user_id=account.id, session_id=user_session.id, secret=secret, now=now
        ),
        refresh_token=refresh_token,
        session_id=user_session.id,
        user=account,
    )


async def refresh_session(
    session: AsyncSession, *, refresh_token: str, secret: str, now: datetime
) -> IssuedSession:
    """Rotate a refresh token, detecting replay of an already-rotated one."""
    digest = hash_refresh_token(refresh_token)

    replayed = (
        await session.execute(select(UsedRefreshToken).where(UsedRefreshToken.digest == digest))
    ).scalar_one_or_none()
    if replayed is not None:
        # Someone presented a token that was already rotated away. Either the token was
        # stolen or the legitimate client replayed one — we cannot tell which, so the
        # safe move is to end the session for both.
        await _revoke_session_by_id(session, replayed.session_id, now=now)
        raise InvalidRefreshTokenError("refresh token has already been used")

    user_session = (
        await session.execute(select(UserSession).where(UserSession.refresh_digest == digest))
    ).scalar_one_or_none()
    if user_session is None or not user_session.is_active(now):
        raise InvalidRefreshTokenError("refresh token is not valid")

    account = (
        await session.execute(select(UserAccount).where(UserAccount.id == user_session.user_id))
    ).scalar_one_or_none()
    if account is None or not account.active:
        raise InvalidRefreshTokenError("account is not active")

    session.add(UsedRefreshToken(session_id=user_session.id, digest=digest))

    rotated = generate_refresh_token()
    user_session.refresh_digest = hash_refresh_token(rotated)
    user_session.last_used_at = now
    await session.flush()

    return IssuedSession(
        access_token=issue_access_token(
            user_id=account.id, session_id=user_session.id, secret=secret, now=now
        ),
        refresh_token=rotated,
        session_id=user_session.id,
        user=account,
    )


async def _revoke_session_by_id(
    session: AsyncSession, session_id: uuid.UUID, *, now: datetime
) -> None:
    user_session = (
        await session.execute(select(UserSession).where(UserSession.id == session_id))
    ).scalar_one_or_none()
    if user_session is not None and user_session.revoked_at is None:
        user_session.revoked_at = now
        await session.flush()


async def revoke_session(session: AsyncSession, *, session_id: uuid.UUID, now: datetime) -> None:
    """Log out. Idempotent — revoking an already-revoked session is not an error."""
    await _revoke_session_by_id(session, session_id, now=now)


async def load_active_session(
    session: AsyncSession, *, session_id: uuid.UUID, now: datetime
) -> UserSession | None:
    """The session behind an access token, if it is still live.

    Checked on every authenticated request so that logging out actually ends access
    rather than leaving the unexpired access token working until it lapses.
    """
    user_session = (
        await session.execute(select(UserSession).where(UserSession.id == session_id))
    ).scalar_one_or_none()
    if user_session is None or not user_session.is_active(now):
        return None
    return user_session


async def complete_mfa_login(
    session: AsyncSession, *, account: UserAccount, secret: str, now: datetime
) -> IssuedSession:
    """Issue the session once the second factor has been verified."""
    issued = await _issue_session(session, account=account, secret=secret, now=now)
    session.add(
        AuthEvent(email=account.email, user_id=account.id, event_type=AuthEventType.login_succeeded)
    )
    await session.flush()
    return issued
