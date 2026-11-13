"""Synthetic tests; do not read the organizers' practice answer key."""
import json

import pandas as pd
import pytest

from tripwire.contract import Change
from tripwire.mutation_lab.core import CLINICAL, PROTEIN, evaluate, generate
from tripwire.mutation_lab.__main__ import main
from tripwire.release import file_sha256


@pytest.mark.parametrize("scenario,kind,count", [
    ("unchanged", None, 0), ("reordered", None, 0), ("swap", "swap", 2),
    ("duplicate", "duplicate", 1), ("disappeared", "disappeared", 1),
    ("label_change", "label_change", 1), ("value_shift", "value_shift", 1),
])
def test_mutations_are_observable_and_source_is_unchanged(releases, scenario, kind, count):
    source, target, _, _ = releases
    hashes = {p.name: file_sha256(p) for p in source.iterdir()}
    expected = generate(source, target, scenario, seed=12)
    assert len(expected) == count
    assert all(c.change_type == kind for c in expected)
    assert hashes == {p.name: file_sha256(p) for p in source.iterdir()}
    old = pd.read_csv(source / PROTEIN, sep="\t", index_col=0)
    new = pd.read_csv(target / PROTEIN, sep="\t", index_col=0)
    if scenario == "swap":
        x, y = expected[0].sample_id, expected[0].related_sample_id
        pd.testing.assert_series_equal(new[x], old[y], check_names=False)
        pd.testing.assert_series_equal(new[y], old[x], check_names=False)
        assert len(old.columns) == len(new.columns)
    elif scenario == "duplicate":
        x, y = expected[0].sample_id, expected[0].related_sample_id
        pd.testing.assert_series_equal(new[x], old[y], check_names=False)
        assert not old[x].equals(new[x])
    elif scenario == "disappeared":
        assert expected[0].sample_id not in new.columns
    elif scenario == "label_change":
        new_clinical = pd.read_csv(target / CLINICAL, sep="\t").set_index("sampleID")
        assert new_clinical.loc[expected[0].sample_id, expected[0].fields[0]] == expected[0].after
    elif scenario == "value_shift":
        x = expected[0].sample_id
        assert new.at["ERALPHA", x] == pytest.approx(old.at["ERALPHA", x] + 10)
    elif scenario == "reordered":
        pd.testing.assert_frame_equal(old.sort_index().sort_index(axis=1), new.sort_index().sort_index(axis=1))


def test_reproducibility_and_protect_existing_files(releases, tmp_path):
    source, target, _, _ = releases
    other = tmp_path / "C"
    first = generate(source, target, "swap", seed=19)
    second = generate(source, other, "swap", seed=19)
    assert [c.to_dict() for c in first] == [c.to_dict() for c in second]
    with pytest.raises(FileExistsError):
        generate(source, target, "swap")
    with pytest.raises(ValueError):
        generate(source, source / "nested", "swap")
    with pytest.raises(ValueError):
        generate(source, tmp_path, "swap")


def test_strict_score_counts_misses_duplicates_and_false_alarms():
    a = Change("a", "swap", PROTEIN, related_sample_id="b")
    b = Change("b", "swap", PROTEIN, related_sample_id="a")
    false = Change("c", "duplicate", PROTEIN)
    report = evaluate([a, b], [a, a, false])
    by_kind = {r["change_type"]: r for r in report["by_change_type"]}
    assert by_kind["swap"]["true_positives"] == 1
    assert by_kind["swap"]["false_positives"] == 1
    assert by_kind["swap"]["false_negatives"] == 1
    assert by_kind["swap"]["precision"] == .5 and by_kind["swap"]["recall"] == .5
    assert by_kind["duplicate"]["precision"] == 0 and by_kind["duplicate"]["recall"] is None
    assert evaluate([], [false])["false_positives_on_no_change"] == 1
    assert evaluate([], [])["by_change_type"] == []


def test_cli_reports_stub_and_does_not_treat_it_as_a_pass(releases, tmp_path, capsys):
    source, target, _, _ = releases
    truth = tmp_path / "truth.json"
    assert main(["generate", str(source), str(target), "--scenario", "swap", "--truth", str(truth)]) == 0
    capsys.readouterr()
    assert main(["score", str(source), str(target), "--truth", str(truth)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["expected_total"] == 2
    # Remove this assertion once Role 1 replaces the stub; the report itself is detector-independent.
    if any("stub" in warning.lower() for warning in report["detector_warnings"]):
        assert report["by_change_type"][0]["false_negatives"] == 2
