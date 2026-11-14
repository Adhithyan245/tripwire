"""The dashboard's "Run on your data" gives exactly the CLI's result: same result SHA-256, same findings."""
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
from own_data_tab import run_compare  # noqa: E402

CHALLENGE = ROOT.parent / "oncosys-challenge"
PRACTICE_A = CHALLENGE / "data" / "tcga-brca" / "raw"
PRACTICE_B = CHALLENGE / "envelopes" / "opened" / "practice" / "release"


def _cli(a, b, out):
    subprocess.run([sys.executable, "-m", "tripwire", "diff", str(a), str(b), "--out", str(out)],
                   cwd=ROOT, check=True, capture_output=True)
    return json.loads(out.read_text(encoding="utf-8"))


def _same(cli_doc, ui_doc):
    assert cli_doc["receipt"]["result_sha256"] == ui_doc["receipt"]["result_sha256"]
    assert cli_doc["verdict"] == ui_doc["verdict"]
    assert [f["summary"] for f in cli_doc["findings"]] == [f["summary"] for f in ui_doc["findings"]]


def test_synthetic_release_same_hash(releases, tmp_path):
    from conftest import write
    a, b, clinical, protein = releases
    write(b, clinical, protein.iloc[:, ::-1])
    cli_doc = _cli(a, b, tmp_path / "cli.json")
    rc, _, out = run_compare(str(a), str(b), None, tmp_path / "ui")
    assert rc == 0
    _same(cli_doc, json.loads(out.read_text(encoding="utf-8")))


@pytest.mark.skipif(not (PRACTICE_A.is_dir() and PRACTICE_B.is_dir()), reason="practice envelope not opened")
def test_practice_envelope_same_hash(tmp_path):
    cli_doc = _cli(PRACTICE_A, PRACTICE_B, tmp_path / "cli.json")
    rc, _, out = run_compare(str(PRACTICE_A), str(PRACTICE_B), None, tmp_path / "ui")
    ui_doc = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 0
    _same(cli_doc, ui_doc)
    print("practice result SHA-256:", ui_doc["receipt"]["result_sha256"])
