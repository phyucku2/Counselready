"""Account and data destruction.

Ordering is deliberate. Storage keys are collected first, the database rows are deleted
in one transaction, and the blobs are removed only after that transaction has
committed. Deleting blobs first would, on a database failure, leave live records
pointing at bytes that no longer exist — visible breakage the user cannot fix. In this
order a failure leaves unreferenced objects, which are collectable garbage.

The audit trail survives, anonymized: `auth_event.user_id` and
`case_audit_event.actor_user_id` are `ON DELETE SET NULL`, so the record that activity
occurred outlives the record of who did it. Erasing the account erases its contents and
its identity, not the fact that the system was used.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case
from app.models.document import Document
from app.models.user import UserAccount
from app.storage.base import ObjectStore


@dataclass(frozen=True)
class DeletionSummary:
    """What was destroyed. Counts only — never titles or content."""

    cases: int
    documents: int
    objects_removed: int


async def collect_storage_keys(session: AsyncSession, *, user_id: uuid.UUID) -> list[str]:
    """Every blob belonging to this account, gathered before anything is deleted."""
    keys = (
        await session.execute(
            select(Document.storage_key)
            .join(Case, Case.id == Document.case_id)
            .where(Case.owner_id == user_id)
        )
    ).scalars()
    return list(keys)


async def delete_account(
    session: AsyncSession, store: ObjectStore, *, account: UserAccount
) -> DeletionSummary:
    """Destroy the account and everything it owns.

    Cases, documents, pages, passages, facts, events, sessions, passkeys, MFA
    enrolment, and recovery codes all cascade from `user_account`. The cascades are
    verified by test rather than assumed, because a table added later without the right
    foreign key would leave case material behind silently.
    """
    keys = await collect_storage_keys(session, user_id=account.id)
    case_count = len(
        list((await session.execute(select(Case.id).where(Case.owner_id == account.id))).scalars())
    )

    await session.execute(delete(UserAccount).where(UserAccount.id == account.id))
    await session.flush()

    return DeletionSummary(cases=case_count, documents=len(keys), objects_removed=0)


async def purge_objects(store: ObjectStore, keys: list[str]) -> int:
    """Remove the blobs. Called after the database transaction commits.

    A failure here leaves unreferenced objects rather than broken records, so each
    delete is attempted independently and the count of successes is reported honestly.
    """
    removed = 0
    for key in keys:
        try:
            await store.delete(key)
        except Exception:  # noqa: S112
            # One unreachable object must not strand the rest. Not logged: the key
            # namespaces a case id, and the request log is document-free by
            # construction (CLAUDE.md §3). The shortfall shows in the returned count.
            continue
        removed += 1
    return removed
