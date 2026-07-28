"""Enqueue and claim jobs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.models import MAX_ATTEMPTS, Job, JobKind, JobStatus

# Exponential, capped. Long enough that a dependency outage is not hammered, short
# enough that a transient blip clears within a session.
BACKOFF_BASE = timedelta(seconds=30)
BACKOFF_CAP = timedelta(minutes=30)


# Clamped before the shift, not after: `BACKOFF_BASE * 2**49` raises OverflowError
# rather than producing something large the cap could trim. MAX_ATTEMPTS keeps real
# jobs well under this, but a helper that explodes on a big input is a trap for the
# next caller.
MAX_BACKOFF_DOUBLINGS = 16


def backoff_for(attempts: int) -> timedelta:
    doublings = min(max(0, attempts - 1), MAX_BACKOFF_DOUBLINGS)
    delay: timedelta = BACKOFF_BASE * (2**doublings)
    return delay if delay < BACKOFF_CAP else BACKOFF_CAP


async def enqueue(
    session: AsyncSession, *, kind: JobKind, payload: dict[str, str], now: datetime
) -> Job:
    """Add a job in the caller's transaction.

    Deliberately not a separate connection: the job and the row it refers to must
    commit together, or the queue can hold work for data that was rolled back.
    """
    job = Job(kind=kind, payload=payload, run_after=now, status=JobStatus.queued)
    session.add(job)
    await session.flush()
    return job


async def claim_next(session: AsyncSession, *, now: datetime) -> Job | None:
    """Take the oldest runnable job, or None.

    `FOR UPDATE SKIP LOCKED` is what makes this safe with several workers: each takes a
    different row instead of queueing behind the same one, and a worker that dies
    releases its claim when its transaction dies.
    """
    job = (
        await session.execute(
            select(Job)
            .where(Job.status == JobStatus.queued, Job.run_after <= now)
            .order_by(Job.run_after)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
    ).scalar_one_or_none()

    if job is None:
        return None

    job.status = JobStatus.running
    job.attempts += 1
    await session.flush()
    return job


async def mark_succeeded(session: AsyncSession, job: Job) -> None:
    job.status = JobStatus.succeeded
    job.last_error = None
    await session.flush()


async def mark_failed(session: AsyncSession, job: Job, *, error: str, now: datetime) -> None:
    """Reschedule with backoff, or give up once the attempt budget is spent.

    `error` must be a failure *class* from a closed vocabulary, never an exception
    message — those can carry filenames and extracted text.
    """
    job.last_error = error[:120]
    if job.attempts >= MAX_ATTEMPTS:
        job.status = JobStatus.failed
    else:
        job.status = JobStatus.queued
        job.run_after = now + backoff_for(job.attempts)
    await session.flush()


async def enqueue_ocr(session: AsyncSession, *, document_id: uuid.UUID) -> Job:
    return await enqueue(
        session,
        kind=JobKind.ocr_document,
        payload={"document_id": str(document_id)},
        now=datetime.now(UTC),
    )
