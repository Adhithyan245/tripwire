# Performance: a synthetic scale test

**This is a synthetic scale test, not real data.** `scripts/scale_test.py` resamples the practice release's samples with replacement and gives every one a new, made-up barcode-shaped ID (site codes Z0 to Z9, which no real TCGA sample uses). Small noise is added to the protein values so the resampled samples aren't exact copies of each other. Release B is release A with two protein profiles swapped, so there is one known change to find.

```bash
python scripts/scale_test.py ../oncosys-challenge/envelopes/opened/practice/release <work folder> --factor 10
```

## Result (2026-11-14, Windows 11, Python 3.11, one run)

| | Practice release | Synthetic 10x |
| --- | --- | --- |
| Samples in clinical.tsv | 1,247 | 12,470 |
| survival.tsv rows | 1,236 | 12,370 |
| protein_rppa.tsv.gz | 131 x 747 samples | 131 x 7,497 samples |
| Copy number, mutation | included | **not included** (see the limits below) |
| `diff` wall time | 10.5 s (all five files) | 11.1 s |
| Peak memory of the process | not measured | 213.3 MB (peak working set, psutil) |
| Result | Conditional, 5 findings | Conditional: the planted swap was found (TCGA-Z0-000G-01 with TCGA-Z0-000Z-01), plus an ER-label concordance finding for 89 samples; `format/validate.py` valid |

Building the synthetic pair took another 19.7 s, which isn't counted above.

## Tested limits

- Tested up to 12,470 clinical samples and 7,497 protein samples, in one run on one machine.
- The copy-number and mutation files were not scaled. At 10x they would be about 250 to 320 million cells each, so their time and memory at that size are unmeasured.
- The concordance finding is an artefact of resampling: labels are copied with each resampled sample, so the label-versus-protein mix differs from real data. It is not evidence about real samples.

## A gap found along the way (verdict logic, not changed)

The first attempt used IDs that weren't barcode-shaped (`TCGA-ZZ-000016-01`, six digits), so no sample counted as a primary tumor:
- **A2 came back Ready while reading 0 samples.** An empty cohort should be Insufficient Evidence, not Ready.
- A1's result was NaN, and Driftwire reported it as Blocked ("moved"), so that case failed closed.

Fixing the A2 case needs a change in verdict or analysis logic (`verdicts.py` / `analyses.py`), which was out of bounds for this work. Proposed fix: return Insufficient Evidence whenever an analysis's cohort is empty in either release.
