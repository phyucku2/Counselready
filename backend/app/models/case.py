"""Cases and the people in them.

The case is the top-level container (ADR-0001): family matters routinely run in
parallel — a dissolution, an injunction, and a support case can all be live at once —
and every document, passage, and extracted fact hangs off exactly one of them.
"""

from __future__ import annotations

import uuid
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TimestampedBase


class Jurisdiction(StrEnum):
    """Jurisdiction profile governing terminology and document types (CLAUDE.md §7).

    Florida only for now. The column exists from the first migration so a second
    state is a new value rather than a schema change.
    """

    florida = "florida"


class PartyRole(StrEnum):
    """A person's role in the case.

    `child` is separate because minors are redacted from generated output by default
    (CLAUDE.md §3) — that rule needs a column to key off, not a naming convention.
    """

    petitioner = "petitioner"
    respondent = "respondent"
    child = "child"
    counsel = "counsel"
    guardian_ad_litem = "guardian_ad_litem"
    evaluator = "evaluator"
    judge = "judge"
    other = "other"


class Case(TimestampedBase):
    """One legal matter, owned by one account."""

    __tablename__ = "case"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    jurisdiction: Mapped[Jurisdiction] = mapped_column(
        PgEnum(Jurisdiction, name="jurisdiction", create_type=False),
        nullable=False,
        default=Jurisdiction.florida,
    )
    court: Mapped[str | None] = mapped_column(String(200))
    case_number: Mapped[str | None] = mapped_column(String(100))

    parties: Mapped[list[Party]] = relationship(back_populates="case", cascade="all, delete-orphan")


class Party(TimestampedBase):
    """A person or entity appearing in a case."""

    __tablename__ = "party"
    __table_args__ = (
        # One row per person per role: the same person can be both a parent and
        # their own counsel, but not listed twice in the same role.
        UniqueConstraint("case_id", "display_name", "role"),
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("case.id", ondelete="CASCADE"), nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[PartyRole] = mapped_column(
        PgEnum(PartyRole, name="party_role", create_type=False), nullable=False
    )
    is_minor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    case: Mapped[Case] = relationship(back_populates="parties")
