"""Prepare data with AI: supported types, what may be sent, blockers, and a prepared copy that changes headers only."""
import csv
import io
import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "app"))
import prepare_tab as p  # noqa: E402

CSV = b"barcode,er,subtype,age\nTCGA-A1-A0SB-01,Positive,LumA,55\nTCGA-A1-A0SD-01,Negative,Basal,61\n"


def test_supported_and_unsupported_types():
    assert p.file_support("x.csv")[0] and p.file_support("x.tsv")[0]
    ok, why = p.file_support("x.xlsx")
    assert not ok and "not supported" in why


def test_metadata_never_contains_rows():
    header, n = p.read_header(CSV, "x.csv")
    meta = p.metadata("x.csv", CSV, header, n, "Does ER differ?")
    blob = json.dumps(meta)
    assert meta["columns"] == ["barcode", "er", "subtype", "age"] and n == 2
    assert "TCGA-A1-A0SB-01" not in blob and "LumA" not in blob and "55" not in blob.replace('"size_bytes": ', "")


def test_read_header_rejects_bad_input_in_plain_words():
    for data, name, msg in ((b"", "e.csv", "empty"), (b"a,a\n1,2\n", "d.csv", "Duplicate"), (b"onecolumn\n1\n", "o.csv", "Only one column")):
        try:
            p.read_header(data, name)
        except ValueError as e:
            assert msg in str(e)
        else:
            raise AssertionError(name)


def test_blockers_need_an_id_and_answers():
    m = {"barcode": p.NOT_USED, "er": "breast_carcinoma_estrogen_receptor_status"}
    assert any("sample ID" in b for b in p.blockers("clinical.tsv", m, [], {}))
    m["barcode"] = "sampleID"
    assert p.blockers("clinical.tsv", m, ["Is er the ER status?"], {}) == ["Unanswered question: Is er the ER status?"]
    assert p.blockers("clinical.tsv", m, ["Is er the ER status?"], {"Is er the ER status?": "yes"}) == []
    m["subtype"] = "sampleID"
    assert any("Two columns" in b for b in p.blockers("clinical.tsv", m, [], {}))


def test_no_backend_means_ai_unavailable_not_a_crash():
    assert p._backend() is None  # the separately built backend isn't installed here


def test_prepared_copy_renames_headers_only(tmp_path):
    m = {"barcode": "sampleID", "er": "breast_carcinoma_estrogen_receptor_status", "subtype": "PAM50Call_RNAseq", "age": p.NOT_USED}
    out, rec = p.prepare_copy(CSV, "x.csv", "clinical.tsv", m, tmp_path, "manual", {})
    rows = list(csv.reader(io.StringIO(out.read_text(encoding="utf-8")), delimiter="\t"))
    assert rows[0] == ["sampleID", "breast_carcinoma_estrogen_receptor_status", "PAM50Call_RNAseq", "age"]
    assert rows[1:] == [["TCGA-A1-A0SB-01", "Positive", "LumA", "55"], ["TCGA-A1-A0SD-01", "Negative", "Basal", "61"]]
    r = json.loads(rec.read_text(encoding="utf-8"))
    assert r["rows"] == 2 and r["rows_changed"] == 0 and len(r["header_changes"]) == 3 and "firewall hasn't run" in r["note"]
