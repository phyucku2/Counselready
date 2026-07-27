"""Account identity.

Credential and MFA columns arrive with the auth portion. This table exists now so
case ownership is a real foreign key from the first migration rather than a loose
identifier backfilled later.
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
