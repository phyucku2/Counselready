# ADR-0011 — Account deletion, and the background job queue

**Date:** 2026-07-28
**Status:** Accepted
**Owner decision:** no (engineering choices, recorded for override)

Two portions, recorded together because both turn on the same instinct: do the
destructive or deferred thing in an order where a failure leaves recoverable mess
rather than broken records.

---

## Part 1 — Account and data deletion

### Problem

A hard app-store requirement for any app collecting user data, and the right default
regardless. Someone who no longer wants a third party holding their family court file
should not have to ask permission to remove it.

### Decision

**Re-authentication, including the second factor.** The password is required even though
the caller already holds a session, and when MFA is on a current code is required too.
Destroying the account is precisely what someone who found an unlocked phone would do,
and it is the one action with no undo. An explicit `acknowledge` flag forces the client
to show what is about to be lost rather than offering a bare button.

**Blobs are deleted after the database transaction commits.** The reverse order would,
on a database failure, leave live records pointing at bytes that no longer exist —
visible breakage a user cannot fix. In this order a failure leaves unreferenced objects,
which are collectable garbage. Each object delete is attempted independently, and the
count of successes is reported honestly rather than assumed.

**The audit trail survives, anonymized.** `auth_event.user_id` and
`case_audit_event.actor_user_id` are `ON DELETE SET NULL`, so the record that activity
occurred outlives the record of who did it. Erasing the account erases its contents and
its identity, not the fact that the system was used.

**Cascade completeness is tested, not assumed.** A table added later without the right
foreign key would leave case material behind silently, so the test asserts every relevant
table is empty afterwards — including sessions, passkeys, MFA enrolment, and recovery
codes, each of which is a credential belonging to an account that no longer exists.

---

## Part 2 — Background jobs in PostgreSQL

### Problem

ADR-0003 and ADR-0006 deferred the queue until something needed durability. OCR does: it
is slow, it calls an external service, and it must survive a restart.

### Decision

**A `job` table claimed with `SELECT ... FOR UPDATE SKIP LOCKED`**, not Redis, not a
broker.

The reason is not simplicity for its own sake. It is that **the job and the data it
refers to commit in the same transaction**. A document row and its "OCR this document"
job land together or not at all, so the queue can never hold work for a document that was
rolled back, and a committed document can never be missing its job. With an external
broker that guarantee needs an outbox pattern to recover.

`SKIP LOCKED` is what makes it safe with several workers: each takes a different row
rather than queueing behind the same one, and a worker that dies releases its claim when
its transaction dies. No lease timers, no zombie jobs.

Supporting decisions:

- **Exponential backoff, capped**, and clamped *before* the shift — a test caught
  `BACKOFF_BASE * 2**49` raising `OverflowError` rather than producing something the cap
  could trim. Real jobs never reach that, but a helper that explodes on a large input is
  a trap for the next caller.
- **A five-attempt budget**, after which a job is failed rather than retried forever. A
  poison payload retried endlessly starves everything behind it.
- **`last_error` holds a failure *class* from a closed vocabulary**, never an exception
  message. Exception text carries filenames and extracted page content, and a queue table
  is not a place for case material (CLAUDE.md §3). There is a test that raises an engine
  error with a distinctive message and asserts it reaches neither the exception nor the
  stored row.
- **The payload holds identifiers only.**

---

## Part 3 — The OCR seam

**The engine is a protocol, and no concrete engine ships here.** ADR-0002 puts inference
inside the Azure tenant, and Azure Document Intelligence needs a subscription the owner
has not provisioned. The pipeline is built and tested against the seam; the engine lands
with the credentials. Same pattern as `ObjectStore`.

**The default engine fails loudly.** A no-op that reported success would leave scanned
pages permanently empty while the surface claimed the document had been read — exactly
the dishonesty `needs_ocr` exists to prevent.

**OCR only fills pages that have no text layer.** A native PDF's embedded text is more
accurate than anything OCR would produce, and re-reading it would degrade the citations
that point at it. The ADR-0004 distinction holds: a page read from a text layer keeps
`ocr_confidence = NULL` (never measured), while an OCR'd page gets a real number.

**A document is `complete` only when every page has text.** A page OCR could not read
leaves it honestly marked as still needing work.

## Consequences

- A worker process to drain the queue is **not** here. The claim/complete primitives and
  the OCR step are tested; the loop that runs them is deployment shape and belongs with
  the Azure work.
- No pruning for finished jobs, expired passkey challenges, or expired sessions. Three
  small cleanup jobs, now all pointing at the same queue — worth one portion together.

## Verification

210 tests green (95% coverage), `mypy --strict` clean, eight migrations round-trip.
