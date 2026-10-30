# TEN Capital Network | Investor Screening

A Streamlit application that reviews an investor pitch deck (PDF, PPTX or legacy PPT) against TEN Capital Network's
screening criteria and produces:

1. a detailed, evidence-cited analysis in the browser;
2. the multi-page **Investor Screening Review** PDF in the TEN format (cover summary plus sections 1–11, sources and
   disclaimers), structured per [templates/investor_screening_review_template.md](templates/investor_screening_review_template.md);
3. an **exactly one-page** US Letter screening summary PDF;
4. an evidence appendix PDF (full evidence ledger, readiness rubric, methodology), an optional public (redacted)
   one-pager, and structured JSON.

Claude reads the deck and proposes evidence and assessments. **Eligibility, capital totals, runway, readiness and
scores are computed deterministically in Python**, and every citation Claude makes is checked against the extracted
text before it can count.

---

## Quick start

Requires Python 3.10 or later (developed and tested on Python 3.14.6, Windows 11).

**Windows (PowerShell)**

```powershell
cd "C:\Users\user\Documents\Claude Cowork folder\TENAnalyzer"
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env        # then edit .env: set ANTHROPIC_API_KEY and ANTHROPIC_MODEL
python -m streamlit run app.py
```

**macOS / Linux**

```bash
cd TENAnalyzer
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env               # then edit .env: set ANTHROPIC_API_KEY and ANTHROPIC_MODEL
python -m streamlit run app.py
```

The app opens at <http://localhost:8501>. No login, email or external storage is required.

### Required configuration

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | An API key from the Claude Console: <https://console.anthropic.com> → **Settings → API Keys → Create Key**. The account needs API credits; usage is billed per analysis (two model calls, plus a third when external research is on). |
| `ANTHROPIC_MODEL` | The Claude model id to use, e.g. `claude-opus-5-5`. It must accept image input when visual inspection is on. |
| `APP_PASSWORD` | Shared sign-in password. **Required on Railway**: a hosted deployment stays locked until it is set. Optional locally. |

Neither is hard-coded anywhere. Without them the app still runs extraction and preview, but the analysis button is
disabled and the sidebar names the missing variable. Every optional setting is documented in [.env.example](.env.example).
Two settings depend on the model you choose:

* `TEN_REFUSAL_FALLBACK=on` sends the server-side refusal fallback (`fallbacks: "default"`). Current Opus and Fable models
  on the Claude API support it. If your model rejects the request with a 400 error, set it to `off`.
* `TEN_EFFORT` / `TEN_THINKING` default to `high` / `adaptive`. Use `omit` for models that do not accept these parameters.

### Optional local tools

| Tool | Used for | If missing |
|---|---|---|
| **LibreOffice** (`soffice`) | Converting legacy `.ppt` to `.pptx`; rendering `.pptx` slides to images for visual inspection | `.ppt` uploads explain how to *Save As* PPTX/PDF; PPTX analysis runs on text only and says visual inspection was unavailable |
| **Tesseract OCR** | OCR of scanned / image-only PDF pages (via PyMuPDF) | Scanned pages are flagged for review. If visual inspection is on, Claude reads the rendered page images, and those citations are marked as visual (not text-verifiable) |

Install LibreOffice from <https://www.libreoffice.org>. Install Tesseract with the
[UB Mannheim installer](https://github.com/UB-Mannheim/tesseract/wiki) on Windows, `brew install tesseract` on macOS, or
`apt install tesseract-ocr` on Debian/Ubuntu. Both are auto-detected on `PATH` and in their standard install locations.
The sidebar shows whether each was found.

---

## Using the app

The interface uses the TEN Capital dark navy design with coral, amber and teal accents taken from the logo's three
figures. Sora is the display face, Inter the body face and JetBrains Mono the label face. The tokens live in
[ten_screener/ui.py](ten_screener/ui.py) and [.streamlit/config.toml](.streamlit/config.toml). The accent colours
also carry meaning in results: teal is strong, amber is moderate and coral is weak.

To review the design without an upload or an API key, run
`python -m streamlit run scripts/ui_preview.py`. It preloads a synthetic, fictional report.


1. **Upload**: drop a deck. You can add company context (for example, intro-call notes). It is labeled
   *User-supplied context* and never treated as deck evidence.
2. **Extraction preview**: page and slide counts, characters extracted, pages needing review, speaker-note pages, hidden
   slides and rendered pages. Any extraction limitation is shown *before* analysis. An empty or scanned extraction is
   reported as an extraction problem, never as an empty deck.
3. **Analysis**: two Claude calls with live progress. The first builds the evidence ledger; the second writes the
   assessment.
4. **Results**: track, stage gate, effective fit, underlying score, readiness, any eligibility override, verdict,
   company strengths and concerns, scorecard, expandable sections A to I, a filterable evidence ledger, and limitations.
5. **Downloads**: Screening Review PDF (primary), one-page summary PDF, evidence appendix PDF, JSON, and (if
   toggled) the public one-pager.

Processing failures (bad file, API error, rendering error) are shown as **"Processing problem - not an investment
finding"**, so they are never confused with screening results.

Sidebar options: visual inspection (on by default), external research (**off by default**), public version, and an
optional header logo.

---

## How the screening works

### Pipeline

```
upload -> validate (type, magic bytes, size) -> isolated temp dir -> extract (text, tables, notes, OCR, page images)
  -> Claude stage 1: evidence ledger + structured facts (JSON, validated with Pydantic)
  -> citation verification against extracted text (downgrade anything unlocatable)
  -> deterministic rules: track gate, capital de-duplication, runway, instrument flags, readiness, sensitivity
  -> [optional] web research, kept separate
  -> Claude stage 2: assessment and 1-10 category scores (JSON, validated)
  -> deterministic weighted scoring, bands, overrides -> report -> PDFs / JSON
```

### Evidence standards

Each ledger item has a claim or value, a verbatim excerpt, a page/slide reference, the source kind (visible slide text,
table, speaker notes, or rendered image), a status, and any uncertainty. The statuses are:

* Disclosed in deck
* Calculated from disclosed inputs (inputs and method are shown)
* Analyst inference
* Not disclosed
* Contradictory
* Externally verified (optional research only)
* User-supplied context

Citation verification checks every excerpt against the cited page and assigns one outcome:

* **verified**
* **approximate**: OCR noise or line breaks
* **relocated**: found on another page; the citation is corrected
* **not found**: the claim is downgraded to *Analyst inference*
* **page out of range**
* **visual**: read from an image, so it cannot be text-verified

Unknown values are `null` and render as "Not disclosed". They are never zero. PDF citations use the PDF page index
("PDF p. 7"), not printed slide numbers. PPTX citations use slide order, and speaker notes are labeled separately.

### Track classification and stage gate (deterministic)

* **Track A** (non-life-science): meets the gate only with *actual* revenue **and** disclosed paying commercial
  customers. Pilots, including paid pilots, fail. Projections or bookings alone are not revenue. Single months are not
  annualized.
* **Track B** (therapeutics, devices, diagnostics, regulated digital health): meets the gate with a defined regulatory
  pathway and jurisdiction that fit the product. Preclinical data and pre-submission meetings strengthen the assessment
  but are **not** required.
* A gate **fails** only on affirmative evidence: the deck says it is pre-revenue, only pilots are evidenced, zero
  customers are disclosed, or the deck says the pathway is undetermined. Silence gives **Cannot Determine**. Incomplete
  evidence gives **Partially Meets**. When the track itself is unclear, the result is **Track Undetermined**.
* Facts count only if their citations survived verification.

### Scoring

| Category | Weight |
|---|---:|
| Stage Gate Fit | 20% |
| Team | 15% |
| Market & Growth Potential | 15% |
| Differentiation & Defensibility | 15% |
| Financials & Capital Efficiency | 10% |
| Deal Terms & Capital History | 10% |
| Exit Potential | 10% |
| Pitch Deck Quality | 5% |

`weighted total = sum(score / 10 x weight)`. The bands are applied *before rounding*:

| Total | Band |
|---|---|
| 80-100 | Strong Fit |
| 65 to under 80 | Moderate Fit |
| 50 to under 65 | Weak Fit |
| Below 50 | Likely Pass |

Score anchors: 1-2 severe weakness, 3-4 weak, 5-6 mixed, 7-8 strong, 9-10 exceptional and well supported.

* A category without enough evidence is **Not assessable**. Its weight is not redistributed. The report shows
  supported points, the assessed weight and the possible range, and the final band is withheld until every category
  can be assessed.
* The Stage Gate Fit score is bounded by the gate result: Meets 6-10, Partial 3-6, Does Not Meet 1-3, Cannot Determine
  not assessable.
* **Overrides**: a failed gate or a confirmed exclusion (real estate development, consulting/services, franchises,
  lifestyle businesses) caps the effective rating at Weak Fit, and Likely Pass stays Likely Pass. A partial or
  undetermined gate gives **Pending stage verification**. The underlying score is always shown separately from the
  override.
* **Investor Readiness (1-10)** is separate from investability. It awards one point for each of ten evidenced
  preparation items (ask and use of funds, terms, traction metrics, financials, capital history, team, market sizing,
  competition, milestones, contact and materials), with a minimum of 1.

### One-page PDF

* US Letter portrait with selectable text.
* Navy/teal/white palette. This is a neutral **default**, not verified TEN branding. Edit `PALETTE` in
  [ten_screener/pdf/theme.py](ten_screener/pdf/theme.py) to change it.
* Body text is 10 pt. To fit the page, the layout first tightens wording through five levels, and only then steps the
  font down to 9.5 pt and 9 pt. It never goes below 9 pt.
* Every candidate layout is actually built and measured: it must be one page and at most 720 words (the target is
  roughly 550-700).
* Includes the required disclaimer. It is labeled **"Confidential — Internal Screening"** whenever the deck names
  investors or discloses committed capital, cash or burn, or a valuation or cap.
* The footer follows the TEN Capital document standard in `CLAUDE.md` (title, page number, "Compiled on [date] by TEN
  Capital Network", footer logo, Open Sans 7 pt).
* The public version is a *separate* render. It removes investor names, committed capital, cash, burn, runway,
  valuation and cap, verbatim excerpts and analyst context. Free text is scrubbed sentence by sentence, so review it
  before sharing.

### Security and privacy

* Decks are treated as **untrusted input**. Deck text is wrapped in neutralized tags, the system prompt forbids
  following embedded instructions, and text that looks like it is addressed to an AI is flagged in the extraction
  preview.
* Uploads are written under a neutral filename to a fresh temporary directory, which is deleted as soon as extraction
  finishes. Only extracted text and in-memory page images stay in the browser session.
* Logs record file type, page count and character count only, never content or credentials. `.env`, decks and
  generated reports are gitignored.
* External research is off by default. When it is on, only the company's public identity (name, website, sector,
  stage) is used as search context. Findings carry their URL and retrieval date and stay separate from deck claims.

---

## Result emails (Resend)

After every completed analysis the app emails the results to **Info@tencapital.group**. The email contains a
summary (company, track, stage gate, fit, score, readiness, verdict, strengths, concerns, actions, limitations) and
attaches the Screening Review PDF and the one-page summary. If an analysis fails, a short notice is sent instead. It
contains the filename, the stage and the reason, but no deck content.

Setup:

1. Create an API key at <https://resend.com/api-keys>. *Sending access* is enough. Set it as `RESEND_API_KEY`.
2. **Verify the sending domain.** Add `tencapital.group` at <https://resend.com/domains> and create the DNS records
   Resend lists. Then set `TEN_EMAIL_FROM`, for example `TEN Capital Screening <screening@tencapital.group>`.
   Until the domain is verified, the app falls back to Resend's sandbox sender, `onboarding@resend.dev`. That sender
   only delivers to the email address that owns your Resend account, and the sidebar shows a warning while it is in
   use.
3. Optional settings:
   * `TEN_EMAIL_TO`: comma-separated recipients. The default is `Info@tencapital.group`.
   * `TEN_EMAIL_ATTACH`: any of `review,onepage,evidence,json`.
   * `TEN_EMAIL_REPLY_TO`: a reply-to address.
   * `TEN_EMAIL_ON_FAILURE=off`: turn off failure notices.
   * `TEN_EMAIL_ENABLED=off`: turn off all emails.

Behavior:

* Sending is on automatically when `RESEND_API_KEY` is set (`TEN_EMAIL_ENABLED=auto`).
* An email problem never fails or hides an analysis. The results page shows whether the email was sent, skipped or
  failed, with a **Retry email** button on failure.
* Each analysis has a unique run ID that is used as Resend's idempotency key, so page reruns never send duplicates.
* Emails labeled *Confidential* get a `[Confidential]` subject prefix. All report text is HTML-escaped.

## Deploy on Railway

The repo includes a `Dockerfile` (Python 3.12 with LibreOffice and Tesseract, so PPT conversion, slide rendering and
OCR all work in production), `railway.json` (Dockerfile build, health check on `/_stcore/health`), and `.dockerignore`
(keeps `.env`, decks, tests and scripts out of the image).

**1. Create the service.** Either:

* **CLI** (from this folder):
  ```powershell
  railway login            # opens a browser
  railway init             # create a new project, or `railway link` to use an existing one
  railway up               # uploads this folder and builds the Dockerfile
  ```
* **GitHub:** push this folder to a repository, then in Railway choose **New Project → Deploy from GitHub repo**.

**2. Set variables** (service → **Variables**), then redeploy:

| Variable | Value |
|---|---|
| `ANTHROPIC_API_KEY` | your Console key |
| `ANTHROPIC_MODEL` | e.g. `claude-opus-5-5` |
| `APP_PASSWORD` | a long random password to share with your team |
| `TEN_REFUSAL_FALLBACK` | `on` (or `off` if your model rejects it) |
| `RESEND_API_KEY` | your Resend key (enables result emails) |
| `TEN_EMAIL_FROM` | a sender on your verified domain, e.g. `TEN Capital Screening <screening@tencapital.group>` |

Every other setting in `.env.example` is optional. Railway sets `PORT` automatically.

**3. Get a URL.** In the service's **Settings → Networking**, choose **Generate Domain**. Open it, sign in with
`APP_PASSWORD`, and run one deck end to end.

Operational notes:

* The first build takes several minutes, because LibreOffice is large. Later builds reuse the cached layers.
* An analysis runs for a few minutes over the browser's websocket. Keep the tab open until results appear.
* Uploads are processed in temporary directories inside the container and are never stored. Sessions live in memory,
  so a redeploy clears in-progress results.
* Give the service at least 1 GB of memory. LibreOffice and page rendering are the peak consumers.

## Project layout

```
app.py                         Streamlit interface (upload -> preview -> analysis -> results -> downloads)
ten_screener/
  config.py                    environment settings (no hard-coded keys or model ids)
  ingest.py                    validation, temp workspaces, extraction dispatch, quality and injection checks
  extraction/                  pdf_reader (PyMuPDF + OCR), pptx_reader, convert (LibreOffice), render (page images)
  evidence.py                  deck serialization for the prompt, citation verification
  analysis/                    prompts, llm (Anthropic client, JSON repair, errors), research (optional), analyzer
  rules.py                     stage gate, capital de-duplication, runway, instrument flags, readiness, sensitivity
  scoring.py                   weights, bands, Not-assessable handling, overrides
  schemas.py                   Pydantic models for extraction, evidence, LLM output and the report
  summary.py                   display lines shared by the PDFs and the UI
  review.py                    content rules for the Screening Review (cover rows, capital table, sources)
  auth.py                      shared-password gate (mandatory when hosted)
  notify.py                    Resend result and failure emails (idempotent, never fatal)
  pdf/                         theme, screening_review (TEN format), one_page, full_report (evidence appendix), public
templates/                     investor_screening_review_template.md - the document structure the review follows
Dockerfile, railway.json       Railway deployment
assets/                        Open Sans fonts, TEN Capital footer logo
static/                        public files served at /app/static/ (favicon.png, favicon.ico)
tests/                         pytest suite and SYNTHETIC fixtures (fictional companies)
scripts/render_samples.py      renders sample PDFs from synthetic fixtures for visual inspection
```

## Tests

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```

The suite covers:

* weighted-score maths and band boundaries, including the thresholds-before-rounding rule;
* failed-gate and exclusion overrides, and pending verification;
* Not-assessable categories and the possible score range;
* unknown versus zero values (customers, burn, funding);
* Track B without preclinical data, and Track A with only paid pilots;
* funding double-counting (cumulative statements, duplicated rounds, contradictions, mixed currencies);
* citation verification outcomes and injection-tag neutralization;
* file validation (wrong type, empty, oversize, fake PDF, encrypted PDF/PPTX, corrupt files);
* PDF, PPTX and PPT extraction (the PPT test and PPTX rendering need LibreOffice and are skipped without it);
* Claude client behavior (request parameters from the environment, JSON repair, refusal, truncation, 401/404/400/429/5xx
  and connection errors);
* the end-to-end pipeline and PDF checks: exactly one page, US Letter, selectable text, no body text under 9 pt, long
  names, dense findings, public redaction, and full-report sections.

The Anthropic API is faked in tests, and no network calls are made.

To render sample PDFs for a visual check, run `python scripts/render_samples.py <output_dir>`.

## Known limitations

* The live Anthropic integration is exercised only through a faked SDK client in the test suite. Run one real deck
  after configuring your key to confirm that your chosen model accepts the configured parameters.
* Charts and images are understood only when visual inspection is on and pages can be rendered. PPTX rendering needs
  LibreOffice.
* Citation checks confirm that an excerpt *exists* in the deck, not that Claude interpreted it correctly. Deck claims
  remain company claims.
* Public redaction of free text is best-effort.
* Valuation benchmarking and comparable exits need external research or analyst input. Otherwise they are listed as
  diligence items.
