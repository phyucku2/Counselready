"""Facts extracted from documents.

Every row here carries a NOT NULL `passage_id`. That single constraint is the
ADR-0001 §2 guarantee expressed in the schema: an extracted fact with nowhere to point
cannot be stored, so it cannot reach a user. There is deliberately no nullable escape
hatch — a fact the extractor cannot locate in the text is dropped, not saved unanchored.
"""

from __future__ import annotations

import uuid
from enum import StrEnum

from sqlalchemy import CheckConstraint, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TimestampedBase
from app.models.document import Passage


class FactField(StrEnum):
    """The dissection fields (roadmap 1.3).

    A closed vocabulary rather than free text, so the surface can render each field
    deliberately and a typo cannot invent a new one.
    """

    case_number = "case_number"
    court = "court"
    judge = "judge"
    document_kind = "document_kind"
    filed_date = "filed_date"
    served_date = "served_date"
    party_name = "party_name"
    counsel_name = "counsel_name"
    requested_relief = "requested_relief"
    referenced_exhibit = "referenced_exhibit"
    referenced_date = "referenced_date"
    monetary_amount = "monetary_amount"


class ExtractedFact(TimestampedBase):
    """One field read out of one passage of one document."""

    __tablename__ = "extracted_fact"
    __table_args__ = (
        # The same field read from the same passage by the same extractor is one
        # fact. Re-running an extractor updates rather than duplicates.
        UniqueConstraint("passage_id", "field", "extractor_version"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_is_a_fraction",
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # The citation guarantee. NOT NULL by design — see the module docstring.
    passage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("passage.id", ondelete="CASCADE"), nullable=False, index=True
    )

    field: Mapped[FactField] = mapped_column(
        PgEnum(FactField, name="fact_field", create_type=False), nullable=False
    )
    value: Mapped[str] = mapped_column(Text, nullable=False)

    # Which extractor produced this, so a bad run can be identified and replaced
    # rather than leaving unattributable rows behind.
    extractor_version: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)

    passage: Mapped[Passage] = relationship()
