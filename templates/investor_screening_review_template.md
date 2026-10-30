# TEN Capital Network — Investor Screening Review: Document Template

General structure for the multi-page **Investor Screening Review** that the app generates. It contains no
company data. Every company-specific value is a `{{placeholder}}`. Instructions for the generator appear in
`> GUIDANCE` blocks and are never printed.

**Conventions**

* `{{field}}` is replaced with generated content. Unknown values print **"Not disclosed"**, never 0 and never a guess.
* `[A]` / `[B]` marks content shown only for Track A (non-life-science) or Track B (life science). Track
  Undetermined shows both, labeled.
* `{{source_ref}}` is a page or section citation: "PDF p. N" for PDF decks, "Slide N" for PPTX, and the quoted
  section name for single-page documents. Speaker-note evidence is labeled "notes".
* External findings, and anything else not taken from the deck, carry a hyperlink and appear under **Sources**.
* Lists marked "up to 5" are never padded. If fewer items are supported, print what exists and add
  *"Only {{n}} supported by the materials."*

---

## Page format

| Element | Specification |
|---|---|
| Page | US Letter portrait. Off-white page background (approx. `#FFFCF5`). Generous margins (about 0.9 in left/right). |
| Typeface | Clean sans-serif (Helvetica/Arial class). Headings bold black; body dark grey (approx. `#4A4A4A`). |
| Accent colours | Coral (approx. `#E8553F`) for the eyebrow label, section bars, sub-section labels and the score figure. Teal (approx. `#4BBFD6`) and amber (approx. `#F5A623`) only for highlighted words in the cover title. These are approximate and should be confirmed against TEN brand guidance. |
| Section heading | Short coral bar (about 0.6 in × 4 pt) above a bold heading, numbered "N. Title" (about 20 pt). |
| Lead sentence | A bold sentence under every section heading that states the section's verdict (about 11 pt). |
| Sub-section labels | All-caps coral (e.g. "5 PROS OF THE PITCH DOCUMENT"). |
| Bullets | Labeled bullets: **Label:** sentence(s). |
| Tables | Full width, light-grey header row, thin blue-grey row rules, no vertical lines, bold first column where it is a label. |
| Callout | Verdict box: pale tint background with a coral left border. |
| Links | Blue, underlined on hover. Only for sourced external facts. |
| Running header (pages 2+) | TEN Capital logo on the left. Right: `{{company_legal_name}} | Investor Screening Review | {{analysis_date_long}}`. A thin rule below. |
| Footer | TEN Capital standard (CLAUDE.md): `{{document_title}}   {{page}}   Compiled on {{analysis_date_long}} by TEN Capital Network   [footer logo]`. Single centered line, Open Sans 7 pt. |
| Confidentiality | When the report names investors or discloses committed capital, cash, burn, valuation or cap, show **"Confidential — Internal Screening"** in the running header. |

---

## Page 1 — Cover summary

`[TEN Capital Network logo, top left]`

**INVESTOR SCREENING REVIEW** *(coral eyebrow label)*

# {{company_name}}: {{value_proposition_headline}}

> GUIDANCE: The headline is at most 8 words and states what the company sells, written by the analyst rather
> than copied from the deck's marketing copy. Highlight 2–3 key words in coral, teal and amber.

Screened against TEN Capital Network criteria from the {{source_description}} ({{source_date}}). Prepared by TEN
Capital Network, {{analysis_date_long}}.

> GUIDANCE: `source_description` names the material, for example "full pitch deck (18 slides)", "one-page
> company introduction" or "executive summary".

| Investability Score | TEN Fit Rating | Investor Readiness |
|:---:|:---:|:---:|
| **{{investability_score}}** *(coral, large)* | **{{effective_fit_rating}}** | **{{readiness_score}} / 10** |

> GUIDANCE: When scoring is incomplete, show "Provisional" with `{{supported_points}} pts · {{assessed_weight}}%
> assessed · range {{min}}–{{max}}` and withhold the band. When an override applies, show the effective rating
> here and the underlying band in section 10.

| Item | Finding |
|---|---|
| **Track** | {{track_letter}} – {{track_name}} ({{sector}}: {{product_category_description}}) |
| **Stage gate** | **{{gate_status}}.** {{gate_one_line_reason}} |
| **Funding raised to date** | {{funding_summary_one_line}} |
| **Current raise** | {{current_raise_one_line}} |
| **Exclusion categories** | {{exclusion_one_line}} |
| **Recommended next step** | {{recommended_next_step}} |

*{{source_material_note}}*

> GUIDANCE: The source-material note is a small grey sentence on the completeness of the input. Example: "Source
> material is a single-page introduction, not a full pitch deck. Criteria that cannot be assessed are stated as
> gaps rather than assumed." Omit it when a complete deck was supplied and extraction had no limitations.

---

## 1. Track Classification & Stage Gate

**Track {{track_letter}} – {{gate_status}}{{gate_qualifier}}. {{track_rationale}}. {{gate_requirement_sentence}}**

> GUIDANCE: The `gate_requirement_sentence` restates the minimum qualification.
> [A] "The Track A requirement applies: paying customers and actual revenue from commercial operations."
> [B] "The Track B requirement applies: a defined regulatory pathway appropriate to the product and target market."

| Evidence type | What the {{source_short_name}} states | Counts toward stage gate? |
|---|---|---|
| {{evidence_type}} | {{quoted_or_paraphrased_claim}} ({{source_ref}}) | {{gate_relevance}} |

> GUIDANCE: Add one row for each evidence type below. Use "None stated" when the materials are silent, and say
> in the third column whether and why the row counts.
> [A] Paid revenue / ARR / TTM (actual vs projected, period) · Paying commercial customers (count) · Pilots /
> paid pilots (never count) · Contracts and awards (signed vs LOI vs pursuit) · Pipeline · Bookings / backlog ·
> Non-dilutive or sponsored funding (counts only if received by the company as revenue) · Customer concentration.
> [B] Proposed regulatory pathway and jurisdiction · Basis (management proposal vs regulatory feedback) ·
> Regulator interactions (pre-submission etc.) · Preclinical / clinical / bench validation (strengthens, not
> required) · Authorization status (clearance, approval, registration and CE marking kept distinct) · Next
> regulatory milestone · Time and cost to authorization · Reimbursement (coding, coverage, payment).

{{gate_verdict_paragraph}}

> GUIDANCE: 2–3 sentences. State what would move the gate to Meets or to Does Not Meet, and name the first
> diligence question.

---

## 2. Capital History & Current Raise

**{{capital_lead_sentence}}**

| Item | Disclosed? | Detail |
|---|---|---|
| Equity raised to date | {{Yes/Partly/No}} | {{detail}} |
| Convertible instruments (SAFE / note / KISS) | {{Yes/Partly/No}} | {{detail}} |
| Debt | {{Yes/Partly/No}} | {{detail}} |
| Non-dilutive / grant funding | {{Yes/Partly/No}} | {{detail — sponsor, program (e.g. SBIR/STTR, NIH, NSF, DoD), amount, date, recipient}} |
| Named investors | {{Yes/Partly/No}} | {{detail}} |
| Current raise amount | {{Yes/Partly/No}} | {{detail}} |
| Instrument / valuation or cap | {{Yes/Partly/No}} | {{detail}} |
| Amount committed / lead | {{Yes/Partly/No}} | {{detail}} |
| Use of funds | {{Yes/Partly/No}} | {{detail — itemized, or "Implied: … Not quantified"}} |
| Milestone financed | {{Yes/Partly/No}} | {{detail}} |

> GUIDANCE: Totals come from the app's de-duplicated capital summary. Never add a cumulative "raised to date"
> figure to itemized rounds. Flag contradictions.

**Capital efficiency:** {{capital_efficiency_assessment}}

**Structure flags:** {{instrument_flags_or_"none identified / none can be assessed"}}

> GUIDANCE: Cover uncapped notes, uncapped or custom SAFEs, KISS agreements and pre-money SAFE stacking. Explain
> the specific concern. A label alone is not disqualifying.

**{{conditional_flag_label}}:** {{conditional_flag_text}}

> GUIDANCE: Optional and repeatable. Use for material structural issues, e.g. IP or data rights tied to sponsored
> funding, university licence terms, prior note overhang, or runway below 6 months.

---

## 3. Company Maturity & Team

**{{team_lead_sentence}}**

* **Stage fit:** {{stage_assessment}}; {{valuation_benchmark_or_"valuation cannot be benchmarked — pending diligence"}}
* **Validation:** {{traction_or_technical_validation}}
* **{{founder_role}}:** {{name}}, {{background_or_"no background given"}}, {{full_time_status}}
  *(one bullet per named founder or key executive)*
* **Other team members:** {{collective_description_or_named_list}}
* **Full-time commitment:** {{stated_or_"not stated"}}
* **Single-founder dependency:** {{assessment}}
* **Gaps to probe:** {{missing_roles_critical_to_next_milestone}}
* [B] **Regulatory, clinical and quality capability:** {{RA/QA/clinical/SAB/KOL coverage}}
* **Public footprint:** {{external_research_finding_or_"External research disabled — not checked"}}

---

## 4. Differentiation & Defensibility

**{{differentiation_lead_sentence}}**

* **Claimed edge:** {{claimed_advantage}}. {{whether_supporting_data_is_given}}
* **Customer alternatives / standard of care:** {{current_alternatives}}
* **Competitive field:** {{named_competitors_and_categories}} *(link external examples)*
* **Barriers to entry:** {{switching_costs, proprietary data, network effects, certifications, relationships — with completion status}}
* **IP:** {{patents filed vs granted, jurisdictions, trade secrets, licences}}. Do not infer freedom to operate.
* **Sustainability:** {{how long the advantage lasts and what would erode it}}

---

## 5. Growth Potential

**{{growth_lead_sentence}}**

* **Market tailwinds:** {{demand_drivers}} *(link sourced figures)*
* **Pricing context:** {{price_points, customer budgets, price ceilings}}; {{company_unit_price_or_"not disclosed"}}
* **Target segments:** {{segments_or_programs_named}}
* **TAM/SAM/SOM:** {{figures_with_sources_or_"not provided"}}
* **Go-to-market:** {{sales motion, cycle length, channels, partners}}
* **Unit economics:** {{CAC, LTV, payback, margins — or "not disclosed"}}
* **Scalability:** {{model scalability and recurring revenue}}
* [B] **Commercialization after authorization:** {{partner vs direct, manufacturing, adoption}}
* [B] **Reimbursement dependency:** {{coding, coverage, payment status}}

---

## 6. Financial Review

**{{financial_lead_sentence}}**

* **Revenue and pricing:** {{actual vs projected revenue, pricing validation, gross margin, backlog}}
* **Burn and runway:** {{burn}}; {{runway — calculated from disclosed cash/burn, or "not disclosed"}}. Flag runway under 6 months.
* **Operating / production economics:** {{capex, inventory, working capital, scale-up costs}}
* [B] **Regulatory and clinical costs:** {{regulatory, clinical, quality, manufacturing, contingency}}
* **Financial model:** {{credibility of 24–36-month projections, sales ramp, hiring plan — or what is needed}}
* **Value inflection:** {{whether the raise funds a specific milestone}}

---

## 7. Exit Potential

**{{exit_lead_sentence}}**

| Comparable | Year | Terms | Relevance |
|---|---|---|---|
| [{{acquirer}} – {{target}}]({{source_url}}) | {{year}} | {{price, revenue/EBITDA, multiple}} | {{why it is comparable}} |

> GUIDANCE: Include only sourced transactions (external research enabled or analyst-supplied). Otherwise replace
> the table with: "Comparable exits were not researched; listed as a diligence item."

* **Likely acquirers:** {{acquirer_categories_and_examples}}; {{stated_relationships_or_"none stated"}}
* **10x test:** {{computed with labeled assumptions (entry valuation, ownership, dilution, required exit equity value) or "cannot be computed without valuation"}}. A large TAM is not a return.
* **Timing:** {{trigger_event_and_exit_horizon}}

---

## 8. Exclusion Check

**{{exclusion_verdict}}** {{business_model_evidence}} {{investor_matching_note}}

> GUIDANCE: The categories are real estate development, consulting/services, franchises and lifestyle
> businesses. Distinguish a product business with supporting services from a services business. The optional
> matching note covers sector-specific restrictions some investors apply, such as regulated, export-controlled
> or foreign-investment-sensitive sectors.

---

## 9. Pitch Document Review

**{{deck_lead_sentence}}** {{citation_convention_sentence}}

> GUIDANCE: The citation convention sentence explains how feedback is located. Example: "Feedback cites PDF page
> numbers." For a one-page document: "It is a single page, so feedback cites its sections."

**{{n}} PROS OF THE PITCH DOCUMENT** *(up to 5)*

1. **{{strength_title}} ({{source_ref}}).** {{why_it_works}}

**{{n}} CRITIQUES OF THE PITCH DOCUMENT** *(up to 5)*

1. **{{issue_title}} ({{source_ref}}).** {{what_is_wrong}} *Fix:* {{concrete_fix}}

**MISSING DATA**

* {{missing_item}}

**SUGGESTED STRUCTURE FOR A FULL DECK** *(include when helpful)*

1. {{slide_title_and_purpose}}

**DILIGENCE ITEMS INVESTORS WILL REQUEST** *(priority order)*

* {{diligence_item}}

---

## 10. Investability Score

**{{score}} / 100 – {{band}}. {{override_statement}} {{nondisclosure_note}}**

> GUIDANCE: The override statement is one of: "No cap applies"; "Rating capped at Weak Fit: {{reason}}"; or
> "Pending stage verification". The non-disclosure note explains when low scores reflect missing information
> rather than poor disclosed information.

| Category | Weight | Score | Weighted | Justification |
|---|---:|---:|---:|---|
| Stage Gate Fit | 20% | {{s}} | {{w}} | {{justification}} |
| Team | 15% | {{s}} | {{w}} | {{justification}} |
| Market & Growth Potential | 15% | {{s}} | {{w}} | {{justification}} |
| Differentiation & Defensibility | 15% | {{s}} | {{w}} | {{justification}} |
| Financials & Capital Efficiency | 10% | {{s}} | {{w}} | {{justification}} |
| Deal Terms & Capital History | 10% | {{s}} | {{w}} | {{justification}} |
| Exit Potential | 10% | {{s}} | {{w}} | {{justification}} |
| Pitch Deck Quality | 5% | {{s}} | {{w}} | {{justification}} |
| **Total** | **100%** | | **{{total}}** | **{{band}}** |

> GUIDANCE: Weighted = score ÷ 10 × weight. Bands are applied before rounding (80+ Strong, 65–<80 Moderate,
> 50–<65 Weak, <50 Likely Pass). A category without enough evidence shows "Not assessable" with no weighted
> value. Its weight is not redistributed, and the total row shows "Provisional {{points}} ({{range}})".

---

## 11. Final Investor Verdict

> **{{verdict_headline}}** {{verdict_paragraph}}
> *(callout box: pale tint, coral left border)*

| Item | Result |
|---|---|
| **Track and stage gate** | {{track_letter}} – {{gate_status}} |
| **Funding raised to date** | {{funding_summary_one_line}} |
| **Investability Score** | {{score}} / 100 – {{effective_fit_rating}}{{underlying_band_if_overridden}} |
| **Investor Readiness Score** | {{readiness_score}} / 10 |

**TOP {{n}} COMPANY STRENGTHS** *(up to 5; about the business, not the presentation)*

1. {{strength}}

**TOP {{n}} COMPANY CONCERNS** *(up to 5)*

1. {{concern}}

**KEY ACTIONS BEFORE FUNDRAISING** *(at least 3, priority order)*

* {{action}}

**SOURCES**

* {{source_document_name}} ({{source_date}}) *(the supplied material, unlinked)*
* [{{external_source_title}}]({{url}}) *(each external fact, with retrieval date in the JSON export)*

*Initial screening based on supplied materials; not independent verification. For informational purposes only.
Does not constitute an offer to sell securities.*

*Disclaimer: TEN is a "Funding as a Service" program. It is not a registered broker-dealer and does not offer
investment advice or advise on the raising of capital through securities offerings. TEN does not recommend or
otherwise suggest that any investor make an investment in a specific company, or that any company offer
securities to a particular investor. TEN takes no part in the negotiation or execution of transactions for the
purchase or sale of securities, and at no time has possession of funds or securities. No securities transactions
are executed or negotiated on or through the TEN program. TEN receives no compensation in connection with the
purchase or sale of securities.*

---

## Appendix — Field mapping to the app (`ScreeningReport`)

> Implemented in app v1.1: the "New field" items below now exist in `AssessmentOutput`, are requested in the
> stage-2 prompt, and are rendered by `ten_screener/pdf/screening_review.py` (content rules in
> `ten_screener/review.py`). Comparable exits are accepted only when they cite a retrieved external finding.

| Template field | App source | Status |
|---|---|---|
| company_name, website, source filename, analysis date | `meta.*` | Available |
| company_legal_name | `ledger.company.name` | Available (legal suffix only if stated) |
| value_proposition_headline | — | **New field needed** in `AssessmentOutput` |
| source_description / source_date / source_material_note | `meta.page_count`, `extraction_issues` | **New field needed** (document type and date) |
| investability_score, effective_fit_rating, band, override_statement | `scoring.*` | Available |
| readiness_score | `readiness.score` | Available |
| track_*, gate_status, gate reasons | `gate.*`, `ledger.track` | Available |
| Stage-gate evidence table rows | `ledger.track_a` / `track_b` + evidence ledger | Available; per-row "counts toward gate" text is **new** |
| funding_summary_one_line, capital table | `capital.*`, `ledger.funding_events`, `ledger.current_raise` | Available; "Disclosed? Yes/Partly/No" is **derived** |
| Capital efficiency, structure flags | `assessment.capital_efficiency`, `instrument_flags`, `assessment.instrument_concerns` | Available |
| conditional_flag_* | — | **New optional list** in `AssessmentOutput` |
| Sections 3–6 labeled bullets | `assessment.maturity_and_team` … `financial_review` | Available as summary + findings; fixed bullet labels need a **schema change** |
| recommended_next_step | — | **New field needed** |
| Exit comparables table | `external_findings` | Partial; structured comparables (year, terms, relevance) are **new** |
| 10x test | `assessment.ten_x_scenario` | Available |
| Exclusion verdict and matching note | `ledger.exclusion`, `assessment.exclusion_explanation` | Available; matching note is **new** |
| Pros / critiques / missing data / deck structure / diligence | `assessment.deck_*`, `missing_slides_or_data`, `revised_slide_order`, `diligence_requests` | Available |
| Scorecard table | `scoring.categories` | Available |
| Verdict headline + paragraph | `assessment.investor_verdict` | Available; separate headline is **new** |
| Strengths, concerns, key actions | `assessment.company_strengths/concerns`, `fundraising_actions` | Available |
| Sources | `meta.source_filename`, `external_findings[].url` | Available |
