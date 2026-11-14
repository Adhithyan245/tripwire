"""Independent synthetic controls for profile-chain detection; no organizer answer key."""
import numpy as np
import pandas as pd
import pytest

from conftest import make_release, write
from tripwire.detect import detect_changes
from tripwire.release import Release


@pytest.fixture
def rich_releases(tmp_path):
    a, b = tmp_path / "A", tmp_path / "B"
    clinical, protein = make_release(a)
    rng = np.random.default_rng(5)
    extra = pd.DataFrame(rng.normal(size=(18, len(protein.columns))),
                         index=[f"PROTEIN_{i}" for i in range(18)], columns=protein.columns)
    protein = pd.concat([protein, extra])
    protein.index.name = "sample"
    write(a, clinical, protein)
    return a, b, clinical, protein


def test_closed_three_sample_cycle_is_detected(rich_releases):
    a, b, clinical, p = rich_releases
    x, y, z = p.columns[:3]
    changed = p.copy()
    changed[x], changed[y], changed[z] = p[y], p[z], p[x]
    write(b, clinical, changed)
    assert {(c.sample_id, c.change_type) for c in detect_changes(Release(a), Release(b))} == {
        (x, "swap"), (y, "swap"), (z, "swap")}


def test_open_profile_chain_is_not_claimed_as_a_swap(rich_releases):
    a, b, clinical, p = rich_releases
    x, y, z = p.columns[:3]
    changed = p.copy()
    changed[x], changed[y], changed[z] = p[y], p[z], p[z] + 0.123
    write(b, clinical, changed)
    # X and Y received old profiles; Z independently shifted. No profile moved back to X.
    changes = detect_changes(Release(a), Release(b))
    assert all(c.change_type != "swap" for c in changes)


def test_open_chain_is_reported_as_a_one_way_transfer_with_its_source(rich_releases):
    a, b, clinical, p = rich_releases
    x, y, z = p.columns[:3]
    changed = p.copy()
    changed[x], changed[y], changed[z] = p[y], p[z], p[z] + 0.123
    write(b, clinical, changed)
    by = {c.sample_id: c for c in detect_changes(Release(a), Release(b))}
    assert by[x].change_type == "value_shift" and "one-way transfer" in by[x].evidence and by[x].related_sample_id == y


def test_one_way_copy_with_a_changed_donor_is_not_a_swap(rich_releases):
    a, b, clinical, p = rich_releases
    x, y = p.columns[:2]
    changed = p.copy()
    changed[x], changed[y] = p[y], p[y] + 0.5
    write(b, clinical, changed)
    changes = detect_changes(Release(a), Release(b))
    assert all(c.change_type != "swap" for c in changes)
    assert any(c.sample_id == x and "one-way transfer" in c.evidence for c in changes)


def test_closed_four_sample_cycle_is_still_a_swap(rich_releases):
    a, b, clinical, p = rich_releases
    w, x, y, z = p.columns[:4]
    changed = p.copy()
    changed[w], changed[x], changed[y], changed[z] = p[x], p[y], p[z], p[w]
    write(b, clinical, changed)
    got = {(c.sample_id, c.change_type) for c in detect_changes(Release(a), Release(b))}
    assert got == {(w, "swap"), (x, "swap"), (y, "swap"), (z, "swap")}


def test_plain_pair_swap_unchanged(rich_releases):
    a, b, clinical, p = rich_releases
    x, y = p.columns[:2]
    changed = p.copy()
    changed[x], changed[y] = p[y], p[x]
    write(b, clinical, changed)
    assert {(c.sample_id, c.change_type) for c in detect_changes(Release(a), Release(b))} == {(x, "swap"), (y, "swap")}


def test_transfer_finding_says_transfer_and_asks_a_person(rich_releases):
    from tripwire.findings import build
    a, b, clinical, p = rich_releases
    x, y = p.columns[:2]
    changed = p.copy()
    changed[x], changed[y] = p[y], p[y] + 0.5
    write(b, clinical, changed)
    ra, rb = Release(a), Release(b)
    doc = build(detect_changes(ra, rb), ra, rb)
    f = next(f for f in doc["findings"] if "one-way transfer" in f["summary"])
    r = next(r for r in doc["repairs"] if f["id"] in r["addresses"])
    assert r["action"] == "flag_for_review" and "moved on purpose" in r["justification"]
    assert not any(x["kind"] == "sample_swap" for x in doc["findings"])
