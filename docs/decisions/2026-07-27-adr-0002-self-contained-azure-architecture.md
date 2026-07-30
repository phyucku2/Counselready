# ADR-0002 — Self-contained Azure architecture and AI posture

**Date:** 2026-07-27
**Status:** Accepted
**Owner decision:** yes (hosting and AI-processing posture)

## Problem

CounselReady holds some of the most sensitive documents a person owns: custody
evaluations, abuse allegations, therapy and substance-use records, financial affidavits,
and children's identities. Two questions had to be answered before any code:

1. Where does the data live and get processed?
2. Where does AI inference happen — and what happens to document text when it gets
   there?

## Options considered

**A. Cloud LLM APIs under strict terms.** Fastest path to extraction quality. Document
text leaves the owner's infrastructure for a vendor's, governed by contract rather than
network boundary.

**B. Redact locally, then send to a cloud model.** Strips identifiers before egress.
Costs real accuracy on the features that depend on knowing who said what — party
attribution and language review are close to meaningless on redacted text.

**C. Self-hosted open models only.** Nothing leaves. Materially weaker extraction
quality on messy scanned filings, and a large infrastructure burden for a
single-developer product.

**D. Azure-hosted models inside the owner's tenant.** Inference runs on Azure-hosted
frontier models (Claude via Microsoft Foundry, or Azure OpenAI) under Azure's data
terms: customer content is not used to train models, the region is pinned, and traffic
can route over private networking rather than the public internet.

## Decision

**Option D — self-contained on Azure.** Hosting, storage, database, queues, and
inference all run inside the owner's Azure tenant.

- **Compute:** Azure Container Apps for the API and web frontend.
- **Documents:** Azure Blob Storage, private endpoint only, no public access,
  encryption at rest, per-tenant key separation.
- **Database:** Azure Database for PostgreSQL.
- **Jobs:** OCR, extraction, and AI analysis run as async background jobs, never in the
  request path (a multi-hundred-page case file is not a request-time workload).
- **Secrets:** Azure Key Vault. Never in the repo, never in argv.
- **AI:** Azure-hosted frontier models. No training on customer content, region pinned,
  private networking where available.

**Every egress seam ships OFF by default and config-gated.** Error reporting, analytics,
and any third-party API activate only on an explicit operator action, POST a scrubbed
payload, and fail safe — a reporter error never breaks a request.

**No Vercel and no public preview deployments.** Preview URLs are a liability for a
product holding court files, not a convenience. Where per-PR previews are wanted later,
they run as authenticated Azure Container Apps revisions.

## Why not the alternatives

Option A's protection is contractual only; for this data, a tenant boundary is worth
paying for. Option B guts the features that make the product distinct. Option C trades
away the extraction quality that determines whether the product is trustworthy at all —
and on scanned, stamped, hand-annotated family court filings, extraction quality is the
whole game. Option D gets frontier-model quality with the data staying inside a boundary
the owner controls, which is also the simplest privacy story to state to a user or an
attorney: *your documents stay in our Azure tenant and are never used to train anyone's
model.*

## Consequences

- The privacy claim is auditable, and it is short enough to put in front of a user
  without a legal appendix.
- Model choice is constrained to what Azure hosts. Acceptable: Foundry carries frontier
  models, and extraction/timeline work does not need a model unavailable there.
- Infrastructure cost is higher than a serverless-frontend + vendor-API setup.
- **Every datum's provenance is preserved end to end** — OCR confidence per page,
  extraction model and version, and the source passage offset travel with the record, so
  the ADR-0001 citation guarantee is enforceable at the storage layer rather than
  reconstructed at render time.
- Cost control needs attention: a large case file is a large OCR + inference bill, so
  per-account job quotas belong in Phase 1, not later.

## Open

- Azure subscription, resource-group layout, and any production secret are **owner-side**
  and must not be collected until the owner initiates it.
- Whether OCR uses Azure Document Intelligence or a self-hosted engine is a Phase-1
  design question; both satisfy this ADR.

## References

- [`ADR-0001`](2026-07-27-adr-0001-product-scope-and-non-advice-posture.md) — the citation guarantee this architecture must enforce
- CLAUDE.md §3 (sensitive data posture), §4 (self-contained on Azure)
