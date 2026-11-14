"""Unfamiliar layouts: renamed files, reordered columns, a missing file, unrelated CSVs, an empty folder.

None of these may crash, and nothing may come back Ready because its inputs were absent: each analysis or question
card that can't run says Insufficient Evidence and names what's missing. Recognized files still go through the
detectors unchanged, and findings.json is still written in the contract format.
"""
import json
import shutil

import pandas as pd

from tripwire.__main__ import INPUT_ERROR, main
from tripwire.release import Release

NEEDS_PROTEIN = {"A1", "er_protein_by_er_status", "predict_er_from_protein"}


def _diff(a, b, out):
    rc = main(["diff", str(a), str(b), "--out", str(out / "findings.json"), "--no-report"])
    return rc, json.loads((out / "findings.json").read_text(encoding="utf-8"))


def _verdicts(doc):
    v = {x["id"]: (x["verdict"], x["why"]) for x in doc["analyses"]}
    v.update({x["id"]: (x["verdict"], x["why"]) for x in doc["questions"]})
    return v


def _never_ready_without(doc, ids, missing):
    v = _verdicts(doc)
    for i in ids:
        verdict, why = v[i]
        assert verdict == "Insufficient Evidence", (i, verdict, why)
        assert missing in why, (i, why)


def test_a_renamed_files_and_reordered_columns(releases, tmp_path):
    a, b, clinical, protein = releases
    b.mkdir()
    clinical[list(reversed(clinical.columns))].to_csv(b / "clinical.tsv", sep="\t", index=False)
    shutil.copy(a / "protein_rppa.tsv.gz", b / "RPPA_proteins.tsv.gz")   # a name Driftwire doesn't know
    rc, doc = _diff(a, b, tmp_path / "out")
    assert rc == 0 and doc["verdict"] != "Ready"
    _never_ready_without(doc, NEEDS_PROTEIN, "protein_rppa.tsv.gz")
    # the reordered clinical file is still read by column name: no label changes are invented
    assert not [f for f in doc["findings"] if any(e.get("file") == "clinical.tsv" for e in f["evidence"])]


def test_a_reordered_survival_columns_still_index_by_sample(tmp_path):
    surv = pd.DataFrame({"Redaction": ["", ""], "OS.time": [10, 20], "OS": [0, 1],
                         "sample": ["TCGA-AA-0001-01", "TCGA-AA-0002-01"]})
    surv.to_csv(tmp_path / "survival.tsv", sep="\t", index=False)
    t = Release(tmp_path).table("survival.tsv")
    assert list(t.index) == ["TCGA-AA-0001-01", "TCGA-AA-0002-01"] and "Redaction" in t.columns


def test_b_release_missing_the_protein_file(releases, tmp_path):
    a, b, clinical, protein = releases
    b.mkdir()
    shutil.copy(a / "clinical.tsv", b / "clinical.tsv")
    rc, doc = _diff(a, b, tmp_path / "out")
    assert rc == 0 and doc["verdict"] != "Ready"
    _never_ready_without(doc, NEEDS_PROTEIN, "protein_rppa.tsv.gz")


def test_c_unrelated_csvs(releases, tmp_path):
    a, b, clinical, protein = releases
    b.mkdir()
    (b / "orders.csv").write_text("order,amount\n1,9.99\n", encoding="utf-8")
    (b / "notes.tsv").write_text("foo\tbar\n1\t2\n", encoding="utf-8")
    rc, doc = _diff(a, b, tmp_path / "out")
    assert rc == 0 and doc["verdict"] != "Ready"
    v = _verdicts(doc)
    assert not [i for i, (verdict, _) in v.items() if verdict == "Ready"]
    _never_ready_without(doc, ["A1", "A2", "subtype_mix"], "clinical.tsv")


def test_d_empty_folder(releases, tmp_path):
    a, b, clinical, protein = releases
    b.mkdir()
    rc, doc = _diff(a, b, tmp_path / "out")
    assert rc == 0 and doc["verdict"] != "Ready"
    assert not [i for i, (verdict, _) in _verdicts(doc).items() if verdict == "Ready"]


def test_missing_folder_is_a_plain_message_not_a_traceback(tmp_path, capsys):
    rc = main(["diff", str(tmp_path / "nope_A"), str(tmp_path / "nope_B"), "--out", str(tmp_path / "f.json")])
    err = capsys.readouterr().err
    assert rc == INPUT_ERROR and "release folder not found" in err and "Traceback" not in err
    assert not (tmp_path / "f.json").exists()
