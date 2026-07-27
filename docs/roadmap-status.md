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
| 0.3 | Auth — account creation, MFA (CLAUDE.md §3 makes MFA a launch requirement, not a later hardening item), session handling | ⏳ | ⏳ | ⏳ | |
| 0.4 | Account & data deletion — in-app + API, full destruction of documents and derived data | ⏳ | ⏳ | ⏳ | Hard app-store requirement; build it before it blocks submission, not after. |

## Phase 1 — Ingest, OCR, and document dissection

The phase that determines whether the product is trustworthy at all. Extraction quality
gates everything downstream.

| # | Portion | Built | Tested | Merged | Notes |
|---|---|---|---|---|---|
| 1.1 | Document upload — bounded before materializing, private blob storage, per-account job quota | ⏳ | ⏳ | ⏳ | ADR-0002 cost control. |
| 1.2 | OCR pipeline — async job, per-page confidence propagated to the surface | ⏳ | ⏳ | ⏳ | Engine choice is an ADR. |
| 1.3a | **Core case-file schema** — user/case/party/document/page/passage/extracted_fact, with the citation guarantee as a NOT NULL foreign key | ✅ | ✅ | ⏳ | ADR-0004. Migration `2d61942264a6`, verified reversible (upgrade → downgrade → upgrade). 50 tests (32 unit + 18 live-Postgres integration), 98% coverage, `mypy --strict` clean. The database rejects an unanchored fact — proven by test, not by convention. |
| 1.3b | Document dissection — the extractor that populates those fields from page text | ⏳ | ⏳ | ⏳ | Must locate every value in the source text; a value it cannot anchor is dropped, not stored. |
| 1.4 | Florida jurisdiction profile — document types and terminology behind the profile seam | ⏳ | ⏳ | ⏳ | CLAUDE.md §7. |
| 1.5 | Accuracy validation harness — synthetic gold-standard corpus, precision/recall per field, error taxonomy with hallucination as a release-blocking class | ⏳ | ⏳ | ⏳ | Synthetic documents only (§3). |

## Phase 2 — Timeline

| # | Portion | Built | Tested | Merged | Notes |
|---|---|---|---|---|---|
| 2.1 | Event extraction + date normalization — filed date vs. event date vs. alleged date kept distinct | ⏳ | ⏳ | ⏳ | |
| 2.2 | Timeline assembly — conflicting accounts render as two attributed claims, never merged | ⏳ | ⏳ | ⏳ | CLAUDE.md §2. |
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
