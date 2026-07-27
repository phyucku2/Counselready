# Lessons — mistakes turned into rules

Append-only. Each entry is a **finding-class we actually hit** (or a risk identified in
research before it could bite), rewritten as a **one-line preventive rule** so it never
recurs. Newest at the bottom. Consult this list before building; add to it every time
review or CI catches a class of mistake not already here.

Format: `- **<short name>** — <one preventive rule>. (<where it came from>)`

## Rules

- **An uncited generated statement is a defect, not a rough edge** — every event, flag, and observation must resolve to document + page + passage before it can render; build the citation into the storage schema so an uncitable claim is unrepresentable rather than merely discouraged. (ADR-0001/0002; the 2025 sanction wave — ~712 decisions on AI-hallucinated content, ~90% written in 2025, including South Florida)
- **Never generate legal authority from model knowledge** — the product analyzes documents the user supplies; a statute, case citation, or rule the model recalls is exactly the failure mode courts are sanctioning. Analyze the file, never author the law. (ADR-0001 §2)
- **The name of the risk is overclaiming, not the software** — the FTC's $193,000 DoNotPay order turned on "performs like a lawyer" marketing, so review copy (app store, landing page, in-product headings, push notifications) against the §1 line with the same seriousness as code. A compliant engine behind advice-flavored copy is still the violation. (market research §5)
- **Two accounts of one event are two claims** — never merge conflicting dates or descriptions into a single "fact"; render both, attributed, and let the human judge. Silent reconciliation manufactures evidence. (CLAUDE.md §2)
- **Tone analysis is a bias surface before it is a feature** — dialect and non-native English score as more hostile on off-the-shelf tone classifiers, so language review ships quote-based, after a documented bias evaluation, and never as a score attached to a named person. (ADR-0001 Phase 4)
- **Sensitive-by-default beats sensitive-by-tag** — a family court file mixes medical, financial, and minors' data on adjacent pages, so apply the strictest handling to the whole corpus rather than to pages a classifier tagged. A misclassified page must not be a privacy incident. (CLAUDE.md §3)
- **The threat model runs in both directions** — the same pattern-documentation that helps a survivor evidence a case helps an abuser surveil and harass; account takeover by an ex-partner is a life-safety event, so MFA, login alerting, and no shared-household accounts are launch requirements, not hardening backlog. (CLAUDE.md §3; DV-advocate lens)
- **A jurisdiction assumption is a bug in waiting** — Florida terminology, document types, and local rules go behind the jurisdiction-profile seam from the first parser, because a rule hardcoded in Phase 1 is a rewrite in Phase 5. (CLAUDE.md §7)
- **Store-blocking requirements are built early or they block you late** — account and data deletion is a hard app-store rule for any app collecting user data; schedule it in Phase 0 rather than discovering it at submission. (roadmap 0.4)
- **No public preview URLs for a product holding court files** — a per-PR preview deployment is a convenience for a marketing site and a disclosure risk here; previews, if wanted, are authenticated. (ADR-0002)
