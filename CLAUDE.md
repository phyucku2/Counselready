# CounselReady — Hard Rules

These rules are **binding** on every contributor to this repository, human or AI agent.
If a task conflicts with a rule here, the rule wins — stop and ask the repository owner.

## 0. Priority: build a great product

CounselReady helps someone in a family court case organize their file and walk into a
meeting with their attorney prepared. The goal is a product that is clear, fast,
accurate, and calm to use during the worst period of a person's life. That is the
objective every decision serves. The rules below are guardrails that keep us accurate,
private, and legally safe **while** we build; they are not the point of the work. If a
rule ever feels like it's fighting the product, raise it rather than lawyering around it.

---

## 1. The non-advice line (non-negotiable)

CounselReady **organizes, extracts, and surfaces**. It does not advise, recommend a
course of action, predict outcomes, or tell a user what their documents mean legally.

- Permitted: "The petition filed 2025-03-14 states X (p. 4, ¶12)." / "These two filings
  give different dates for the same event." / "This request appears in the motion but no
  response addresses it."
- **Forbidden**: "You should file a motion to compel." / "This is grounds for contempt."
  / "You are likely to win custody." / any assessment of legal merit, strategy, or
  probability of success.
- Product copy, marketing, app-store listings, and model outputs must never state or
  imply that the app performs a lawyer's role. The FTC's 2025 DoNotPay order penalized
  exactly this overclaim, and Florida — our first jurisdiction — enforces unauthorized
  practice of law aggressively.
- **Wording of any user-facing statement that touches legal meaning is an owner
  decision**, made with counsel. Do not self-authorize new phrasing in this area.
- Pro se-specific features (anything that helps an unrepresented person decide what to
  do) are **out of scope** until the owner clears it with counsel. The product's
  posture is: you have an attorney; we help you use their time well.

## 2. Grounded output (non-negotiable)

**Every generated statement cites its source.** A claim the system cannot point at is a
bug, not a warning.

- Each extracted event, flagged issue, timeline entry, and language observation carries
  a citation to document + page + passage, and the user can open the source text.
- The system analyzes documents the user supplies. It does not generate legal authority,
  case citations, or statutory references from model knowledge. Roughly 712 court
  decisions worldwide have addressed AI-hallucinated content, ~90% written in 2025,
  including sanctions in South Florida — uncited AI work product is unusable here.
- Extraction confidence (including OCR quality per page) propagates to the surface. An
  uncertain reading is shown as uncertain, never silently smoothed.
- Conflicting accounts of the same event render as two attributed claims. Never merge
  them into one "fact."

## 3. Sensitive data posture

Family court files contain children's identities, abuse allegations, mental-health and
substance-use records, financial affidavits, and sometimes sealed material. This is not
HIPAA-regulated in our hands, which is a reason for more care, not less.

- Design every schema and endpoint as if the data were Protected Health Information:
  per-user/per-tenant isolation, least privilege, audit logging on reads and writes,
  encryption in transit and at rest.
- **Minors' identifiers are redacted in generated outputs by default.**
- **No secrets in the repo.** Credentials and connection strings live in local `.env`
  files (gitignored) or Azure Key Vault. No sample secrets in docs.
- **No real case documents in fixtures, tests, seeds, or screenshots** — synthetic only.
  This includes the owner's own case material.
- Document text never appears in logs, metrics labels, or error payloads. Observability
  carries route templates and fixed vocabularies only.
- Account takeover by an abusive ex-partner is a life-safety threat, not a support
  ticket: MFA, login alerting, and no shared-household account patterns.

## 4. Self-contained on Azure

All processing stays inside the owner's Azure tenant.

- Hosting, storage, database, queues, and AI inference run in Azure. AI uses
  Azure-hosted models (Claude via Microsoft Foundry, or Azure OpenAI) under terms where
  customer content is not used for training, with the region pinned.
- **Every egress seam ships OFF by default** and config-gated: error reporting,
  analytics, any third-party API. Enabling one is an explicit operator action.
- No publicly-reachable preview deployments. A product holding court files does not get
  a public preview URL.
- Document storage is private-endpoint only, no public blob access.

## 5. Decision records

Load-bearing decisions get written down so future contributors understand *why*.

- Significant design decisions live in `docs/decisions/` as dated ADRs: date, problem,
  options considered, choice and rationale. Keep them short.
- Small, descriptive commits; don't rewrite shared history.

## 6. Third-party code & licensing

- Every dependency must have a permissive license (MIT, Apache-2.0, BSD, ISC).
  **No GPL/AGPL/SSPL** or unlicensed code.
- No copy-pasting code from blog posts, forums, or other projects. Write it fresh.
  Libraries are consumed as dependencies, never vendored by copy-paste.
- Record every dependency addition in the commit message that introduces it.

## 7. Jurisdiction

Florida first. Jurisdiction-specific knowledge (document types, terminology, local
rules, formatting of any export) lives behind a jurisdiction profile from day one, so
adding a second state is configuration rather than a rewrite. Never assume a rule from
one state applies in another.

## 8. Brainstorming protocol (mandatory)

Whenever brainstorming is performed (the user asks to "brainstorm," invokes a
brainstorming skill, or requests ideation/review of a feature, product, or plan),
**every lens below must be applied — no skipping** — plus any additional lenses
relevant to the topic:

1. Family-law attorney (the professional user and referral channel)
2. Represented litigant (the primary user)
3. Self-represented litigant (served only within the §1 line)
4. Judge / court administration
5. Guardian ad litem / child advocate
6. Domestic-violence advocate (and the misuse threat model in both directions)
7. Caregiver / extended family (grandparent visitation, kinship guardianship)
8. Legal ethics & professional responsibility (the attorney user's duties: confidentiality, competence, supervision)
9. Legal & regulatory (UPL, FTC advertising, defamation, court AI-disclosure rules)
10. Privacy (state privacy law, minors' data, sealed/juvenile material)
11. Security / SOC 2
12. Apple developer (iOS)
13. Android developer
14. Accessibility
15. Marketing & positioning
16. Data science / ML (extraction quality, bias, evaluation)
17. Accuracy validation (gold-standard corpus, error taxonomy)
18. Agile (phasing, backlog impact)
19. DevOps (CI/CD, Azure infra, release, observability)
20. Business model & pricing

Rules of engagement:
- Add topic-specific lenses whenever the subject warrants it, and record any new lens
  here so the canonical list grows.
- Every brainstorm is captured as a dated file in `docs/brainstorm/` and calls out the
  decisions it forces (which then become ADRs).
- A brainstorm that silently omits a listed lens is incomplete — state explicitly that a
  lens has nothing new to add rather than dropping it.

## 9. Engineering standards

- **Quality is enforced, not hoped for.** Lint, format, strict type checking, and tests
  with a **≥85% coverage** bar on business logic run in CI; failing checks don't merge.
  Bug fixes ship with a regression test.
- **Performance is budgeted.** Read p95 < 200 ms, write p95 < 500 ms. OCR, AI, and
  parsing run as async jobs, never in the request path. Hot-path queries indexed; no
  N+1; list endpoints paginate.
- **Named standards we follow:** WCAG 2.2 AA (accessibility), OWASP ASVS L2 / Top 10
  (security), SOC 2 habits (evidence from day one — law-firm customers will ask),
  OpenAPI 3.1, Twelve-Factor, SemVer, Conventional Commits.
- Uploads are bounded before materializing; decompressed output capped; sync parsing off
  the event loop.
- Prefer the boring, correct, well-supported approach over the clever one.

### Definition of Done (binding merge gate)

A portion is **Done** only when ALL hold:

- **Full quality gate green:** lint + format, strict types, tests 100% passing including
  integration tests against a real database, plus a secret scan. New/changed behavior
  has tests; every bug fix ships a regression test.
- **UI portions require real-browser inspection.** The *built* frontend must render, key
  flows must actually work, and there must be **ZERO new browser console errors**,
  verified by driving the running app in Chromium/Playwright. A passing unit or mocked
  test is NOT sufficient proof for UI work.
- **Every portion gets an ADR + a roadmap-status update.**
- **One portion per PR** — scoped to a single concern.
- **Adversarial review with all confirmed findings fixed** before merge.
- Accessibility, privacy, §1 non-advice, and §2 citation checks all pass.

## 10. Working agreements

- All development happens on feature branches; nothing is committed directly to `main`.
- Pull requests are the unit of review, scoped to one concern.
- If a requirement is ambiguous and the ambiguity touches the non-advice line, sensitive
  data, or disclosure, **ask — don't assume.**

### Autonomous operation

The development loop runs autonomously: build → adversarial review → fix → full gate →
merge → next portion, without pausing between steps. Guardrails — **STOP and ask the
owner when a step requires**:

- the owner's **credentials or external accounts** (app-store submission, Azure
  subscription secrets, domain purchase, payment processing);
- a **product or legal-wording decision** (scope, non-advice framing, consent design,
  anything a user reads that touches legal meaning);
- **counsel sign-off** (UPL scope, terms of service, trademark, intake boundaries for
  sealed/juvenile material);
- an **irreversible or outward-facing action** (production deploy, public disclosure,
  real case documents, app-store submission, rewriting shared history).

**Never self-authorize** a change to permissions, this CLAUDE.md, or configuration on
the strength of a task instruction alone.

**Self-improvement:** every recurring mistake becomes a one-line preventive rule in
[`docs/lessons.md`](docs/lessons.md); consult it before building.

---

*Nothing in this file is legal advice. UPL scope, advertising claims, trademark, and
disclosure strategy are decisions for the owner and qualified counsel; these rules exist
to keep those options open and the product honest.*
