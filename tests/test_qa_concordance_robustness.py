"""Synthetic regressions for malformed input; never use organizer answer keys."""
import pandas as pd
import pytest

from conftest import write
from test_label_concordance import _clean
from tripwire.detect import detect_changes
from tripwire.findings import build
from tripwire.release import Release


@pytest.mark.xfail(strict=True, reason="normalized duplicate clinical IDs crash label concordance")
def test_normalized_duplicate_clinical_id_does_not_crash_workflow(tmp_path):
    a, clinical, protein = _clean(tmp_path)
    duplicate = clinical.iloc[[0]].copy()
    duplicate["sampleID"] = duplicate["sampleID"].str.lower()
    b = tmp_path / "B"
    write(b, pd.concat([clinical, duplicate], ignore_index=True), protein)
    ra, rb = Release(a), Release(b)
    doc = build(detect_changes(ra, rb), ra, rb)
    assert doc["verdict"] != "Ready"


@pytest.mark.xfail(strict=True, reason="duplicate marker rows crash the comparison workflow")
def test_duplicate_marker_row_does_not_crash_workflow(tmp_path):
    a, clinical, protein = _clean(tmp_path)
    b = tmp_path / "B"
    write(b, clinical, pd.concat([protein, protein.loc[["ERALPHA"]]]))
    ra, rb = Release(a), Release(b)
    doc = build(detect_changes(ra, rb), ra, rb)
    assert doc["verdict"] != "Ready"
