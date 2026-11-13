import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tripwire.dashboard_input import parse_findings
from tripwire.contract import Change
from tripwire.findings import build
from tripwire.release import Release
from conftest import write
from test_impact_verdicts import er_pair, swapped


EXAMPLE = Path(__file__).resolve().parents[1] / "app" / "synthetic.json"


def test_example_and_structure_checks():
    doc = parse_findings(EXAMPLE.read_bytes())
    assert doc["analyses"][0]["id"] == "A1"
    with pytest.raises(ValueError, match="Invalid JSON"):
        parse_findings(b"{")
    doc["findings"] = ["not an object"]
    with pytest.raises(ValueError, match="findings"):
        parse_findings(json.dumps(doc).encode())


def test_imported_decisions_must_match_repairs():
    doc = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    doc["decisions"] = [{"repair_id": "missing", "decision": "approve", "reason": "ok", "reviewer_role": "curator"}]
    with pytest.raises(ValueError, match="repair IDs"):
        parse_findings(json.dumps(doc).encode())


def test_accepts_generated_findings_with_review(releases):
    a, b, clinical, protein = releases
    x, y = er_pair(clinical, protein)
    write(b, clinical, swapped(protein, x, y))
    doc = build([Change(x, "swap", "protein_rppa.tsv.gz", related_sample_id=y)], Release(a), Release(b))
    doc["decisions"] = [{"repair_id": doc["repairs"][0]["id"], "decision": "approve", "reason": "checked", "reviewer_role": "curator", "original_preserved": True}]
    assert parse_findings(json.dumps(doc).encode()) == doc


def test_dashboard_example_and_empty_findings():
    app = AppTest.from_file(str(EXAMPLE.parent / "dashboard.py")).run()
    next(r for r in app.sidebar.radio if r.label == "Findings source").set_value("Synthetic example").run()
    next(button for button in app.sidebar.button if button.label == "Load synthetic example").click().run()
    assert not app.exception
    assert any("Synthetic demonstration" in warning.value for warning in app.warning)
    doc = dict(app.session_state["doc"])
    doc["findings"] = []
    app.session_state["doc"] = doc
    app.run()
    assert not app.exception
    assert any("does not prove" in info.value for info in app.info)


def test_dashboard_first_visit_tour_and_mutation_lab_view():
    app = AppTest.from_file(str(EXAMPLE.parent / "dashboard.py"), default_timeout=60).run()
    assert not app.exception
    assert app.session_state["toured"] is True  # the tour opened once on first visit
    next(r for r in app.sidebar.radio if r.label == "View").set_value("Mutation Lab").run()
    assert not app.exception
    assert any(s.value == "Mutation Lab" for s in app.subheader)
