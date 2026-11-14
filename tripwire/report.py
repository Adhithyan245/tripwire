"""Human-readable audit report: one self-contained HTML file built from findings.json.

Everything on the page comes from findings.json; nothing is computed or inferred here. No scripts, no external files,
so it opens anywhere, prints cleanly, and can go to a reviewer or a judge as-is.

    python -m driftwire report out/findings.json            -> out/findings.html
"""
from __future__ import annotations

import html
import json
import pathlib

VERDICT_CLASS = {"Ready": "ok", "Conditional": "warn", "Insufficient Evidence": "warn", "Blocked": "bad",
                 "Proceed": "ok", "Fix a problem": "warn", "Narrow the question": "warn", "Stop": "bad"}
SEV_CLASS = {"high": "bad", "medium": "warn", "low": "muted", "none": "muted"}

CSS = """
:root{--bg:#ffffff;--fg:#1f2328;--muted:#59636e;--line:#d1d9e0;--card:#f6f8fa;
--ok:#1a7f37;--ok-bg:#dafbe1;--warn:#9a6700;--warn-bg:#fff8c5;--bad:#cf222e;--bad-bg:#ffebe9}
@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--fg:#e6edf3;--muted:#9198a1;--line:#3d444d;--card:#151b23;
--ok:#3fb950;--ok-bg:#12261e;--warn:#d29922;--warn-bg:#272115;--bad:#f85149;--bad-bg:#2d1517}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1040px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:32px 0 8px;border-bottom:1px solid var(--line);padding-bottom:6px}
h3{font-size:15px;margin:0 0 4px}.muted{color:var(--muted)}.small{font-size:13px}
.banner{border:1px solid var(--line);border-radius:10px;padding:16px;margin:16px 0;display:flex;gap:16px;
align-items:center;flex-wrap:wrap}.pill{display:inline-block;border-radius:999px;padding:2px 10px;font-weight:600;
font-size:13px;white-space:nowrap}.ok{color:var(--ok);background:var(--ok-bg)}.warn{color:var(--warn);
background:var(--warn-bg)}.bad{color:var(--bad);background:var(--bad-bg)}.muted.pill{background:var(--card)}
.big{font-size:20px;padding:6px 16px}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:14px 16px;margin:10px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px}
.kv{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:8px 10px}
.kv b{display:block;font-size:18px}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);
font-weight:600}code{font:12px ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:anywhere}
.label{border:1px solid var(--line);border-radius:8px;padding:8px 12px;font-size:13px;margin-top:8px}
details summary{cursor:pointer;color:var(--muted);font-size:13px;margin-top:6px}
@media print{details{display:block}details>*{display:block}}
"""


def esc(v) -> str:
    return html.escape("" if v is None else str(v))


def pill(text: str, cls: str, big: bool = False) -> str:
    return f'<span class="pill {cls}{" big" if big else ""}">{esc(text)}</span>'


def kv_table(d: dict) -> str:
    rows = "".join(f"<tr><th>{esc(k)}</th><td><code>{esc(json.dumps(v) if isinstance(v, (dict, list)) else v)}"
                   f"</code></td></tr>" for k, v in d.items())
    return f'<div class="scroll"><table>{rows}</table></div>'


def before_after(a: dict) -> str:
    b, f = a.get("before") or {}, a.get("after") or {}
    keys = list(dict.fromkeys(list(b) + list(f)))
    if not keys:
        return ""
    rows = []
    for k in keys:
        x, y = b.get(k), f.get(k)
        moved = " ← moved" if x != y else ""
        rows.append(f"<tr><th>{esc(k)}</th><td><code>{esc(json.dumps(x))}</code></td>"
                    f"<td><code>{esc(json.dumps(y))}</code></td><td class='muted'>{moved}</td></tr>")
    return ('<div class="scroll"><table><tr><th>result</th><th>before</th><th>after</th><th></th></tr>'
            + "".join(rows) + "</table></div>")


def evidence_table(ev: list[dict]) -> str:
    def _id(e):
        code = f"<code>{esc(e.get('id'))}</code>"
        url = e.get("url") or ""
        return (f"<a href='{esc(url)}' target='_blank' rel='noopener' title='tissue slide (IDC viewer)'>{code}</a>"
                if url.startswith("https://") else code)
    rows = "".join(f"<tr><td>{esc(e.get('kind'))}</td><td>{_id(e)}</td>"
                   f"<td>{esc(e.get('release', ''))}</td><td>{esc(e.get('file', ''))}</td>"
                   f"<td>{esc(e.get('note', ''))}</td></tr>" for e in ev)
    head = "<tr><th>kind</th><th>id</th><th>release</th><th>file</th><th>note</th></tr>"
    table = f'<div class="scroll"><table>{head}{rows}</table></div>'
    if len(ev) > 8:
        return f"<details><summary>All {len(ev)} evidence records</summary>{table}</details>"
    return table


def render(doc: dict) -> str:
    v = doc.get("verdict", "")
    rel = doc.get("data", {}).get("releases", [])
    names = " → ".join(esc(r.get("name")) for r in rel)
    findings, analyses = doc.get("findings", []), doc.get("analyses", [])
    repairs, questions = doc.get("repairs", []), doc.get("questions", [])
    review = [f for f in findings if f.get("needs_human_review")]
    p = doc.get("producer", {})

    out = [f"<h1>Driftwire audit report</h1><div class='muted'>{esc(p.get('team'))} · {esc(p.get('product'))} · "
           f"{esc(doc.get('data', {}).get('dataset', ''))} · releases {names}</div>"]
    out.append(f"<div class='banner'>{pill(v, VERDICT_CLASS.get(v, 'muted'), big=True)}<div><b>{esc(doc.get('question'))}"
               f"</b><div class='small muted'>Overall verdict: the most serious verdict among the results below.</div>"
               f"</div></div>")
    out.append("<div class='grid'>" + "".join(
        f"<div class='kv'><b>{n}</b><span class='small muted'>{esc(t)}</span></div>" for n, t in (
            (len(findings), "findings"), (len(review), "need human review"),
            (len(repairs), "proposed repairs (none applied)"), (len(analyses), "analyses checked"))) + "</div>")
    out.append("<div class='label'><b>Research use only.</b> Not a diagnosis, treatment advice, risk score or clinical "
               "claim. Every swap or duplicate needs a curator's review; repairs are proposals and are never applied "
               "automatically.</div>")

    plan = doc.get("next_steps") or {}
    if plan.get("steps"):
        rows = "".join(f"<li><b>{esc(s['who'])}:</b> {esc(s['action'])}"
                       + (f"<div class='small muted'>{esc(s['why'])}</div>" if s.get("why") else "")
                       + (f"<div class='small'><b>Effect:</b> {esc(s['effect'])}</div>" if s.get("effect") else "")
                       + "</li>" for s in plan["steps"])
        out.append(f"<h2>What to do next</h2><ol>{rows}</ol>")
        if plan.get("all_repairs_together"):
            out.append(f"<p class='small'><b>All repairs approved together:</b> {esc(plan['all_repairs_together'])}</p>")
        out.append("<h2>What Driftwire can't tell you</h2><ul>"
                   + "".join(f"<li>{esc(c)}</li>" for c in plan.get("cannot_tell", [])) + "</ul>")

    if questions:
        out.append("<h2>Research questions</h2><p class='small muted'>The same release can be fine for one question and "
                   "not for another. Each verdict cites the rule that produced it.</p>")
        rows = []
        for q in questions:
            cov = q.get("coverage", {})
            gaps = [c for k in ("skipped", "unavailable", "missing") for c in cov.get(k, [])]
            rows.append(f"<tr><td>{pill(q.get('verdict'), VERDICT_CLASS.get(q.get('verdict'), 'muted'))}</td>"
                        f"<td><b>{esc(q.get('title'))}</b><div class='small muted'>{esc(q.get('intended_use'))} · "
                        f"{esc(q.get('cohort'))}</div></td><td>{esc(q.get('why'))}"
                        + (f"<div class='small muted'>Checks not run (not a pass): {esc(', '.join(gaps))}</div>" if gaps else "")
                        + "".join(f"<div class='small'><b>{esc(c.get('name'))}</b> ({esc(c.get('status'))}): "
                                  f"{esc(c.get('summary'))}" + (f" <b>Fix:</b> {esc(c['fix'])}" if c.get("fix") else "")
                                  + "</div>" for c in q.get("checks", [])
                                  if c.get("status") not in ("skipped", "unavailable"))
                        + f"</td><td>{esc(', '.join(q.get('relevant_findings', [])) or '—')}</td></tr>")
        out.append("<div class='scroll'><table><tr><th>verdict</th><th>question</th><th>why</th><th>findings</th></tr>"
                   + "".join(rows) + "</table></div>")

    out.append("<h2>Analyses</h2>")
    for a in analyses:
        ic = a.get("input_changes")
        out.append(f"<div class='card'><h3>{pill(a.get('verdict'), VERDICT_CLASS.get(a.get('verdict'), 'muted'))} "
                   f"{esc(a.get('id'))} · {esc(a.get('title', ''))} <span class='muted small'>({esc(a.get('status'))})"
                   f"</span></h3><div>{esc(a.get('why'))}</div><div class='small muted'>{esc(a.get('impact', ''))}</div>"
                   + (f"<div class='small muted'>Reads {esc(', '.join(a.get('inputs', [])))} · cohort: {esc(a.get('cohort'))}</div>"
                      if a.get("inputs") else "")
                   + (f"<div class='small'>Sample by sample, what it reads: {ic.get('identical')} identical, "
                      f"{ic.get('added')} entered, {ic.get('removed')} left, {ic.get('values_changed')} changed value.</div>"
                      if ic else "")
                   + before_after(a) + "</div>")

    out.append("<h2>Findings</h2>")
    if not findings:
        out.append("<p>No changes found between the releases.</p>")
    for f in findings:
        sev = f.get("severity", "")
        out.append(f"<div class='card'><h3>{esc(f.get('id'))} · {esc(f.get('kind'))} {pill(sev + ' severity', SEV_CLASS.get(sev, 'muted'))} "
                   f"{pill('confidence ' + f.get('confidence', ''), 'muted')}"
                   + (f" {pill('needs human review', 'warn')}" if f.get("needs_human_review") else "")
                   + f"</h3><div>{esc(f.get('summary'))}</div>"
                   + (f"<div class='small'><b>Why this severity:</b> {esc(f['severity_reason'])}</div>" if f.get("severity_reason") else "")
                   + f"<div class='small muted'>Affects: {esc(', '.join(f.get('affects_analyses', [])) or 'none')} · "
                     f"not affected: {esc(', '.join(f.get('not_affected_analyses', [])) or 'none')}</div>"
                   + (f"<div class='small muted'><b>Limitation:</b> {esc(f['limitation'])}</div>" if f.get("limitation") else "")
                   + evidence_table(f.get("evidence", [])) + "</div>")

    if repairs:
        out.append("<h2>Proposed repairs</h2><p class='small muted'>Proposals for a reviewer to approve, reject or ask "
                   "more about. Nothing here has been applied.</p>")
        def _pv(r):
            pv = r.get("preview") or {}
            lines = [esc(x.get("summary")) for x in pv.get("analyses", [])]
            return "<br>".join(lines) or f"<span class='muted'>{esc(pv.get('note', ''))}</span>"
        rows = "".join(f"<tr><td><code>{esc(r.get('id'))}</code></td><td>{esc(r.get('action'))}</td>"
                       f"<td>{esc(', '.join(r.get('addresses', [])))}</td><td>{esc(r.get('justification'))}</td>"
                       f"<td>{len(r.get('targets', []))}</td><td class='small'>{_pv(r)}</td></tr>" for r in repairs)
        out.append("<div class='scroll'><table><tr><th>id</th><th>action</th><th>for</th><th>justification</th>"
                   f"<th>targets</th><th>if approved (on a copy)</th></tr>{rows}</table></div>")
        allp = doc.get("repair_preview_all") or {}
        if allp.get("analyses"):
            out.append("<div class='card'><b>If every proposed repair were approved</b> "
                       f"({esc(', '.join(allp.get('repairs', [])))}):<br>"
                       + "<br>".join(f"{pill(x.get('verdict_if_approved'), VERDICT_CLASS.get(x.get('verdict_if_approved'), 'muted'))} "
                                     f"{esc(x.get('summary'))}" for x in allp["analyses"])
                       + f"<div class='small muted'>{esc(allp.get('note', ''))}</div></div>")

    if doc.get("decisions"):
        rows = "".join(f"<tr><td><code>{esc(d.get('repair_id'))}</code></td><td>{esc(d.get('decision'))}</td>"
                       f"<td>{esc(d.get('reviewer_role'))}</td><td>{esc(d.get('reason'))}</td></tr>" for d in doc["decisions"])
        out.append("<h2>Review decisions</h2><div class='scroll'><table><tr><th>repair</th><th>decision</th>"
                   f"<th>reviewer</th><th>reason</th></tr>{rows}</table></div>")

    out.append("<h2>Settings and data</h2>")
    if doc.get("settings"):
        out.append("<p class='small muted'>Tolerances and minimums are prototype policy choices, not clinical standards."
                   "</p>" + kv_table(doc["settings"]))
    for r in rel:
        rows = "".join(f"<tr><td>{esc(x.get('file'))}</td><td><code>{esc(x.get('sha256'))}</code></td>"
                       f"<td>{esc(x.get('hash_of', 'file'))}</td></tr>" for x in r.get("files", []))
        out.append(f"<h3 style='margin-top:12px'>Release {esc(r.get('name'))}</h3><div class='scroll'><table>"
                   f"<tr><th>file</th><th>sha256</th><th>hash of</th></tr>{rows}</table></div>")
    out.append(f"<p class='small muted'>Generated by {esc(p.get('tool', 'Driftwire'))} from findings.json "
               f"(shared format v{esc(doc.get('format_version'))}).</p>")

    title = f"Driftwire report: {esc(rel[-1].get('name') if rel else '')}"
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><title>{title}</title><style>{CSS}</style></head>"
            f"<body><main>{''.join(out)}</main></body></html>")


def write_report(doc: dict, path) -> pathlib.Path:
    path = pathlib.Path(path)
    path.write_text(render(doc), encoding="utf-8")
    return path
