"""Account identity.

MFA columns arrive with the MFA portion (roadmap 0.3b), which must land before launch:
CLAUDE.md §3 treats account takeover by an ex-partner as a life-safety risk, not a
hardening nicety.
"""

from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TimestampedBase


class UserAccount(TimestampedBase):
    """A person who owns cases in the system."""

    __tablename__ = "user_account"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Argon2id, produced by app.auth.passwords. Nullable only so the column could be
    # added to an existing table; every account created through the service has one.
    password_hash: Mapped[str | None] = mapped_column(String(255))
