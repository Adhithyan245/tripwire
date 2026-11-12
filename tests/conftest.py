"""Synthetic releases for tests. Built from scratch, never from the practice answer key."""
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

SUBTYPES = ["LumA", "LumB", "Basal", "Her2", "Normal"]


def make_release(dest: pathlib.Path, n=80, seed=0):
    rng = np.random.default_rng(seed)
    ids = [f"TCGA-T{i // 100}-{i:04d}-01" for i in range(n)] + [f"TCGA-T0-{i:04d}-11" for i in range(5)]
    er = ["Positive" if i % 3 else "Negative" for i in range(len(ids))]
    clinical = pd.DataFrame({"sampleID": ids, "breast_carcinoma_estrogen_receptor_status": er,
                             "PAM50Call_RNAseq": [SUBTYPES[i % 5] for i in range(len(ids))],
                             "age": rng.integers(30, 80, len(ids))})
    prot_ids = ids[: n - 10] + ids[n:]  # last 10 primaries have no protein
    eralpha = [2.0 + rng.normal(0, .3) if er[ids.index(s)] == "Positive" else -1.0 + rng.normal(0, .3) for s in prot_ids]
    protein = pd.DataFrame([eralpha, rng.normal(0, 1, len(prot_ids))], index=["ERALPHA", "AKT"], columns=prot_ids)
    protein.index.name = "sample"
    write(dest, clinical, protein)
    return clinical, protein


def write(dest, clinical, protein):
    dest.mkdir(parents=True, exist_ok=True)
    clinical.to_csv(dest / "clinical.tsv", sep="\t", index=False)
    protein.to_csv(dest / "protein_rppa.tsv.gz", sep="\t", compression={"method": "gzip", "mtime": 0})


@pytest.fixture
def releases(tmp_path):
    clinical, protein = make_release(tmp_path / "A")
    return tmp_path / "A", tmp_path / "B", clinical, protein
