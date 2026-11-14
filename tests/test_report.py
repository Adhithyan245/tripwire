import json

from conftest import write
from test_impact_verdicts import er_pair, swapped
from tripwire.__main__ import main
from tripwire.contract import Change
from tripwire.findings import build
from tripwire.release import Release
from tripwire.report import render


def test_report_shows_verdicts_findings_and_safety_label(releases):
    a, b, clinical, protein = releases
    x, y = er_pair(clinical, protein)
    write(b, clinical, swapped(protein, x, y))
    doc = build([Change(x, "swap", "protein_rppa.tsv.gz", related_sample_id=y)], Release(a), Release(b))
    page = render(doc)
    assert doc["verdict"] in page and "Research use only" in page and "never applied" in page
    assert x in page and y in page and "A1" in page and "A2" in page
    assert "<script" not in page  # self-contained, no scripts


def test_report_escapes_untrusted_text():
    doc = {"verdict": "Ready", "question": "<img src=x onerror=alert(1)>", "findings": [], "analyses": [],
           "data": {"releases": [{"name": "<b>r</b>", "files": []}]}}
    page = render(doc)
    assert "<img src=x" not in page and "&lt;img" in page


def test_diff_writes_report_next_to_findings(releases, tmp_path):
    a, _, _, _ = releases
    out = tmp_path / "f.json"
    main(["diff", str(a), str(a), "--out", str(out), "--name-b", "again"])
    assert out.exists() and out.with_suffix(".html").exists()
    assert main(["report", str(out), "--out", str(tmp_path / "r.html")]) == 0
    assert "Driftwire audit report" in (tmp_path / "r.html").read_text(encoding="utf-8")
