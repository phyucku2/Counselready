"""Background job queue, held in PostgreSQL.

No Redis, no broker. Claiming a job is `SELECT ... FOR UPDATE SKIP LOCKED`, which is
exactly what that clause exists for: several workers can take different rows
concurrently without blocking each other, and a worker that dies mid-job releases its
lock when its transaction dies.

The reason to prefer this over a dedicated broker is not simplicity for its own sake —
it is that the job and the data it operates on live in the same transaction. A document
row and its "extract this document" job commit together or not at all, so the queue can
never hold work for a document that was rolled back, and a committed document can never
be missing its job.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TimestampedBase

# Beyond this a job is treated as permanently failed rather than retried forever. A
# poison payload that retries endlessly starves everything behind it.
MAX_ATTEMPTS = 5


class JobKind(StrEnum):
    ocr_document = "ocr_document"


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class Job(TimestampedBase):
    """One unit of background work."""

    __tablename__ = "job"
    __table_args__ = (
        # The claim query: oldest runnable job of any kind.
        Index("ix_job_status_run_after", "status", "run_after"),
    )

    kind: Mapped[JobKind] = mapped_column(
        PgEnum(JobKind, name="job_kind", create_type=False), nullable=False
    )
    status: Mapped[JobStatus] = mapped_column(
        PgEnum(JobStatus, name="job_status", create_type=False),
        nullable=False,
        default=JobStatus.queued,
    )

    # Identifiers only — never document text. A queue row is not a place for case
    # material (CLAUDE.md §3).
    payload: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Backoff target. A retry that runs immediately just burns attempts against
    # whatever is still broken.
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Failure *class*, from a closed vocabulary — never an exception message, which
    # could carry a filename or extracted text.
    last_error: Mapped[str | None] = mapped_column(String(120))

    # Free-text detail is deliberately absent; this column exists only so a future
    # migration has somewhere obvious to put structured, scrubbed diagnostics.
    notes: Mapped[str | None] = mapped_column(Text)

    def as_document_id(self) -> uuid.UUID:
        return uuid.UUID(self.payload["document_id"])
