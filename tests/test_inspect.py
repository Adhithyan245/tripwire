"""driftwire inspect: file roles, shapes, missing files, and what can run, without guessing or crashing."""
from conftest import write
from tripwire.inspect import inspect_folder


def test_practice_layout_is_recognized(releases):
    a, b, clinical, protein = releases
    rep = inspect_folder(a)
    roles = {f["file"]: f["role"] for f in rep["files"]}
    assert roles["clinical.tsv"] == "clinical" and roles["protein_rppa.tsv.gz"] == "protein"
    assert {x["id"]: x["can_run"] for x in rep["analyses"]}["A1"] is True


def test_renamed_file_is_unrecognized_with_a_reason(releases):
    a, b, clinical, protein = releases
    (a / "protein_rppa.tsv.gz").rename(a / "my_proteins.tsv.gz")
    rep = inspect_folder(a)
    f = next(x for x in rep["files"] if x["file"] == "my_proteins.tsv.gz")
    assert f["role"] == "unrecognized" and "expected file names" in f["note"]
    a1 = next(x for x in rep["analyses"] if x["id"] == "A1")
    assert not a1["can_run"] and any("protein_rppa.tsv.gz is not in this folder" in w for w in a1["why_not"])


def test_unrelated_csv_and_empty_folder_never_crash(tmp_path):
    (tmp_path / "notes.csv").write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    rep = inspect_folder(tmp_path)
    assert rep["files"][0]["role"] == "unrecognized" and "comma-separated" in rep["files"][0]["note"]
    assert not any(x["can_run"] for x in rep["analyses"])
    empty = tmp_path / "empty"
    empty.mkdir()
    rep2 = inspect_folder(empty)
    assert rep2["files"] == [] and not any(x["can_run"] for x in rep2["analyses"])
    assert inspect_folder(tmp_path / "nope")["error"].startswith("not a folder")
