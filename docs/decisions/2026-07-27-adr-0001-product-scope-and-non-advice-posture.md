# ADR-0001 — Product scope, positioning, and the non-advice posture

**Date:** 2026-07-27
**Status:** Accepted
**Owner decision:** yes (scope, positioning, and customer segment are owner-level)

## Problem

CounselReady reads family court documents and produces dissection, issue flags,
timelines, and language analysis. Every one of those outputs can be framed either as
*organizing information* or as *telling someone what their case means*. The second
framing is unauthorized practice of law, invites FTC advertising liability, and — for
the language-analysis feature — defamation exposure. The product needs one line drawn
once, at the start, that every later feature is measured against.

We also had to choose which customer to build for first: family-law attorneys (a
professional tool) or litigants (a consumer app).

## Options considered

**A. Attorney-first professional tool.** Sell to family-law firms as a case-file
analysis product. Lowest UPL risk (the buyer is a lawyer). But the segment is filling
up fast — Paxton, NexLaw, StrongSuit, and Thomson Reuters CoCounsel all now market
family-law document analysis and chronology extraction to firms — and it requires a
sales motion the owner doesn't have.

**B. Pro se litigant tool.** Largest population: 60–90% of family cases have at least
one self-represented party. Also the largest UPL exposure, in a state (Florida) that
enforces UPL aggressively, for a product whose whole value is telling someone what's in
their case. The DoNotPay FTC order ($193,000, January 2025) shows where that ends.

**C. Represented-litigant tool, attorney as channel.** Build for the person who *has* a
lawyer and needs to arrive at meetings organized. Market research found no product doing
this: the closest consumer analogs (CourtCase's custody organizer, Courtroom5) work from
raw evidence like texts and photos or general civil posture, not from dissecting formal
filings across a case file. Family-law firms already publicly advise clients to arrive
organized to save billable time, so attorneys are a referral channel rather than a
gatekeeper, and the framing itself constrains the product away from advice.

## Decision

**Option C.** CounselReady is built for a litigant who has counsel, and its promise is
"walk into your attorney meeting prepared." The owner's own Florida case is the first
real use.

The **non-advice line** (CLAUDE.md §1) is the governing constraint:

- The product **organizes, extracts, and surfaces**. It does not advise, recommend
  action, predict outcomes, or interpret legal meaning.
- Every output is **grounded in a citation** to the source document, page, and passage
  (ADR-0002 covers how). The product analyzes what the user supplies; it never generates
  legal authority from model knowledge.
- Marketing and app-store copy never state or imply the app does a lawyer's job.
- Pro se-specific features stay out of scope until counsel clears them. This is a
  deferral, not a permanent exclusion — it is where the largest market is, and revisiting
  it is a legitimate future decision with counsel's input.

**Build order, sequenced by risk:**

1. **Phase 1** — ingest + OCR + document dissection with citations.
2. **Phase 2** — timeline assembly across the case file.
3. **Phase 3** — issue spotting (cross-filing inconsistencies, unanswered requests).
4. **Phase 4** — language review, **last**. It carries the highest bias risk (tone
   classifiers are known to score dialects and non-native English as more hostile) and
   the only real defamation exposure. It ships quote-based rather than score-based, and
   only after a documented bias evaluation. No "aggression scores" or any gamified
   rendering of a named person's character.

**Platforms:** iOS + Android apps and a web app over one backend. Document-heavy review
needs a large screen; capture and reading suit mobile.

**Jurisdiction:** Florida first, behind a jurisdiction profile from day one (CLAUDE.md §7).

## Why this is the right line

The FTC's DoNotPay order punished the claim ("performs like a lawyer"), not the
software's existence. A product that shows a user what their own documents say, with a
citation to each statement, is doing what a well-organized binder does. The moment it
says what the user should *do*, it is something else. Keeping that boundary in the
product's core promise — rather than in a disclaimer bolted on later — is what makes it
defensible.

## Consequences

- Feature requests get tested against §1 before they get designed. "Flag potential
  issues" survives ("these two filings state different dates"); "tell me if I have a
  case" does not.
- Pricing follows the consumer reference class: co-parenting apps sustain $7–32/month
  per parent, so ~$19–29/month or a one-time case-analysis package is the target band.
  A later professional tier benchmarks at $75–150/seat/month.
- An attorney/GAL review view is the natural fast-follow, and the same grounded-citation
  architecture serves it — attorneys are the users least tolerant of an uncited claim,
  because they are the ones sanctioned when it's wrong.
- Deferring pro se features costs the larger market. Recorded deliberately; revisit with
  counsel.

## Open, deferred to Phase-1 design

- **Intake boundaries:** whether the product accepts sealed or juvenile material, how a
  user's entitlement to uploaded documents is established, and the retention/deletion
  policy. Needs counsel; blocks the terms of service.
- **Trademark clearance** on the CounselReady name before any app-store submission. A
  web search found no direct collision (nearest neighbor: LexisNexis CounselLink,
  enterprise legal-spend software), which is not a substitute for a counsel-run search.

## References

- [`docs/brainstorm/2026-07-27-family-court-document-analysis-saas.md`](../brainstorm/2026-07-27-family-court-document-analysis-saas.md) — the founding multi-lens brainstorm and owner decisions
- [`docs/brainstorm/2026-07-27-family-court-market-research.md`](../brainstorm/2026-07-27-family-court-market-research.md) — competitive landscape, sizing, pricing, and regulatory cautions with sources
