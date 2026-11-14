"""Reproducibility receipt: same inputs give the same result, and anything that differs is named."""
import json

from conftest import write
from tripwire.__main__ import VERIFY_FAILED, main
from tripwire.receipt import result_sha256, verify


def _run(releases, tmp_path, swap=True):
    a, b, clinical, protein = releases
    p = protein.copy()
    if swap:
        c = list(p.columns)
        p[c[0]], p[c[1]] = protein[c[1]], protein[c[0]]
    write(b, clinical, p)
    out = tmp_path / "f.json"
    main(["diff", str(a), str(b), "--out", str(out), "--no-report"])
    return a, b, json.loads(out.read_text(encoding="utf-8")), out, clinical, p


def test_every_findings_json_has_a_receipt(releases, tmp_path):
    _, _, doc, _, _, _ = _run(releases, tmp_path)
    r = doc["receipt"]
    assert r["tool"].startswith("Driftwire") and r["result_sha256"] == result_sha256(doc)


def test_same_inputs_verify_identical(releases, tmp_path):
    a, b, doc, out, _, _ = _run(releases, tmp_path)
    assert verify(doc, a, b)[0] == "identical"
    assert main(["verify", str(out), str(a), str(b)]) == 0


def test_changed_input_is_named(releases, tmp_path):
    a, b, doc, out, clinical, p = _run(releases, tmp_path)
    p.iloc[0, 0] = p.iloc[0, 0] + 1.0
    write(b, clinical, p)
    outcome, details = verify(doc, a, b)
    assert outcome == "inputs differ" and any("protein_rppa.tsv.gz" in d for d in details)
    assert main(["verify", str(out), str(a), str(b)]) == VERIFY_FAILED


def test_edited_result_is_caught(releases, tmp_path):
    a, b, doc, _, _, _ = _run(releases, tmp_path)
    doc["verdict"] = "Ready" if doc["verdict"] != "Ready" else "Blocked"
    outcome, details = verify(doc, a, b)
    assert outcome == "different" and any(d.startswith("verdict") for d in details)


def test_review_decisions_do_not_change_the_hash(releases, tmp_path):
    _, _, doc, _, _, _ = _run(releases, tmp_path)
    before = result_sha256(doc)
    doc["decisions"] = [{"repair_id": "R1", "decision": "approve", "reason": "ok", "reviewer_role": "curator",
                         "original_preserved": True}]
    assert result_sha256(doc) == before
