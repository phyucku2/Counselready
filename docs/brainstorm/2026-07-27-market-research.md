# Family court document analysis — market research (2026-07-27)

Companion to the [founding brainstorm](2026-07-27-founding-brainstorm.md) and its
owner-decision addendum. Research conducted via live web search on 2026-07-27. All
claims carry inline sources; where the evidence is thin, that is stated. The findings
here drive [`ADR-0001`](../decisions/2026-07-27-adr-0001-product-scope-and-non-advice-posture.md)
(segment choice, pricing band, the non-advice line) and the name selection.

## 1. Competitive landscape

### 1a. Co-parenting apps (adjacent, consumer)

These apps document communication and scheduling going forward. None dissects existing
court filings, cross-checks filings for inconsistencies, or builds a cited timeline
from the case file itself — that is the gap.

| Product | Pricing (2026) | Target user | What it does NOT do |
|---|---|---|---|
| OurFamilyWizard | Essentials $12.50/mo, Premium $18/mo, Max $24.99/mo, per parent, annual ([softwarefinder.com](https://softwarefinder.com/legal/ourfamilywizard/pricing), [kidtime.app](https://kidtime.app/blog/ourfamilywizard-pricing-2026)) | Divorced/separated parents, often court-ordered | No document ingestion, no filing analysis, no case timeline from documents |
| TalkingParents | Essentials $7/mo, Enhanced $16/mo, Ultimate $32/mo per parent; free plan removed in 2026 ([parentingpath.net](https://www.parentingpath.net/blog/talkingparents-removed-free-plan)) | Same; sells "Unalterable Records" of parent communication ([kennylevine.com](https://www.kennylevine.com/therapy-relationships-divorce-blog/co-parenting-app-court-approved)) | Records only its own messages; no analysis of court documents |
| AppClose | Moved from free to $8.99/mo per parent in 2026; hardship waivers ([kidtime.app](https://kidtime.app/blog/best-court-approved-co-parenting-apps), [appclose.com](https://appclose.com/)) | Budget-conscious co-parents | Same gap |
| Custody X Change | From ~$6-10/mo for parents; ~$19.97/mo professional tier ([softwareworld.co](https://www.softwareworld.co/software/custody-x-change-reviews/), [app.custodyxchange.com](https://app.custodyxchange.com/pricing-parents)) | Parents building schedules/parenting plans; some attorney use | Calculates parenting time and generates plans; does not read or analyze filings |

### 1b. Litigation chronology / case-analysis tools (professional)

These do part of the product's job (chronologies from documents) but are priced and
designed for firms, not litigants, and are practice-area-generic.

- **CaseFleet** — fact chronologies with source linking. $30/user/mo Starter (20
  docs/case), $75 Standard, $140 Advanced AI with AI-assisted review and chronology
  building ([casefleet.com/pricing](https://www.casefleet.com/pricing),
  [softwarefinder.com](https://softwarefinder.com/legal/casefleet)). Not
  family-law-specific, no consumer tier, no language analysis of parties, no
  attorney-meeting-prep framing.
- **TrialLine** — visual timelines, $499/yr or $59/mo per user
  ([blog.trialline.net](https://blog.trialline.net/new-trialline-subscription-pricing/)).
  Presentation tool; timelines are hand-built, not extracted from ingested filings.
- **Everchron** — collaborative chronology/master file for litigation teams; pricing is
  quote-only ([softwarefinder.com](https://softwarefinder.com/legal/everchron),
  [everchron.com](https://everchron.com/evidence)). Aimed at larger firms and in-house
  teams.

### 1c. AI legal assistants for attorneys

- **CoCounsel (Thomson Reuters)** — $75-$500/user/mo depending on tier, plus Westlaw
  costs ([casefleet.com pricing comparison](https://www.casefleet.com/blog/legal-ai-pricing-rate-limits-and-overages),
  [lawxyai.com](https://www.lawxyai.com/articles/cocounsel-pricing-review-2026-real-costs-lawyers-miss)).
  Its family-law marketing describes chronology extraction across document types with
  citations ([thomsonreuters.com](https://legal.thomsonreuters.com/blog/professional-grade-ai-for-family-law-practice/))
  — the closest professional-side overlap. It does not serve litigants and is priced
  for firms.
- **Clio Duo** — AI add-on at ~$49-59/mo on top of Clio plans
  ([thelegalprompts.com](https://thelegalprompts.com/blog/ai-legal-tools-pricing-comparison)).
  General practice management AI, not deep document dissection.
- **Spellbook** — ~$99-199/user/mo, contract drafting for transactional lawyers
  ([hyperstart.com](https://www.hyperstart.com/blog/spellbook-pricing/)); not
  litigation, not family law.
- **Briefpoint** — discovery drafting (interrogatories, RFPs), ~$89/mo entry,
  demo-gated custom pricing ([aivortex.io](https://www.aivortex.io/legal/ai-tools/briefpoint/),
  [lawyerist.com](https://lawyerist.com/reviews/artificial-intelligence-in-law-firms/briefpoint-artificial-intelligence-for-lawyers/)).
  Drafting, not analysis.
- **EvenUp** — per-case pricing, personal injury demand packages only; 1,500+ PI firms
  ([businesswire.com](https://www.businesswire.com/news/home/20250514536151/en)).
  Relevant as the model for a vertical-specific document-AI company, not as a
  competitor.
- **Family-law-specific attorney AI**: **Paxton** markets analysis of financial
  disclosures, custody evaluations, and court filings with inconsistency spotting
  ([paxton.ai/solutions/family-law](https://www.paxton.ai/solutions/family-law));
  **NexLaw** markets custody timelines and best-interest-factor organization
  ([nexlaw.ai](https://www.nexlaw.ai/solutions/practice-areas/family-law/));
  **StrongSuit** targets family law firms ([strongsuit.com](https://strongsuit.com/family-law/)).
  These attack the attorney segment directly. None targets the litigant.

### 1d. Direct analogs for litigants

- **CourtCase "Custody Case Organizer"** — AI organizes texts, photos, visitation
  records into court-formatted timelines and flags patterns (missed visitations,
  communication gaps) ([courtcase.frontofai.com](https://courtcase.frontofai.com/custody-case-organizer)).
  Closest consumer analog found. It works from the user's evidence (messages, photos),
  not from dissecting formal filings (petitions, motions, orders) across a case file.
- **Courtroom5** — subscription platform for pro se civil litigants; its STRATEGY tool
  reads uploaded case documents and maps litigation posture; entry pricing advertised
  "from $1" ([courtroom5.com/pricing](https://courtroom5.com/pricing/),
  [softwarefinder.com](https://softwarefinder.com/legal/courtroom5)). General civil,
  not family-law-specific; the company itself has written about UPL exposure as its
  main structural risk ([courtroom5.com blog](https://courtroom5.com/blog/the-personal-practice-of-law-empowering-pro-se-litigants-to-reclaim-the-courts/)).
- **Pro Se Tools** — a Gumroad-sold AI toolkit for self-represented litigants
  ([prosetools.gumroad.com](https://prosetools.gumroad.com/l/pro-se-tools)) — evidence
  that demand exists at the low end, but it is a document/prompt kit, not a product.

**Net:** no product found that does the specific combination — structured dissection of
formal family-court filings + cross-filing inconsistency flags + cited case-wide
timeline + party language analysis — for a represented litigant preparing for attorney
meetings. The attorney-side version of this exists (Paxton, NexLaw, CoCounsel); the
litigant-side version does not, beyond partial analogs.

## 2. Attorney demand signals

- AI adoption among legal professionals is high and rising: Clio's 2025 Legal Trends
  Report found 79% of legal professionals use AI in daily work (up from 19% in 2023),
  71% even at solo firms, and 70% of clients are neutral-to-positive about firms using
  AI ([clio.com press release](https://www.clio.com/about/press/the-science-behind-smarter-law-clios-2025-legal-trends-report-reveals-how-technology-is-rewiring-the-way-lawyers-work/),
  [2civility.org](https://www.2civility.org/2025-clio-legal-trends-report/)). The ABA's
  more conservative 2024 survey put firm AI use at 30% overall, with family law firms
  at 20% — tied with PI for second among practice areas
  ([abajournal.com](https://www.abajournal.com/web/article/aba-tech-report-finds-that-ai-adoption-is-growing-but-some-are-hesitant),
  [lawnext.com](https://www.lawnext.com/2025/03/aba-tech-survey-finds-growing-adoption-of-ai-in-legal-practice-with-efficiency-gains-as-primary-driver.html)).
- Family-law attorneys routinely and publicly tell clients that arriving organized
  saves fees: firm blogs advise clients to organize documents, bring requested
  materials, and batch questions specifically to cut billable time
  ([nivinlaw.com](https://www.nivinlaw.com/blogs/5050/how-to-save-money-in-legal-fees-during-a-divorce-or-family-law-case),
  [shellyingramlaw.com](https://www.shellyingramlaw.com/finances-taxes/2023/11/02/5-money-saving-ideas-to-lower-your-legal-fees/),
  [lawyerforfamilies.com](https://www.lawyerforfamilies.com/save-money-on-attorneys-fees/),
  [plogsteinlaw.com](https://www.plogsteinlaw.com/blog/what-to-bring-to-a-first-meeting-with-a-family-law-attorney/)).
  This matches the product's positioning exactly.
- Family lawyers already review and recommend consumer apps to clients: practitioner
  reviews of co-parenting apps are a common content genre
  ([lakemunrolaw.com](https://www.lakemunrolaw.com/blogs/co-parenting-apps-in-2025--reviews-and-insights),
  [wassermanwhite.com](https://wassermanwhite.com/co-parenting-apps/)), and courts
  order their use. A precedent exists for attorney-recommended client-side tools.
- Specific forum threads of family-law practitioners praising organized clients:
  **no strong evidence found** in indexed search results; direct forum research would
  be needed. The proxy evidence (firm blogs above, and the document-chaos problem
  described in practice-management writing, e.g.
  [Harvard TagTeam feed](https://tagteam.harvard.edu/hub_feeds/4607/feed_items/12431460))
  is consistent but softer.

## 3. Market size proxies

- **National volume:** state courts handle ~3.8M family law cases/year, including
  ~1.09M divorces, ~880K child support matters, and ~380K paternity cases
  ([clio.com family law statistics](https://www.clio.com/blog/family-law-statistics/);
  underlying data: NCSC Court Statistics Project,
  [ncsc.org](https://www.ncsc.org/explore-court-caseload-data)).
- **Florida:** ~70,800 dissolution-of-marriage filings in FY2023-24 out of ~241,900
  total family court filings statewide
  ([Florida Courts Statistical Reference Guide, flcourts.gov](https://flcourts-media.flcourts.gov/content/download/218404/file/ReferenceGuide11-12-Chp5.pdf);
  summarized at [findthelawyers.com](https://findthelawyers.com/blog/florida-divorce-statistics/)).
- **Self-representation:** commonly cited range is 60-90% of family cases with at
  least one self-represented party
  ([IAALS](https://iaals.du.edu/blog/high-numbers-self-represented-litigants-left-underserved-family-courts));
  California courts report 70% at filing rising to 80% by judgment
  ([californialawreview.org](https://www.californialawreview.org/online/self-represented-litigants-in-family-law));
  a Miami-Dade snapshot found 62%
  ([americanbar.org](https://www.americanbar.org/groups/legal_services/publications/dialogue/volume/20/fall-2017/pro-bono-everyone-counts/)).
  Implication: the "represented litigant" segment is a minority of case volume, but the
  pro se pool is large if UPL risk is later accepted.
- **Rates and case cost (Florida):** family attorneys charge roughly $300-$600/hr,
  median ~$300-350; retainers $4,000-$15,000
  ([mcnary.law](https://mcnary.law/blog/how-much-does-a-family-law-attorney-cost-in-florida/),
  [legalmatch.com](https://www.legalmatch.com/law-library/article/family-lawyer-cost-in-florida.html)).
  Contested divorces run $11,000-$25,000 on average, complex custody cases
  $50,000-$100,000+ ([divorce.law Florida guide](https://divorce.law/guides/divorce-cost/florida/),
  [wblaws.com](https://wblaws.com/the-cost-of-a-custody-lawyer-in-florida/)). At
  $300/hr, saving 3-4 attorney hours pays for a year of a ~$25/mo consumer
  subscription — a defensible value story.

## 4. Willingness to pay

- **Litigants** already pay $7-$32/mo per parent for co-parenting documentation apps,
  often for years, and often both parents pay
  ([softwarefinder.com OFW pricing](https://softwarefinder.com/legal/ourfamilywizard/pricing),
  [parentingpath.net TalkingParents](https://www.parentingpath.net/blog/talkingparents-removed-free-plan)).
  AppClose's move from free to paid in 2026 suggests the free-app equilibrium is ending
  ([kidtime.app](https://kidtime.app/blog/best-court-approved-co-parenting-apps)). A
  litigant in active litigation is spending $300+/hr on counsel; the reference class
  supports **$15-35/mo consumer pricing**, possibly with a higher one-time "case file
  analysis" purchase during litigation spikes.
- **Attorneys** pay $30-$140/user/mo for chronology tools (CaseFleet,
  [casefleet.com/pricing](https://www.casefleet.com/pricing)), ~$41-59/mo for timelines
  (TrialLine, [blog.trialline.net](https://blog.trialline.net/new-trialline-subscription-pricing/)),
  $49-59/mo for practice-management AI add-ons (Clio Duo), and $75-500/user/mo for
  research-grade AI (CoCounsel)
  ([casefleet.com comparison](https://www.casefleet.com/blog/legal-ai-pricing-rate-limits-and-overages)).
  A family-law-specific analysis tool plausibly prices at **$75-150/seat/mo** for
  solo/small firms — above generic chronology tools, below CoCounsel.

## 5. Regulatory and market cautions

- **UPL/FTC:** DoNotPay paid $193,000 and accepted restrictions under an FTC final
  order (Jan 2025) over "robot lawyer" claims, after a 2023 California Bar UPL
  cease-and-desist ([ftc.gov](https://www.ftc.gov/news-events/news/press-releases/2025/02/ftc-finalizes-order-donotpay-prohibits-deceptive-ai-lawyer-claims-imposes-monetary-relief-requires),
  [abajournal.com](https://www.abajournal.com/news/article/robot-lawyer-website-donotpay-settles-ftc-claims-it-couldnt-deliver-on-promises)).
  The enforcement hook was overclaiming ("performs like a lawyer"), not the software's
  existence. The "arrive prepared for your attorney" positioning is the right side of
  this line; marketing must never imply legal advice or outcome prediction. Note
  Florida is historically among the more aggressive UPL-enforcement states
  (Courtroom5's own writing treats UPL as its central structural risk:
  [courtroom5.com](https://courtroom5.com/blog/the-personal-practice-of-law-empowering-pro-se-litigants-to-reclaim-the-courts/)).
- **Hallucination sanctions:** ~712 court decisions worldwide address AI-hallucinated
  content, ~90% written in 2025; sanctions include a South Florida judge sanctioning a
  lawyer over fabricated citations across eight cases
  ([sternekessler.com](https://www.sternekessler.com/news-insights/insights/ai-ip-year-in-reviewai-hallucinations-in-court-filings-and-orders-a-2025-review-of-sanctions-across-the-courts-and-rule-proposals/),
  [damiencharlotin.com database](https://www.damiencharlotin.com/hallucinations/),
  [scientificamerican.com](https://www.scientificamerican.com/article/why-lawyers-keep-citing-fake-cases-invented-by-ai/)).
  Judges are primed to distrust AI work product. Every output must carry pin citations
  to the source document, and the product should analyze documents it ingests rather
  than generate legal authority — which is already the design.

## 6. Name collision check

Domain signals: DNS/HTTP checks run 2026-07-27; "resolves" means registered, not
necessarily an active product. These are signals, not registrar-verified availability,
and none of this replaces a counsel-run trademark search before store submission.

| Name | Findings | Verdict |
|---|---|---|
| **CaseReady** | Live litigation platform "CaseReady" by Eversheds Sutherland / Opus 2, in legal tech since 2018 ([opus2.com](https://www.opus2.com/resources/clients/eversheds-sutherland-eversheds-sutherland-launches-caseready-platform-for-litigators/), [artificiallawyer.com](https://www.artificiallawyer.com/2018/11/29/eversheds-sutherland-launches-litigation-platform-with-opus-2/)). caseready.com and caseready.app both registered. | **Taken** (same industry — direct conflict) |
| **CaseBinder** | "CaseBinder" is a live legal product name — ChartRequest's medical-records-retrieval solution for law firms ([chartrequest.com](https://chartrequest.com/legal-solutions/casebinder/)); adjacent "digital case binder" products SupraBook and Align occupy the concept ([suprabook.com](https://suprabook.com/), [align.lawyer](https://align.lawyer/)). casebinder.com registered and serving. | **Taken/crowded** |
| **PrepMyCase** | prepmycase.com is an existing family-law/matrimonial litigation-support consultancy for attorneys ([prepmycase.com](http://prepmycase.com/)) — same practice area. | **Taken** (worst possible collision: same niche) |
| **DocketReady** | No product named "DocketReady" found; but "Docket" is heavily used across app stores and software (waste management, meetings, health) ([yourdocket.com](https://www.yourdocket.com/), [docket.care](https://docket.care/)). docketready.com registered but no live product identified. | **Clear-ish but crowded namespace**; domain likely needs purchase |
| **CasePrep** | No legal-tech product found, but "Case Prep" is saturated in consulting-interview prep apps ([case-prep.com](https://www.case-prep.com/), [casetools.app](https://casetools.app/), [casestudyprep.ai](https://www.casestudyprep.ai/)); a "My Case Prep" also exists, and MyCase is a major legal practice-management brand ([lawyerist.com](https://lawyerist.com/reviews/law-practice-management-software/mycase/)) — confusing-similarity risk. caseprep.com registered. | **Crowded** |
| **MeetPrepared** | No app or product of this name found in search; meetprepared.com did not resolve in DNS (strongest availability signal of the six). Generic phrase used in meeting-software marketing but no branded collision. | **Clear** |

## Executive summary

1. There is a credible attorney-side market: family law is tied for second in AI
   adoption by practice area (20%, ABA 2024) and 79% of legal professionals now use AI
   daily (Clio 2025).
2. But the attorney side is getting crowded fast — Paxton, NexLaw, StrongSuit, and
   CoCounsel all now market family-law document analysis and chronology extraction to
   firms.
3. The litigant side is nearly empty: no found product dissects formal filings, flags
   cross-filing inconsistencies, and builds a cited case timeline for a represented
   client; the closest analogs (CourtCase, Courtroom5) work from raw evidence or
   generic civil posture.
4. Enter with represented litigants as the wedge, with an attorney/GAL review view as
   the fast-follow — attorneys are already publicly telling clients to arrive
   organized, which makes them a channel, not a gatekeeper.
5. Litigant willingness to pay is proven at $7-32/mo per parent (OurFamilyWizard,
   TalkingParents); suggested consumer price: ~$19-29/mo or a one-time case-analysis
   package (single-buyer, unlike per-parent co-parenting apps).
6. Suggested professional price: $75-150/seat/mo, benchmarked between CaseFleet AI
   ($140) and Clio Duo ($49-59).
7. Market volume supports a Florida start: ~242K family filings/yr statewide, ~70.8K
   dissolutions, median attorney rates $300-350/hr, contested custody commonly
   $11K-100K.
8. Regulatory line: DoNotPay's $193K FTC order punished "performs like a lawyer"
   claims — the "prepared for your attorney, not instead of your attorney" positioning
   must be literal in all marketing, and Florida's UPL posture argues for deferring
   pro se features.
9. Every AI output needs pin citations to ingested documents; 2025's sanction wave
   (including a South Florida case) means uncited AI work product is radioactive with
   judges and attorneys alike.
10. Names: MeetPrepared is clear (and the domain appears unregistered); DocketReady is
    possible but crowded; CaseReady, PrepMyCase, and CaseBinder are taken by
    legal-industry products; CasePrep is crowded and risks confusion with MyCase.
