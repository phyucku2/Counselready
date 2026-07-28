"""Multi-factor enrolment state.

Split from `user_account` because MFA has its own lifecycle — pending, confirmed,
disabled — and because the encrypted secret is a credential that benefits from living
in a table a query for account details never touches by accident.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TimestampedBase


class UserMfa(TimestampedBase):
    """One account's TOTP enrolment. At most one row per account."""

    __tablename__ = "user_mfa"
    __table_args__ = (Index("ix_user_mfa_user_id", "user_id", unique=True),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )

    # Fernet-encrypted (app.auth.mfa). Plaintext here would make a database disclosure
    # enough to generate valid codes indefinitely.
    encrypted_secret: Mapped[str] = mapped_column(String(500), nullable=False)

    # NULL until the user proves they can produce a code. An enrolment that activated
    # on issue would lock out anyone whose QR scan silently failed.
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # The TOTP step of the last accepted code, so it cannot be replayed inside its own
    # validity window.
    last_used_counter: Mapped[int | None] = mapped_column(BigInteger)

    @property
    def is_active(self) -> bool:
        return self.confirmed_at is not None


class RecoveryCode(TimestampedBase):
    """A single-use backup code, stored as a digest.

    Issued as a set at enrolment. Consumed rather than deleted so a user can see how
    many they have left without us keeping the codes themselves.
    """

    __tablename__ = "recovery_code"
    __table_args__ = (Index("ix_recovery_code_user_digest", "user_id", "digest", unique=True),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
