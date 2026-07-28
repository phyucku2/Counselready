# ADR-0009 — Case and document routes

**Date:** 2026-07-28
**Status:** Accepted
**Owner decision:** no (engineering choices, recorded for override)

## Problem

ADR-0006 built the ingest engine and deliberately withheld its HTTP surface until an
authentication gate existed. ADR-0007 built the gate. This portion connects them, which
means the product now accepts real case documents over the network — and every
authorization mistake from here forward is a disclosure of someone's family court file.

## Decision

### Ownership is a dependency, not a check

`owned_case` resolves a case scoped to the signed-in account and every case-scoped route
depends on it. Making it a dependency rather than a line inside each handler means
forgetting it requires actively omitting a parameter, which is visible in review, rather
than merely failing to write a check, which is invisible.

### Another account's case is a 404, never a 403

A 403 says "this exists and you may not have it". For a product where the most likely
unauthorized reader is the opposing party in the case, confirming existence is itself a
disclosure. A case you do not own is byte-identical to a case that never existed — there
is a test asserting exactly that.

### Every read and write of case material is audited

`case_audit_event` records actor, case, action, and a `detail` object restricted to
counts (`{"pages": 12}`, `{"documents": 3}`). The action vocabulary is a closed enum, so
the trail cannot accidentally come to hold document text. A test asserts the uploaded
document's text appears nowhere in the audit rows.

`case_id` is `ON DELETE SET NULL`: deleting a case must erase what it contained, not the
record that it was accessed.

Because ownership is resolved in a dependency, a rejected cross-account attempt never
reaches the handler and so leaves no entry on the victim's case — also tested, since an
audit trail that records other people's failed attempts against your case would be its
own small privacy problem.

### The bounded reader runs on the real request path

The upload handler streams the body through `read_bounded` (ADR-0006) with the
`Content-Length` passed only as an early hint. A test drives an oversized upload through
the actual endpoint and asserts 413, so the guarantee is proven where it is used rather
than only where it is defined.

### Upload failures explain themselves in plain words

A password-protected PDF says so and suggests removing the password; a non-PDF says it is
not a PDF; a duplicate returns 409 **with the existing document's id**, because the same
order genuinely does arrive from both counsel and the clerk portal and the useful answer
is "you already have this one". These users are stressed and mostly not technical — an
opaque 422 is a support burden and a reason to give up.

## Consequences

- The ingest path works end to end for the first time: sign in, create a case, upload a
  PDF, list what is in it.
- The object store is a request dependency, so the Azure backend swaps in without
  touching a handler.
- `GET /documents/{id}` returning page text is **not** here. It needs a decision about
  redaction of minors' identifiers (CLAUDE.md §3) before any case text is served.
- No pagination yet. Fine for a personal case file, not for the attorney tier; the list
  endpoints will need it before that ships.

## Dependency added

`python-multipart` 0.0.32 — Apache-2.0, required by FastAPI for form uploads.

## Verification

175 tests green (95% coverage), `mypy --strict` clean, six migrations round-trip.
