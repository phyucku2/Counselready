# Roadmap status board

The single source of truth for what remains and where each portion stands. Updated every
development-loop cycle; one portion = one small PR (CLAUDE.md §10). States: **Built**
(code complete on a branch), **Tested** (full gate green per Definition of Done,
adversarial review findings fixed), **Merged** (on `main`).

## Phase 0 — Foundations

| # | Portion | Built | Tested | Merged | Notes |
|---|---|---|---|---|---|
| 0.1 | Repo scaffolding — governance (CLAUDE.md), ADR-0001 (scope & non-advice posture), ADR-0002 (Azure architecture), founding brainstorm + market research migrated | ✅ | n/a | ⏳ | Docs only; no code. |
| 0.2 | Backend skeleton — API service, database session, migration infrastructure, CI quality gate (lint/format/types/tests/coverage/secret-scan), license scan | ✅ | ✅ | ⏳ | ADR-0003. FastAPI + SQLAlchemy 2 async + Alembic + Postgres. Liveness/readiness probes (readiness fails closed to 503). Document-text-free request logging: route templates only, request id resolved before downstream so a 500 still logs one correlated line. Startup guard in the lifespan, not in `Settings`, so Alembic is unaffected. Naming convention on the metadata for stable migration constraint names. 32 tests, 97% coverage, `mypy --strict` clean; generated migrations verified lint-clean. |
| 0.3a | **Auth — passwords, sessions, and the route gate** — Argon2id, access/refresh tokens with rotation + replay detection, immediate logout, per-identity rate limiting, `current_user` dependency | ✅ | ✅ | ⏳ | ADR-0007. Login does not disclose whether an account exists (identical bodies + timing test). Replaying a rotated refresh token revokes the whole session. `logout-all` shipped now, not in a later hardening pass. JWT secret must be ≥32 chars or the boot fails. 136 tests, 97% coverage. |
| 0.3b | **MFA (TOTP)** — two-step enrolment, challenge-based login, replay-protected codes, single-use recovery codes, encrypted-at-rest secrets | ✅ | ✅ | ⏳ | ADR-0008. No vendor: TOTP is verified locally, SMS rejected (SIM-swap, and a shared family plan hands codes to the wrong person). A password alone now yields only a 5-minute challenge. 159 tests, 96% coverage. |
| 0.3b-i | **Rate-limit MFA code attempts** | ⏳ | ⏳ | ⏳ | **Known gap, close before launch** (ADR-0008): the verify step is unthrottled, so a 6-digit code is brute-forceable within a challenge's lifetime. |
| 0.3c | Password reset + login alerting | ⏳ | ⏳ | ⏳ | Both need the email-sending egress seam, which under ADR-0002 ships off by default and in-tenant. `auth_event` already records what an alert would need. |
| 0.4 | Account & data deletion — in-app + API, full destruction of documents and derived data | ⏳ | ⏳ | ⏳ | Hard app-store requirement; build it before it blocks submission, not after. |

## Phase 1 — Ingest, OCR, and document dissection

The phase that determines whether the product is trustworthy at all. Extraction quality
gates everything downstream.

| # | Portion | Built | Tested | Merged | Notes |
|---|---|---|---|---|---|
| 1.1 | **Document ingest engine** — bounded-before-materializing upload reader, content-addressed blob storage behind a protocol, SHA-256 dedup, text-layer extraction into pages | ✅ | ✅ | ⏳ | ADR-0006. Blob written before the row, so a failure leaves a collectable object rather than a record pointing at nothing. `needs_ocr` added as a distinct state. 90 tests at the time. |
| 1.1b | **Case + document HTTP routes** — create/list/read cases, upload/list documents, ownership as a dependency, case-material audit trail | ✅ | ✅ | ⏳ | ADR-0009. Another account's case is a 404, not a 403 — byte-identical to one that never existed. Audit holds counts only, proven by absence. Oversized upload refused with 413 on the real path. 175 tests, 95% coverage. |
| 1.1c | `GET /documents/{id}` with page text | ⏳ | ⏳ | ⏳ | Blocked on a redaction decision: serving page text means serving minors' identifiers unless they are stripped (CLAUDE.md §3). |
| 1.2 | OCR pipeline — async job, per-page confidence propagated to the surface | ⏳ | ⏳ | ⏳ | Engine choice is an ADR. Carries the durable-queue decision deferred by ADR-0003/0006 — the text-layer pass runs inline, real OCR must not. |
| 1.3a | **Core case-file schema** — user/case/party/document/page/passage/extracted_fact, with the citation guarantee as a NOT NULL foreign key | ✅ | ✅ | ⏳ | ADR-0004. Migration `2d61942264a6`, verified reversible (upgrade → downgrade → upgrade). 50 tests (32 unit + 18 live-Postgres integration), 98% coverage, `mypy --strict` clean. The database rejects an unanchored fact — proven by test, not by convention. |
| 1.3b | Document dissection — the extractor that populates those fields from page text | ⏳ | ⏳ | ⏳ | Must locate every value in the source text; a value it cannot anchor is dropped, not stored. |
| 1.4 | Florida jurisdiction profile — document types and terminology behind the profile seam | ⏳ | ⏳ | ⏳ | CLAUDE.md §7. |
| 1.5 | Accuracy validation harness — synthetic gold-standard corpus, precision/recall per field, error taxonomy with hallucination as a release-blocking class | ⏳ | ⏳ | ⏳ | Synthetic documents only (§3). |

## Phase 2 — Timeline

| # | Portion | Built | Tested | Merged | Notes |
|---|---|---|---|---|---|
| 2.1a | **Timeline event schema + provenance split** — `case_event` with CHECK constraints: document-derived events cite a passage and are not attributed to a person; user-asserted events name their author and hold no passage | ✅ | ✅ | ⏳ | ADR-0005. Migration `8a1be962755b`, round-tripped. `date_precision` prevents false precision on "in March"-style sources. Conflicting accounts proven to persist as two attributed rows. 60 tests, 98% coverage. |
| 2.1b | Event extraction — populate documentary events from page text | ⏳ | ⏳ | ⏳ | Rides with the dissection extractor (1.3b); an event that cannot be anchored is dropped. |
| 2.2 | Timeline assembly + read API — ordering, filtering, and the `date_precision`-aware renderer | ⏳ | ⏳ | ⏳ | A renderer that formats `occurred_at` without consulting `date_precision` reintroduces false precision — needs its own test (ADR-0005). |
| 2.3 | Timeline UI — accessible by construction; a list/table equivalent ships alongside any visualization | ⏳ | ⏳ | ⏳ | WCAG 2.2 AA. |

## Phase 3 — Issue spotting

| # | Portion | Built | Tested | Merged | Notes |
|---|---|---|---|---|---|
| 3.1 | Cross-filing inconsistency detection — contradicted dates, unanswered requests, missing responses | ⏳ | ⏳ | ⏳ | Framed as "questions to review," never verdicts (ADR-0001). |

## Phase 4 — Language review (last, deliberately)

| # | Portion | Built | Tested | Merged | Notes |
|---|---|---|---|---|---|
| 4.0 | **Bias evaluation, documented** — before any of 4.1 ships | ⏳ | ⏳ | ⏳ | Tone classifiers score dialects and non-native English as more hostile; this gate exists because of that. |
| 4.1 | Party language review — quote-based and attributed, never scored | ⏳ | ⏳ | ⏳ | No "aggression scores." Owner + counsel sign off on wording. |

## Cross-cutting, not a phase

| Portion | Status | Notes |
|---|---|---|
| Mobile apps (iOS + Android) | ⏳ | Web first, wrap once flows are proven. Deletion flow (0.4) is a hard prerequisite for store submission. |
| Attorney / GAL review view | ⏳ | Fast-follow after Phase 2 — same citation architecture serves it. |
| Terms of service + intake boundaries | 🚫 Blocked | Needs counsel: sealed/juvenile material, entitlement to uploaded documents, retention. (ADR-0001 open items.) |
| Trademark clearance on "CounselReady" | 🚫 Blocked | Owner + counsel, before any app-store submission. |
| Azure subscription and production secrets | 🚫 Blocked | Owner-side; do not collect until the owner initiates. |
