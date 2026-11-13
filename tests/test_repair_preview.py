from conftest import write
from test_impact_verdicts import er_pair, swapped
from tripwire.analyses import a1_run, public
from tripwire.contract import Change
from tripwire.findings import build
from tripwire.release import Release
from tripwire.validate import challenge_dir, validate


def test_restoring_a_swap_previews_release_A_exactly(releases):
    a, b, clinical, protein = releases
    x, y = er_pair(clinical, protein)
    write(b, clinical, swapped(protein, x, y))
    doc = build([Change(x, "swap", "protein_rppa.tsv.gz", related_sample_id=y),
                 Change(y, "swap", "protein_rppa.tsv.gz", related_sample_id=x)], Release(a), Release(b))
    r = next(r for r in doc["repairs"] if r["action"] == "restore_from_previous_release")
    p = next(x for x in r["preview"]["analyses"] if x["analysis"] == "A1")
    assert p["if_approved"] == public(a1_run(Release(a)))       # undoing the swap gives release A's result back
    assert p["now"] != p["if_approved"] and p["verdict_if_approved"] == "Ready"
    assert "nothing is applied" in r["preview"]["note"].lower()
    assert doc["repair_preview_all"]["repairs"] == [r["id"]]


def test_exclusion_preview_and_source_untouched(releases):
    a, b, clinical, protein = releases
    dup = protein.columns[3]
    p2 = protein.copy()
    p2[dup] = p2[protein.columns[4]]
    write(b, clinical, p2)
    before = (b / "protein_rppa.tsv.gz").read_bytes()
    doc = build([Change(dup, "duplicate", "protein_rppa.tsv.gz", related_sample_id=protein.columns[4])],
                Release(a), Release(b))
    r = next(r for r in doc["repairs"] if r["action"] == "exclude")
    a1 = next(x for x in r["preview"]["analyses"] if x["analysis"] == "A1")
    assert a1["if_approved"]["n_samples"] == a1["now"]["n_samples"] - (1 if dup[13:15] == "01" else 0)
    assert (b / "protein_rppa.tsv.gz").read_bytes() == before   # nothing written


def test_flag_for_review_has_no_numbers_to_preview(releases):
    a, b, clinical, protein = releases
    write(b, clinical, protein.drop(columns=protein.columns[:2]))
    doc = build([Change(s, "disappeared", "protein_rppa.tsv.gz") for s in protein.columns[:2]], Release(a), Release(b))
    assert all("analyses" not in r["preview"] for r in doc["repairs"] if r["action"] == "flag_for_review")


def test_previews_keep_findings_valid(releases):
    if challenge_dir() is None:
        return
    a, b, clinical, protein = releases
    x, y = er_pair(clinical, protein)
    write(b, clinical, swapped(protein, x, y))
    doc = build([Change(x, "swap", "protein_rppa.tsv.gz", related_sample_id=y)], Release(a), Release(b))
    assert validate(doc) == []
