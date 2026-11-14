"""Driftwire as a library: one call from a notebook or a pipeline.

    import driftwire
    result = driftwire.check("data/release-A", "data/release-B", question="predict_er_from_protein")
    result.verdict              # "Ready" | "Conditional" | "Blocked" | "Insufficient Evidence"
    result.findings             # what changed, with evidence
    result.next_steps           # the ordered plan, and what Driftwire can't tell you
    result.save("findings.json")
    result                      # in Jupyter: a readable summary

Same engine and same output as `python -m driftwire diff`: the detector, impact map, reruns, verdicts, question cards
and findings.json in the shared v0.2 format. Nothing here applies a repair or changes data. Research use only.
"""
from __future__ import annotations

import html
import json
import pathlib
import time
from dataclasses import dataclass, field

from .config import VERDICT_ORDER
from .detect import detect_changes
from .findings import build
from .release import Release

ICON = {"Ready": "✓", "Conditional": "!", "Blocked": "✕", "Insufficient Evidence": "?"}
COLOR = {"Ready": "#0ca30c", "Conditional": "#fab219", "Blocked": "#d03b3b", "Insufficient Evidence": "#898781"}


@dataclass
class Result:
    """The outcome of one comparison. `doc` is the full findings.json document."""
    doc: dict
    seconds: float = 0.0
    _errors: list[str] | None = field(default=None, repr=False)

    @property
    def verdict(self) -> str:
        return self.doc["verdict"]

    @property
    def findings(self) -> list[dict]:
        return self.doc.get("findings", [])

    @property
    def analyses(self) -> dict[str, str]:
        return {a["id"]: a["verdict"] for a in self.doc.get("analyses", [])}

    @property
    def questions(self) -> dict[str, str]:
        return {q["id"]: q["verdict"] for q in self.doc.get("questions", [])}

    @property
    def next_steps(self) -> dict:
        return self.doc.get("next_steps", {})

    def at_least(self, verdict: str) -> bool:
        """True when this result is `verdict` or worse (Ready < Conditional < Insufficient Evidence < Blocked)."""
        return VERDICT_ORDER.index(self.verdict) >= VERDICT_ORDER.index(verdict)

    def validate(self, challenge_dir: str | None = None) -> list[str]:
        """Problems the organizers' format/validate.py finds (empty list: valid)."""
        from .validate import validate
        self._errors = validate(self.doc, challenge_dir)
        return self._errors

    def save(self, path: str | pathlib.Path) -> pathlib.Path:
        p = pathlib.Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.doc, indent=2), encoding="utf-8")
        return p

    def __repr__(self) -> str:
        return (f"<Driftwire {self.verdict}: {len(self.findings)} finding(s); analyses "
                f"{', '.join(f'{k} {v}' for k, v in self.analyses.items())}; {self.seconds:.1f}s>")

    def _repr_html_(self) -> str:  # Jupyter renders this
        e = html.escape
        def pill(v):
            return (f'<span style="display:inline-flex;align-items:center;gap:5px;padding:2px 10px 2px 4px;'
                    f'border-radius:999px;border:1px solid #ddd;font-weight:600;font-size:12px">'
                    f'<span style="width:16px;height:16px;border-radius:50%;background:{COLOR.get(v, "#999")};'
                    f'color:{"#111" if v == "Conditional" else "#fff"};display:inline-grid;place-items:center;'
                    f'font-size:10px">{ICON.get(v, "•")}</span>{e(v)}</span>')
        rows = "".join(f"<tr><td style='padding:4px 10px 4px 0'><b>{e(f['id'])}</b></td>"
                       f"<td style='padding:4px 0'>{e(f['summary'])}</td></tr>" for f in self.findings)
        qs = "".join(f"<tr><td style='padding:3px 10px 3px 0'>{e(k)}</td><td>{pill(v)}</td></tr>"
                     for k, v in self.questions.items())
        steps = "".join(f"<li>{e(s.get('action', ''))}</li>" for s in self.next_steps.get("steps", [])[:5])
        return (f"<div style='font-family:system-ui,sans-serif;border:1px solid #e4e2dc;border-radius:12px;padding:14px;"
                f"max-width:900px'><div style='display:flex;gap:10px;align-items:center'><b style='font-size:16px'>"
                f"Driftwire</b>{pill(self.verdict)}<span style='color:#777;font-size:12px'>{len(self.findings)} "
                f"finding(s), {self.seconds:.1f}s</span></div>"
                f"<table style='margin-top:10px;font-size:13px'>{rows or '<tr><td>Nothing changed.</td></tr>'}</table>"
                f"<div style='margin-top:10px;font-size:13px'><b>Questions</b><table>{qs}</table></div>"
                f"<div style='margin-top:10px;font-size:13px'><b>Next steps</b><ol style='margin:4px 0'>{steps}</ol></div>"
                f"<div style='color:#888;font-size:11px;margin-top:8px'>{e(self.doc.get('research_use_only', ''))}</div></div>")


def check(trusted: str | pathlib.Path, new: str | pathlib.Path, question: str | None = None,
          name_a: str | None = None, name_b: str | None = None) -> Result:
    """Compare a new release with the trusted one. `question` is a question-card id
    (see `python -m driftwire questions`); without it the overall verdict covers the reference analyses."""
    t0 = time.time()
    a, b = Release(trusted, name_a), Release(new, name_b)
    doc = build(detect_changes(a, b), a, b, question=question)
    return Result(doc, time.time() - t0)
