# One finding, traced end to end: the sample swap (F1)

Every value below is copied from a real run on the organizers' practice envelope (`python -m driftwire envelope practice orange meadow pilot lantern`, output `out/findings-practice.json`, result SHA-256 `e612c917c726c97c8fef3a7d2fc7a99867d0f2c3b66ba1a8826e866d582d15d5`) and from reading the two protein files directly.

## 1. The finding
| Field | Value |
| --- | --- |
| ID | **F1** |
| Kind | `sample_swap` |
| Severity / confidence | high / high |
| Summary | Profiles of TCGA-A8-A09K-01 and TCGA-B6-A0WX-01 in protein_rppa.tsv.gz appear exchanged between releases. Affected samples by release-A labels: subtype: 1 Basal, 1 LumA; ER: 1 Negative, 1 Positive. |
| Why high | It feeds results that are Blocked overall: predict_er_from_protein. |
| Limitation | A swap is inferred from two profiles trading places between releases; the release doesn't say why. |

## 2. The samples and their release-A labels
| Sample | ER status (clinical) | PAM50 subtype |
| --- | --- | --- |
| TCGA-A8-A09K-01 | Positive | LumA |
| TCGA-B6-A0WX-01 | Negative | Basal |

## 3. The file, fingerprinted
| Release | File | SHA-256 |
| --- | --- | --- |
| raw (trusted) | protein_rppa.tsv.gz | `7823a7a375495f7e5f114d0c7ec8773e070cb9ac409785f98045d12ab71195e6` (file bytes) |
| practice (new) | protein_rppa.tsv.gz | `e5ee5f77c9a5dfb3c6ea90d84a47db2866543d3dcaebc5093efb691b8847da5f` (content, line endings normalised) |

Both files hold 747 samples, so a count check sees nothing.

## 4. Before and after: the values traded places
| Sample | Feature | Trusted (raw) | New (practice) |
| --- | --- | --- | --- |
| TCGA-A8-A09K-01 (ER-positive) | ERALPHA | 3.4327 | **-1.0701** |
| TCGA-A8-A09K-01 | HER2 | 0.5508 | -0.0318 |
| TCGA-A8-A09K-01 | PR | -0.0850 | -0.1818 |
| TCGA-B6-A0WX-01 (ER-negative) | ERALPHA | -1.0701 | **3.4327** |
| TCGA-B6-A0WX-01 | HER2 | -0.0318 | 0.5508 |
| TCGA-B6-A0WX-01 | PR | -0.1818 | -0.0850 |

Checked across all 131 protein features: each sample's new profile equals the other's old profile exactly. Driftwire's evidence note says the same thing: "profile is identical to TCGA-B6-A0WX-01's in the previous release, and TCGA-B6-A0WX-01 now carries this sample's old profile".

The ER-positive tumor now carries ER-negative-level ER-alpha, and the reverse. The receptor-label check (finding **F4**) independently flags TCGA-B6-A0WX-01 as an ER-negative label whose protein now sits at the ER-positive level, and marks it as new in this release.

## 5. What it touches
| Target | Effect |
| --- | --- |
| Analysis **A1** (ER-alpha by ER status) | Affected. Rerun: difference 3.051 → 3.019 (1.0% relative; tolerance 5%), so **Conditional** |
| Analysis **A2** (subtype mix) | Not affected: it reads clinical.tsv, not the protein file |
| Question `er_protein_by_er_status` | **Conditional**: computed by A1 |
| Question `predict_er_from_protein` | **Blocked**: 12 detected change(s) touch this question's inputs, including duplicate, swap. For model training that means wrong labels or copies across a train/test split |

## 6. The proposed repair, sized
**R1, `restore_from_previous_release`**: "Restore both profiles as they were in raw until the swap is explained. Proposed only; never applied automatically."

Preview on a copy of the new release, for A1:
- now: 3.051 → 3.019 (1.0%);
- if R1 alone is approved: 3.051 → 3.054 (0.1%).

## 7. The slides
Each sample links to its tissue slide in NCI Imaging Data Commons' public viewer (from the organizers' `slide_manifest.csv`):
- [TCGA-A8-A09K-01](https://viewer.imaging.datacommons.cancer.gov/slim/studies/2.25.252549812871880097372040409338754599918/series/1.3.6.1.4.1.5962.99.1.1353496534.594267531.1637736069078.2.0)
- [TCGA-B6-A0WX-01](https://viewer.imaging.datacommons.cancer.gov/slim/studies/2.25.313876930275437405700886098015749945827/series/1.3.6.1.4.1.5962.99.1.1311646388.1333858778.1637694218932.2.0)

The same links appear in the HTML report (`out/findings-practice.html`), on the dashboard and on the website.
