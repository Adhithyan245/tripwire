# Role 3 QA: integrated run

## Controlled incident evidence

[INCIDENT_EVIDENCE.md](INCIDENT_EVIDENCE.md) adds a reproducible, literature-motivated QA experiment using a seeded synthetic swap, a count-only comparison, a no-change control, question-dependent outcomes and a ground-truth recovery. It measures partner accuracy separately and validates all three findings documents. It is a simulation, not a reproduction of an identified historical incident or a claim of superiority to an existing tool. Reproduce with `python scripts/qa/incident_replay.py <release-A> --seed 42 --out out/incident-replay-seed42`.

## Saturday retest after fixes (11:16 AM ET)

Tested Driftwire `6a34c5b550096246438c96fa2395d543cc42098f` with organizer commit `6e15a399a64ffbf80778db0b462ac239e70086b9` using the existing local environment and data. This is a retest, not a new fresh-clone timing. The two malformed-input crash regressions reported below were fixed in #44 and now pass without expected-failure markers. Full suite: **265 passed**, one pandas performance warning. The practice envelope was already open; comparison wrote findings in 3.4 seconds, the organizer validator returned `valid`, and the new `driftwire verify` reported `identical` on a separate rerun. Mutation Lab: **20/20** scenarios exactly matched with seed 7 in 31.3 seconds. Its generated cases are development tests, and the score does not verify partner or evidence correctness. Gitleaks scanned 44 reachable commits through `6a34c5b` and found no leaks. Repeat validation and Gitleaks on the final submitted commit.

The following Saturday morning section is historical: its two expected failures were resolved by #44, and its secret scan and clean-clone timing apply to the earlier commit named there.

## Saturday November 14 QA (10:28–10:31 AM ET)

Fresh macOS clone tested Driftwire `5e21febc1393e3656438766e1a6618a4711fb3c6` and organizer repo `6e15a399a64ffbf80778db0b462ac239e70086b9`, Python 3.13.12, new venv and five checksum-verified no-RNA files. Package downloads used the existing pip cache. The README data-fetch command initially failed with `CERTIFICATE_VERIFY_FAILED` at 22.37 seconds from the start; the README's `SSL_CERT_FILE`/certifi workaround succeeded with certificate verification enabled. Resuming from that point took 14.61 seconds through doctor, practice envelope and the organizer validator (`valid`). The sum of measured segments was 36.98 seconds **excluding the pause to diagnose and restart**; this is not an uninterrupted clean-clone time. The practice command itself took 5.60 seconds wall time, including 1.6 seconds reported for unsealing; system load and network/cache conditions affect these figures.

- **Mutation Lab:** 20/20 existing scenarios exact for seed 1 in 32.0 seconds, with no extra/missed sample/type/file matches or execution errors. These are known synthetic development cases, not a held-out benchmark; partner accuracy and explanation accuracy are not scored. The vanished-file case contributes 1,080 records, so pooled counts are dominated by that one scenario.
- **Tests:** 258 passed, one pandas fragmentation warning, before adding the two new expected-failure tests described below. The previously reported open swap-chain regression is fixed in #38; its tests now pass.
- **Gitleaks:** `gitleaks git --no-banner --redact --log-opts=HEAD .` at `5e21feb` scanned 39 reachable commits and found no leaks. Repeat on the final submission commit; subsequent commits have not been scanned by this run.
- **New robustness gaps:** two wholly synthetic malformed releases cause the full detection/findings workflow to fail. A clinical row with a case-variant duplicate sample ID triggers an `IndexError` when the new label-concordance check aligns normalized labels; a duplicate ERALPHA marker row causes a `ValueError` during comparison (calling the concordance check separately raises `TypeError`). Both are reproducible in `tests/test_qa_concordance_robustness.py`, marked strict expected failures until fixed. Report ambiguous repeated IDs/rows for review or as insufficient evidence rather than silently choosing a value; do not crash or assert a clean result.

This checks a Saturday morning commit, not necessarily the final submitted commit. Re-run the focused tests, validator and Gitleaks after fixes or other changes, and verify the submitted commit and judging access.

## Independent adversarial checks (November 13, Friday)

Driftwire code commit `fc43279` was tested against the organizer's checksum-verified, five-file no-RNA release A. Mutation Lab ran all 20 existing scenario types with seeds 11, 29 and 47: **60/60 exact runs**, no reported extras, misses or execution errors, in 51.6 seconds on this Mac. Exact means matching change type, file and sample, not evidence accuracy or partner correctness. These are generated development cases, not held-out judge inputs; the vanished-file case contributes 1,080 sample-level records per run.

An additional synthetic scenario not in that scorecard found a **known false swap-chain claim**: X takes Y's old profile, Y takes Z's old profile, and Z independently shifts all its values. No old profile closes the chain back to X. The detector nevertheless calls X and Y swaps and describes each as part of a swap chain. The findings layer makes a high-severity `sample_swap` and proposes restoring from the previous release; human review is required. A genuine three-way cycle was detected in a positive control. The simpler one-way-copy plus changed donor also produces an unsupported swap claim. These examples use wholly synthetic records, not the organizer answer key.

Recommended detector-owner fix: build profile-transfer relationships and call a swap chain only when the evidence closes a cycle; treat open chains as unconfirmed transfers/value changes and avoid asserting an unproven reciprocal partner. Preserve evidence for the observed transfer and require human review. Test closed cycles, open chains, copies whose donors also change, ambiguous/shared profiles and near matches before changing classification. The reproducible open-chain test is a **strict expected failure** in `tests/test_adversarial_swap_chains.py`; remove the expected-failure marker after the behavior is fixed, rather than counting it as a pass.

On the synthetic one-way case, question-specific verdicts differed as expected: ER protein descriptive `Conditional`, subtype mix `Ready`, and ER prediction from protein `Blocked`. This is one check of question-dependent behavior, not validation of all research questions. Full suite with the new controls: **235 passed, 1 expected failure**, and one pandas performance warning.

## November 13 rehearsal (Friday, America/New_York)

This is a rehearsal, not the requested Saturday morning final check. A fresh macOS checkout tested Driftwire `e2f662b89948b0c99a30f2ecde1d2c9f86c16880` and organizer repo `d0fbebd53b16681ba939b61b38d3475e2c99aaab` with Python 3.13.12 and a new virtual environment. Five no-RNA release A files passed the published checksums.

- **Fresh-clone workflow:** the README data fetch failed with `SSL: CERTIFICATE_VERIFY_FAILED` on this Python installation. Retrying it with `SSL_CERT_FILE="$(python -c 'import certifi; print(certifi.where())')"` before the fetch command succeeded without disabling certificate verification. Doctor then passed, the practice envelope opened, and the organizer validator returned `valid`. Driftwire reported 1.6 seconds to write the practice findings after unsealing (unsealing reported 1.0 seconds). Total clean-setup time was not measured, so these timings are not fresh-clone timings.
- **Mutation Lab:** 20 of 20 scenarios were exact with seed 1 (19.1 seconds). Exact means no missed or extra sample/type/file matches; these are development mutations, not held-out validation. A vanished file contributes 1,080 sample-level findings, so pooled counts are not representative of per-scenario performance. Partner correctness and evidence quality are not measured by this score.
- **Tests:** 234 passed; one pandas fragmentation performance warning.
- **Gitleaks:** `gitleaks git --no-banner --redact --log-opts=e2f662b89948b0c99a30f2ecde1d2c9f86c16880 .` scanned 30 reachable commits and reported no leaks. This is not a scan of Saturday's final commit.

**Saturday still required:** time a new README-only fresh clone against the final `dev`, record any stumbling step, rerun the Mutation Lab and validator, and scan the final commit with Gitleaks. Replace this status with the actual Saturday results, including the tested commit SHA.

## Historical November 12 results

The sections below describe earlier code and are retained for context. The dependency issue was subsequently fixed and #16 closed; the historical coverage-loss classification gap was fixed in the later code exercised above.

This is a snapshot of an evaluation, not a claim of clinical validity or performance on all releases. Run on November 12, 2026 against Driftwire `a4276964e24b205f02a28527d52898938b08f807` and organizer challenge repository `d0fbebd53b16681ba939b61b38d3475e2c99aaab`. Input: the organizers' TCGA-BRCA release A, five files fetched with `--no-rna` and verified by their pinned checksums. No practice answer key or reference findings example was opened.

## Reproducibility and live workflow

A separate checkout used a new Python 3.13 virtual environment and `pip install -r requirements.txt`: 142 tests passed. The documented practice-envelope command then failed because `cryptography` was absent even though doctor said "All set." This is tracked separately in plan-change proposal #16 and draft PR #17. After manually installing `cryptography>=41`, the same practice-envelope command unsealed, wrote output and passed the organizer validator in **1.9 seconds end-to-end on this machine**. This is one local timing, not a guarantee for judging day. It used the actual organizer practice envelope, not a hidden judge envelope.

## Controlled changes on release A

`app.mutation_tab.run_one` ran all 15 currently exposed scenarios for each of seeds 1, 2 and 3 on copies of release A, calling the integrated detector and matching to planted truth by **change type, file and sample ID**. No changed release was saved to the repository. These scenarios and seeds were not held out from the development team; they are not an independent or exhaustive benchmark.

| Scenario | Runs | Expected sample-level records | True positives | False positives | False negatives |
| --- | ---: | ---: | ---: | ---: | ---: |
| unchanged | 3 | 0 | 0 | 0 | 0 |
| reordered | 3 | 0 | 0 | 0 | 0 |
| swap | 3 | 6 | 6 | 0 | 0 |
| duplicate | 3 | 3 | 3 | 0 | 0 |
| disappeared | 3 | 3 | 3 | 0 | 0 |
| label_change | 3 | 3 | 3 | 0 | 0 |
| value_shift | 3 | 3 | 3 | 0 | 0 |
| id_case | 3 | 3 | 3 | 0 | 0 |
| type_code | 3 | 3 | 3 | 0 | 0 |
| near_copy | 3 | 6 | 6 | 0 | 0 |
| unit_scale | 3 | 3 | 3 | 0 | 0 |
| new_sample | 3 | 3 | 3 | 0 | 0 |
| vanished_file | 3 | 3,240 | 3,240 | 0 | 0 |
| relabel_pam50 | 3 | 9 | 9 | 0 | 0 |
| resaved_clinical | 3 | 0 | 0 | 0 | 0 |

All 45 runs had zero matched-sample/type/file misses or extras. The missing-file test dominates any pooled count: it contributes 3,240 of 3,285 expected records. Per-scenario results are more informative. There are **three** no-change control types: unchanged, reordered and resaved_clinical, totaling nine control runs; precision/recall are undefined when no findings are expected or reported. A swap counts two records; near_copy includes a copied profile and a missing profile.

The scorecard's headline matching does not assess whether proposed partners or affected fields are correct, whether evidence supports the explanation, or whether a finding represents an actual biological error. A release comparison cannot identify an error shared by both releases. Additional held-out mutations, low-information profiles, real release changes and a review of false positives remain important.

## Earlier measured example

On a separate seed-42 planted swap against the same pinned no-RNA release, the A1 cohort remained 698 samples and its ER-alpha group mean difference moved from 3.051 to 3.021; A2 counts were unchanged. These are calculations for one synthetic intervention, not a historical MODMatcher result. The detector was a stub during that earlier test, so no detection success was claimed for it.

## Additional Role 3 scenarios

A follow-up version added `id_case_change`, `id_whitespace`, `sample_type_change` and `coverage_loss`. On the same pinned no-RNA release A and integrated detector, each new scenario was run with seeds 1, 2 and 3. The first three scenarios matched their one expected record in all nine runs, with zero extra reports. For each coverage-loss run, 43 protein profiles in one ER subgroup were blanked. The detector reported those same 43 records as `value_shift`, rather than `coverage_loss`: strict type matching is 0 true positives, 43 false positives and 43 false negatives per run, while same-sample reporting finds 43 of 43 under a different type. This does not mean the detector identified subgroup-level coverage loss. The tests retain three explicit expected failures for this classification gap.

Across the original 45 runs and the 12 follow-up runs, **54 of 57** were exact under the scorecard's strict sample/type/file rule. The three coverage-loss runs are the exceptions. The follow-up cases are development tests, not held-out or proof of generalization. Neither affected-feature lists nor proposed partner correctness is included in the headline exact-run metric.
