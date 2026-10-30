"""Automated result emails through Resend (https://resend.com).

One rule governs this module: **an email problem must never fail or lose an
analysis.** Every public function returns an ``EmailResult`` instead of raising,
and logs what went wrong (never the API key or deck content).

Resend is called over its REST API with ``httpx`` (already installed with the
Anthropic SDK). Each analysis email carries an ``Idempotency-Key`` derived from the
run id, so a Streamlit rerun or a manual retry can never deliver a duplicate.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass, field
from html import escape

import httpx

from ten_screener import REPORT_TITLE
from ten_screener.config import Settings
from ten_screener.schemas import ScreeningReport

LOGGER = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"
TIMEOUT_SECONDS = 20.0
#: Resend allows 40 MB per message; stay well inside it. Oversized attachments are dropped, not fatal.
MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024
#: Resend's shared sender works without domain verification but only delivers to the Resend
#: account owner's own address - fine for a first test, not for a team inbox.
SANDBOX_SENDER = "TEN Capital Screening <onboarding@resend.dev>"

ATTACHMENT_NAMES = {
    "review": "Investor_Screening_Review.pdf",
    "onepage": "Screening_OnePage.pdf",
    "evidence": "Screening_Evidence_Appendix.pdf",
    "json": "Screening.json",
}


@dataclass
class Attachment:
    filename: str
    content: bytes


@dataclass
class EmailResult:
    sent: bool = False
    message_id: str | None = None
    recipients: list[str] = field(default_factory=list)
    error: str | None = None
    skipped_reason: str | None = None
    attachments_dropped: list[str] = field(default_factory=list)
    retryable: bool = False

    @property
    def summary(self) -> str:
        if self.sent:
            dropped = f" (too large to attach: {', '.join(self.attachments_dropped)})" if self.attachments_dropped else ""
            return f"Results emailed to {', '.join(self.recipients)}{dropped}."
        if self.skipped_reason:
            return f"Email not sent: {self.skipped_reason}"
        return f"Email failed: {self.error}"


def sender(settings: Settings) -> str:
    return settings.email_from or SANDBOX_SENDER


def uses_sandbox_sender(settings: Settings) -> bool:
    return "onboarding@resend.dev" in sender(settings)


def status_line(settings: Settings) -> str:
    """One-line configuration status for the sidebar."""
    if settings.email_mode == "off":
        return "Result emails: off (TEN_EMAIL_ENABLED=off)"
    if not settings.resend_api_key:
        return "Result emails: not configured (set RESEND_API_KEY)"
    text = f"Result emails: on → {', '.join(settings.email_to)}"
    if uses_sandbox_sender(settings):
        text += " · WARNING: sandbox sender only reaches the Resend account owner; set TEN_EMAIL_FROM on a verified domain"
    return text


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------
def send(settings: Settings, *, subject: str, html: str, text: str, attachments: list[Attachment],
         idempotency_key: str | None = None, tags: dict[str, str] | None = None,
         client: httpx.Client | None = None) -> EmailResult:
    recipients = list(settings.email_to)
    if not settings.email_enabled:
        reason = "result emails are turned off." if settings.email_mode == "off" else "RESEND_API_KEY is not set."
        return EmailResult(skipped_reason=reason, recipients=recipients)
    if not settings.resend_api_key:
        return EmailResult(skipped_reason="RESEND_API_KEY is not set.", recipients=recipients)

    kept, dropped, total = [], [], 0
    for item in attachments:
        if total + len(item.content) > MAX_ATTACHMENT_BYTES:
            dropped.append(item.filename)
            continue
        kept.append(item)
        total += len(item.content)

    payload: dict = {"from": sender(settings), "to": recipients, "subject": subject, "html": html, "text": text}
    if settings.email_reply_to:
        payload["reply_to"] = settings.email_reply_to
    if kept:
        payload["attachments"] = [{"filename": a.filename, "content": base64.b64encode(a.content).decode("ascii")} for a in kept]
    if tags:
        payload["tags"] = [{"name": k, "value": _tag_value(v)} for k, v in tags.items()]
    headers = {"Authorization": f"Bearer {settings.resend_api_key}", "Content-Type": "application/json"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key

    try:
        poster = client.post if client is not None else httpx.post
        response = poster(RESEND_ENDPOINT, json=payload, headers=headers, timeout=TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        LOGGER.warning("Resend request failed: %s", exc.__class__.__name__)
        return EmailResult(error=f"could not reach Resend ({exc.__class__.__name__}).", recipients=recipients,
                           attachments_dropped=dropped, retryable=True)

    if response.status_code >= 400:
        detail = _error_detail(response)
        LOGGER.warning("Resend rejected the email (HTTP %s): %s", response.status_code, detail)
        return EmailResult(error=f"Resend returned HTTP {response.status_code}: {detail}{_hint(response.status_code, settings)}",
                           recipients=recipients, attachments_dropped=dropped,
                           retryable=response.status_code == 429 or response.status_code >= 500)
    try:
        message_id = response.json().get("id")
    except ValueError:
        message_id = None
    LOGGER.info("result email sent (id %s)", message_id)
    return EmailResult(sent=True, message_id=message_id, recipients=recipients, attachments_dropped=dropped)


def _tag_value(value: str) -> str:
    """Resend tags allow only ASCII letters, numbers, underscores and dashes."""
    cleaned = "".join(ch if ch.isascii() and (ch.isalnum() or ch in "_-") else "_" for ch in value)
    return cleaned[:256] or "unknown"


def _error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
        if isinstance(body, dict):
            return str(body.get("message") or body.get("error") or body)[:300]
    except ValueError:
        pass
    return (response.text or "")[:300]


def _hint(status: int, settings: Settings) -> str:
    if status in (401, 403):
        if uses_sandbox_sender(settings):
            return (" The sandbox sender (onboarding@resend.dev) only delivers to your Resend account's own email; "
                    "verify tencapital.group in Resend and set TEN_EMAIL_FROM.")
        return " Check RESEND_API_KEY and that the TEN_EMAIL_FROM domain is verified in Resend."
    if status == 422:
        return " Check TEN_EMAIL_FROM is a valid address on a verified domain."
    return ""


# ---------------------------------------------------------------------------
# Composing
# ---------------------------------------------------------------------------
def _deployment() -> str:
    domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
    return f"https://{domain}" if domain else "local instance"


def analysis_email(report: ScreeningReport) -> tuple[str, str, str]:
    """Subject, HTML and plain-text body for a completed analysis. All report text is HTML-escaped."""
    m, a, sc, g = report.meta, report.assessment, report.scoring, report.gate
    score = f"{sc.total:.1f}/100" if sc.complete else "provisional score"
    prefix = "[Confidential] " if report.sensitivity.confidential else ""
    subject = f"{prefix}TEN Screening: {m.company_name} - {sc.effective_rating} ({score})"[:250]

    rows = [
        ("Company", m.company_name),
        ("Website", m.website or "Not disclosed"),
        ("Source file", f"{m.source_filename} ({m.page_count} {'pages' if m.page_label_kind == 'PDF page' else 'slides'})"),
        ("Analyzed", m.analysis_date),
        ("Track", g.track_label),
        ("Stage gate", f"{g.status.value}: {' '.join(g.reasons)}"),
        ("Effective TEN fit", sc.effective_rating),
        ("Investability score", sc.status_label + (f" (underlying {sc.underlying_band})" if sc.underlying_band else "")),
        ("Investor readiness", f"{report.readiness.score} / 10"),
    ]
    if sc.override_applied:
        rows.append(("Eligibility override", sc.override_applied))
    if a.recommended_next_step:
        rows.append(("Recommended next step", a.recommended_next_step))

    def html_list(items: list[str], ordered: bool = True) -> str:
        tag = "ol" if ordered else "ul"
        return f"<{tag}>" + "".join(f"<li>{escape(i)}</li>" for i in items) + f"</{tag}>" if items else "<p>None supported by the materials.</p>"

    strengths = [p.headline for p in a.company_strengths]
    concerns = [p.headline for p in a.company_concerns]
    limitations = report.limitations[:6]
    table = "".join(
        f"<tr><td style='padding:6px 10px;border-bottom:1px solid #e2e8f0;font-weight:bold;white-space:nowrap;vertical-align:top'>{escape(k)}</td>"
        f"<td style='padding:6px 10px;border-bottom:1px solid #e2e8f0'>{escape(v)}</td></tr>" for k, v in rows
    )
    confidential = ("<p style='color:#E8553F;font-weight:bold'>Confidential — Internal Screening ("
                    + escape(", ".join(report.sensitivity.reasons)) + ")</p>") if report.sensitivity.confidential else ""
    html = f"""<div style="font-family:Helvetica,Arial,sans-serif;color:#1d2733;max-width:720px">
<p style="color:#E8553F;font-weight:bold;letter-spacing:.04em;margin:0">INVESTOR SCREENING REVIEW</p>
<h2 style="margin:4px 0 12px">{escape(m.company_name)}{': ' + escape(a.value_proposition_headline) if a.value_proposition_headline else ''}</h2>
{confidential}
<table style="border-collapse:collapse;font-size:14px;width:100%">{table}</table>
<h3>Investor verdict</h3>
<p>{('<b>' + escape(a.verdict_headline) + '</b> ') if a.verdict_headline else ''}{escape(a.investor_verdict)}</p>
<h3>Company strengths</h3>{html_list(strengths)}
<h3>Company concerns</h3>{html_list(concerns)}
<h3>Key actions before fundraising</h3>{html_list(a.fundraising_actions, ordered=False)}
<h3>Screening limitations</h3>{html_list(limitations, ordered=False)}
<p style="font-size:12px;color:#56657a">The full Investor Screening Review and supporting files are attached.
Generated by the TEN Screener ({escape(_deployment())}) with model {escape(m.model)}, app v{escape(m.app_version)}, run {escape(m.run_id[:12])}.
Initial screening based on supplied materials; not independent verification. For informational purposes only.
Does not constitute an offer to sell securities.</p></div>"""

    def text_list(items: list[str]) -> str:
        return "\n".join(f"  {i}. {x}" for i, x in enumerate(items, start=1)) or "  None supported by the materials."

    text = "\n".join([
        "INVESTOR SCREENING REVIEW", REPORT_TITLE, "",
        *(f"{k}: {v}" for k, v in rows), "",
        ("CONFIDENTIAL - INTERNAL SCREENING\n" if report.sensitivity.confidential else "")
        + "Investor verdict: " + " ".join(filter(None, [a.verdict_headline, a.investor_verdict])), "",
        "Company strengths:", text_list(strengths), "",
        "Company concerns:", text_list(concerns), "",
        "Key actions before fundraising:", text_list(a.fundraising_actions), "",
        "Screening limitations:", text_list(limitations), "",
        f"Generated by the TEN Screener ({_deployment()}), model {m.model}, app v{m.app_version}, run {m.run_id[:12]}.",
        "Initial screening based on supplied materials; not independent verification. For informational purposes "
        "only. Does not constitute an offer to sell securities.",
    ])
    return subject, html, text


def build_attachments(report: ScreeningReport, outputs: dict[str, bytes], wanted: tuple[str, ...]) -> list[Attachment]:
    stem = "".join(ch if ch.isalnum() else "_" for ch in report.meta.company_name)[:50].strip("_") or "company"
    out: list[Attachment] = []
    for key in wanted:
        if key == "json":
            content = json.dumps(json.loads(report.model_dump_json()), indent=2).encode("utf-8")
        else:
            content = outputs.get(key)
        if content:
            out.append(Attachment(filename=f"{stem}_TEN_{ATTACHMENT_NAMES[key]}", content=content))
    return out


def notify_analysis(report: ScreeningReport, outputs: dict[str, bytes], settings: Settings, *,
                    attempt: int = 0, client: httpx.Client | None = None) -> EmailResult:
    """Email a completed analysis to the configured recipients (default Info@tencapital.group).

    ``attempt`` > 0 marks an explicit manual retry, which gets its own idempotency key; automatic
    reruns reuse attempt 0, so Resend delivers each analysis at most once.
    """
    key = f"ten-screening-{report.meta.run_id}" + (f"-retry{attempt}" if attempt else "") if report.meta.run_id else None
    try:
        subject, html, text = analysis_email(report)
        return send(
            settings, subject=subject, html=html, text=text,
            attachments=build_attachments(report, outputs, settings.email_attachments),
            idempotency_key=key,
            tags={"type": "screening", "fit": report.scoring.effective_rating}, client=client,
        )
    except Exception as exc:  # noqa: BLE001 - a mail bug must never lose the report
        LOGGER.exception("could not compose or send the result email")
        return EmailResult(error=f"{exc.__class__.__name__} while composing the email.", recipients=list(settings.email_to))


def notify_failure(filename: str, stage: str, message: str, settings: Settings, *,
                   client: httpx.Client | None = None) -> EmailResult:
    """Tell the inbox an analysis failed, so a silent drop is never the outcome. Contains no deck content."""
    if not settings.email_on_failure:
        return EmailResult(skipped_reason="failure emails are turned off.", recipients=list(settings.email_to))
    try:
        subject = f"TEN Screening FAILED: {filename}"[:250]
        html = (f"<div style='font-family:Helvetica,Arial,sans-serif'><h3>Screening could not be completed</h3>"
                f"<p><b>File:</b> {escape(filename)}<br><b>Stage:</b> {escape(stage)}<br><b>Reason:</b> {escape(message)}</p>"
                f"<p style='font-size:12px;color:#56657a'>Sent by the TEN Screener ({escape(_deployment())}). "
                f"This is a processing failure, not an investment finding.</p></div>")
        text = (f"Screening could not be completed.\nFile: {filename}\nStage: {stage}\nReason: {message}\n"
                f"Sent by the TEN Screener ({_deployment()}). This is a processing failure, not an investment finding.")
        return send(settings, subject=subject, html=html, text=text, attachments=[], tags={"type": "failure"}, client=client)
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("could not send the failure email")
        return EmailResult(error=f"{exc.__class__.__name__} while sending the failure email.", recipients=list(settings.email_to))
