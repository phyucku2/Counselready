"""MFA enrolment, verification, and the two-step login it introduces.

Once MFA is active, `authenticate` must not hand back a session. It returns a
short-lived **challenge** instead, which is exchanged for tokens only after a valid
code. A challenge carries no authority of its own: presenting one to any other route
does nothing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.mfa import (
    Enrolment,
    begin_enrolment,
    decrypt_secret,
    hash_recovery_code,
    matching_counter,
)
from app.models.mfa import RecoveryCode, UserMfa
from app.models.user import UserAccount

# Long enough to open an authenticator app and type six digits; short enough that a
# stolen challenge is worth little.
CHALLENGE_TTL = timedelta(minutes=5)

MAX_CODE_ATTEMPTS = 5


class MfaAlreadyEnrolledError(Exception):
    """MFA is already active for this account."""


class MfaNotEnrolledError(Exception):
    """No confirmed MFA enrolment exists for this account."""


class InvalidMfaCodeError(Exception):
    """The code did not verify, or was already used."""


@dataclass(frozen=True)
class PendingEnrolment:
    """Returned once at setup. The plaintext parts are never retrievable again."""

    provisioning_uri: str
    recovery_codes: list[str]


async def load_mfa(session: AsyncSession, *, user_id: uuid.UUID) -> UserMfa | None:
    return (
        await session.execute(select(UserMfa).where(UserMfa.user_id == user_id))
    ).scalar_one_or_none()


async def is_mfa_active(session: AsyncSession, *, user_id: uuid.UUID) -> bool:
    record = await load_mfa(session, user_id=user_id)
    return record is not None and record.is_active


async def start_enrolment(
    session: AsyncSession, *, account: UserAccount, key: str | None
) -> PendingEnrolment:
    """Create (or replace) an unconfirmed enrolment.

    Replacing an unconfirmed one is deliberate: a user whose first QR scan failed must
    be able to start over without an administrator.
    """
    existing = await load_mfa(session, user_id=account.id)
    if existing is not None and existing.is_active:
        raise MfaAlreadyEnrolledError(str(account.id))

    enrolment: Enrolment = begin_enrolment(email=account.email, key=key)

    if existing is not None:
        existing.encrypted_secret = enrolment.encrypted_secret
        existing.last_used_counter = None
    else:
        session.add(UserMfa(user_id=account.id, encrypted_secret=enrolment.encrypted_secret))

    # Recovery codes belong to the enrolment attempt, so a restarted setup discards
    # codes the user may have written down for a secret they never confirmed.
    for stale in (
        await session.execute(select(RecoveryCode).where(RecoveryCode.user_id == account.id))
    ).scalars():
        await session.delete(stale)
    await session.flush()

    session.add_all(
        [RecoveryCode(user_id=account.id, digest=digest) for digest in enrolment.recovery_digests]
    )
    await session.flush()

    return PendingEnrolment(
        provisioning_uri=enrolment.provisioning_uri, recovery_codes=enrolment.recovery_codes
    )


async def confirm_enrolment(
    session: AsyncSession, *, account: UserAccount, code: str, key: str | None, now: datetime
) -> None:
    """Activate MFA once the user proves they can produce a code."""
    record = await load_mfa(session, user_id=account.id)
    if record is None:
        raise MfaNotEnrolledError(str(account.id))
    if record.is_active:
        raise MfaAlreadyEnrolledError(str(account.id))

    secret = decrypt_secret(record.encrypted_secret, key=key)
    step = matching_counter(secret, code, int(now.timestamp()))
    if step is None:
        raise InvalidMfaCodeError("code did not verify")

    record.confirmed_at = now
    record.last_used_counter = step
    await session.flush()


async def verify_code_for_login(
    session: AsyncSession, *, account: UserAccount, code: str, key: str | None, now: datetime
) -> None:
    """Check a TOTP code or a recovery code, consuming what it uses."""
    record = await load_mfa(session, user_id=account.id)
    if record is None or not record.is_active:
        raise MfaNotEnrolledError(str(account.id))

    secret = decrypt_secret(record.encrypted_secret, key=key)
    step = matching_counter(secret, code, int(now.timestamp()))

    if step is not None:
        if record.last_used_counter is not None and step <= record.last_used_counter:
            # Replay inside the validity window. Without this, a code glimpsed over a
            # shoulder stays usable for up to ninety seconds.
            raise InvalidMfaCodeError("code has already been used")
        record.last_used_counter = step
        await session.flush()
        return

    await _consume_recovery_code(session, account=account, code=code, now=now)


async def _consume_recovery_code(
    session: AsyncSession, *, account: UserAccount, code: str, now: datetime
) -> None:
    digest = hash_recovery_code(code)
    recovery = (
        await session.execute(
            select(RecoveryCode).where(
                RecoveryCode.user_id == account.id, RecoveryCode.digest == digest
            )
        )
    ).scalar_one_or_none()

    if recovery is None or recovery.used_at is not None:
        raise InvalidMfaCodeError("code did not verify")

    recovery.used_at = now
    await session.flush()


async def remaining_recovery_codes(session: AsyncSession, *, user_id: uuid.UUID) -> int:
    codes = (
        await session.execute(
            select(RecoveryCode).where(
                RecoveryCode.user_id == user_id, RecoveryCode.used_at.is_(None)
            )
        )
    ).scalars()
    return len(list(codes))


async def disable_mfa(session: AsyncSession, *, account: UserAccount) -> None:
    """Turn MFA off. Callers must re-verify the password first."""
    record = await load_mfa(session, user_id=account.id)
    if record is None or not record.is_active:
        raise MfaNotEnrolledError(str(account.id))

    await session.delete(record)
    for recovery in (
        await session.execute(select(RecoveryCode).where(RecoveryCode.user_id == account.id))
    ).scalars():
        await session.delete(recovery)
    await session.flush()


def challenge_expiry(now: datetime) -> datetime:
    return now + CHALLENGE_TTL


def utc_now() -> datetime:
    return datetime.now(UTC)
