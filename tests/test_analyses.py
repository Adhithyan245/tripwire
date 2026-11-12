"""Our A1/A2 must equal the organizers' reference_analyses.py on the real release."""
import importlib.util

import pytest

from tripwire.analyses import a1_run, a2_run
from tripwire.release import Release
from tripwire.validate import challenge_dir

ROOT = challenge_dir()
RAW = ROOT / "data" / "tcga-brca" / "raw" if ROOT else None


@pytest.mark.skipif(not (RAW and (RAW / "protein_rppa.tsv.gz").exists()), reason="release A not fetched")
def test_matches_reference_on_release_A():
    spec = importlib.util.spec_from_file_location("ref", ROOT / "data" / "tcga-brca" / "reference_analyses.py")
    ref = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ref)
    clinical, protein = ref.load(RAW)
    r = Release(RAW)
    assert a1_run(r) == {k: v for k, v in ref.a1(clinical, protein).items() if k not in ("analysis", "inputs")}
    assert a2_run(r) == {k: v for k, v in ref.a2(clinical).items() if k not in ("analysis", "inputs")}
