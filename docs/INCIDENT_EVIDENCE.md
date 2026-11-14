# A sample-swap incident, reproduced as a controlled experiment

**Research use only. This is a synthetic intervention on the event's frozen data, not a reproduction of a specific historical incident or an evaluation of clinical outcomes.**

Driftwire can demonstrate a complete evidence chain: an error that a count check misses, the affected research result, a question that should stop, and recovery of the planted damage without claiming all data problems are fixed.

## Why this failure mode matters

The NCI-CPTAC/precisionFDA mislabeling challenge used data from 181 colorectal tumors and drew 52 teams from 15 countries. Its experiments introduced duplicated, swapped and shifted sample labels, and evaluated detection and correction against known truth. The subsequent COSMO study also tested across separately generated datasets. This establishes the failure class and the value of controlled evaluation; it does not establish Driftwire's accuracy. [Primary study: *A community effort to identify and correct mislabeled samples in proteogenomic studies*](https://pmc.ncbi.nlm.nih.gov/articles/PMC8134945/).

Cross-omics identity inference in COSMO/proMODMatcher is a different task from Driftwire's comparison of successive releases. Driftwire does not replace those methods or reproduce their published scores. General-purpose validation tools also support custom checks. Driftwire demonstrates changed samples, question-dependent impact, human review and a reproducible result in one workflow; we have not benchmarked that workflow against GX. [GX Core documentation](https://docs.greatexpectations.io/docs/core/introduction/).

## Measured experiment

Measured November 14, 2026 on Driftwire code `505d827`, organizer data at `6e15a399a64ffbf80778db0b462ac239e70086b9`, Python 3.13.12. The QA script uses the pre-existing Mutation Lab example seed 42 to exchange two protein profiles in a temporary copy of the five-file no-RNA release A. It passes only the releases to the detector, then scores the output against the separately generated truth. No organizer answer key is read. There are no raw TCGA files or generated releases committed here.

| Measurement | Trusted baseline | Planted swap | Oracle restore (known truth) |
| --- | --- | --- | --- |
| Protein sample count | 747 | 747 | 747 |
| Count-only sanity baseline alarm | None | None | None |
| Detected cross-release changes | 0 | Both planted records; both partners correct; 0 extra reports | 0 |
| A1 ER-alpha group mean difference | 3.051 | 3.021 | 3.051 |
| A1 analysis verdict | Ready | Conditional | Ready |
| A2 subtype analysis | Ready | Ready; relevant inputs unchanged | Ready |
| ER prediction from protein question | Conditional | Blocked | Conditional |
| Organizer output validator | Valid | Valid | Valid |

The three-stage experiment took 13.52 seconds on this machine, including validation. This is one local measurement with data already available, not setup time or a speed guarantee. The baseline is deliberately just a sample-count check; no competing product was benchmarked.

The A1 difference changed by about 1%, within the prototype's 5% tolerance. This threshold is a prototype policy choice, not a statistically or clinically validated boundary. Driftwire therefore reports Conditional rather than manufacturing a changed scientific conclusion. Its model-training question is stricter because swapped profiles undermine the mapping from measurements to labels. The unrelated subtype question remains usable. On recovery, the model-training question remains Conditional because pre-existing concordance concerns persist. A recovered numeric result is not universal approval of the data.

Recovery is an **oracle counterfactual**: the script restores the known planted protein file from the trusted prior release. It does not test whether an automated repair can infer the truth. Driftwire itself applies no repairs. A real curator must establish which source is correct before approving use.

## Reproduce it

From the project root, after the README installation and data fetch:

```bash
python scripts/qa/incident_replay.py ../oncosys-challenge/data/tcga-brca/raw --seed 42 --out out/incident-replay-seed42
```

Choose a fresh output directory on every run. The script refuses to overwrite evidence or write into the source release. It records the code and organizer commits, script hash, Python version and working-tree status, verifies the loaded input files' fingerprints are unchanged, validates all three findings documents, deletes temporary releases and writes only derived results into the output folder:

- `summary.json`: strict detection and separate partner scores, all question verdicts, analysis values, fingerprints and limitations.
- `baseline.json`, `incident.json`, `oracle-recovery.json`: independently validator-checked findings files.

The file for each stage can be opened in the existing site or dashboard. The source release is never edited. Other seeds may choose same-group profiles or samples outside A1's cohort, so their measured impact can differ; that is an expected limitation rather than a reason to retune the detector.

## What this experiment does not establish

One selected swap and its no-change/recovery controls are not a held-out benchmark, a general false-positive rate, a clinical validation or a comparison against COSMO. The two partner matches apply to this experiment only. The broader Mutation Lab remains the source for per-scenario detection results. Duplicate rows, open transfers, altered labels and missing data have their own regression tests; the unseen judge envelope remains unknown.

The event gives 20 points to detection, 20 to reasoning for the question, 15 to evidence and 15 to safety. This experiment supplies inspectable evidence for those criteria; it does not guarantee any score or award. [Official rubric](https://the-open-accelerator.com/hackathon/upcoming/OncoSysHack/).
