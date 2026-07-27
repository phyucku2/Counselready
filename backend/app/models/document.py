"""Documents, their pages, and the passages that anchor every citation.

`Passage` is the load-bearing table in the whole schema. ADR-0001 §2 requires that
every generated statement point at the text it came from; making a passage a row that
other tables reference by a NOT NULL foreign key is what turns that requirement from a
convention into something the database enforces.
"""

from __future__ import annotations

import uuid
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TimestampedBase


class DocumentKind(StrEnum):
    """What a document is. `unclassified` is the honest default before dissection."""

    unclassified = "unclassified"
    petition = "petition"
    motion = "motion"
    response = "response"
    order = "order"
    notice = "notice"
    financial_affidavit = "financial_affidavit"
    parenting_plan = "parenting_plan"
    evaluation = "evaluation"
    correspondence = "correspondence"
    exhibit = "exhibit"
    other = "other"


class IngestSource(StrEnum):
    """How the document reached us. Relevant to how much its metadata can be trusted."""

    upload = "upload"
    camera = "camera"
    email = "email"


class OcrStatus(StrEnum):
    """Where a document is in the extraction pipeline."""

    pending = "pending"
    processing = "processing"
    complete = "complete"
    failed = "failed"


class Document(TimestampedBase):
    """One file in a case file."""

    __tablename__ = "document"
    __table_args__ = (
        # The same bytes uploaded twice is one document, not two. Court files are
        # full of duplicates — the same order arrives from counsel and the portal.
        UniqueConstraint("case_id", "content_hash"),
        CheckConstraint("page_count >= 0", name="page_count_non_negative"),
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("case.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    kind: Mapped[DocumentKind] = mapped_column(
        PgEnum(DocumentKind, name="document_kind", create_type=False),
        nullable=False,
        default=DocumentKind.unclassified,
    )
    ingest_source: Mapped[IngestSource] = mapped_column(
        PgEnum(IngestSource, name="ingest_source", create_type=False), nullable=False
    )

    # Blob storage key (ADR-0002). The bytes never live in the database.
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Dates asserted by the document itself, not by us. Both nullable: plenty of
    # documents state neither, and inventing one would be fabricating a fact.
    filed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    served_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))

    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ocr_status: Mapped[OcrStatus] = mapped_column(
        PgEnum(OcrStatus, name="ocr_status", create_type=False),
        nullable=False,
        default=OcrStatus.pending,
    )

    pages: Mapped[list[DocumentPage]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentPage(TimestampedBase):
    """One page of extracted text, with the confidence of that extraction.

    Confidence is stored per page rather than per document because family court files
    mix clean native PDFs with skewed photocopies — a document-level average would
    hide the one page that was unreadable.
    """

    __tablename__ = "document_page"
    __table_args__ = (
        UniqueConstraint("document_id", "page_number"),
        CheckConstraint("page_number >= 1", name="page_number_positive"),
        CheckConstraint(
            "ocr_confidence IS NULL OR (ocr_confidence >= 0 AND ocr_confidence <= 1)",
            name="ocr_confidence_is_a_fraction",
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # NULL means "not measured" (a native PDF with an embedded text layer), which is
    # different from a measured zero. The distinction has to survive to the surface.
    ocr_confidence: Mapped[float | None] = mapped_column(Float)

    document: Mapped[Document] = relationship(back_populates="pages")
    passages: Mapped[list[Passage]] = relationship(
        back_populates="page", cascade="all, delete-orphan"
    )


class Passage(TimestampedBase):
    """A span of text on a page — the anchor every citation points at.

    The quoted text is stored alongside the offsets deliberately. Offsets alone would
    silently start pointing at different words if a page were ever re-OCRed, and a
    citation that drifts is worse than no citation.
    """

    __tablename__ = "passage"
    __table_args__ = (
        CheckConstraint("start_offset >= 0", name="start_offset_non_negative"),
        CheckConstraint("end_offset > start_offset", name="end_offset_after_start"),
    )

    page_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_page.id", ondelete="CASCADE"), nullable=False, index=True
    )
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)

    page: Mapped[DocumentPage] = relationship(back_populates="passages")
