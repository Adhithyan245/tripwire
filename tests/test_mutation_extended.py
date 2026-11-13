"""Every extended scenario must be caught exactly by the detector (no misses, no extras) on synthetic data."""
import numpy as np
import pandas as pd
import pytest

from conftest import write
from tripwire.detect import detect_changes
from tripwire.mutation_lab.core import evaluate
from tripwire.mutation_lab.extended import EXTENDED, generate_extended
from tripwire.release import Release


@pytest.fixture
def source(releases):
    a, _, clinical, protein = releases
    rng = np.random.default_rng(9)
    extra = pd.DataFrame(rng.normal(0, 1, (30, protein.shape[1])), columns=protein.columns,
                         index=[f"PROT{i}" for i in range(30)])
    wide = pd.concat([protein, extra])
    wide.index.name = protein.index.name
    write(a, clinical, wide)
    cn = pd.DataFrame(rng.integers(-2, 3, (40, len(clinical))), columns=clinical.sampleID,
                      index=[f"G{i}" for i in range(40)])
    cn.index.name = "gene"
    cn.to_csv(a / "copy_number_gistic.tsv.gz", sep="\t", compression={"method": "gzip", "mtime": 0})
    return a


@pytest.mark.parametrize("scenario", EXTENDED)
@pytest.mark.parametrize("seed", [1, 2])
def test_extended_scenario_caught_exactly(source, tmp_path, scenario, seed):
    target = tmp_path / f"{scenario}-{seed}"
    truth = generate_extended(source, target, scenario, seed)
    observed = detect_changes(Release(source), Release(target))
    r = evaluate(truth, observed)
    fp = sum(x["false_positives"] for x in r["by_change_type"])
    fn = sum(x["false_negatives"] for x in r["by_change_type"])
    assert (fp, fn) == (0, 0), r


def test_unknown_scenario_and_existing_target(source, tmp_path):
    with pytest.raises(ValueError):
        generate_extended(source, tmp_path / "x", "teleport")
    (tmp_path / "y").mkdir()
    with pytest.raises(FileExistsError):
        generate_extended(source, tmp_path / "y", "id_case")
