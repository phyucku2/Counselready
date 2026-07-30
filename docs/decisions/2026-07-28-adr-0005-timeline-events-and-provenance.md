# ADR-0005 — Timeline events and the provenance split

**Date:** 2026-07-28
**Status:** Accepted
**Owner decision:** no (engineering choice, recorded for override)

## Problem

The timeline has to hold two kinds of entry that look identical on screen and are
completely different in weight:

- what a **document** says happened ("the motion filed 2026-03-14 states the children
  were not returned"), and
- what the **user** says happened ("I recorded that the exchange did not occur").

The owner chose the wider evidence scope, so both belong in v1. If they share a table
with no structural distinction, the first careless write path produces a user's typed
note rendered as though a filing said it — which would be, in the most literal sense,
manufacturing evidence. An attorney reading the export needs to know which is which at
a glance, because the second kind needs corroboration before it is worth anything in a
filing.

A third problem: two parties routinely give incompatible accounts of one incident. A
timeline that reconciles them into a single entry has invented a fact neither party
asserted.

## Decision

**One `case_event` table with a `provenance` discriminator, and two CHECK constraints
that make each shape's companion columns mandatory and the other shape's impossible.**

```sql
CHECK ((provenance = 'document_derived' AND passage_id IS NOT NULL)
    OR (provenance = 'user_asserted'    AND passage_id IS NULL))

CHECK ((provenance = 'user_asserted'    AND recorded_by_user_id IS NOT NULL)
    OR (provenance = 'document_derived' AND recorded_by_user_id IS NULL))
```

A document-derived event cites its passage and is not attributed to an account holder.
A user-asserted event names its author and has no passage to borrow. Neither shape can
masquerade as the other, and the database — not a service-layer convention — is what
refuses.

Supporting decisions:

- **`kind` separates `procedural` from `alleged`.** A motion being filed is a matter of
  record; what the motion *says* happened is a claim. Merging them is what makes a
  chronology untrustworthy.
- **`date_precision` travels with `occurred_at`.** Filings say "in March" or "last
  spring" constantly. Without a precision column the surface renders
  "March 1, 2026 12:00 AM" for something the source dated to a month. False precision
  on a legal chronology is a defect, not a formatting quirk.
- **`asserted_by_party_id` and `about_party_id` are separate and both optional.** In
  "Petitioner alleges Respondent missed the exchange", the asserting party and the
  subject are different people, and the timeline needs both to render a fair account.
  A procedural event such as a hearing being scheduled has neither, so neither is
  required.
- **Party references are `ON DELETE SET NULL`, not CASCADE.** Losing an attribution
  must not silently delete the underlying record and its citation.
- **No denormalized `document_id`.** The document is reached through
  passage → page → document. A duplicated column could disagree with the passage the
  event actually cites, and a citation that contradicts itself is worse than an extra
  join.
- **Index on `(case_id, occurred_at)`** — the timeline's only real read pattern.

## Why not the alternatives

**Separate tables for documentary and asserted events** would enforce the shapes by
construction, but every timeline read becomes a UNION, and the ordering, filtering, and
pagination logic doubles. The constraint approach gets the same guarantee at one table's
cost.

**A nullable `passage_id` with no constraint** is what most codebases would do. It
enforces nothing: the shape that must never exist — a document-derived event with no
source — is exactly the one it permits.

**Reconciling conflicting accounts into one event with a "disputed" flag** would destroy
the attribution that makes each account meaningful, and require the system to decide
which version is canonical. It is not equipped to make that call and should not appear
to.

## Consequences

- Conflicting accounts persist as two attributed events at the same moment. The surface
  can show both side by side; nothing in the schema pushes toward merging them.
- Adding messages and photos as evidence (the owner's wider scope) will extend the
  provenance enum and the CHECK constraints rather than reworking the table — a message
  is a third anchor type, not a fourth table.
- The extractor must supply a passage for every documentary event, matching the
  ADR-0004 posture: an event it cannot anchor is dropped, not stored unanchored.
- `date_precision` has to be honored by every renderer. A surface that formats
  `occurred_at` without consulting it reintroduces the false precision this column
  exists to prevent — worth a test when the first timeline view ships.

## Verification

60 tests green: 32 unit, 28 integration against live PostgreSQL 16. Both migrations
round-tripped upgrade → downgrade → upgrade, individually and to base. `mypy --strict`
clean, 98% coverage. The four malformed event shapes are each proven rejected by the
database, and the conflicting-accounts case is proven to persist as two attributed
rows.
