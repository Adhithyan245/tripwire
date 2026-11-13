"""Exercise the real detector against independent, seeded mutation scenarios.

Until Role 1 merges a detector, these tests skip rather than crediting a stub.
They do not use the organizers' practice answer key.
"""
import warnings

import numpy as np
import pandas as pd
import pytest

from conftest import write
from tripwire.detect import detect_changes
from tripwire.mutation_lab.core import evaluate, generate
from tripwire.release import Release


@pytest.mark.parametrize("scenario", ["unchanged", "reordered", "swap", "duplicate", "disappeared", "label_change", "value_shift"])
@pytest.mark.parametrize("seed", [11, 23, 47])
def test_detector_against_seeded_mutation(releases, scenario, seed):
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
    expected = generate(source, target, scenario, seed)
    report = evaluate(expected, detect_changes(Release(source), Release(target)))
    assert all(row["false_positives"] == 0 and row["false_negatives"] == 0
               for row in report["by_change_type"]), report
    if not expected:
        assert report["false_positives_on_no_change"] == 0
