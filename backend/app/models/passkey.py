"""Passkey (WebAuthn) credentials.

A passkey is a public key we hold and a private key the device holds, unlocked by Face
ID or a fingerprint. The biometric never reaches us — what reaches us is a signature,
which is why this is a real factor rather than a convenience.

Passkeys are bound to our origin, so unlike a TOTP code they cannot be phished onto a
convincing fake login page.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TimestampedBase


class Passkey(TimestampedBase):
    """One registered credential."""

    __tablename__ = "passkey"
    __table_args__ = (Index("ix_passkey_credential_id", "credential_id", unique=True),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # The authenticator's credential id, and its public key. Neither is secret — the
    # private key never leaves the device — so no encryption is needed here, unlike
    # the TOTP secret.
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    public_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    # Monotonic counter some authenticators maintain. A value that goes backwards
    # suggests a cloned credential; zero means the authenticator does not keep one
    # (common for synced passkeys), so it cannot be treated as a failure.
    sign_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    # True when the credential is synced through iCloud Keychain or Google Password
    # Manager. Surfaced to the user deliberately: a synced passkey lives wherever that
    # account is signed in, which matters when someone is separating from a person they
    # shared an Apple ID with (CLAUDE.md §3).
    backed_up: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    label: Mapped[str | None] = mapped_column(String(120))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PasskeyChallenge(TimestampedBase):
    """A pending WebAuthn challenge, consumed once.

    Held server-side rather than round-tripped to the client, and deleted on use: a
    challenge that verified twice would let a captured response be replayed.
    """

    __tablename__ = "passkey_challenge"
    __table_args__ = (Index("ix_passkey_challenge_value", "challenge", unique=True),)

    # NULL for a sign-in challenge issued before we know who is answering.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True
    )
    challenge: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
