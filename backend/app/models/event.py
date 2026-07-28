"""Timeline events.

Two things a family court timeline must never do: merge two parties' accounts of the
same incident into one "fact", and present something a user typed as though a document
said it. Both are prevented here by CHECK constraints rather than by convention.

An event is either:

* **document_derived** — read out of a filing, and therefore anchored to the passage it
  came from (ADR-0001 §2), or
* **user_asserted** — recorded by the account holder, with no passage to point at, and
  attributed to the person who entered it.

The constraints make each shape's required companion column mandatory and the other
one's impossible, so a row can never claim documentary support it does not have.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TimestampedBase
from app.models.document import Passage


class EventKind(StrEnum):
    """What sort of thing happened.

    Keeping these apart is what stops the timeline becoming a jumble: a motion being
    filed is a matter of record, while what a motion *says* happened is a claim.
    """

    procedural = "procedural"
    alleged = "alleged"


class EventProvenance(StrEnum):
    """Where the event came from. Drives which companion columns are required."""

    document_derived = "document_derived"
    user_asserted = "user_asserted"


class DatePrecision(StrEnum):
    """How precisely the date is actually known.

    Filings routinely say "in March" or "last spring". Storing precision alongside the
    timestamp is what stops the surface rendering "March 1, 2025 12:00 AM" for
    something the source dated only to a month — false precision on a legal chronology
    is a defect, not a formatting quirk.
    """

    exact = "exact"
    day = "day"
    month = "month"
    year = "year"


class CaseEvent(TimestampedBase):
    """One dated entry on a case timeline."""

    __tablename__ = "case_event"
    __table_args__ = (
        # The citation guarantee, in its conditional form: an event claiming to come
        # from a document must carry the passage; one that does not must not pretend to.
        CheckConstraint(
            "(provenance = 'document_derived' AND passage_id IS NOT NULL)"
            " OR (provenance = 'user_asserted' AND passage_id IS NULL)",
            name="documentary_events_cite_a_passage",
        ),
        # Attribution's mirror image: a user-entered event records who entered it, and
        # a document-derived one is not attributed to a person.
        CheckConstraint(
            "(provenance = 'user_asserted' AND recorded_by_user_id IS NOT NULL)"
            " OR (provenance = 'document_derived' AND recorded_by_user_id IS NULL)",
            name="asserted_events_name_their_author",
        ),
        Index("ix_case_event_case_id_occurred_at", "case_id", "occurred_at"),
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("case.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[EventKind] = mapped_column(
        PgEnum(EventKind, name="event_kind", create_type=False), nullable=False
    )
    provenance: Mapped[EventProvenance] = mapped_column(
        PgEnum(EventProvenance, name="event_provenance", create_type=False), nullable=False
    )

    # Present exactly when provenance is document_derived. The document is reached
    # through passage → page → document rather than duplicated here, so a denormalized
    # copy can never disagree with the passage the event actually cites.
    passage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("passage.id", ondelete="CASCADE"), index=True
    )

    # Present exactly when provenance is user_asserted.
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE")
    )

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    date_precision: Mapped[DatePrecision] = mapped_column(
        PgEnum(DatePrecision, name="date_precision", create_type=False),
        nullable=False,
        default=DatePrecision.day,
    )

    # A neutral description of what the source says happened. Not a characterization
    # and not a conclusion — the wording rules in CLAUDE.md §1 apply to whatever
    # populates this.
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    # Who says so, and who it concerns. Both optional: a procedural event such as a
    # hearing being scheduled has neither.
    asserted_by_party_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("party.id", ondelete="SET NULL")
    )
    about_party_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("party.id", ondelete="SET NULL")
    )

    passage: Mapped[Passage | None] = relationship()
