from conftest import write
from test_impact_verdicts import er_pair, swapped
from tripwire.contract import Change
from tripwire.findings import build
from tripwire.questions import BY_ID, circular_inputs
from tripwire.release import Release


def test_plan_orders_repairs_first_and_cites_preview_effect(releases):
    a, b, clinical, protein = releases
    x, y = er_pair(clinical, protein)
    write(b, clinical, swapped(protein, x, y))
    doc = build([Change(x, "swap", "protein_rppa.tsv.gz", related_sample_id=y),
                 Change(y, "swap", "protein_rppa.tsv.gz", related_sample_id=x)], Release(a), Release(b))
    plan = doc["next_steps"]
    first = plan["steps"][0]
    assert first["step"] == 1 and first["who"] == "Curator" and "restoring" in first["action"]
    assert "A1" in (first["effect"] or "")                      # effect comes from the repair preview
    assert set(first["refs"]) >= {"R1", "F1"}
    assert any("Why a change happened" in c for c in plan["cannot_tell"])


def test_no_changes_means_no_action(releases):
    a, _, _, _ = releases
    plan = build([], Release(a), Release(a, name="again"))["next_steps"]
    assert all("Curator" != s["who"] for s in plan["steps"])
    holds = [s for s in plan["steps"] if s["action"].startswith("Hold")]
    assert [h["refs"] for h in holds] == [["predict_subtype_from_rna"]]  # only the circular question, whatever the data


def test_predicting_an_rna_derived_label_from_rna_is_circular(releases):
    card = BY_ID["predict_subtype_from_rna"]
    assert circular_inputs(card) == {"rna_hiseq.tsv.gz"}
    assert not circular_inputs(BY_ID["predict_subtype_from_copy_number"])
    a, _, _, _ = releases
    q = next(q for q in build([], Release(a), Release(a, name="again"))["questions"] if q["id"] == card.id)
    assert q["verdict"] == "Blocked" and "Circular" in q["why"]   # decided even though the release has no RNA
    assert q["checks"][0]["name"] == "label_circularity" and q["checks"][0]["status"] == "fail"
