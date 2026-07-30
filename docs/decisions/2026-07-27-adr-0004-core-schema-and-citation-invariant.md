# ADR-0004 — Core case-file schema and the citation invariant

**Date:** 2026-07-27
**Status:** Accepted
**Owner decision:** no (engineering choice, recorded for override)

## Problem

ADR-0001 §2 says every generated statement must cite the text it came from. Stated as a
policy, that survives exactly as long as every future code path remembers it. One
handler that writes a fact without a source, and the product is producing uncited
claims — the failure mode courts sanctioned roughly 712 times in 2025.

The schema had to make the rule structural rather than aspirational.

## Decision

**A passage is a row, and every derived claim references it by a NOT NULL foreign key.**

The spine:

```
user_account → case → document → document_page → passage
                                                     ↑
                                        extracted_fact.passage_id  (NOT NULL)
```

`extracted_fact.passage_id` has no nullable escape hatch. An extractor that produces a
value it cannot locate in the page text has nowhere to put it, so the row is dropped
rather than stored unanchored. Un-anchored facts are unrepresentable, not merely
discouraged.

Supporting decisions inside the schema:

- **A passage stores its quoted text alongside its offsets.** Offsets alone would
  silently start pointing at different words if a page were re-OCRed. A citation that
  drifts is worse than no citation, because it still looks authoritative.
- **OCR confidence is per page, nullable, and range-checked.** Family court files mix
  clean native PDFs with skewed photocopies; a document-level average hides the one
  unreadable page. NULL means "not measured" (native text layer) and is deliberately
  distinct from a measured 0.0 — collapsing them would hide which pages were never
  checked.
- **`filed_at` and `served_at` are nullable.** Many documents state neither. Defaulting
  to the upload time would fabricate a fact about a legal filing.
- **Documents default to `unclassified` / `ocr_status=pending`.** Honest defaults: we
  have not read it yet and the schema does not pretend otherwise.
- **Deduplication is `(case_id, content_hash)`, scoped to a case rather than global.**
  The same order arrives from counsel and from the clerk portal — that is one document.
  But parallel matters legitimately share an exhibit, so the same bytes may exist in two
  cases.
- **`party.is_minor` is a column, not a naming convention**, because "redact minors from
  generated output by default" (CLAUDE.md §3) needs something to key off.
- **A party is unique on `(case, name, role)`, not `(case, name)`.** A self-represented
  parent is both a party and their own counsel.
- **Extracted facts are unique on `(passage, field, extractor_version)`**, so re-running
  an extractor updates rather than duplicates, and a new version may re-read the same
  passage without deleting the old rows first — a bad extraction run can be superseded
  and compared rather than silently overwritten.
- **The `case` is the top-level container** (multi-case from day one, per the owner's
  decision): dissolution, injunction, and support matters routinely run in parallel.
- **Jurisdiction is a column from the first migration**, so a second state is a new enum
  value rather than a schema change (CLAUDE.md §7).

## Why not the alternatives

**Citation as columns on the fact row** (`document_id`, `page`, `start`, `end`) would
work, but it duplicates the anchor on every fact and gives nothing to attach the quote
to. Multiple facts commonly come from the same sentence.

**Citation as a JSON blob** would satisfy nobody: not type-checked, not foreign-keyed,
not queryable, and trivially written empty.

**Enforcing it in the service layer only** is the option that fails the moment a
background job, an admin script, or a future contributor writes a row directly.

## Consequences

- The guarantee is testable, and is tested against a real PostgreSQL: an insert with a
  NULL `passage_id` is rejected by the database, not by application code that a future
  path might bypass.
- Extraction must locate its output in the source text. That is real work for the
  extractor and the reason quality is a Phase-1 concern rather than a later polish item.
- Cascade deletes reach the whole graph from the case down, so deleting a case leaves no
  orphaned case material.
- Enum types are created and dropped explicitly in the migration. Left implicit,
  `CREATE TYPE` runs as a side effect of the first table that references it and is never
  dropped on downgrade, so downgrade-then-upgrade fails with "type already exists".
- Timeline events and the order-obligations register are **not** in this portion. They
  arrive in Phase 2 and Phase 3 with their own provenance modelling — user-asserted log
  entries have no passage to point at, so they need a provenance discriminator plus a
  CHECK constraint rather than a plain NOT NULL, and that belongs with the feature.
- Audit logging of case-material reads and writes (CLAUDE.md §3) lands with the first
  endpoint that reads case data; there are no such endpoints yet.

## Verification

50 tests green: 32 unit, 18 integration against live PostgreSQL 16. `mypy --strict`
clean. Migration verified reversible by round-tripping upgrade → downgrade → upgrade,
and the integration fixture verified against a freshly created database. The unit suite
still runs with no database configured (integration tests skip rather than fail).
