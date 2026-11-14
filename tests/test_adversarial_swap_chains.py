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


@pytest.mark.xfail(strict=True, reason="open profile chain is currently asserted to be a swap cycle")
def test_open_profile_chain_is_not_claimed_as_a_swap(rich_releases):
    a, b, clinical, p = rich_releases
    x, y, z = p.columns[:3]
    changed = p.copy()
    changed[x], changed[y], changed[z] = p[y], p[z], p[z] + 0.123
    write(b, clinical, changed)
    # X and Y received old profiles; Z independently shifted. No profile moved back to X.
    changes = detect_changes(Release(a), Release(b))
    assert all(c.change_type != "swap" for c in changes)
