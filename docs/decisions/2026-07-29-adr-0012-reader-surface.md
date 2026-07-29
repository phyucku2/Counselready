# ADR-0012 — The reader surface: document view, timeline API, corrections, and the first web client

- **Date:** 2026-07-29
- **Status:** Accepted
- **Relates to:** ADR-0001 (non-advice posture), ADR-0004 (citation invariant),
  ADR-0005 (timeline provenance), ADR-0009 (case & document routes)

## Problem

Everything built so far is invisible. Documents can be uploaded and pages extracted,
and `case_event` can hold a chronology, but nothing can be read back. Until a person
can open a filing and see a timeline, none of the guarantees the schema enforces are
doing anything for anyone.

Four decisions were in the way.

### 1. Does serving page text violate the redaction rule?

Roadmap item 1.1c had been blocked on this: CLAUDE.md §3 requires minors to be
redacted, and a document's page text obviously contains them.

**Decision: the redaction rule governs generated output and exports, not the account
holder reading their own file.**

The rule exists so that material CounselReady *produces* — summaries, exports,
anything that leaves the account holder's hands or is shown to a third party — does not
propagate children's identifiers. The reader is looking at a document they already
possess, that they uploaded, in a case they own. Redacting their own children's names
out of their own filing would be theatre, and worse, it would make the viewer useless
for the one job it has: letting someone check that what we extracted matches what the
document actually says.

The rule stands unchanged everywhere it was meant to apply. Redaction attaches to the
**export and generation boundary**, and that is where it will be implemented and
tested. Any future route serving case text to anyone other than the owning account is a
new decision, not covered by this one.

### 2. Can a client create a document-derived event?

No. The API accepts **user_asserted events only**.

`case_event`'s CHECK constraints already make an uncited "documentary" event
impossible, but relying on that would make the API's contract "send whatever you like
and the database will sort it out". Documentary events are written by extraction, the
only code path holding a passage to cite. `provenance` is therefore absent from the
request body entirely rather than validated — a field that cannot be sent cannot be
smuggled. A request including it is ignored, and a test asserts that.

### 3. How does someone fix a mistake on the timeline?

**Entries are permanent. A correction is a note recorded beside the entry, never an
edit to it.** (`case_event_note`; `POST /cases/{id}/events/{id}/notes`.)

There is no update route and no delete route, and a test asserts their absence against
the OpenAPI schema rather than against a status code — so adding one fails the build
rather than silently changing the product's character.

Two reasons this beats a mutable row:

- A chronology whose entries can be silently rewritten is worth less the moment anyone
  else looks at it. What was originally recorded, and when, survives. For a document
  whose whole purpose is to make a meeting with counsel shorter and better prepared,
  "here is what I first wrote and here is what I corrected" is *more* useful than a
  tidied version, not less.
- For a **document-derived** event, editing is not even coherent. The summary is what
  the filing says, anchored to a passage. Someone who disagrees is not correcting our
  reading of the document — they are contradicting the document. That is a different
  claim, and it has to stay attributed to them while the citation continues to point at
  what the filing actually says. The correction path makes that the natural shape; an
  edit control would have made it impossible to express.

A note is therefore always the account holder's own statement. There is no documentary
variant, and `author_user_id` is unconditionally NOT NULL — every note has a person
behind it, so none of `case_event`'s conditional provenance machinery applies.

### 4. What does the first client need to be?

A small React + Vite SPA, served same-origin behind a dev/preview proxy so no CORS
relaxation exists anywhere. Four screens: sign in, cases, case detail with upload,
document viewer, timeline.

Tokens live **in memory only**, never `localStorage`. Closing the tab signs you out.
For a product holding one family's court file, a token that survives the tab and is
readable by any injected script is the wrong trade, and "sign in again" is a cost worth
paying.

## What was built

**`GET /cases/{case_id}/documents/{document_id}`** — pages in order, each with text,
OCR confidence, and passages. Scoped through the existing `owned_case` dependency and
then filtered by `case_id`, so a document id copied from elsewhere is not a capability:
it has to sit in the case named in the path. Two tests, one for each way of getting
that wrong. The event routes take the same shape for the same reason.

`ocr_confidence` stays nullable all the way to the client. NULL means *not measured* —
a native PDF with a text layer — a different claim from a measured zero, and flattening
the two would tell a reader their clean document was read badly.

**`GET`/`POST /cases/{case_id}/events`** and **`POST .../events/{id}/notes`** — the
chronology, merged across both provenances, ordered by `occurred_at` with `created_at`
as the tiebreak so two things on the same day do not shuffle between loads.
Document-derived events resolve passage → page → document and carry a `citation`
object; user-asserted ones carry `null`, explicitly, so a client cannot mistake absence
for "not loaded yet". Every event carries `notes`, oldest first.

**Audit vocabulary** gained `event_created`, `event_list`, and `event_note_created`
(migration `4b7c1d90e2aa`, which also creates `case_event_note`). Folding timeline
access into `case_read` would have been cheaper and would have made the audit trail lie
about what happened. PostgreSQL cannot drop an enum value, so the downgrade rebuilds the
type; rows carrying a value that no longer exists are deleted rather than rewritten to a
different action, because a silently altered audit record is worse than a gap.

**The web client** — the four screens, plus `formatOccurred`, which renders a date no
more precisely than `date_precision` says it is known. ADR-0005 predicted this exact
defect ("a renderer that formats `occurred_at` without consulting `date_precision`
reintroduces false precision"); the renderer consults it, and the browser check asserts
a month-precision entry displays as "March 2026" and not as a day.

Corrections render indented and quieter beneath the entry they annotate, and the control
says *"Add a correction"* rather than *"Edit"* — the label has to match what actually
happens, or permanence becomes a surprise the first time someone tries to fix a typo.

Passage highlighting clamps offsets rather than trusting them. A bad offset must degrade
to *no highlight*, never to text quietly dropped from the page a reader came to verify.

## Consequences

- Item 1.1c is unblocked and done. Redaction work moves to the export boundary, where it
  belongs, and needs its own portion before anything is exportable.
- A correction cannot itself be corrected or withdrawn — notes are as permanent as
  entries. That is consistent, and it is also a real edge: somebody will eventually paste
  the wrong thing into one. Revisit if it bites, but not by adding a delete.
- Notes are plain text with no structure. A correction that says "the date was wrong"
  does not move the entry in the ordering, so a chronology with many corrections reads
  correctly only if you read the notes. Structured date corrections are a later decision,
  not an omission to fix quietly.
- No client-side test suite exists yet. The browser check is a script driven through
  Chromium; it verifies the built bundle end to end, which the Definition of Done
  requires, but it is not a regression suite.
- Party attribution (`asserted_by_party_id`, `about_party_id`) is unused by the API.
  There is no party UI, and inventing one to fill columns would have widened the portion.
