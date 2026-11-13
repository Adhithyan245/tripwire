import numpy as np
import pandas as pd

from conftest import write
from tripwire.checks import cramers_v, patient_leakage, site_confounding
from tripwire.questions import BY_ID
from tripwire.release import Release

CARD = BY_ID["predict_er_from_protein"]


def wide(protein, n=20, seed=3):
    rng = np.random.default_rng(seed)
    extra = pd.DataFrame(rng.normal(0, 1, (n, protein.shape[1])), columns=protein.columns,
                         index=[f"P{i}" for i in range(n)])
    w = pd.concat([protein, extra])
    w.index.name = protein.index.name
    return w


def test_leakage_passes_when_every_sample_is_its_own_patient_and_profile(releases):
    a, _, clinical, protein = releases
    write(a, clinical, wide(protein))
    r = patient_leakage(CARD, Release(a))
    assert r.status == "pass"


def test_leakage_flags_copied_profiles_as_fixable_not_proven(releases):
    a, _, clinical, protein = releases
    w = wide(protein)
    s1, s2 = [c for c in w.columns if c[13:15] == "01"][:2]
    w[s2] = w[s1]
    write(a, clinical, w)
    r = patient_leakage(CARD, Release(a))
    assert r.status == "fixable" and "not demonstrated" in r.summary and "split by patient_id" in r.fix
    assert any(s1 in e["id"] or s1 in e.get("note", "") for e in r.evidence)


def test_leakage_ignores_flat_profiles(releases):
    a, _, clinical, protein = releases
    w = wide(protein)
    for s in w.columns[:3]:
        w[s] = 0.0
    write(a, clinical, w)
    assert patient_leakage(CARD, Release(a)).status == "pass"


def test_cramers_v_bounds():
    assert cramers_v(["a", "b"] * 50, ["x", "y"] * 50) > 0.99           # label fully determined by site
    assert cramers_v(["a", "b"] * 50, ["x"] * 50 + ["y"] * 50) < 0.05    # independent
    assert cramers_v(["a"] * 10, ["x", "y"] * 5) == 0.0                   # one label: nothing to confound


def test_site_confounding_fails_when_site_predicts_label(releases):
    a, _, clinical, protein = releases
    c = clinical.copy()
    # sites T0 and T1 from the barcode; make ER status follow the site exactly
    c["breast_carcinoma_estrogen_receptor_status"] = np.where(c.sampleID.str[5:7] == "T0", "Positive", "Negative")
    write(a, c, wide(protein))
    r = site_confounding(CARD, Release(a))
    assert r.status == "fail" and "Cramer's V" in r.summary
