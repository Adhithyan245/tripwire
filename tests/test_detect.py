"""Detector tests on synthetic releases (never the practice answer key)."""
import numpy as np
import pandas as pd
import pytest

from conftest import write
from test_impact_verdicts import er_pair, swapped
from tripwire.detect import detect_changes
from tripwire.findings import build
from tripwire.release import Release

P = "protein_rppa.tsv.gz"


@pytest.fixture
def releases(releases):
    """Same releases, but 20 proteins per sample: real RPPA has 131, and 2 values identify nobody."""
    a, b, clinical, protein = releases
    rng = np.random.default_rng(5)
    extra = pd.DataFrame(rng.normal(0, 1, (18, protein.shape[1])), columns=protein.columns,
                         index=[f"PROT{i}" for i in range(18)])
    wide = pd.concat([protein, extra])
    wide.index.name = protein.index.name
    write(a, clinical, wide)
    return a, b, clinical, wide


def kinds(changes):
    return {(c.file, c.sample_id, c.change_type) for c in changes}


def test_no_change_and_reordered_copy_report_nothing(releases):
    a, b, clinical, protein = releases
    assert detect_changes(Release(a), Release(a, name="same")) == []
    write(b, clinical.sample(frac=1, random_state=3), protein[protein.columns[::-1]].iloc[::-1])
    assert detect_changes(Release(a), Release(b)) == []


def test_swap_found_as_a_pair(releases):
    a, b, clinical, protein = releases
    x, y = er_pair(clinical, protein)
    write(b, clinical, swapped(protein, x, y))
    ch = detect_changes(Release(a), Release(b))
    assert kinds(ch) == {(P, x, "swap"), (P, y, "swap")}
    assert {c.related_sample_id for c in ch} == {x, y}


def test_duplicate_under_new_id_with_same_count(releases):
    a, b, clinical, protein = releases
    donor, victim = protein.columns[1], protein.columns[2]
    new = next(s for s in clinical.sampleID if s not in protein.columns and s[13:15] == "01")
    p = protein.drop(columns=[victim])
    p[new] = p[donor]
    write(b, clinical, p)
    ch = detect_changes(Release(a), Release(b))
    assert kinds(ch) == {(P, new, "duplicate"), (P, victim, "disappeared")}
    assert next(c for c in ch if c.change_type == "duplicate").related_sample_id == donor


def test_near_duplicate_on_continuous_data(releases):
    a, b, clinical, protein = releases
    rng = np.random.default_rng(1)
    big = protein.reindex(range(60)).copy()  # more features so a near-copy is distinguishable
    big.index = [f"P{i}" for i in range(60)]
    big[:] = rng.normal(0, 1, big.shape)
    write(a, clinical, big)
    new = next(s for s in clinical.sampleID if s not in big.columns and s[13:15] == "01")
    p = big.copy()
    p[new] = p[big.columns[0]] + rng.normal(0, 1e-4, 60)
    write(b, clinical, p)
    ch = detect_changes(Release(a), Release(b))
    assert (P, new, "duplicate") in kinds(ch)


def test_label_change_reports_the_column(releases):
    a, b, clinical, protein = releases
    c2 = clinical.copy()
    c2.loc[3, "PAM50Call_RNAseq"] = "Her2" if c2.loc[3, "PAM50Call_RNAseq"] != "Her2" else "LumA"
    write(b, c2, protein)
    ch = detect_changes(Release(a), Release(b))
    assert len(ch) == 1 and ch[0].change_type == "label_change" and ch[0].fields == ["PAM50Call_RNAseq"]


def test_id_case_and_sample_type_code(releases):
    a, b, clinical, protein = releases
    s1, s2 = protein.columns[4], protein.columns[5]
    p = protein.rename(columns={s1: s1.lower(), s2: s2[:13] + "06"})
    write(b, clinical, p)
    ch = kinds(detect_changes(Release(a), Release(b)))
    assert (P, s1, "id_format_change") in ch and (P, s2, "sample_type_change") in ch


def test_value_shift_lists_fields_and_scale(releases):
    a, b, clinical, protein = releases
    p = protein.copy()
    s = p.columns[6]
    p[s] = p[s] * 2
    write(b, clinical, p)
    ch = detect_changes(Release(a), Release(b))
    assert len(ch) == 1 and ch[0].change_type == "value_shift"
    assert set(ch[0].fields) == set(p.index) and "scaled by about 2" in ch[0].evidence


def test_shared_profiles_are_not_called_copies(releases):
    """A profile several samples already share in A identifies nobody: no swap or duplicate claims."""
    a, b, clinical, protein = releases
    p = protein.copy()
    flat = [1.0] * len(p.index)
    flat[0] = 2.0
    for s in p.columns[:3]:
        p[s] = flat
    write(a, clinical, p)
    p2 = p.copy()
    p2[p.columns[3]] = flat  # a 4th sample takes the shared flat profile
    write(b, clinical, p2)
    ch = detect_changes(Release(a), Release(b))
    assert [c.change_type for c in ch] == ["value_shift"]


def test_detector_feeds_impact_and_findings(releases):
    a, b, clinical, protein = releases
    x, y = er_pair(clinical, protein)
    write(b, clinical, swapped(protein, x, y))
    doc = build(detect_changes(Release(a), Release(b)), Release(a), Release(b))
    f = doc["findings"][0]
    assert f["kind"] == "sample_swap" and f["affects_analyses"] == ["A1"] and f["not_affected_analyses"] == ["A2"]
    assert not any(x["kind"] == "other" for x in doc["findings"])  # explained, so no "unexplained" finding


def test_resaved_clinical_formatting_is_not_a_change(releases):
    """Another tool re-saving the file ('55' -> '55.0', 'true' -> 'True', '' -> 'NA') changes no values."""
    a, b, clinical, protein = releases
    c = clinical.copy()
    c["flag"] = ["true" if i % 2 else "" for i in range(len(c))]
    write(a, c, protein)
    c2 = c.copy()
    c2["age"] = c2["age"].astype(float)
    c2["flag"] = c2["flag"].map(lambda v: "True" if v == "true" else "NA")
    write(b, c2, protein)
    assert detect_changes(Release(a), Release(b)) == []


def test_vanished_file_is_a_finding_except_rna(releases, tmp_path):
    a, b, clinical, protein = releases
    write(b, clinical, protein)
    (b / "protein_rppa.tsv.gz").unlink()
    ch = detect_changes(Release(a), Release(b))
    assert ch and all(c.change_type == "disappeared" and c.file == P for c in ch)
    assert {c.sample_id for c in ch} == set(protein.columns)
    # RNA missing from the new release is expected for envelopes: no finding
    import shutil
    shutil.copy(a / "protein_rppa.tsv.gz", a / "rna_hiseq.tsv.gz")
    write(b, clinical, protein)
    assert detect_changes(Release(a), Release(b)) == []


def test_repeated_column_id_is_a_duplicate_not_a_new_sample(releases):
    """pandas renames a repeated column to 'ID.1'; that must not become a fake new sample."""
    a, b, clinical, protein = releases
    s = protein.columns[2]
    p = protein.copy()
    raw = p.to_csv(sep="\t").splitlines()
    # write the file by hand with the same column header twice
    header = raw[0].split("\t") + [s]
    rows = [r + "\t" + r.split("\t")[1 + list(p.columns).index(s)] for r in raw[1:]]
    import gzip
    write(b, clinical, p)
    with gzip.open(b / "protein_rppa.tsv.gz", "wt", newline="") as f:
        f.write("\t".join(header) + "\n" + "\n".join(rows) + "\n")
    ch = detect_changes(Release(a), Release(b))
    assert [(c.change_type, c.sample_id) for c in ch] == [("duplicate", s)]
    assert "appears 2 times" in ch[0].evidence


def test_repeated_clinical_row_is_reported(releases):
    a, b, clinical, protein = releases
    c2 = pd.concat([clinical, clinical.iloc[[5]]], ignore_index=True)
    write(b, c2, protein)
    ch = detect_changes(Release(a), Release(b))
    assert [(c.change_type, c.file, c.sample_id) for c in ch] == [("duplicate", "clinical.tsv", clinical.sampleID[5])]
