"""Synthetic tests; do not read the organizers' practice answer key."""
import gzip
import json
import math
import types

import pandas as pd
import pytest

from tripwire.contract import Change, norm_id
from tripwire.mutation_lab import __main__ as cli
from tripwire.mutation_lab.core import (CLINICAL, CONTROLS, COVERAGE_FRACTION, DESCRIPTIONS, ER_COL, PROTEIN,
                                        SCENARIOS, evaluate, generate)
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


# ------------------------------------------------ ID format, sample type and subgroup coverage scenarios

ORIGINAL = ("unchanged", "reordered", "swap", "duplicate", "disappeared", "label_change", "value_shift")
NEW = ("id_case_change", "id_whitespace", "sample_type_change", "coverage_loss")

# TCGA-style barcodes with the same awkward text as RAW_*: blanks, NA, leading zeros, 1.50, 1e-3,
# a non-numeric cell, a normal (11) whose 01 sibling exists, and a 06 sample with no ER label.
BC = ["TCGA-AA-0001-01", "TCGA-AA-0002-01", "TCGA-AA-0003-01", "TCGA-AA-0004-01", "TCGA-AA-0001-11",
      "TCGA-AA-0005-06"]
RAW_BC_CLINICAL = ("sampleID\tbreast_carcinoma_estrogen_receptor_status\tage\tcode\n"
                   f"{BC[0]}\tPositive\t45\t007\n{BC[1]}\tNegative\t\tNA\n{BC[2]}\tPositive\t50\t010\n"
                   f"{BC[3]}\tNegative\t61\t\n{BC[4]}\tIndeterminate\t45\t\n{BC[5]}\t\t70\t\n")
RAW_BC_PROTEIN = ("sample\t" + "\t".join(BC) + "\n"
                  "ERALPHA\t1.50\t-0.2500\tNA\t2\t0.0\t3\n"
                  "AKT\t0.1\t1e-3\t0.30\t\tx\t1.0\n")


def test_original_scenarios_keep_names_and_order():
    assert SCENARIOS[:len(ORIGINAL)] == ORIGINAL
    assert set(SCENARIOS) == set(ORIGINAL) | set(NEW) == set(DESCRIPTIONS)
    assert set(CONTROLS) == {"unchanged", "reordered"}


@pytest.mark.parametrize("scenario", NEW)
@pytest.mark.parametrize("seed", range(6))
def test_new_scenarios_change_only_planted_cells_and_record_truth(tmp_path, scenario, seed):
    source = write_raw(tmp_path / "A", RAW_BC_CLINICAL, RAW_BC_PROTEIN)
    target = tmp_path / "B"
    expected = generate(source, target, scenario, seed=seed)
    assert expected and len({(c.change_type, c.file, c.sample_id) for c in expected}) == len(expected)
    assert all(c.file == PROTEIN for c in expected)
    old_p, new_p = read_text(source / PROTEIN, index_col=0), read_text(target / PROTEIN, index_col=0)
    old_num = old_p.apply(pd.to_numeric, errors="coerce")
    want_p = old_p.copy()
    if scenario == "coverage_loss":
        status = dict(zip(read_text(source / CLINICAL)["sampleID"], read_text(source / CLINICAL)[ER_COL]))
        assert len({status[c.sample_id] for c in expected}) == 1  # concentrated in one subgroup
        for c in expected:
            assert c.change_type == "coverage_loss" and c.fields
            assert old_num.loc[c.fields, c.sample_id].notna().all()  # only present values are blanked
            assert c.before == f"{len(c.fields)} of {len(old_p.index)} values present"
            assert c.after == f"0 of {len(old_p.index)} values present"
            want_p.loc[c.fields, c.sample_id] = "NA"
    else:
        (c,) = expected
        assert c.before == c.sample_id and c.after != c.before and c.fields == []
        if scenario == "sample_type_change":
            assert c.change_type == "sample_type_change" and c.related_sample_id == c.after
            assert c.after[:12] == c.before[:12] and c.after[15:] == c.before[15:]
            assert (c.before[13:15], c.after[13:15]) in {("01", "06"), ("06", "01")}
            assert c.sample_id != BC[4]  # 11 -> 01 would collide with the existing primary sample
        else:
            assert c.change_type == "id_format_change" and norm_id(c.after) == norm_id(c.before)
            if scenario == "id_whitespace":
                assert c.after.strip() == c.before and c.after != c.before
            else:
                assert c.after.upper() == c.before.upper() and c.after.strip() == c.after
        want_p = want_p.rename(columns={c.sample_id: c.after})
    pd.testing.assert_frame_equal(new_p, want_p)
    assert file_sha256(source / CLINICAL) == file_sha256(target / CLINICAL)


@pytest.mark.parametrize("scenario", NEW)
def test_new_scenarios_are_observable_reproducible_and_leave_source(releases, tmp_path, scenario):
    source, target, _, _ = releases
    hashes = {p.name: file_sha256(p) for p in source.iterdir()}
    first = generate(source, target, scenario, seed=5)
    again = generate(source, tmp_path / "again", scenario, seed=5)
    assert [c.to_dict() for c in first] == [c.to_dict() for c in again]
    picks = {tuple(c.sample_id for c in generate(source, tmp_path / f"s{seed}", scenario, seed=seed))
             for seed in range(6)}
    assert len(picks) > 1  # the seed really chooses
    assert hashes == {p.name: file_sha256(p) for p in source.iterdir()}
    old = pd.read_csv(source / PROTEIN, sep="\t", index_col=0)
    new = pd.read_csv(target / PROTEIN, sep="\t", index_col=0)
    if scenario == "coverage_loss":
        for c in first:
            assert old[c.sample_id].notna().any() and new[c.sample_id].isna().all()
        untouched = [s for s in old.columns if s not in {c.sample_id for c in first}]
        pd.testing.assert_frame_equal(old[untouched], new[untouched])
    else:
        (c,) = first
        assert c.sample_id in old.columns and c.sample_id not in new.columns and c.after in new.columns
        pd.testing.assert_series_equal(old[c.sample_id], new[c.after], check_names=False)
        assert len(old.columns) == len(new.columns)


def test_coverage_loss_is_concentrated_in_one_er_subgroup(releases):
    source, target, clinical, protein = releases
    expected = generate(source, target, "coverage_loss", seed=3)
    status = dict(zip(clinical["sampleID"], clinical[ER_COL]))
    (group,) = {status[c.sample_id] for c in expected}
    members = [s for s in protein.columns if status[s] == group]
    assert len(expected) == math.ceil(COVERAGE_FRACTION * len(members))
    old = pd.read_csv(source / PROTEIN, sep="\t", index_col=0)
    new = pd.read_csv(target / PROTEIN, sep="\t", index_col=0)

    def missing_rate(df, er):
        cols = [s for s in df.columns if status.get(s) == er]
        return df[cols].isna().to_numpy().mean()
    other = "Negative" if group == "Positive" else "Positive"
    assert missing_rate(new, group) > missing_rate(old, group)
    assert missing_rate(new, other) == missing_rate(old, other)


def test_sample_type_change_skips_ambiguous_candidates(tmp_path):
    ids = ["TCGA-AA-0001-01", "TCGA-AA-0001-06",   # each one's new ID already exists
           "TCGA-AA-0002-01", "TCGA-AA-0003-01",   # numerically identical profiles (2 vs 2.0)
           "TCGA-AA-0004-01",                      # no values
           "TCGA-AA-0006-01",                      # new ID 0006-06 exists in clinical.tsv
           "TCGA-AA-0007-02",                      # type code the lab does not rewrite
           "S9",                                   # not a barcode
           "TCGA-AA-0005-01"]                      # the only valid choice
    protein = ("sample\t" + "\t".join(ids) + "\n"
               "ERALPHA\t1\t2\t2\t2.0\tNA\t5\t6\t7\t8\n"
               "AKT\t1\t3\t4\t4\t\t5\t6\t7\t9\n")
    clinical = "sampleID\tbreast_carcinoma_estrogen_receptor_status\n" + \
        "".join(f"{s}\tPositive\n" for s in ids) + "TCGA-AA-0006-06\tNegative\n"
    source = write_raw(tmp_path / "A", clinical, protein)
    for seed in range(8):
        (change,) = generate(source, tmp_path / f"B{seed}", "sample_type_change", seed=seed)
        assert (change.sample_id, change.after) == ("TCGA-AA-0005-01", "TCGA-AA-0005-06")


def test_new_scenarios_refuse_unsuitable_sources_before_any_output(tmp_path):
    source = write_raw(tmp_path / "A")  # S1..S4: not barcodes
    with pytest.raises(ValueError, match="TCGA barcode"):
        generate(source, tmp_path / "B", "sample_type_change")
    no_er = write_raw(tmp_path / "A2", clinical="sampleID\tage\nS1\t1\nS2\t2\n")
    with pytest.raises(ValueError, match="missing"):
        generate(no_er, tmp_path / "B", "coverage_loss")
    unlabelled = write_raw(tmp_path / "A3", clinical=f"sampleID\t{ER_COL}\nS1\tIndeterminate\nS2\t\n")
    with pytest.raises(ValueError, match="ER Positive or Negative"):
        generate(unlabelled, tmp_path / "B", "coverage_loss")
    no_letters = write_raw(tmp_path / "A4", protein="sample\t101\t102\nERALPHA\t1\t2\n")
    with pytest.raises(ValueError, match="case"):
        generate(no_letters, tmp_path / "B", "id_case_change")
    assert not (tmp_path / "B").exists()


def test_id_scenarios_skip_ids_that_already_differ_only_by_format(tmp_path):
    # "S1" and "s1" already share a comparison key, so neither may be the planted sample.
    source = write_raw(tmp_path / "A", protein="sample\tS1\ts1\t123\tAB\nERALPHA\t1\t2\t3\t4\n")
    for seed in range(8):
        (case,) = generate(source, tmp_path / f"C{seed}", "id_case_change", seed=seed)
        assert (case.sample_id, case.after) == ("AB", "ab")
        (space,) = generate(source, tmp_path / f"W{seed}", "id_whitespace", seed=seed)
        assert space.sample_id in {"123", "AB"}


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_truth_scores_perfectly_against_itself(releases, scenario):
    # Self-consistency of the answer key: unique keys, no partner or type mismatch with itself.
    source, target, _, _ = releases
    expected = generate(source, target, scenario, seed=8)
    report = evaluate(expected, list(expected))
    assert report["reported_as_other_type"] == []
    assert all(r["false_positives"] == r["false_negatives"] == 0 and r["recall"] == 1
               and r["partner_matches"] == r["expected_with_partner"] for r in report["by_change_type"])
    if scenario in CONTROLS:
        assert expected == [] and report["false_positives_on_no_change"] == 0


def test_controls_flag_any_report_as_false_positive():
    stray = [Change("x", "id_format_change", PROTEIN), Change("y", "coverage_loss", PROTEIN)]
    report = evaluate([], stray)
    assert report["false_positives_on_no_change"] == 2
    assert all(r["precision"] == 0 and r["recall"] is None for r in report["by_change_type"])
    assert report["reported_as_other_type"] == []


def test_other_type_reports_expose_interpretation_without_changing_strict_counts():
    expected = [Change("a", "coverage_loss", PROTEIN), Change("b", "coverage_loss", PROTEIN),
                Change("c", "sample_type_change", PROTEIN), Change("d", "id_format_change", PROTEIN)]
    observed = [Change("a", "value_shift", PROTEIN),          # same sample and file, other type
                Change("b", "value_shift", CLINICAL),         # other file: not paired
                Change("z", "value_shift", PROTEIN),          # other sample: not paired
                Change("c", "disappeared", PROTEIN),          # same sample, other type
                Change("d", "id_format_change", PROTEIN)]     # exact match: not listed
    report = evaluate(expected, observed)
    by = {r["change_type"]: r for r in report["by_change_type"]}
    assert by["coverage_loss"]["false_negatives"] == 2 and by["coverage_loss"]["true_positives"] == 0
    assert by["coverage_loss"]["missed_but_reported_as_other_type"] == 1
    assert by["value_shift"]["false_positives"] == 3
    assert by["sample_type_change"]["missed_but_reported_as_other_type"] == 1
    assert by["id_format_change"]["true_positives"] == 1
    assert by["id_format_change"]["missed_but_reported_as_other_type"] == 0
    assert report["reported_as_other_type"] == [
        {"expected_type": "coverage_loss", "reported_type": "value_shift", "count": 1},
        {"expected_type": "sample_type_change", "reported_type": "disappeared", "count": 1}]


def test_one_report_is_not_paired_with_two_misses():
    expected = [Change("a", "coverage_loss", PROTEIN), Change("a", "sample_type_change", PROTEIN)]
    report = evaluate(expected, [Change("a", "value_shift", PROTEIN)])
    assert sum(x["count"] for x in report["reported_as_other_type"]) == 1


def test_cli_lists_scenarios(capsys):
    assert main(["scenarios"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [line.split(":")[0].split(" ")[0] for line in lines] == list(SCENARIOS)
    assert sum("no-change control" in line for line in lines) == len(CONTROLS)


def test_cli_scores_coverage_loss_and_explains_type_mismatch(releases, tmp_path, capsys):
    source, target, _, _ = releases
    truth = tmp_path / "truth.json"
    assert main(["generate", str(source), str(target), "--scenario", "coverage_loss", "--truth", str(truth)]) == 0
    manifest = json.loads(truth.read_text())
    assert manifest["changes"] and {c["change_type"] for c in manifest["changes"]} == {"coverage_loss"}
    capsys.readouterr()
    assert main(["score", str(source), str(target), "--truth", str(truth)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["expected_total"] == len(manifest["changes"]) and report["truth_hashes_verified"]
    assert "reported_as_other_type" in report
    if report["reported_as_other_type"]:
        assert any("another change type" in line for line in report["limitations"])
