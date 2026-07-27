# Brainstorm — Family court document analysis SaaS (founding document)

> **Provenance note.** This brainstorm was authored on 2026-07-27 during a working
> session in the owner's other repository, before CounselReady had a repo of its own —
> which is why it applies that project's lens list and refers to its client (BioMech
> Health) and its rules by section number. It is preserved verbatim as the founding
> record of how this product was scoped and what alternatives were weighed. The
> decisions it reaches are carried forward into
> [`ADR-0001`](../decisions/2026-07-27-adr-0001-product-scope-and-non-advice-posture.md)
> and [`ADR-0002`](../decisions/2026-07-27-adr-0002-self-contained-azure-architecture.md);
> the canonical lens list for this repo now lives in `CLAUDE.md` §8.

**Date:** 2026-07-27
**Trigger:** Owner direction: "We are building a SaaS that reads family court documents.
Our main goal is to dissect, report potential issues, create timelines of events, and
review language of each party."
**Protocol:** CLAUDE.md §6 — all 17 canonical lenses applied, plus topic-specific lenses
added at the end. Lenses with little to add say so explicitly rather than being dropped.

## What is being proposed

A SaaS product that ingests family court documents (petitions, motions, declarations,
custody evaluations, orders, correspondence entered into the record) and produces four
outputs:

1. **Dissection** — structured extraction: parties, counsel, case numbers, claims,
   requested relief, exhibits, referenced events.
2. **Issue spotting** — flagging *potential* issues for a human to review
   (inconsistencies between filings, missing responses, contradicted dates,
   unaddressed allegations).
3. **Timelines** — a chronology of events assembled across documents, with every entry
   linked to the source passage it came from.
4. **Language review** — analysis of each party's written language (tone, escalation,
   inflammatory phrasing, contradictions between a party's own statements).

This is a new product, not a feature of the neuropathy app. That fact drives the
biggest forced decisions (see the final section).

---

## Canonical lenses

### 1. Physician (neurology / endocrinology / podiatry / primary care)

Family court files routinely embed clinical material: custody evaluations by forensic
psychologists, substance-use test results, therapy records, disability claims affecting
parenting-capacity arguments. Two constraints follow. The product must extract and
timeline these as *documents and dates*, never interpret them clinically ("the
evaluation dated X was filed on Y" is fine; "the parent shows signs of Z" is not). And
clinical records inside a court file are among the most damaging data to leak, so they
raise the data-handling bar for the whole corpus, not just for pages tagged as medical.

### 2. Patient (here: the litigant parties)

The people in these documents are going through one of the worst periods of their
lives. Product implications: outputs must be calm and factual, never gamified or
score-like ("your opponent's aggression score: 87" would be harmful and legally
reckless); the issue-spotting output should be framed as "questions to review," not
verdicts; and the product must assume both parties may eventually see any output,
because litigation discovery can reach it. A separate risk: one party using the tool
against the other is the core use case, so the tool must not manufacture ammunition —
every flagged issue must cite the exact source text so a human can judge it.

### 3. BioMech Health (client / licensee)

Nothing connects this product to BioMech Health's brief. Their license (ADR-0001)
covers the neuropathy app. Whether this new product is (a) a BioMech request, (b) a
second product for a different client, or (c) owner-initiated is unknown and changes
the IP and disclosure posture. This lens has nothing further to add until the owner
answers that — recorded as forced decision D2.

### 4. Apple developer (iOS)

The likely v1 is a web SaaS, so iOS is not on the v1 path. If a mobile client ships
later: document capture (camera scan of paper filings) is the natural mobile feature;
App Store review is stricter for apps touching legal services, and the privacy
nutrition label would have to declare collection of highly sensitive data. The Wave-2
lesson from this repo generalizes: a wrapped web app is the cheap staged path, and
account/data deletion must exist before any store submission.

### 5. Android developer

Same posture as iOS: not on the v1 path; camera-scan intake is the mobile value-add;
Play's Data Safety form and mandatory deletion flow apply. Nothing else new.

### 6. HIPAA / privacy

The company would generally *not* be a HIPAA covered entity or business associate here
— court documents are not received from a covered entity for treatment/payment/ops.
But that is a reason for more care, not less: the data (abuse allegations, minors'
identities, mental-health and substance-use records, financial affidavits, sealed
material) is as sensitive as PHI with fewer default legal guardrails. Design to the
PHI-grade posture this repo already practices (§5): per-tenant isolation, audit logging
on every read/write, encryption at rest and in transit, no document content in logs or
metrics, deletion that actually destroys. Add family-court-specific rules: some
jurisdictions seal family files or bar republication of juvenile records — ingesting a
document the user was not entitled to hold is a real scenario, so terms and intake
design must address it. State privacy laws (CCPA/CPRA and successors) apply to the
litigant data regardless of HIPAA.

### 7. SOC 2 / security

Law-firm customers will require SOC 2 Type II and security questionnaires before
uploading client files; this is a sales blocker, not a nice-to-have, so evidence habits
start on day one. Specific threats worth designing for: an opposing party gaining
account access (credential stuffing against an emotionally-targeted user base — require
MFA); insider access to inflammatory content (least privilege, access logging, no
support-staff browsing of documents); and subpoenas directed at the SaaS itself
(retention policy and customer-notice policy decided up front). Attorney work product
uploaded alongside court filings must be segregable, because its confidentiality rules
differ from public-record filings.

### 8. Marketing

Positioning must never promise legal outcomes or advice. Viable framings: "document
organization and chronology for family law matters," "case-file review assistant for
attorneys." Channels: family-law bar sections, practice-management communities,
legal-tech directories; for a pro se tier (if the owner chooses one, D3), courthouse
self-help centers and legal-aid organizations. Testimonials are constrained: family
court stories are confidential and painful, so case studies must be composite or
anonymized. The competitor set (general legal-doc AI: summarizers, e-discovery tools)
is crowded; the family-law-specific timeline + cross-party language analysis is the
differentiator worth naming.

### 9. Legal & regulatory (incl. FDA SaMD, licensing, patents)

FDA is not implicated — this is not a medical device. The dominant regulatory risk is
**unauthorized practice of law (UPL)**, which is state-by-state: software that flags
"potential issues" for a *lawyer* is a tool; the same output handed to a *pro se
litigant* with any suggestion of what to do about it approaches legal advice. This is
the product's equivalent of the neuropathy app's non-diagnostic framing, and the same
discipline applies: wording of outputs is an owner-level decision with counsel
(forced decision D3). Second-order risks: courts sanctioning AI-fabricated citations
means every generated statement must be grounded in a quoted source passage; several
courts now require disclosure of AI assistance in filings, which affects how outputs
may be used; "review language of each party" output about a named individual carries
defamation exposure if presented as fact rather than as quoted text plus neutral
observation. On IP: the timeline-assembly and cross-document contradiction methods may
be worth a note for counsel, per §2 — one line in the eventual ADR is enough.

### 10. Accessibility

WCAG 2.2 AA as in this repo's standards. Additional user realities in family court:
many self-represented users, high stress, low legal literacy, and significant
ESL representation. Plain-language output (reading level checked), glossary for legal
terms in extracted text, and full keyboard/screen-reader support for the timeline UI
(a timeline visualization is exactly the kind of component that ships inaccessible by
default — it needs a list/table equivalent view).

### 11. Payer / reimbursement

No CMS or insurance pathway exists for legal document analysis; the canonical lens has
nothing to add in its own terms. The nearest analogs, recorded for completeness: legal
insurance / prepaid legal plans (a possible B2B2C channel), legal-aid funding (grants
could subsidize a pro se tier), and court e-filing vendor partnerships. None affects
v1 design.

### 12. Data science / ML

The hard problems, in order: (a) **OCR quality** — family court files are scanned,
stamped, handwritten-annotated, and skewed; extraction quality gates everything
downstream, and a per-page confidence score must propagate to outputs. (b) **Grounded
extraction** — every event, issue, and language observation must carry a citation to
document + page + passage; an output the system cannot cite does not ship (the direct
analog of this repo's "a datum without provenance is a bug"). (c) **Timeline
assembly** — date normalization (filed date vs. event date vs. alleged date),
conflicting accounts of the same event must render as two attributed claims, never
silently merged. (d) **Language review is the highest-bias-risk feature**: tone
classifiers are known to score dialects and non-native English as more hostile;
shipping this without a bias evaluation would be irresponsible and commercially
dangerous. It should be last in the build order, evidence-quoted rather than
score-based, and evaluated per D4. All AI/OCR runs as async jobs off the request path,
per the existing performance standards.

### 13. Clinical research / validation (here: accuracy validation)

The credibility of the product is an empirical claim: "the timeline is right" and "the
flagged issues are real." Build a gold-standard corpus (synthetic + purchased/public
redacted filings), measure extraction precision/recall per field, timeline-event recall,
and issue-flag precision against attorney annotation, and publish the method to
customers. Define an error taxonomy (missed event, wrong date, wrong attribution,
hallucinated content) with hallucination treated as a release-blocking defect class.
This is the same "research-grade" instinct as ADR-0006, transplanted.

### 14. Caregiver / family

Children are the subjects of these files but never the users; their data deserves the
strictest handling (redaction of minors' identifiers in outputs by default, no
child-focused analytics). Extended-family litigants (grandparent visitation, kinship
guardianship) are real users with the same needs. Domestic-violence survivors are a
critical sub-population: account takeover by an abusive ex-partner is a life-safety
issue, which reinforces mandatory MFA, login alerting, and no shared-household
account patterns.

### 15. Agile (operating model, phasing, backlog impact)

This product should not enter the neuropathy roadmap board; it needs its own board and
its own repo (D1). Sensible phasing by risk: **Phase 1** ingest + OCR + document
dissection with citations; **Phase 2** timeline assembly; **Phase 3** issue spotting
(cross-document inconsistencies); **Phase 4** language review, last, because it
carries the bias and defamation risk and needs the validation apparatus from
Phase 1–3 first. One portion per PR, adversarial review, DoD — the working agreements
transfer unchanged.

### 16. DevOps (CI/CD, infra, release, observability impact)

The habits in `docs/lessons.md` transfer almost verbatim: document content is the new
PHI for observability purposes (route templates and fixed vocabularies in metrics,
never filenames or content; error events built from a whitelist); uploads bounded
before materializing; parsing off the event loop; egress seams (OCR/LLM vendors) ship
off-by-default behind config with a data-processing agreement per vendor. New
infra concerns: large-file object storage with per-tenant encryption keys, a job queue
sized for multi-hundred-page OCR runs, and storage-cost-aware retention.

### 17. Reimbursement (Medicare/Medicaid)

Not applicable: no data stream in this product maps to RTM/RPM/CCM/PCM/DMHT or any
CMS billing pathway, and no capture requirement follows. Stated explicitly per the
protocol rather than skipped. (Adjacent funding channels are covered under lens 11.)

---

## Added lenses (topic-specific, per §6 rules of engagement)

### 18. Family-law attorney (primary professional user)

Wants hours saved on file review, a chronology they can drop into a declaration, and
confidence they missed nothing in the opposing party's filings. Non-negotiables:
citations to the record for every generated statement (they are the one sanctioned if
it's wrong), export to formats courts and practice-management tools accept, and clear
boundaries between the public-record file and their privileged notes. They will not
tolerate a tool that invents; a single hallucinated event in a filed declaration ends
the customer relationship and possibly their case.

### 19. Self-represented (pro se) litigant

The largest population in family court — a majority of family cases involve at least
one unrepresented party. Serving them is the largest social impact and the largest UPL
risk simultaneously. If the owner enables this tier (D3), the product ships
organization and chronology only — no issue spotting, no "what to do" — with prominent
non-advice framing and referrals to legal-aid resources.

### 20. Judge / court administration

Courts are not v1 users, but their rules shape the product: AI-assistance disclosure
requirements, formatting rules for chronologies attached to filings, and local rules on
republishing sealed material. A product that emits court-rule-compliant exports per
jurisdiction is more valuable and safer; a jurisdiction-rules layer belongs in the
backlog early.

### 21. Guardian ad litem / child advocate / DV advocate

GALs review entire case files under time pressure and are a natural professional user
segment with the same needs as lens 18 plus the child-data defaults from lens 14. DV
advocates add a design demand: outputs that neutrally document a documented pattern
(dates and quotes of alleged incidents across filings) can help a survivor's case, but
the same feature misused by an abuser to surveil or harass drives the safety features
in lenses 7 and 14. Threat-model both directions explicitly.

### 22. Legal ethics & professional responsibility

Distinct from lens 9 (which covers the company's exposure): the *attorney user's*
duties. Model Rule 1.6 confidentiality means the attorney needs vendor terms that let
them upload client material at all (no training on customer data, subprocessor
transparency, breach notice); Rule 1.1 technological competence means the product must
make its limits legible (confidence indicators, "verify against the record" framing);
supervision duties (5.3) mean audit trails of what the tool produced vs. what the
human edited. These become contract and product requirements, not just marketing.

Per §6, these four lenses should be added to the canonical list — but the canonical
list lives in the CLAUDE.md of whichever repo this product lands in (D1), and editing
CLAUDE.md is owner-gated (§8). Deferred to the owner with D1.

---

## Decisions this brainstorm forces (owner-level unless noted)

- **D1 — Where does this product live?** It is not the neuropathy app. Recommendation:
  a separate private repo with its own CLAUDE.md (same governance skeleton: clean-room,
  ADRs, DoD, lenses list seeded with 1–22 as reinterpreted here), so the two products'
  IP, clients, and roadmaps never entangle. Owner call because it creates a new
  repository and governance surface.
- **D2 — Whose product is it?** Is this a BioMech Health request, a new client, or
  owner-initiated? Determines whether an ADR-0001-style ownership/licensing agreement
  must be papered before any disclosure, and where inbound requirements get filed.
- **D3 — Who is the customer for v1: attorneys only, or also pro se litigants?** This
  is the UPL fork. Recommendation: attorneys/GALs only for v1; a pro se tier only
  after counsel signs off on scope and framing. Output wording is owner + counsel, the
  same way clinical wording is in the neuropathy app.
- **D4 — Does "language review" ship in v1?** It is the stated goal with the highest
  bias, defamation, and misuse risk. Recommendation: build it last (Phase 4), quote-
  based rather than score-based, gated on a documented bias evaluation. Owner call
  because it is a product-scope and risk decision.
- **D5 — Data intake boundaries.** Whether the product accepts sealed/juvenile
  material, how it verifies the user's entitlement to the documents they upload, and
  the retention/deletion policy. Needs counsel input; blocks the terms of service.
- **Engineering decisions that follow without owner input** (become ADRs in the new
  repo once D1 is settled): grounded-citation architecture as a hard invariant;
  async-job pipeline for OCR/AI; per-tenant isolation and encryption; SOC 2 evidence
  habits from day one; phasing per lens 15.

## Immediate next step

Nothing gets built until D1–D3 are answered — building a second product inside this
repo, or building for an unknown client, would violate §8 (scope) and §3
(client/disclosure posture) respectively. The concrete ask to the owner is those three
answers; D4 and D5 can follow during Phase-1 design.

---

## Addendum — owner decisions (2026-07-27, same day)

The owner answered the forced decisions in session:

- **D1 — Separate repo: YES.** The product gets its own repository (name pending, see
  naming below) with its own CLAUDE.md governance seeded from this brainstorm's lenses.
- **D2 — Ownership: owner-initiated, completely new.** No BioMech Health involvement.
  Distribution: app stores plus the owner's personal use. No third-party licensing to
  paper before build.
- **D3 — v1 customer: the owner's personal use first; attorney demand unproven.**
  Market research commissioned (running in parallel) on whether family-law attorneys
  would adopt or recommend it. The chosen positioning reduces UPL exposure materially:
  the product helps a *represented* litigant arrive at meetings with their attorney
  prepared and organized — it feeds the attorney relationship rather than substituting
  for it. Pro se advice features remain out of scope.
- **Platforms:** mobile apps (iOS + Android) plus a web app, one backend.
- **Jurisdiction:** Florida first; other states later as jurisdiction profiles.
- **AI + hosting posture: self-contained on Azure.** Inference via Azure-hosted models
  (Claude through Microsoft Foundry, or Azure OpenAI) inside the tenant boundary —
  no training on customer data, region-pinned, private networking. All egress
  (OCR/AI/error reporting/analytics) stays in-tenant or ships off-by-default. No
  Vercel: no publicly-reachable preview deployments for a product holding court files.
- **First step: market research and repo scaffolding in parallel.**
- **Naming:** direction chosen — the name should evoke being better prepared and
  organized for meeting with your attorney. Shortlist under trademark/collision check:
  CaseReady, CaseBinder, PrepMyCase, DocketReady, CounselPrep, MeetPrepared.

Remaining open: D4 (language-review timing) and D5 (intake boundaries/retention) —
deferred into Phase-1 design in the new repo, per the original plan.
