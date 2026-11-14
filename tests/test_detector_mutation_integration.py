"""Exercise the real detector against independent, seeded mutation scenarios.

The merged detector is exercised; a stub is skipped rather than credited as a pass.
They do not use the organizers' practice answer key, and they do not tune or change the detector:
where the detector's interpretation differs from the planted change type, the test says so.
"""
import warnings

import numpy as np
import pandas as pd
import pytest

from conftest import write
from tripwire.detect import detect_changes
from tripwire.mutation_lab.core import evaluate, generate
from tripwire.release import Release

EXACT = ["unchanged", "reordered", "swap", "duplicate", "disappeared", "label_change", "value_shift",
         "id_case_change", "id_whitespace", "sample_type_change"]


def rich_source(releases):
    source, target, clinical, protein = releases
    # The standard fixture has only two features; add distinct features so the
    # detector can distinguish profiles without relying on two-point correlations.
    rng = np.random.default_rng(1123)
    extra = pd.DataFrame(rng.normal(size=(32, len(protein.columns))),
                         index=[f"F{i}" for i in range(32)], columns=protein.columns)
    rich_protein = pd.concat([protein, extra])
    rich_protein.index.name = "sample"
    write(source, clinical, rich_protein)
    original = Release(source)
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        detect_changes(original, original)
    if any("stub" in str(w.message).lower() for w in captured):
        pytest.skip("Role 1 detector is still a stub")
    return source, target


@pytest.mark.parametrize("scenario", EXACT)
@pytest.mark.parametrize("seed", [11, 23, 47])
def test_detector_against_seeded_mutation(releases, scenario, seed):
    source, target = rich_source(releases)
    expected = generate(source, target, scenario, seed)
    report = evaluate(expected, detect_changes(Release(source), Release(target)))
    assert all(row["false_positives"] == 0 and row["false_negatives"] == 0
               for row in report["by_change_type"]), report
    assert report["reported_as_other_type"] == [], report
    if not expected:
        assert report["false_positives_on_no_change"] == 0


@pytest.mark.parametrize("seed", [11, 23, 47])
def test_detector_against_subgroup_coverage_loss(releases, seed):
    source, target = rich_source(releases)
    expected = generate(source, target, "coverage_loss", seed)
    observed = detect_changes(Release(source), Release(target))
    report = evaluate(expected, observed)
    # Whatever it calls them, the detector must flag every blanked profile and nothing else
    # (the other subgroup and the unchosen members are untouched).
    assert len(observed) == len(expected), report
    assert {(c.file, c.sample_id) for c in observed} == {(c.file, c.sample_id) for c in expected}, report
    assert all(r["false_positives"] == 0 and r["false_negatives"] == 0
               for r in report["by_change_type"]), report
    assert report["reported_as_other_type"] == [], report
