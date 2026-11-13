# Role 3 QA: integrated run

## November 13 rehearsal (Friday, America/New_York)

This is a rehearsal, not the requested Saturday morning final check. A fresh macOS checkout tested Tripwire `e2f662b89948b0c99a30f2ecde1d2c9f86c16880` and organizer repo `d0fbebd53b16681ba939b61b38d3475e2c99aaab` with Python 3.13.12 and a new virtual environment. Five no-RNA release A files passed the published checksums.

- **Fresh-clone workflow:** the README data fetch failed with `SSL: CERTIFICATE_VERIFY_FAILED` on this Python installation. Retrying it with `SSL_CERT_FILE="$(python -c 'import certifi; print(certifi.where())')"` before the fetch command succeeded without disabling certificate verification. Doctor then passed, the practice envelope opened, and the organizer validator returned `valid`. Tripwire reported 1.6 seconds to write the practice findings after unsealing (unsealing reported 1.0 seconds). Total clean-setup time was not measured, so these timings are not fresh-clone timings.
- **Mutation Lab:** 20 of 20 scenarios were exact with seed 1 (19.1 seconds). Exact means no missed or extra sample/type/file matches; these are development mutations, not held-out validation. A vanished file contributes 1,080 sample-level findings, so pooled counts are not representative of per-scenario performance. Partner correctness and evidence quality are not measured by this score.
- **Tests:** 234 passed; one pandas fragmentation performance warning.
- **Gitleaks:** `gitleaks git --no-banner --redact --log-opts=e2f662b89948b0c99a30f2ecde1d2c9f86c16880 .` scanned 30 reachable commits and reported no leaks. This is not a scan of Saturday's final commit.

**Saturday still required:** time a new README-only fresh clone against the final `dev`, record any stumbling step, rerun the Mutation Lab and validator, and scan the final commit with Gitleaks. Replace this status with the actual Saturday results, including the tested commit SHA.

## Historical November 12 results

The sections below describe earlier code and are retained for context. The dependency issue was subsequently fixed and #16 closed; the historical coverage-loss classification gap was fixed in the later code exercised above.

This is a snapshot of an evaluation, not a claim of clinical validity or performance on all releases. Run on November 12, 2026 against Tripwire `a4276964e24b205f02a28527d52898938b08f807` and organizer challenge repository `d0fbebd53b16681ba939b61b38d3475e2c99aaab`. Input: the organizers' TCGA-BRCA release A, five files fetched with `--no-rna` and verified by their pinned checksums. No practice answer key or reference findings example was opened.

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
