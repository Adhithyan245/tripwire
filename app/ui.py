"""Visual layer for the dashboard: one stylesheet plus small HTML building blocks.

Status colors are reserved for verdicts and always come with an icon and a word, never color alone.
All text passed in is escaped.
"""
from __future__ import annotations

import html

STATUS = {  # verdict -> (css class, icon, ink color)
    "Ready": ("good", "✓", "#36bb72"),
    "Conditional": ("warn", "!", "#d99400"),
    "Insufficient Evidence": ("serious", "?", "#f39976"),
    "Blocked": ("critical", "✕", "#ee665b"),
}
SEVERITY = {"high": "critical", "medium": "warn", "low": "muted", "none": "muted"}

CSS = """
<style>
:root{--ink:#f3f1ec;--ink-2:#c5c6ca;--ink-3:#a2a5ae;--line:#5a5f6b;--card:#171a21;--surface:#0c0e12;
--accent:#ff8a76;--good:#36bb72;--warn:#fab219;--serious:#f39976;--critical:#ee665b;}
/* chrome */
[data-testid="stHeaderActionElements"], .stDeployButton, [data-testid="stAppDeployButton"]{display:none!important}
header[data-testid="stHeader"]{background:transparent}
.block-container{padding-top:1.6rem!important;max-width:1180px}
h1,h2,h3,h4{letter-spacing:-0.01em}
[data-testid="stSidebar"]{border-right:1px solid var(--line)}
[data-testid="stSidebar"] .block-container{padding-top:1rem!important}
button[kind="primary"], [data-testid="stBaseButton-primary"]{color:#0c0e12!important}
/* tabs */
.stTabs [data-baseweb="tab-list"]{gap:4px;border-bottom:1px solid var(--line)}
.stTabs [data-baseweb="tab"]{font-size:15px;font-weight:600;padding:10px 14px;color:var(--ink-2)}
.stTabs [aria-selected="true"]{color:var(--ink)}
/* bordered containers become cards */
[data-testid="stVerticalBlockBorderWrapper"]{border-radius:14px!important;border-color:var(--line)!important;
background:var(--card)}
/* brand */
.tw-brand{display:flex;align-items:center;gap:10px;margin:0 0 4px}
.tw-mark{width:32px;height:32px;border-radius:9px;background:#f3f1ec;position:relative;display:grid;place-items:center}
.tw-mark:before{content:"";width:21px;height:3px;border-radius:3px;background:#ee665b}
.tw-mark:after{content:"";position:absolute;width:8px;height:8px;border-radius:50%;background:#fab219}
.tw-name{font-weight:800;font-size:19px;color:var(--ink)}
.tw-sub{font-size:12.5px;color:var(--ink-3);margin-bottom:6px}
.tw-sec{font-size:11.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-3);
margin:14px 0 2px}
/* app bar */
.tw-bar{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:6px}
.tw-title{font-size:30px;font-weight:800;color:var(--ink);line-height:1.15}
.tw-tag{font-size:15px;color:var(--ink-2);margin-top:2px}
.tw-chip{font-size:12px;font-weight:600;color:var(--ink-2);border:1px solid var(--line);border-radius:999px;
padding:4px 10px;background:var(--card);white-space:nowrap}
/* pills */
.tw-pill{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:3px 10px 3px 4px;font-weight:700;
font-size:13px;color:var(--ink);border:1px solid;white-space:nowrap;vertical-align:middle}
.tw-pill i{font-style:normal;width:18px;height:18px;border-radius:50%;display:grid;place-items:center;color:#0c0e12;
font-size:11px;font-weight:800}
.tw-pill.good{background:#0ca30c14;border-color:#0ca30c55}.tw-pill.good i{background:var(--good)}
.tw-pill.warn{background:#fab21922;border-color:#fab21988}.tw-pill.warn i{background:#d99400}
.tw-pill.serious{background:#ec835a1f;border-color:#ec835a88}.tw-pill.serious i{background:var(--serious)}
.tw-pill.critical{background:#d03b3b14;border-color:#d03b3b66}.tw-pill.critical i{background:var(--critical)}
.tw-pill.muted{background:#252831;border-color:var(--line)}.tw-pill.muted i{background:#6f737c}
/* verdict hero */
.tw-hero{border:1px solid var(--line);border-left:8px solid var(--c);border-radius:16px;background:var(--card);
padding:20px 22px;display:flex;gap:18px;align-items:flex-start;box-shadow:0 1px 2px #0000000a}
.tw-hero .ico{flex:none;width:52px;height:52px;border-radius:14px;background:var(--c);color:#0c0e12;display:grid;
place-items:center;font-size:26px;font-weight:800}
.tw-hero .lbl{font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-3)}
.tw-hero .v{font-size:30px;font-weight:800;color:var(--ink);line-height:1.1;margin:2px 0 4px}
.tw-hero .m{font-size:15px;color:var(--ink-2)}
.tw-hero .q{font-size:15px;color:var(--ink);font-weight:600;margin-top:10px}
.tw-hero .meta{font-size:12.5px;color:var(--ink-3);margin-top:4px}
/* stat tiles */
.tw-tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:12px 0 4px}
.tw-tile{border:1px solid var(--line);border-radius:14px;background:var(--card);padding:12px 14px}
.tw-tile b{display:block;font-size:26px;font-weight:800;color:var(--ink);line-height:1.1}
.tw-tile span{font-size:12.5px;color:var(--ink-2)}
/* notice */
.tw-note{border:1px solid var(--line);background:#22252d;border-radius:12px;padding:9px 14px;font-size:13.5px;
color:var(--ink-2);margin:10px 0 6px}
.tw-note b{color:var(--ink)}
/* card header */
.tw-ch{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.tw-ct{font-size:16.5px;font-weight:700;color:var(--ink)}
.tw-cm{font-size:12.5px;color:var(--ink-3);margin-top:3px}
.tw-cb{font-size:14.5px;color:var(--ink);margin-top:8px}
/* home */
.tw-home{border:1px solid var(--line);border-radius:20px;padding:28px 28px 22px;margin-bottom:14px;
background:linear-gradient(100deg,#241c20 0%,#171a21 62%);border-top:3px solid #ff7059}
.tw-home h1{font-size:34px;line-height:1.15;margin:0 0 8px;font-weight:800;color:var(--ink)}
.tw-home p{font-size:16px;color:var(--ink-2);max-width:760px;margin:0}
.tw-step{font-size:12px;font-weight:700;color:var(--accent);letter-spacing:.06em;text-transform:uppercase}
.tw-legend{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin-top:6px}
.tw-legend div{border:1px solid var(--line);border-radius:14px;padding:12px 14px;background:var(--card);
font-size:13.5px;color:var(--ink-2)}
.tw-legend .tw-pill{margin-bottom:6px}
@media (max-width:640px){.tw-hero{flex-direction:column}.tw-title{font-size:24px}.tw-home h1{font-size:26px}}
</style>
"""


def esc(s) -> str:
    return html.escape("" if s is None else str(s))


def pill(verdict: str) -> str:
    cls, icon, _ = STATUS.get(verdict, ("muted", "•", "#9a9993"))
    return f'<span class="tw-pill {cls}"><i>{icon}</i>{esc(verdict)}</span>'


def sev_pill(severity: str) -> str:
    cls = SEVERITY.get(severity, "muted")
    icon = {"critical": "!", "warn": "!", "muted": "·"}[cls]
    return f'<span class="tw-pill {cls}"><i>{icon}</i>{esc(severity)} severity</span>'


def brand(team: str) -> str:
    return (f'<div class="tw-brand"><div class="tw-mark" aria-hidden="true"></div><div class="tw-name">Driftwire</div></div>'
            f'<div class="tw-sub">Cohort Control Tower · team {esc(team)}</div>')


def section(label: str) -> str:
    return f'<div class="tw-sec">{esc(label)}</div>'


def app_bar() -> str:
    return ('<div class="tw-bar"><div><div class="tw-title">Release check</div>'
            '<div class="tw-tag">Same sample count, different data. What changed, what it breaks, and what it can\'t '
            'see.</div></div><span class="tw-chip">Research use only</span></div>')


def hero(verdict: str, meaning: str, question: str, meta: str) -> str:
    cls, icon, color = STATUS.get(verdict, ("muted", "•", "#9a9993"))
    return (f'<div class="tw-hero" style="--c:{color}"><div class="ico">{icon}</div><div>'
            f'<div class="lbl">Overall verdict</div><div class="v">{esc(verdict)}</div>'
            f'<div class="m">{esc(meaning)}</div><div class="q">{esc(question)}</div>'
            f'<div class="meta">{esc(meta)}</div></div></div>')


def tiles(items: list[tuple[str, str]]) -> str:
    return '<div class="tw-tiles">' + "".join(f'<div class="tw-tile"><b>{esc(v)}</b><span>{esc(k)}</span></div>'
                                              for k, v in items) + "</div>"


def note(bold: str, text: str) -> str:
    return f'<div class="tw-note"><b>{esc(bold)}</b> {esc(text)}</div>'


def card_head(verdict: str, title: str, meta: str = "", body: str = "") -> str:
    return (f'<div class="tw-ch">{pill(verdict)}<span class="tw-ct">{esc(title)}</span></div>'
            + (f'<div class="tw-cm">{esc(meta)}</div>' if meta else "")
            + (f'<div class="tw-cb">{esc(body)}</div>' if body else ""))


def home(headline: str, text: str) -> str:
    return f'<div class="tw-home"><h1>{esc(headline)}</h1><p>{esc(text)}</p></div>'


def legend(items: dict[str, str]) -> str:
    return '<div class="tw-legend">' + "".join(f'<div>{pill(k)}<br>{esc(v)}</div>' for k, v in items.items()) + "</div>"


PLAN_CSS = """
<style>
.tw-plan{border:1px solid var(--line);border-radius:16px;background:var(--card);padding:16px 18px;margin:12px 0}
.tw-plan h4{margin:0 0 10px;font-size:17px;color:var(--ink)}
.tw-st{display:grid;grid-template-columns:28px 1fr;gap:10px;padding:10px 0;border-top:1px solid var(--line)}
.tw-st:first-of-type{border-top:none}
.tw-n{width:26px;height:26px;border-radius:50%;background:var(--accent);color:#0c0e12;font-weight:800;font-size:13px;
display:grid;place-items:center}
.tw-who{display:inline-block;font-size:11.5px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;
color:var(--accent);margin-right:6px}
.tw-act{font-weight:650;color:var(--ink);font-size:14.5px}
.tw-why{font-size:13px;color:var(--ink-2);margin-top:2px}
.tw-eff{font-size:13px;color:var(--ink);margin-top:4px;background:#2a78d60d;border-radius:8px;padding:4px 8px}
.tw-cant{font-size:13.5px;color:var(--ink-2);margin:4px 0 0 18px}
</style>
"""


def plan(p: dict, limit: int = 6) -> str:
    steps = p.get("steps", [])[:limit]
    rows = "".join(
        f'<div class="tw-st"><div class="tw-n">{s["step"]}</div><div><span class="tw-who">{esc(s["who"])}</span>'
        f'<span class="tw-act">{esc(s["action"])}</span><div class="tw-why">{esc(s.get("why", ""))}</div>'
        + (f'<div class="tw-eff"><b>If approved:</b> {esc(s["effect"])}</div>' if s.get("effect")
           and s["who"] == "Curator" else
           (f'<div class="tw-eff"><b>Fix:</b> {esc(s["effect"])}</div>' if s.get("effect") else ""))
        + "</div></div>" for s in steps)
    more = len(p.get("steps", [])) - len(steps)
    together = (f'<div class="tw-why" style="margin-top:8px"><b>All repairs approved together:</b> '
                f'{esc(p["all_repairs_together"])}</div>' if p.get("all_repairs_together") else "")
    return (PLAN_CSS + f'<div class="tw-plan"><h4>What to do next</h4>{rows}'
            + (f'<div class="tw-why">…and {more} more in the Review and Verdicts tabs.</div>' if more > 0 else "")
            + together + "</div>")


def cannot_tell(p: dict) -> str:
    items = "".join(f"<li>{esc(c)}</li>" for c in p.get("cannot_tell", []))
    return f'<div class="tw-plan"><h4>What Driftwire can\'t tell you</h4><ul class="tw-cant">{items}</ul></div>'
