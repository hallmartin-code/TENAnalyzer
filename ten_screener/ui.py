"""TEN Capital web UI: design tokens, page CSS and small HTML fragments for the Streamlit app.

Visual language from the "Deck to One-Pager" design: dark navy surface, tri-colour
coral / amber / teal accents from the logo's three figures, Sora for display, Inter
for body, JetBrains Mono for labels. The colours also carry meaning across the app:
teal reads as strong, amber as moderate, coral as weak.

Every dynamic value inserted into HTML here is escaped by the helper that inserts it.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from html import escape

from ten_screener.config import ASSETS_DIR, ROOT_DIR

#: Streamlit's public directory: files here are served at /app/static/<name> (enableStaticServing).
STATIC_DIR = ROOT_DIR / "static"
FAVICON = STATIC_DIR / "favicon.png"


def favicon() -> str:
    """Favicon for st.set_page_config; falls back to an emoji if the file is missing from a deployment."""
    return str(FAVICON) if FAVICON.exists() else "📊"

TOKENS = {
    "navy_950": "#0B1526", "navy_900": "#101E33", "navy_800": "#16283F", "navy_700": "#1E354F",
    "coral": "#EE5A4E", "coral_soft": "#F0776C", "amber": "#F3A22A", "teal": "#35BEBB",
    "ink_100": "#F3F6FA", "ink_300": "#C4D0E0", "ink_500": "#7E90A8", "ink_600": "#5C6E86",
}

#: Semantic colour for each effective rating / gate status.
RATING_TONE = {
    "Strong Fit": "teal", "Moderate Fit": "amber", "Weak Fit": "coral_soft", "Likely Pass": "coral",
    "Meets Stage Gate": "teal", "Partially Meets": "amber", "Does Not Meet": "coral", "Cannot Determine": "ink_300",
}

CSS = """
<style>
:root{
  --navy-950:#0B1526; --navy-900:#101E33; --navy-800:#16283F; --navy-700:#1E354F;
  --coral:#EE5A4E; --coral-soft:#F0776C; --amber:#F3A22A; --teal:#35BEBB;
  --ink-100:#F3F6FA; --ink-300:#C4D0E0; --ink-500:#7E90A8; --ink-600:#5C6E86;
  --display:'Sora',sans-serif; --mono:'JetBrains Mono',monospace;
}
/* page: ambient tri-colour glow echoing the logo's three figures */
.stApp{ background:var(--navy-950); }
.stApp::before{
  content:""; position:fixed; inset:0; pointer-events:none; z-index:0;
  background:
    radial-gradient(480px 380px at 14% 8%, rgba(238,90,78,.16), transparent 60%),
    radial-gradient(480px 380px at 86% 6%, rgba(243,162,42,.13), transparent 60%),
    radial-gradient(560px 420px at 50% 100%, rgba(53,190,187,.14), transparent 60%);
}
[data-testid="stHeader"]{ background:transparent; }
.block-container{ max-width:1080px; padding-top:2.25rem; position:relative; z-index:1; }

/* brand lockup */
.ten-brand{ display:flex; align-items:center; gap:12px; margin:0 auto 26px; max-width:620px; padding-left:4px; }
.ten-brand img{ width:34px; height:34px; }
.ten-brand-word{ font-family:var(--display); font-weight:800; font-size:15px; letter-spacing:.04em; line-height:1.15;
  color:var(--ink-100); text-transform:uppercase; }
.ten-brand-word span{ display:block; font-weight:600; font-size:10px; letter-spacing:.22em; color:var(--ink-500); margin-top:2px; }

/* cards: the hero and every content panel are keyed containers */
.st-key-hero, [class*="st-key-panel"]{
  background:linear-gradient(180deg, var(--navy-900) 0%, var(--navy-800) 100%);
  border:1px solid var(--navy-700); border-radius:20px; position:relative; overflow:hidden;
  box-shadow:0 30px 60px -20px rgba(0,0,0,.55), inset 0 1px 0 rgba(255,255,255,.03);
}
.st-key-hero{ max-width:620px; margin:0 auto; padding:44px 44px 36px; }
[class*="st-key-panel"]{ padding:32px 36px 28px; margin-top:22px; }
.st-key-hero::after, [class*="st-key-panel"]::after{
  content:""; position:absolute; top:-2px; left:44px; right:44px; height:2px; border-radius:2px;
  background:linear-gradient(90deg, var(--coral), var(--amber), var(--teal));
}

/* type */
.ten-eyebrow{ display:flex; align-items:center; gap:8px; font-family:var(--mono); font-size:11px; letter-spacing:.14em;
  text-transform:uppercase; color:var(--teal); margin-bottom:14px; }
.ten-eyebrow::before{ content:""; width:6px; height:6px; border-radius:50%; background:var(--teal);
  box-shadow:0 0 0 3px rgba(53,190,187,.18); }
/* !important: Streamlit's own markdown h1 rules are more specific than a single class */
.ten-hero-title{ font-family:var(--display) !important; font-size:28px !important; font-weight:700 !important;
  line-height:1.25 !important; margin:0 0 12px !important; padding:0 !important; letter-spacing:-.01em; color:var(--ink-100); }
.ten-hero-title .arrow{ color:var(--ink-500); font-weight:400; margin:0 4px; }
.ten-hero-title .to{ background:linear-gradient(90deg, var(--coral-soft), var(--amber)); -webkit-background-clip:text;
  background-clip:text; color:transparent; }
.ten-lede{ color:var(--ink-300); font-size:15px; line-height:1.6; margin:0 0 26px; max-width:46ch; }
.ten-panel-title{ font-family:var(--display); font-size:21px; font-weight:700; color:var(--ink-100); margin:0 0 4px; }
.ten-panel-sub{ color:var(--ink-500); font-size:13.5px; margin:0 0 18px; }
.ten-section-label{ font-family:var(--mono); font-size:11px; letter-spacing:.14em; text-transform:uppercase;
  color:var(--ink-500); margin:18px 0 8px; }

/* dropzone */
.st-key-hero [data-testid="stFileUploaderDropzone"]{
  border:1.5px dashed var(--navy-700); border-radius:14px; padding:30px 24px; background:rgba(255,255,255,.015);
  transition:border-color .18s ease, background .18s ease;
}
.st-key-hero [data-testid="stFileUploaderDropzone"]:hover{ border-color:var(--teal); background:rgba(53,190,187,.05); }
.st-key-hero [data-testid="stFileUploaderDropzoneInstructions"] small{ font-family:var(--mono); color:var(--ink-500); }

/* primary CTA (also used by the primary download button) */
.stButton button[kind="primary"], .stDownloadButton button[kind="primary"],
[data-testid="stBaseButton-primary"]{
  background:linear-gradient(90deg, var(--coral) 0%, var(--coral-soft) 45%, var(--amber) 100%);
  color:#17130E !important; border:none; border-radius:12px; font-family:var(--display); font-weight:700;
  letter-spacing:.01em; padding:.85rem 1.2rem; box-shadow:0 10px 24px -10px rgba(238,90,78,.45);
  transition:filter .15s ease, transform .15s ease;
}
.stButton button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover{ filter:brightness(1.06); transform:translateY(-1px); }
.stButton button[kind="primary"] p, [data-testid="stBaseButton-primary"] p{ color:#17130E; font-weight:700; }
.stButton button[kind="primary"]:disabled, [data-testid="stBaseButton-primary"]:disabled{
  opacity:.45; filter:grayscale(.35); transform:none; box-shadow:none; }
button:focus-visible{ outline:2px solid var(--teal) !important; outline-offset:2px; }
.st-key-hero .stButton{ margin-top:6px; }

/* chips (extraction status inside the hero) */
.ten-chips{ display:flex; flex-wrap:wrap; gap:8px; margin:12px 0 4px; }
.ten-chip{ font-family:var(--mono); font-size:11.5px; padding:4px 10px; border-radius:999px; border:1px solid var(--navy-700);
  color:var(--ink-300); background:rgba(11,21,38,.55); }
.ten-chip.ok{ border-color:rgba(53,190,187,.45); color:var(--teal); }
.ten-chip.warn{ border-color:rgba(243,162,42,.45); color:var(--amber); }
.ten-chip.bad{ border-color:rgba(238,90,78,.5); color:var(--coral-soft); }

/* disclosure + footer */
.ten-disclosure{ margin-top:22px; padding-top:18px; border-top:1px solid var(--navy-700); font-size:12px; line-height:1.6; color:var(--ink-500); }
.ten-disclosure code{ font-family:var(--mono); background:var(--navy-950); border:1px solid var(--navy-700); color:var(--ink-300);
  padding:2px 6px; border-radius:5px; font-size:11.5px; }
.ten-footer{ text-align:center; margin:30px 0 8px; font-family:var(--mono); font-size:11px; letter-spacing:.08em;
  color:var(--ink-600); text-transform:uppercase; }

/* stepper */
.ten-steps{ display:flex; gap:8px; justify-content:center; flex-wrap:wrap; margin:24px auto 0; max-width:720px; }
.ten-step{ display:flex; align-items:center; gap:8px; font-family:var(--mono); font-size:11px; letter-spacing:.08em;
  text-transform:uppercase; color:var(--ink-600); padding:6px 12px; border-radius:999px; border:1px solid var(--navy-700);
  background:rgba(16,30,51,.6); }
.ten-step b{ display:inline-flex; width:18px; height:18px; border-radius:50%; align-items:center; justify-content:center;
  font-size:10px; background:var(--navy-700); color:var(--ink-300); }
.ten-step.done{ color:var(--ink-300); } .ten-step.done b{ background:var(--teal); color:var(--navy-950); }
.ten-step.current{ color:var(--ink-100); border-color:var(--amber); } .ten-step.current b{ background:var(--amber); color:var(--navy-950); }

/* stat tiles */
.ten-tiles{ display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:12px; margin:6px 0 18px; }
.ten-tile{ background:rgba(11,21,38,.55); border:1px solid var(--navy-700); border-top:2px solid var(--tone, var(--navy-700));
  border-radius:14px; padding:14px 16px 16px; }
.ten-tile-label{ font-family:var(--mono); font-size:10.5px; letter-spacing:.12em; text-transform:uppercase; color:var(--ink-500); }
.ten-tile-value{ font-family:var(--display); font-weight:700; font-size:22px; line-height:1.2; margin-top:6px; color:var(--tone, var(--ink-100)); }
.ten-tile-sub{ font-size:12px; color:var(--ink-500); margin-top:4px; line-height:1.4; }

/* widgets inside dark cards */
[data-testid="stExpander"] details{ border:1px solid var(--navy-700); border-radius:12px; background:rgba(11,21,38,.35); }
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3{ font-family:var(--display); }

@media (prefers-reduced-motion: reduce){ *{ transition:none !important; } }
@media (max-width:480px){
  .st-key-hero{ padding:32px 24px 28px; } [class*="st-key-panel"]{ padding:26px 20px 22px; }
  .ten-hero-title{ font-size:23px !important; }
}
</style>
"""


@lru_cache(maxsize=1)
def _mark_data_uri() -> str:
    path = ASSETS_DIR / "ten_mark.png"
    try:
        return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return ""


def md(text: object) -> str:
    """Escape model, deck and user text for st.markdown/st.write.

    Without this, "$1.2M ... $4M" renders as LaTeX math and stray * or _ break formatting.
    """
    out = str(text or "")
    for ch in "\\`*_$[]#|~":
        out = out.replace(ch, "\\" + ch)
    return out


def brand() -> str:
    mark = _mark_data_uri()
    img = f'<img src="{mark}" alt="TEN Capital Network logo">' if mark else ""
    return f'<div class="ten-brand">{img}<div class="ten-brand-word">Ten Capital<span>Network</span></div></div>'


def hero_header(eyebrow: str, title: str, highlight: str, lede: str) -> str:
    return (f'<div class="ten-eyebrow">{escape(eyebrow)}</div>'
            f'<h1 class="ten-hero-title">{escape(title)}<span class="arrow">&rarr;</span>'
            f'<span class="to">{escape(highlight)}</span></h1><p class="ten-lede">{escape(lede)}</p>')


def panel_header(title: str, subtitle: str = "") -> str:
    sub = f'<p class="ten-panel-sub">{escape(subtitle)}</p>' if subtitle else ""
    return f'<div class="ten-panel-title">{escape(title)}</div>{sub}'


def section_label(text: str) -> str:
    return f'<div class="ten-section-label">{escape(text)}</div>'


def chips(items: list[tuple[str, str]]) -> str:
    """items: (text, tone) with tone in "", "ok", "warn", "bad"."""
    return '<div class="ten-chips">' + "".join(f'<span class="ten-chip {escape(t)}">{escape(x)}</span>' for x, t in items) + "</div>"


def stepper(current: int) -> str:
    steps = ["Upload", "Review extraction", "Screen", "Results"]
    out = []
    for i, name in enumerate(steps, start=1):
        cls = "done" if i < current else "current" if i == current else ""
        out.append(f'<div class="ten-step {cls}"><b>{"✓" if i < current else i}</b>{escape(name)}</div>')
    return '<div class="ten-steps">' + "".join(out) + "</div>"


def tiles(items: list[tuple[str, str, str, str | None]]) -> str:
    """items: (label, value, sub, tone_key) - tone_key from TOKENS or None."""
    cells = []
    for label, value, sub, tone in items:
        style = f' style="--tone:{TOKENS[tone]}"' if tone in TOKENS else ""
        sub_html = f'<div class="ten-tile-sub">{escape(sub)}</div>' if sub else ""
        cells.append(f'<div class="ten-tile"{style}><div class="ten-tile-label">{escape(label)}</div>'
                     f'<div class="ten-tile-value">{escape(value)}</div>{sub_html}</div>')
    return '<div class="ten-tiles">' + "".join(cells) + "</div>"


def disclosure(email_to: tuple[str, ...] | None) -> str:
    base = "The uploaded file is processed on the server in a temporary folder that is deleted after extraction."
    if email_to:
        codes = ", ".join(f"<code>{escape(a)}</code>" for a in email_to)
        return f'<div class="ten-disclosure">{base} A copy of every screening result is emailed to {codes}.</div>'
    return f'<div class="ten-disclosure">{base} Result emails are not configured.</div>'


def footer() -> str:
    return '<div class="ten-footer">Powered by TEN Capital Network</div>'
