"""Driftwire where data moves: a notebook API and an opt-in CI gate. Same engine, same findings.json."""
import json

from conftest import write
from tripwire.__main__ import GATE_FAILED, main


def test_check_returns_verdict_findings_and_html(releases):
    import driftwire
    a, b, clinical, protein = releases
    cols = list(protein.columns)
    swapped = protein.copy()
    swapped[cols[0]], swapped[cols[1]] = protein[cols[1]], protein[cols[0]]
    write(b, clinical, swapped)
    r = driftwire.check(a, b)
    assert r.verdict in ("Ready", "Conditional", "Blocked", "Insufficient Evidence")
    assert r.findings, "the swapped samples must be found"
    assert set(r.analyses) == {"A1", "A2"} and r.questions
    html = r._repr_html_()
    assert "Driftwire" in html and r.verdict in html and "<script" not in html
    assert r.at_least("Ready") and (r.at_least("Blocked") == (r.verdict == "Blocked"))


def test_check_unchanged_release_is_ready(releases, tmp_path):
    import driftwire
    a, b, clinical, protein = releases
    write(b, clinical, protein)
    r = driftwire.check(a, b)
    assert r.verdict == "Ready" and r.findings == []
    out = r.save(tmp_path / "f.json")
    assert json.loads(out.read_text())["verdict"] == "Ready"


def test_gate_is_opt_in_and_uses_its_own_exit_code(releases, tmp_path):
    a, b, clinical, protein = releases
    cols = list(protein.columns)
    swapped = protein.copy()
    swapped[cols[0]], swapped[cols[1]] = protein[cols[1]], protein[cols[0]]
    write(b, clinical, swapped)
    base = ["diff", str(a), str(b), "--out", str(tmp_path / "f.json"), "--no-report"]
    verdict = None
    assert main(base) in (0, 1)  # no gate: the exit code never depends on the verdict
    verdict = json.loads((tmp_path / "f.json").read_text())["verdict"]
    assert verdict != "Ready"
    assert main(base + ["--fail-on", "Conditional"]) == GATE_FAILED
    assert GATE_FAILED not in (0, 1, 3)


def test_gate_passes_an_unchanged_release(releases, tmp_path):
    a, b, clinical, protein = releases
    write(b, clinical, protein)
    assert main(["diff", str(a), str(b), "--out", str(tmp_path / "f.json"), "--no-report", "--fail-on", "Conditional"]) == 0
