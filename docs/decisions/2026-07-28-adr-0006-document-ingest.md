# ADR-0006 — Document ingest

**Date:** 2026-07-28
**Status:** Accepted
**Owner decision:** no (engineering choices, recorded for override)

## Problem

Getting documents in is where most users of a tool like this give up, and it is also
the largest untrusted-input surface in the product. A family court file is a hundred
scanned pages from a clerk portal, a photo of something served at the door, and a PDF
emailed by counsel — all arriving as bytes we did not produce.

Three questions had to be settled: where the bytes live, how the upload is bounded, and
what "we have read this document" is allowed to mean.

## Decision

### Storage behind a protocol, written before the database row

Documents live in blob storage, never in the database (ADR-0002). Ingest depends on an
`ObjectStore` protocol; the Azure implementation needs a subscription the owner has not
provisioned, so a filesystem backend serves development and tests.

Keys are **content-addressed and namespaced per case**: `cases/{case_id}/documents/{sha256}`.
Content addressing makes storing the same bytes twice idempotent, and the per-case
prefix makes destroying a case a prefix operation rather than a scan — which matters
when a user asks for their case to be erased (CLAUDE.md §3).

**The blob is written before the database row.** If the database write then fails, the
result is an unreferenced object a sweep can collect. The reverse order leaves a
`Document` row pointing at storage that holds nothing — a broken record the user can
see and no sweep can repair. A test pins this ordering by rolling back the transaction
and asserting the object survives while the row does not.

### The upload cap fires before the body is materialized

`read_bounded` accumulates incrementally and aborts the moment the running total crosses
the cap, without draining the rest of the stream. A `Content-Length` is used only as a
cheap early rejection and is never trusted as the real size — a client can under-declare
it or omit it entirely.

This distinction is the entire point. A limit checked after the body is in memory has
already permitted the exhaustion it exists to prevent, and it passes a naive test
identically. The tests therefore assert on **how much was consumed**, not just that an
exception was raised: an endless stream must stop being read after roughly one chunk
past the cap.

### `needs_ocr` is a distinct state from `complete`

This portion reads the text a PDF already carries. It does not perform OCR.

A scanned filing has an image and no words, and an empty string for that page is
indistinguishable from a genuinely blank page. So `OcrStatus` gains **`needs_ocr`**, set
when *any* page lacks a text layer — "any", not "all", because a scanned exhibit stapled
into a native PDF is exactly the case where a document-level `complete` would hide the
one page nobody has read.

Pages read from an embedded text layer get `ocr_confidence = NULL`, preserving the
ADR-0004 distinction: no confidence was ever measured, which is not the same as a
measured zero.

### Parsing runs off the event loop

`extract_text_layer` is synchronous and CPU-bound, so the service calls it through
`asyncio.to_thread` (CLAUDE.md §9). It is bounded on both axes — a page cap and a
per-page character cap — so a pathological document cannot exhaust memory after passing
the byte check.

## Deliberately not in this portion

**No HTTP endpoint.** There is no authentication yet (roadmap 0.3), and an
unauthenticated endpoint that accepts and reads case documents is precisely the thing
CLAUDE.md §3 exists to prevent — including in development. The ingest engine is complete
and tested; the upload route ships with auth, and `read_bounded` is written against an
arbitrary async byte stream so wiring it to a request body changes nothing about the
guarantee.

**No durable job queue.** ADR-0003 deferred the queue until the pipeline needed it. The
text-layer pass is fast enough to run inline within ingest; real OCR is not, and it
arrives with the queue decision rather than pretending an in-process background task is
durable. The revisit trigger is the OCR portion.

## Consequences

- Ingest is fully testable before any Azure resource exists, and the Azure backend is a
  new class implementing one protocol rather than a rewrite.
- An encrypted PDF is reported as encrypted rather than yielding zero pages. Silently
  returning nothing would route it to OCR and quietly produce an empty document.
- A single unreadable page does not lose the other four hundred: the page is recorded
  with empty text, which routes it to OCR — the correct destination anyway.
- Duplicate uploads raise an error naming the existing document, so the caller can point
  the user at the record they already have instead of failing opaquely.
- Bytes are held in memory during ingest, bounded by the 100 MiB cap. If that becomes a
  problem under concurrency, the fix is streaming straight to blob storage with hashing
  in flight — deferred rather than pre-built.

## Dependency added

`pypdf` 6.14.2 — **BSD-3-Clause**, permissive, passes CLAUDE.md §6. Note that it declares
its license via `License-Expression` metadata rather than a classifier, which the CI
scanner reads correctly.

## Verification

90 tests green: 56 unit, 34 integration against live PostgreSQL 16 and a real object
store. `mypy --strict` clean, 97% coverage. The enum migration was round-tripped with a
row actually holding `needs_ocr`, confirming the downgrade moves it to `pending` rather
than orphaning it — PostgreSQL has no `ALTER TYPE ... DROP VALUE`, so the downgrade
rebuilds the type.
