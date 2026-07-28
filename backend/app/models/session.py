"""Login sessions and their refresh tokens.

A session is a family of refresh tokens: each refresh rotates the token, and the
replaced one is recorded as used. Presenting an already-used token is the signature of
a stolen token being replayed, so it revokes the entire session rather than merely
failing — the legitimate holder is logged out, which is the correct outcome when we
cannot tell which of the two callers is the thief.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TimestampedBase


class UserSession(TimestampedBase):
    """One login. Holds the current refresh token digest and the revocation state."""

    __tablename__ = "user_session"
    __table_args__ = (
        # Refresh looks a token up by digest; it must be an indexed equality probe.
        Index("ix_user_session_refresh_digest", "refresh_digest", unique=True),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # SHA-256 of the current refresh token. The token itself is never stored.
    refresh_digest: Mapped[str] = mapped_column(String(64), nullable=False)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Set when the session ends — by logout, by expiry cleanup, or by the reuse
    # detection above. A revoked session is never resurrected.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Rolling record of the last refresh, so a support question about "when was this
    # session last active" has an answer without logging every request.
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def is_active(self, now: datetime) -> bool:
        return self.revoked_at is None and self.expires_at > now


class UsedRefreshToken(TimestampedBase):
    """A refresh token digest that has already been rotated away.

    Kept so a replay can be *detected* rather than merely rejected. Rows are pruned
    once the session they belong to has expired.
    """

    __tablename__ = "used_refresh_token"
    __table_args__ = (Index("ix_used_refresh_token_digest", "digest", unique=True),)

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_session.id", ondelete="CASCADE"), nullable=False, index=True
    )
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
