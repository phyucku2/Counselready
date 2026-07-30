# ADR-0003 — Backend stack

**Date:** 2026-07-27
**Status:** Accepted
**Owner decision:** no (engineering choice, recorded for override)

## Problem

CounselReady needs a backend that runs on Azure Container Apps (ADR-0002), handles
long-running OCR and AI extraction as background jobs, enforces a citation guarantee at
the storage layer, and holds a strict quality bar from the first commit.

## Decision

**Python 3.12 + FastAPI + SQLAlchemy 2 (async) + Alembic + PostgreSQL.**

- **FastAPI** — async by default, which matters because nearly every request either
  waits on the database or enqueues a job; OpenAPI 3.1 generated from the code, so the
  API contract can't drift from the implementation.
- **SQLAlchemy 2 async + Alembic** — the citation guarantee (ADR-0001 §2) is a schema
  invariant, so migrations are first-class from the start rather than retrofitted.
- **PostgreSQL** (Azure Database for PostgreSQL) — relational integrity for the
  case/document/citation graph, JSONB where extraction payloads are genuinely
  schemaless, and full-text search available without adding a second datastore.
- **Quality gate:** ruff (lint + format), mypy `--strict`, pytest with ≥85% coverage on
  business logic, a secret scan, and a dependency license scan. All blocking in CI.

## Why not the alternatives

**Node/TypeScript** would share a language with the frontend, but Python's document
ecosystem is the deciding factor: OCR, PDF parsing, and the Azure Document Intelligence
and AI SDKs are all first-class in Python, and document processing is the core of this
product rather than an accessory to it.

**Django** brings an admin and batteries included, but its sync-first ORM fights the
job-heavy workload, and the admin is a liability for a product where every read of case
material must be audited and least-privilege — a general-purpose admin panel is the
opposite of that.

## Consequences

- Two languages in the repo (Python backend, TypeScript frontend). Accepted; the
  boundary is a generated OpenAPI schema.
- Background jobs need a worker and a queue. Deferred to its own ADR when the OCR
  pipeline lands, so the skeleton doesn't carry infrastructure it isn't using yet.
- `mypy --strict` from commit one means no untyped escape hatches accumulate.

## Notes on structure

- Deployment-context fail-fast guards live in the **application lifespan**, not in
  `Settings` construction. A config-time validator fires in every context that imports
  config — including Alembic — which breaks migrations that legitimately hold a database
  URL without serving-only secrets.
- Request logging is the outermost middleware and resolves the request id **before**
  calling downstream, so an unhandled exception still logs one correlated line.
- Logs carry route templates and fixed vocabularies only. Never a raw path, never
  document text, never a query or body (CLAUDE.md §3).
