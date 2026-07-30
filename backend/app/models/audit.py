"""Authentication audit trail.

Records sign-in outcomes. Two jobs: feeding the login rate limiter, and giving an
account holder a record of attempts on their account — which matters more here than in
most products, because "someone else is trying to get into my account" is a safety
question for this user base, not just a security one (CLAUDE.md §3).

Deliberately holds no case material, no password, and no token: an email, an optional
user id, and an outcome from a closed vocabulary.
"""

from __future__ import annotations

import uuid
from enum import StrEnum

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TimestampedBase


class AuthEventType(StrEnum):
    login_succeeded = "login_succeeded"
    login_failed = "login_failed"


class AuthEvent(TimestampedBase):
    """One sign-in attempt."""

    __tablename__ = "auth_event"
    __table_args__ = (
        # The rate limiter's query: failures for one email inside a time window.
        Index("ix_auth_event_email_type_created", "email", "event_type", "created_at"),
    )

    # Stored even when no account matches, because failed attempts against a
    # non-existent address are exactly what the limiter must count.
    email: Mapped[str] = mapped_column(String(320), nullable=False)

    # NULL when the email matched no account. SET NULL on delete so an account's
    # removal does not erase the record that attempts occurred.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL"), index=True
    )

    event_type: Mapped[AuthEventType] = mapped_column(
        PgEnum(AuthEventType, name="auth_event_type", create_type=False), nullable=False
    )


class CaseAction(StrEnum):
    """What was done with case material. A closed vocabulary so the audit trail can
    never accidentally carry document text."""

    case_created = "case_created"
    case_read = "case_read"
    case_list = "case_list"
    document_uploaded = "document_uploaded"
    document_list = "document_list"
    document_read = "document_read"
    event_created = "event_created"
    event_list = "event_list"
    event_note_created = "event_note_created"


class CaseAuditEvent(TimestampedBase):
    """A read or write of case material (CLAUDE.md §3).

    Records who, what, and which case — never the content. `detail` holds counts and
    references only, so a leaked audit table discloses activity, not case facts.
    """

    __tablename__ = "case_audit_event"
    __table_args__ = (Index("ix_case_audit_event_case_created", "case_id", "created_at"),)

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL"), index=True
    )
    # SET NULL rather than CASCADE: deleting a case must not erase the record that it
    # was accessed, only what it contained.
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("case.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[CaseAction] = mapped_column(
        PgEnum(CaseAction, name="case_action", create_type=False), nullable=False
    )
    detail: Mapped[dict[str, int] | None] = mapped_column(JSONB)
