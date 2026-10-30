"""TEN Capital Network | Investor Screening - Streamlit interface.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import hashlib
import json
import logging

import pandas as pd
import streamlit as st

from ten_screener import REPORT_TITLE, auth, notify, ui
from ten_screener.analysis.analyzer import analyse
from ten_screener.config import load_settings
from ten_screener.errors import ScreenerError
from ten_screener.extraction.convert import find_soffice
from ten_screener.extraction.pdf_reader import tesseract_available
from ten_screener.ingest import extract_upload
from ten_screener.pdf.full_report import render_full_report
from ten_screener.pdf.one_page import render_one_page
from ten_screener.pdf.screening_review import render_screening_review
from ten_screener.schemas import READINESS_RUBRIC, ExtractionResult, ScreeningReport
from ten_screener.summary import capital_lines, snapshot_title, track_snapshot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

st.set_page_config(page_title=REPORT_TITLE, page_icon=ui.favicon(), layout="wide")
settings = load_settings()  # also loads .env, so APP_PASSWORD may live there locally
state = st.session_state


def html(markup: str) -> None:
    """Render a trusted HTML fragment from ten_screener.ui (which escapes every dynamic value)."""
    st.markdown(markup, unsafe_allow_html=True)


md = ui.md  # escape model, deck and user text before st.markdown / st.write


html(ui.CSS)


def require_password() -> None:
    """Shared-password gate. Mandatory on hosted deployments so the API key cannot be used by strangers."""
    expected = auth.configured_password()
    if expected is None:
        if auth.is_hosted():
            html(ui.brand())
            with st.container(key="hero"):
                html(ui.hero_header("Secure access", "TEN Screener", "Locked",
                                    "This deployment has no APP_PASSWORD set, so it is locked."))
                st.error("Add an APP_PASSWORD variable in the Railway service settings and redeploy.")
            st.stop()
        return
    if state.get("authenticated"):
        return
    html(ui.brand())
    with st.container(key="hero"):
        html(ui.hero_header("Secure access", "TEN Screener", "Sign in",
                            "Enter the team password to screen pitch decks against TEN Capital criteria."))
        with st.form("login", border=False):
            given = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", type="primary", width="stretch")
        if submitted:
            if auth.password_matches(given, expected):
                state["authenticated"] = True
                st.rerun()
            st.error("Incorrect password.")
    html(ui.footer())
    st.stop()


require_password()


def processing_error(exc: ScreenerError) -> None:
    """Processing failures are visually distinct from investment findings."""
    st.error(f"**Processing problem ({exc.stage}) - not an investment finding.**\n\n{md(exc.user_message)}")
    if exc.retryable:
        st.caption("This error is usually temporary. You can retry.")


def reset_results() -> None:
    for key in ("report", "usage", "pdf_one", "pdf_full", "pdf_review", "pdf_public", "one_info", "email_result", "email_attempt"):
        state.pop(key, None)


# ---------------------------------------------------------------------------
# Sidebar: configuration and options
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Configuration")
    missing = settings.missing_api_config()
    if missing:
        st.error("Missing: " + ", ".join(missing) + ". Set them in `.env` and restart.")
    else:
        st.success(f"Anthropic API configured\n\nModel: `{settings.model}`")
    st.caption(
        f"LibreOffice (PPT conversion, slide rendering): {'found' if find_soffice() else 'not found'}  \n"
        f"Tesseract OCR (scanned PDFs): {'found' if tesseract_available() else 'not found'}"
    )
    st.caption(notify.status_line(settings))
    st.header("Options")
    visual = st.toggle("Visual inspection of rendered pages", value=True,
                       help="Sends rendered page images to Claude so charts, images and layout can be read.")
    external = st.toggle("External research (web search)", value=settings.external_research_enabled,
                         help="Off by default. When on, the company's name, website, sector and stage are used for web "
                              "searches; deck figures and investor information are not sent. Findings are kept separate from deck claims.")
    if external:
        st.warning("External research is ON: public web results will be cited separately from deck evidence.")
    offer_public = st.toggle("Also generate a public one-page version", value=False,
                             help="A separate PDF with investor names, committed capital, cash/burn and valuation removed.")
    logo_file = st.file_uploader("Optional logo for the one-page PDF header", type=["png", "jpg", "jpeg"])


def render_outputs(report: ScreeningReport) -> None:
    """Render every PDF into session state (cached; the one-pagers re-render when the logo changes)."""
    logo = logo_file.getvalue() if logo_file else None
    logo_digest = hashlib.sha256(logo).hexdigest() if logo else None
    if state.get("logo_digest") != logo_digest:
        state.pop("pdf_one", None)
        state.pop("pdf_public", None)
        state["logo_digest"] = logo_digest
    if "pdf_one" not in state:
        result = render_one_page(report, logo=logo)
        state["pdf_one"], state["one_info"] = result.pdf, result
    if "pdf_review" not in state:
        state["pdf_review"] = render_screening_review(report)
    if "pdf_full" not in state:
        state["pdf_full"] = render_full_report(report)
    if offer_public and "pdf_public" not in state:
        state["pdf_public"] = render_one_page(report, logo=logo, public=True).pdf


def email_outputs() -> dict[str, bytes]:
    return {k: v for k, v in (("review", state.get("pdf_review")), ("onepage", state.get("pdf_one")),
                              ("evidence", state.get("pdf_full"))) if v}


def extraction_chips(extraction: ExtractionResult) -> list[tuple[str, str]]:
    unit = "pages" if extraction.file_type == "pdf" else "slides"
    review = len(extraction.pages_needing_review)
    errors = any(i.severity == "error" for i in extraction.issues)
    return [
        (f"✓ {extraction.filename}", "ok"),
        (f"{extraction.page_count} {unit}", ""),
        (f"{extraction.total_chars:,} characters", "bad" if errors else ""),
        (f"{review} need review" if review else "all pages readable", "warn" if review else "ok"),
        (f"{len(extraction.page_images)} rendered" if extraction.page_images else "no visual inspection",
         "" if extraction.page_images else "warn"),
    ]


# ---------------------------------------------------------------------------
# Hero: upload and run
# ---------------------------------------------------------------------------
html(ui.brand())
with st.container(key="hero"):
    html(ui.hero_header(
        "Deck Analyzer", "Pitch Deck", "Investor Screening",
        "Upload a pitch deck and get TEN Capital's investor screening review and one-page summary, "
        "analyzed and scored by Claude against TEN criteria.",
    ))
    uploaded = st.file_uploader(
        f"Pitch deck (PDF, PPTX or PPT, up to {settings.max_upload_mb} MB)", type=["pdf", "pptx", "ppt"],
        label_visibility="collapsed",
    )
    if uploaded is not None:
        data = uploaded.getvalue()
        digest = hashlib.sha256(data).hexdigest()[:16]
        if state.get("file_digest") != digest or state.get("visual_flag") != visual:
            state.pop("extraction", None)
            reset_results()
            state["file_digest"] = digest
            state["visual_flag"] = visual
        if "extraction" not in state:
            with st.spinner("Validating and extracting..."):
                try:
                    state["extraction"] = extract_upload(uploaded.name, data, settings, visual=visual)
                except ScreenerError as exc:
                    processing_error(exc)
                except Exception:  # noqa: BLE001 - never show a raw traceback for a bad upload
                    logging.exception("unexpected extraction failure")
                    st.error("**Processing problem - not an investment finding.** The file could not be processed. "
                             "Try re-exporting it as PDF or PPTX.")
    extraction: ExtractionResult | None = state.get("extraction")
    if extraction is not None:
        html(ui.chips(extraction_chips(extraction)))
    with st.expander("Add company context (optional)"):
        user_context = st.text_area(
            "Company context (kept separate from deck evidence)",
            placeholder="e.g. notes from an intro call. Labeled 'User-supplied context' and never treated as deck evidence.",
            height=90,
        )
    run = st.button("Run investor screening", type="primary", width="stretch",
                    disabled=bool(missing) or extraction is None)
    if missing:
        st.caption("Screening is disabled until the Anthropic API key and model are configured.")
    html(ui.disclosure(settings.email_to if settings.email_enabled else None))

report: ScreeningReport | None = state.get("report")
html(ui.stepper(4 if report is not None else 3 if run else 2 if extraction is not None else 1))

# ---------------------------------------------------------------------------
# Extraction preview
# ---------------------------------------------------------------------------
if extraction is not None:
    with st.container(key="panel_preview"):
        note = "Citations use PDF page numbers, which may differ from printed slide numbers." if extraction.file_type == "pdf" \
            else "Citations use slide numbers; speaker notes are labeled separately."
        html(ui.panel_header("Extraction preview", note))
        review_count = len(extraction.pages_needing_review)
        html(ui.tiles([
            ("Pages" if extraction.file_type == "pdf" else "Slides", str(extraction.page_count), "", None),
            ("Characters", f"{extraction.total_chars:,}", "extracted text", None),
            ("Need review", str(review_count), "low text, OCR or images", "amber" if review_count else "teal"),
            ("Rendered", str(len(extraction.page_images)), "for visual inspection", None),
            ("Speaker notes", str(sum(1 for p in extraction.pages if p.notes)), "pages with notes", None),
        ]))
        html(ui.section_label("Extraction limitations"))
        if not extraction.issues:
            st.success("No extraction limitations detected.")
        for issue in extraction.issues:
            pages = f" ({', '.join(extraction.label_for(p) for p in issue.pages[:12])}{'...' if len(issue.pages) > 12 else ''})" if issue.pages else ""
            {"error": st.error, "warning": st.warning, "info": st.info}[issue.severity](md(issue.message + pages))
        with st.expander("Page-by-page details", expanded=any(i.severity == "error" for i in extraction.issues)):
            st.dataframe(pd.DataFrame([{
                "Page": p.label, "Characters": p.char_count, "Text source": p.text_source, "Tables": len(p.tables),
                "Speaker notes": "yes" if p.notes else "", "Hidden": "yes" if p.hidden else "",
                "Rendered": "yes" if p.number in extraction.page_images else "", "Review": p.review_reason or "",
            } for p in extraction.pages]), hide_index=True, width="stretch")
            choice = st.selectbox("Inspect page", [p.label for p in extraction.pages])
            page = next(p for p in extraction.pages if p.label == choice)
            left, right = st.columns([3, 2])
            left.text_area("Visible text", page.text or "[no extractable text]", height=240, disabled=True)
            for t in page.tables:
                left.dataframe(pd.DataFrame(t), hide_index=True)
            if page.notes:
                left.text_area("Speaker notes (not visible to investors)", page.notes, height=110, disabled=True)
            if page.number in extraction.page_images:
                right.image(extraction.page_images[page.number], caption=f"Rendered {page.label}")

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if run and extraction is not None:
    reset_results()
    with st.container(key="panel_run"):
        with st.status("Running screening...", expanded=True) as status:
            try:
                report, usage = analyse(
                    extraction, settings, user_context=user_context or None,
                    external_research=external, progress=status.write,
                )
                state["report"], state["usage"] = report, usage
                status.write("Generating PDF reports")
                try:
                    render_outputs(report)
                except ScreenerError as exc:
                    processing_error(exc)
                if settings.email_enabled:
                    status.write(f"Emailing results to {', '.join(settings.email_to)}")
                state["email_result"] = notify.notify_analysis(report, email_outputs(), settings)
                status.update(label="Screening complete", state="complete", expanded=False)
            except ScreenerError as exc:
                report = None
                status.update(label="Screening failed", state="error")
                processing_error(exc)
                if settings.email_enabled:
                    st.caption(notify.notify_failure(extraction.filename, exc.stage, exc.user_message, settings).summary)
            except Exception:  # noqa: BLE001
                report = None
                logging.exception("unexpected analysis failure")
                status.update(label="Screening failed", state="error")
                st.error("**Processing problem - not an investment finding.** An unexpected error occurred during analysis. Retry; if it persists, check the logs.")
                if settings.email_enabled:
                    st.caption(notify.notify_failure(extraction.filename, "analysis", "Unexpected error; see the server logs.", settings).summary)

# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
report = state.get("report")
if report is not None:
    a, sc, meta = report.assessment, report.scoring, report.meta
    with st.container(key="panel_results"):
        html(ui.panel_header(meta.company_name, " · ".join(filter(None, [
            meta.website, meta.source_filename, f"analyzed {meta.analysis_date}"]))))
        if report.sensitivity.confidential:
            html(ui.chips([("Confidential — Internal Screening", "bad")] + [(r, "") for r in report.sensitivity.reasons]))
        html(ui.tiles([
            ("Track", report.gate.track_label.split(" - ")[0], report.gate.track_label.split(" - ")[-1], None),
            ("Stage gate", report.gate.status.value, "", ui.RATING_TONE.get(report.gate.status.value)),
            ("Effective fit", sc.effective_rating, f"Underlying: {sc.underlying_band}" if sc.underlying_band else "Band withheld",
             ui.RATING_TONE.get(sc.effective_rating, "ink_300")),
            ("Investability", f"{sc.total:.1f} / 100" if sc.complete else "Provisional",
             "All categories assessed" if sc.complete else f"{sc.supported_points:.1f} pts · {sc.assessed_weight}% assessed", None),
            ("Investor readiness", f"{report.readiness.score} / 10", "Preparation, not investability", None),
        ]))
        email = state.get("email_result")
        if email is not None:
            if email.sent:
                st.success("✉ " + md(email.summary))
            elif email.skipped_reason:
                st.caption("✉ " + md(email.summary))
            else:
                st.warning("✉ " + md(email.summary) + " The analysis itself is complete and available below.")
                if st.button("Retry email"):
                    state["email_attempt"] = state.get("email_attempt", 0) + 1
                    state["email_result"] = notify.notify_analysis(report, email_outputs(), settings, attempt=state["email_attempt"])
                    st.rerun()
        st.write(md(a.business_description))
        if sc.override_applied:
            st.warning("Eligibility override: " + md(sc.override_applied))
        st.info(("**" + md(a.verdict_headline) + "** " if a.verdict_headline else "**Investor verdict.** ") + md(a.investor_verdict))
        gate_ref = report.cite(report.gate.evidence_ids)
        st.write("**Stage gate reasoning:** " + md(" ".join(report.gate.reasons)) + (f" ({md(gate_ref)})" if gate_ref else ""))

        def points(items) -> None:  # noqa: ANN001
            if not items:
                st.write("None supported by the evidence.")
            for i, item in enumerate(items, start=1):
                ref = report.cite(item.evidence_ids)
                st.markdown(f"{i}. **{md(item.headline)}** {md(item.detail)}" + (f" _({md(ref)})_" if ref else ""))
            if 0 < len(items) < 5:
                st.caption(f"Only {len(items)} supported; not padded to five.")

        col1, col2 = st.columns(2)
        with col1:
            html(ui.section_label("Company strengths"))
            points(a.company_strengths)
        with col2:
            html(ui.section_label("Company concerns"))
            points(a.company_concerns)
        html(ui.section_label("Prioritized actions before fundraising"))
        for i, action in enumerate(a.fundraising_actions, start=1):
            st.markdown(f"{i}. {md(action)}")

        html(ui.section_label("Scorecard"))
        st.dataframe(pd.DataFrame([{
            "Category": c.name, "Weight": f"{c.weight}%", "Score": c.score if c.score is not None else "Not assessable",
            "Points": round(c.points, 1) if c.points is not None else None,
            "Justification": c.justification + (f" [{c.adjustment_note}]" if c.adjustment_note else ""),
            "Evidence": report.cite(c.evidence_ids),
        } for c in sc.categories]), hide_index=True, width="stretch")
        st.caption(f"Underlying score: {md(sc.status_label)}" + (f" - underlying band {sc.underlying_band}" if sc.underlying_band
                                                             else " - final band withheld until every category is assessable"))

        html(ui.section_label("Detailed analysis"))
        with st.expander(f"{snapshot_title(report)} and capital"):
            for line in track_snapshot(report):
                st.markdown(f"- {md(line)}")
            for k, v in capital_lines(report):
                st.markdown(f"- **{k}:** {md(v)}")
            st.markdown(f"- **Runway:** {md(report.runway.basis)}")
            for note in report.capital.notes:
                st.caption(md(note))
            for flag in report.instrument_flags:
                st.warning(f"**{md(flag.flag)}:** {md(flag.concern)}")

        def section(title: str, sec, extra=None) -> None:  # noqa: ANN001
            with st.expander(title):
                if sec.lead:
                    st.markdown(f"**{md(sec.lead)}**")
                st.write(md(sec.summary))
                for p in sec.points:
                    ref = report.cite(p.evidence_ids)
                    st.markdown(f"- **{md(p.label)}:** {md(p.text)}" + (f" _({md(ref)})_" if ref else ""))
                for f in sec.findings:
                    ref = report.cite(f.evidence_ids)
                    st.markdown(f"- **{md(f.headline)}** {md(f.detail)}" + (f" _({md(ref)})_" if ref else ""))
                if extra:
                    extra()

        def capital_extra() -> None:
            st.write("**Capital efficiency:** " + md(a.capital_efficiency))
            st.write("**Current raise:** " + md(a.current_raise.summary))
            for c in a.instrument_concerns:
                st.markdown(f"- **{md(c.instrument)}:** {md(c.concern)}")

        section("A. Capital history and current raise", a.capital_history, capital_extra)
        section("B. Company maturity and team", a.maturity_and_team,
                lambda: st.write("**Valuation benchmarking:** " + md(a.valuation_benchmarking)))
        section("C. Differentiation and defensibility", a.differentiation)
        section("D. Market and growth", a.market_and_growth)
        section("E. Financial review", a.financial_review,
                lambda: st.write(f"**Raise funds a value-inflection milestone:** {a.raise_funds_milestone}. {md(a.raise_funds_milestone_explanation)}"))
        section("F. Exit potential", a.exit_potential,
                lambda: a.ten_x_scenario and st.json(a.ten_x_scenario.model_dump()))
        with st.expander("G. Exclusion check"):
            ex = report.ledger.exclusion
            st.write(f"**{ex.category.replace('_', ' ')} - {ex.status.replace('_', ' ')}.** {md(a.exclusion_explanation)}")
        with st.expander("H. Pitch deck review"):
            st.write(md(a.deck_narrative_assessment))
            labels = lambda pages: ", ".join(report.page_labels.get(p, str(p)) for p in pages)  # noqa: E731
            st.markdown("**Deck strengths**")
            for d in a.deck_strengths:
                st.markdown(f"- **{md(d.headline)}** {md(d.detail)} _({md(labels(d.pages))})_")
            st.markdown("**Critiques and fixes**")
            for d in a.deck_critiques:
                st.markdown(f"- **{md(d.issue)}** Fix: {md(d.fix)} _({md(labels(d.pages))})_")
            if a.missing_slides_or_data:
                st.markdown("**Missing slides or data:** " + md("; ".join(a.missing_slides_or_data)))
            if a.revised_slide_order:
                st.markdown("**Suggested slide order:** " + md(" → ".join(a.revised_slide_order)))
            st.markdown("**Prioritized diligence requests**")
            for i, req in enumerate(a.diligence_requests, start=1):
                st.markdown(f"{i}. {md(req)}")
        with st.expander("I. Investor readiness"):
            st.caption(report.readiness.rubric_note)
            st.write(md(a.readiness_justification))
            st.dataframe(pd.DataFrame([{"Item": READINESS_RUBRIC[i.key], "Met": "Yes" if i.met else "No", "Note": i.note}
                                       for i in report.readiness.items]), hide_index=True, width="stretch")
        if report.external_findings:
            with st.expander("External research (separate from deck claims)"):
                st.dataframe(pd.DataFrame([f.model_dump() for f in report.external_findings]), hide_index=True, width="stretch")
        if report.user_context:
            with st.expander("Analyst-supplied context (not deck evidence)"):
                st.write(md(report.user_context))
        with st.expander("Evidence ledger"):
            rows = [{
                "Id": e.id, "Topic": e.topic, "Claim": e.claim, "Value": e.value or "", "Status": e.status.value,
                "Nature": "" if e.nature in ("not_applicable", "unclear") else e.nature.replace("_", " "),
                "Source": report.cite([e.id], limit=4),
                "Verification": ", ".join(sorted({s.verification for s in e.sources})) or "-",
                "Excerpt": " | ".join(s.excerpt for s in e.sources if s.excerpt)[:300],
                "Notes": " ".join(filter(None, [e.calculation, e.uncertainty, e.citation_note])),
            } for e in report.ledger.evidence]
            df = pd.DataFrame(rows)
            statuses = st.multiselect("Filter by status", sorted(df["Status"].unique()) if not df.empty else [])
            st.dataframe(df[df["Status"].isin(statuses)] if statuses else df, hide_index=True, width="stretch")
            st.caption("Citation checks: " + ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in report.citation_summary.items()))
        with st.expander("Limitations"):
            for item in report.limitations:
                st.markdown(f"- {md(item)}")
            if report.ledger.contradictions:
                st.markdown("**Contradictions and anomalies**")
                for item in report.ledger.contradictions:
                    st.markdown(f"- {md(item)}")
            st.caption("API usage: " + json.dumps(state.get("usage", {})))

    # -----------------------------------------------------------------------
    # Downloads
    # -----------------------------------------------------------------------
    with st.container(key="panel_downloads"):
        html(ui.panel_header("Downloads", "The Screening Review follows the TEN format; the other files support it."))
        try:
            render_outputs(report)
        except ScreenerError as exc:
            processing_error(exc)
        stem = "".join(ch if ch.isalnum() else "_" for ch in meta.company_name)[:50].strip("_") or "company"
        if "pdf_review" in state:
            st.download_button("Download Screening Review PDF", state["pdf_review"], f"{stem}_TEN_Investor_Screening_Review.pdf",
                               "application/pdf", type="primary", width="stretch")
        d = st.columns(4 if offer_public else 3)
        if "pdf_one" in state:
            d[0].download_button("One-page summary PDF", state["pdf_one"], f"{stem}_TEN_Screening_OnePage.pdf", "application/pdf", width="stretch")
            info = state["one_info"]
            d[0].caption(f"{info.pages} page · {info.words} words · {info.body_size:g} pt body")
        if "pdf_full" in state:
            d[1].download_button("Evidence appendix PDF", state["pdf_full"], f"{stem}_TEN_Screening_Evidence.pdf", "application/pdf", width="stretch")
            d[1].caption("Evidence ledger, readiness rubric, methodology")
        payload = json.loads(report.model_dump_json())
        payload["api_usage"] = state.get("usage", {})
        d[2].download_button("Structured JSON", json.dumps(payload, indent=2), f"{stem}_TEN_Screening.json", "application/json", width="stretch")
        d[2].caption("All evidence, facts and scores")
        if offer_public and "pdf_public" in state:
            d[3].download_button("Public one-page PDF", state["pdf_public"], f"{stem}_TEN_Screening_Public.pdf", "application/pdf", width="stretch")
            d[3].caption("Sensitive details removed (best effort) - review before sharing.")

html(ui.footer())
