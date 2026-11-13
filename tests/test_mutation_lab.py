"""Synthetic tests; do not read the organizers' practice answer key."""
import gzip
import json
import types

import pandas as pd
import pytest

from tripwire.contract import Change
from tripwire.mutation_lab import __main__ as cli
from tripwire.mutation_lab.core import CLINICAL, PROTEIN, evaluate, generate
from tripwire.mutation_lab.__main__ import main
from tripwire.release import file_sha256

# Hand-written text with blanks, NA, leading zeros and odd float formatting, which a
# type-inferring pandas round trip would silently rewrite.
RAW_CLINICAL = ("sampleID\tbreast_carcinoma_estrogen_receptor_status\tage\tcode\n"
                "S1\tPositive\t45\t007\nS2\tNegative\t\tNA\nS3\tPositive\t50\t010\nS4\tNegative\t61\t\n")
RAW_PROTEIN = "sample\tS1\tS2\tS3\tS4\nERALPHA\t1.50\t-0.2500\tNA\t2\nAKT\t0.1\t1e-3\t0.30\t\n"


def write_raw(dest, clinical=RAW_CLINICAL, protein=RAW_PROTEIN):
    dest.mkdir()
    (dest / CLINICAL).write_text(clinical)
    with gzip.open(dest / PROTEIN, "wt") as f:
        f.write(protein)
    return dest


def read_text(path, **kwargs):
    return pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False, na_filter=False, **kwargs)


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
    assert report["truth_hashes_verified"] is True


@pytest.mark.parametrize("scenario", ["unchanged", "reordered", "swap", "duplicate",
                                      "disappeared", "label_change", "value_shift"])
@pytest.mark.parametrize("seed", range(4))
def test_only_planted_cells_change_text_is_preserved(tmp_path, scenario, seed):
    source = write_raw(tmp_path / "A")
    target = tmp_path / "B"
    expected = generate(source, target, scenario, seed=seed)
    old_c, new_c = read_text(source / CLINICAL), read_text(target / CLINICAL)
    old_p, new_p = read_text(source / PROTEIN, index_col=0), read_text(target / PROTEIN, index_col=0)
    want_c, want_p = old_c.copy(), old_p.copy()
    if scenario == "reordered":
        want_c, want_p = old_c.iloc[::-1], old_p.iloc[::-1, ::-1]
    elif scenario == "swap":
        x, y = expected[0].sample_id, expected[0].related_sample_id
        want_p[x], want_p[y] = old_p[y], old_p[x]
    elif scenario == "duplicate":
        want_p[expected[0].sample_id] = old_p[expected[0].related_sample_id]
    elif scenario == "disappeared":
        want_p = old_p.drop(columns=[expected[0].sample_id])
    elif scenario == "label_change":
        change = expected[0]
        row = want_c.index[want_c["sampleID"] == change.sample_id][0]
        assert want_c.at[row, change.fields[0]] == change.before
        want_c.at[row, change.fields[0]] = change.after
    elif scenario == "value_shift":
        change = expected[0]
        assert change.sample_id != "S3"  # "NA" is never shifted
        assert float(old_p.at["ERALPHA", change.sample_id]) == change.before
        want_p.at["ERALPHA", change.sample_id] = repr(change.before + 10.0)
    pd.testing.assert_frame_equal(new_c.reset_index(drop=True), want_c.reset_index(drop=True))
    pd.testing.assert_frame_equal(new_p, want_p)
    if scenario not in {"label_change", "reordered"}:
        assert file_sha256(source / CLINICAL) == file_sha256(target / CLINICAL)
    if scenario in {"unchanged", "label_change"}:
        assert file_sha256(source / PROTEIN) == file_sha256(target / PROTEIN)


def test_repeated_headers_are_rejected_before_any_output(tmp_path):
    source = write_raw(tmp_path / "A", protein="sample\tS1\tS1\nERALPHA\t1\t2\n")
    with pytest.raises(ValueError, match="repeated column"):
        generate(source, tmp_path / "B", "swap")
    assert not (tmp_path / "B").exists()


def test_value_shift_skips_unobservable_values(tmp_path):
    source = write_raw(tmp_path / "A", protein="sample\tS1\tS2\tS3\tS4\nERALPHA\tinf\t1e20\tNA\t1.0\n")
    for seed in range(10):
        target = tmp_path / f"B{seed}"
        assert generate(source, target, "value_shift", seed=seed)[0].sample_id == "S4"


def test_numerically_identical_profiles_are_not_a_valid_swap(tmp_path):
    source = write_raw(tmp_path / "A", protein="sample\tS1\tS2\nERALPHA\t1\t1.0\nAKT\t2\t2.00\n")
    with pytest.raises(ValueError, match="distinct"):
        generate(source, tmp_path / "B", "swap")
    assert not (tmp_path / "B").exists()


def test_failed_write_rolls_back_even_on_interrupt(releases, monkeypatch):
    source, target, _, _ = releases

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt
    monkeypatch.setattr(pd.DataFrame, "to_csv", interrupted)
    with pytest.raises(KeyboardInterrupt):
        generate(source, target, "swap")
    assert not target.exists()


def test_dangling_symlink_target_is_refused(releases, tmp_path):
    source, _, _, _ = releases
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "elsewhere")
    with pytest.raises(FileExistsError):
        generate(source, link, "swap")
    assert not (tmp_path / "elsewhere").exists()


def test_partner_is_scored_separately():
    expected = [Change("a", "swap", PROTEIN, related_sample_id="b"),
                Change("b", "swap", PROTEIN, related_sample_id="a")]
    observed = [Change("a", "swap", PROTEIN, related_sample_id="c"),
                Change("b", "swap", PROTEIN, related_sample_id="a")]
    swap = evaluate(expected, observed)["by_change_type"][0]
    assert swap["true_positives"] == 2 and swap["recall"] == 1
    assert swap["expected_with_partner"] == 2 and swap["partner_matches"] == 1


def test_cli_refuses_truth_for_other_releases(releases, tmp_path, capsys):
    source, target, _, _ = releases
    truth = tmp_path / "truth.json"
    assert main(["generate", str(source), str(target), "--scenario", "value_shift", "--truth", str(truth)]) == 0
    manifest = json.loads(truth.read_text())
    assert set(manifest["source_files"]) == {CLINICAL, PROTEIN}
    assert main(["score", str(source), str(target), "--truth", str(truth)]) == 0
    capsys.readouterr()
    other = tmp_path / "other"
    generate(source, other, "swap", seed=3)
    with pytest.raises(SystemExit):
        main(["score", str(source), str(other), "--truth", str(truth)])
    assert "do not match" in capsys.readouterr().err


def test_cli_rolls_back_target_and_truth_when_manifest_write_fails(releases, tmp_path, monkeypatch):
    source, target, _, _ = releases
    truth = tmp_path / "truth.json"

    def broken_dump(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(cli, "json", types.SimpleNamespace(dump=broken_dump, loads=json.loads))
    with pytest.raises(OSError):
        main(["generate", str(source), str(target), "--scenario", "swap", "--truth", str(truth)])
    assert not target.exists() and not truth.exists()


def test_cli_reports_bad_source_without_traceback(tmp_path, capsys):
    source = tmp_path / "A"
    source.mkdir()
    with pytest.raises(SystemExit) as exc:
        main(["generate", str(source), str(tmp_path / "B"), "--scenario", "swap",
              "--truth", str(tmp_path / "t.json")])
    assert exc.value.code == 2 and "must contain" in capsys.readouterr().err
    assert not (tmp_path / "B").exists() and not (tmp_path / "t.json").exists()


def test_cli_rejects_dangling_target_symlink(releases, tmp_path):
    source, target, _, _ = releases
    destination = tmp_path / "must-not-be-created"
    target.symlink_to(destination, target_is_directory=True)
    with pytest.raises(SystemExit):
        main(["generate", str(source), str(target), "--scenario", "swap", "--truth", str(tmp_path / "truth.json")])
    assert not destination.exists()
    assert target.is_symlink()


def test_cli_rejects_partial_or_malformed_truth(releases, tmp_path):
    source, target, _, _ = releases
    truth = tmp_path / "truth.json"
    main(["generate", str(source), str(target), "--scenario", "swap", "--truth", str(truth)])
    doc = json.loads(truth.read_text())
    del doc["target_files"]
    truth.write_text(json.dumps(doc))
    with pytest.raises(SystemExit):
        main(["score", str(source), str(target), "--truth", str(truth)])
    truth.write_text('{}')
    with pytest.raises(SystemExit):
        main(["score", str(source), str(target), "--truth", str(truth)])
