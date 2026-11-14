"""Fail-safe input handling: malformed release B files give a clear one-line error (exit 2) or a written result that is
not Ready. Never an unhandled traceback, never a Ready verdict for data Driftwire couldn't read."""
import gzip
import json

import pytest

from tripwire.__main__ import INPUT_ERROR, main


def _corrupt(b, how, clinical, protein):
    from conftest import write
    write(b, clinical, protein)
    clin, prot = b / "clinical.tsv", b / "protein_rppa.tsv.gz"
    if how == "empty file":
        clin.write_bytes(b"")
    elif how == "truncated gz":
        prot.write_bytes(prot.read_bytes()[:40])
    elif how == "wrong delimiter":
        clinical.to_csv(clin, index=False)  # comma-separated under a .tsv name
    elif how == "missing required columns":
        clinical.drop(columns=["breast_carcinoma_estrogen_receptor_status"]).to_csv(clin, sep="\t", index=False)
    elif how == "non-UTF-8 bytes":
        clin.write_bytes(clin.read_bytes().replace(b"Positive", b"Posit\xff\xfeve"))
    elif how == "duplicate headers":
        text = clin.read_text(encoding="utf-8").split("\n", 1)
        cols = text[0].split("\t")
        clin.write_text("\t".join(cols[:-1] + [cols[0]]) + "\n" + text[1], encoding="utf-8")
    elif how == "NaN and inf values":
        p = protein.copy()
        p.iloc[0, :5] = float("nan")
        p.iloc[1, 5:10] = float("inf")
        write(b, clinical, p)
    elif how == "gzip that is not a table":
        prot.write_bytes(gzip.compress(b"\x00\x01binary\x02" * 50))


CASES = ["empty file", "truncated gz", "wrong delimiter", "missing required columns", "non-UTF-8 bytes",
         "duplicate headers", "NaN and inf values", "gzip that is not a table"]


@pytest.mark.parametrize("how", CASES)
def test_malformed_release_b_never_crashes_and_is_never_ready(how, releases, tmp_path, capsys):
    a, b, clinical, protein = releases
    _corrupt(b, how, clinical, protein)
    out = tmp_path / "findings.json"
    rc = main(["diff", str(a), str(b), "--out", str(out), "--no-report"])
    err = capsys.readouterr().err
    assert "Traceback" not in err
    if rc == INPUT_ERROR:
        assert not out.exists() and len(err.strip().splitlines()) <= 2 and "couldn't compare" in err
    else:
        assert rc == 0, rc
        doc = json.loads(out.read_text(encoding="utf-8"))
        assert doc["verdict"] != "Ready", (how, doc["verdict"])


def test_release_a_missing(releases, tmp_path, capsys):
    a, b, clinical, protein = releases
    from conftest import write
    write(b, clinical, protein)
    rc = main(["diff", str(tmp_path / "missing_A"), str(b), "--out", str(tmp_path / "f.json")])
    assert rc == INPUT_ERROR and "release folder not found" in capsys.readouterr().err


def test_fail_closed_if_any_internal_step_raises(releases, tmp_path, monkeypatch, capsys):
    """If a step inside the pipeline raises, no findings file is written at all, so nothing can read as Ready."""
    a, b, clinical, protein = releases
    from conftest import write
    write(b, clinical, protein)
    import tripwire.findings as findings

    def boom(*args, **kw):
        raise RuntimeError("simulated internal failure")
    monkeypatch.setattr(findings, "map_impact", boom)
    out = tmp_path / "findings.json"
    rc = main(["diff", str(a), str(b), "--out", str(out), "--no-report"])
    assert rc == INPUT_ERROR and not out.exists()
    assert "simulated internal failure" in capsys.readouterr().err
