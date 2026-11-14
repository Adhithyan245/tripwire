# Driftwire

**Same sample count, different data. Driftwire tells you what changed, what it breaks, and what it can't see.**

OncoSys AI Healthcare Hackathon, Nov 2026 · Team **Skill issue** · Track 1, Cohort Firewall · Product: Cohort Control Tower

## Judge quickstart (under 2 minutes once installed)

**Requirements:** Python 3.11 or newer and git. Tested from a fresh clone on Windows 11 with Python 3.11.0 ([full record](docs/clean_clone_run.md)); our QA also ran it on macOS with Python 3.13.

First, clone the organizers' repo and this one side by side, then work from `tripwire/`:
`git clone https://github.com/disleveK/oncosys-hackathon-challenge oncosys-challenge && git clone https://github.com/Adhithyan245/tripwire tripwire && cd tripwire`. A virtual environment is recommended ([setup](#quickstart-about-5-minutes)).

```bash
pip install -r requirements.txt && python ../oncosys-challenge/data/tcga-brca/fetch.py --no-rna
```
```bash
python -m driftwire doctor
```
```bash
python -m driftwire envelope practice orange meadow pilot lantern
```

**Expected output** of the last command (14 s on our laptop, including unsealing). From the real run:

```
Driftwire: raw -> practice   overall verdict: Conditional
  A1  Conditional            Inputs changed; the result moved within tolerance (difference 3.051 -> 3.019 (1.0% relative; tolerance 5%)).
  A2  Ready                  Nothing this analysis uses changed: the 844 samples it reads are identical in both releases; ...
  Questions:
   er_protein_by_er_status            Conditional
   subtype_mix                        Ready
   os_by_subtype                      Ready
   predict_er_from_protein            Blocked
   predict_subtype_from_copy_number   Conditional
   predict_er_from_rna                Insufficient Evidence
   predict_subtype_from_rna           Blocked
  5 finding(s), 5 proposed repair(s) (none applied)
  format/validate.py: valid
```

**What it means:** the practice release has the same sample counts as the trusted one, yet Driftwire finds a swap, 5 copied profiles, 5 samples that lost data, and receptor labels that contradict their own data. A1 still holds within tolerance and A2 is untouched. The same release is **Ready** for the subtype-mix and survival questions, but **Blocked** for training a model on protein, because the model would train on swapped and copied profiles. Re-check the result with `python -m driftwire verify out/findings-practice.json ../oncosys-challenge/data/tcga-brca/raw ../oncosys-challenge/envelopes/opened/practice/release` ("identical" in our fresh-clone run).

**See also:**
- [Live site](https://driftwire.vercel.app)
- Demo video: VIDEO_LINK_TBD
- [Seven verdicts on one release](#same-release-different-answers)
- [One finding traced end to end](docs/trace_example.md)
- [What the verdicts mean](#what-the-verdicts-mean)
- [Full setup](#quickstart-about-5-minutes)
- [Fresh-clone record](docs/clean_clone_run.md)

**Live site: [driftwire.vercel.app](https://driftwire.vercel.app)**. Step through a real run on the practice release: the scan, the findings with review, the question cards and what to do next. You can also drop any Driftwire `findings.json` on it.

You own a dataset that gets new releases. A new release can keep the same number of samples while some are swapped, copied or dropped, and a count check won't notice. Point Driftwire at the old release (A) and the new one (B). It:

1. finds every change, file by file (swaps, copies, appeared or lost samples, changed labels, value shifts);
2. works out which analyses and research questions each change touches, and reruns only those;
3. gives each one a verdict, **Ready**, **Conditional**, **Blocked** or **Insufficient Evidence**, with the rule and evidence behind it;
4. proposes repairs for a person to approve or reject (it never applies them), and writes `findings.json` in the shared v0.2 format plus a readable HTML report.

*Research use only. No diagnosis, treatment advice, risk score or clinical claim.*

## Quickstart (about 5 minutes)

You need Python 3.11+ and git. The two repos sit side by side:

```
your-folder/
├── oncosys-challenge/   ← the organizers' repo (data, validator, envelopes)
└── tripwire/            ← this repo; run every command from here
```

**1. Get both repos**

```bash
git clone https://github.com/disleveK/oncosys-hackathon-challenge oncosys-challenge
```
```bash
git clone https://github.com/Adhithyan245/tripwire tripwire
```
```bash
cd tripwire
```

**2. Install** (check Python first: on a Mac, `python3` is often the old system 3.9)

```bash
python3 --version
```

If it says less than 3.11, install 3.11+ from python.org (or `brew install python@3.12`) and use that `python3`.
Then make a virtual environment so nothing touches your system Python:

```bash
python3 -m venv .venv
```
```bash
source .venv/bin/activate
```

On Windows: `py -3.11 -m venv .venv` then `.venv\Scripts\activate`. Once it's active, `python` means the right
version for every command below.

```bash
pip install -r requirements.txt
```

**3. Download release A** (the frozen TCGA-BRCA release; about 4 MB, checked against the organizers' checksums)

```bash
python ../oncosys-challenge/data/tcga-brca/fetch.py --no-rna
```

**4. Check your setup.** This prints a ✓ for every check, or the exact command that fixes it:

```bash
python -m driftwire doctor
```

**5. See it work.** This opens the organizers' public practice envelope, compares it with release A, and writes `out/findings-practice.json` and `out/findings-practice.html`. Open the `.html` file in a browser.

```bash
python -m driftwire envelope practice orange meadow pilot lantern
```

**6. Open the dashboard.** A short guided tour starts by itself; **Practice demo** in the sidebar runs step 5 in one click.

```bash
streamlit run app/dashboard.py
```

## Same release, different answers

One practice release, seven research questions, and four different verdicts, each with its written reason. Reproduce it with `python -m driftwire verdicts ../oncosys-challenge/data/tcga-brca/raw ../oncosys-challenge/envelopes/opened/practice/release`.

| Question | Use | Verdict | Driftwire's reason |
| --- | --- | --- | --- |
| Does ER-alpha protein differ between ER-positive and ER-negative tumors? | describe the data | **Conditional** | Computed by A1: Inputs changed; the result moved within tolerance (difference 3.051 -> 3.019 (1.0% relative; tolerance 5%)). |
| What is the PAM50 subtype mix of primary tumors? | describe the data | **Ready** | Computed by A2: Nothing this analysis uses changed: the 844 samples it reads are identical in both releases; a check rerun confirms it (largest subtype share shift 0.0 pp (tolerance 1.0 pp)). |
| Does overall survival differ between PAM50 subtypes? | describe the data | **Ready** | Nothing this question reads changed between releases. |
| Train a research model to predict ER status from protein (RPPA). | train a model | **Blocked** | 12 detected change(s) touch this question's inputs, including duplicate, swap. |
| Train a research model to predict PAM50 subtype from copy number. | train a model | **Conditional** | site_confounding: label vs tissue source site: Cramer's V = 0.19 over 17 site groups (831 samples; sites under 10 pooled). |
| Train a research model to predict ER status from RNA expression. | train a model | **Insufficient Evidence** | This data can't answer the question: rna_hiseq.tsv.gz is not in release practice. |
| Train a research model to predict PAM50 subtype from RNA expression. | train a model | **Blocked (circular)** | Circular question: the label PAM50Call_RNAseq was computed from rna_hiseq.tsv.gz, the same data this model would use as input, so it would mostly re-learn the labelling algorithm. |

The same data passes for describing subtypes and survival, but training a model on protein is **Blocked**: the swapped and copied profiles would become wrong labels and leak across a train/test split. Saved in [docs/verdict_table.md](docs/verdict_table.md).

## What the verdicts mean

| Verdict | Meaning |
| --- | --- |
| **Ready** | Nothing this result depends on changed. |
| **Conditional** | Its inputs changed, but the result stayed within the stated tolerance. Usable, with care. |
| **Blocked** | The result moved beyond tolerance, its conclusion flipped, or something changed that nothing explains. |
| **Insufficient Evidence** | Too few samples, missing data, or a required check that didn't run. Never read as a pass. |

Tolerances and minimum sample counts are prototype policy choices, not clinical standards. They're printed in every report.

**For model-training questions**, Driftwire also runs readiness checks, and gives a fix for each problem it finds:
- **sample size per class**;
- **patient leakage:** a patient with several samples, or one profile copied under several IDs, could end up on both sides of a train/test split. It's reported as a *potential* risk, because Driftwire never sees your split;
- **site confounding:** the label spread unevenly across the hospitals that submitted samples, measured by Cramér's V against the barcode's site code.

**Every proposed repair comes with a preview:** what each affected result would become if a reviewer approved it, alone and all together. It's computed on a copy of the new release, and nothing is applied.

## Using it

| I want to… | Run |
| --- | --- |
| Compare any two release folders | `python -m driftwire diff <release-A> <release-B>` (writes `out/findings.json` and `.html`) |
| Open a sealed envelope and compare it (judging day) | `python -m driftwire envelope <number> <four words>` |
| Ask whether a release is fine for a specific research question | add `--question <id>`; list the questions with `python -m driftwire questions` |
| Rebuild the HTML report from a findings file | `python -m driftwire report out/findings.json` |
| Prove it catches changes | dashboard → View: **Mutation Lab**, or `python -m driftwire.mutation_lab --help` |
| Check the shared format myself | `python ../oncosys-challenge/format/validate.py out/findings.json` |

**Judging day.** The judge gives an envelope number and four words, for example `python -m driftwire envelope 07 amber falcon river quartz`. It opens the envelope with the organizers' own `unseal.py`, compares, validates and writes the report, usually in a few seconds. The envelope has no RNA file by design, and Driftwire doesn't flag that.

Exit codes: **0** means findings were written and the validator passed. **1** means they were written but the validator found problems. **3** means the envelope didn't open, and the last line says why: release A missing, a wrong number or words, or an out-of-date challenge repo. The verdict is in the output, and only reaches the exit code if you ask for it with `--fail-on` (see below).

**The dashboard** can compare two releases, open a sealed envelope, show a `findings.json` from another tool (upload it: it gets structural checks, and the organizers' validator runs in Data & export), or load a clearly labelled synthetic example. It has these tabs:
- **Verdicts:** the overall verdict, each research question and each analysis, with before and after values.
- **Findings & evidence:** every change with its samples, files, severity reason and limitation, plus "trace one sample".
- **Review:** approve, reject or request more evidence on each proposed repair, with a reason. This is saved into `findings.json`; nothing is applied.
- **What Driftwire can't see:** its blind spots.
- **Data & export:** a validator check and downloads.
- **Mutation Lab** (its own view in the sidebar): plant a known change, or run the full scorecard.

## It also checks the labels themselves

A comparison between releases can't see an error that was already in the trusted release. Driftwire adds one check that can: **receptor labels that contradict the tumor's own molecular data.** ER and HER2 status decide treatment and trial eligibility (rules such as "ER ≥ 1%" read exactly these labels), and a mislabelled sample silently corrupts any model or cohort built on it.

| Label | Cross-checked against | Flagged when |
| --- | --- | --- |
| ER status | ER-alpha protein (RPPA) | ER-negative but protein at or above the typical ER-positive level and at least 3 robust SDs above its group, or the mirror case |
| HER2 status | ERBB2 copy number (GISTIC) and HER2 protein | HER2-negative but highly amplified with positive-level protein, or the mirror case |

On the practice release, it flags **6 ER and 4 HER2 labels that were already contradicted in the trusted release**. It also independently flags one of the two swapped samples, which now carries an ER-positive profile under an ER-negative label. Each flag becomes a `label_conflict` finding (a kind defined in the shared format), with the sample's own values as evidence. A flag-for-review repair goes to pathology or the data provider, and the ER question cards show a `label_concordance` check. Driftwire never relabels anything: a flag is evidence for a person, not a correction.

## Use it where your data moves

**In a notebook.** One call runs the same engine and returns the same findings.json. In Jupyter the result shows as a readable summary.

```python
import driftwire
result = driftwire.check("path/to/release-A", "path/to/release-B", question="predict_er_from_protein")
result.verdict          # "Blocked" for this question on the practice release
result.findings         # what changed, with evidence
result.next_steps       # the ordered plan, and what Driftwire can't tell you
result.save("findings.json")
```

**As a release gate in CI.** Add `--fail-on Blocked` (or `Conditional`) and a run exits **4** when the verdict is that or worse. findings.json and the report are still written for a person to review. Without the flag, the verdict never changes the exit code. [`docs/ci/driftwire-gate.yml`](docs/ci/driftwire-gate.yml) is a ready-made GitHub Actions workflow: it checks every pull request that changes a release, and attaches the findings to the run.

```bash
python -m driftwire diff releases/trusted releases/candidate --fail-on Blocked
```

## Re-check any result with one command

Every `findings.json` carries a **receipt**: the Driftwire version and git commit, the question asked, and a SHA-256 of the result. The fingerprint of every input file is already in `data.releases`. Anyone with the same two releases can re-check it:

```bash
python -m driftwire verify findings.json path/to/release-A path/to/release-B
```

| Outcome | Meaning | Exit code |
| --- | --- | --- |
| **identical** | Same inputs, same result hash | 0 |
| **same conclusions** | Only numeric detail differs (another machine or library); every verdict and finding is unchanged | 0 |
| **inputs differ** | Names each file that no longer matches its recorded fingerprint | 5 |
| **different** | Names each verdict or finding that changed, and says if the file was edited after the run | 5 |

Review decisions are left out of the hash, because they are a person's record added after the run. The output is deterministic: the practice run gives the same result hash in every process.

## Beyond oncology

Driftwire is built and tested on TCGA-BRCA, but nothing in its approach is specific to cancer. Any medical dataset that ships in versions, such as an ECG cohort, a table of echocardiography measurements or an EHR extract for a cardiac study, can silently swap, copy or drop records between releases. Each new version raises the same question: is it still fit for this analysis, or this model?

- **Release changes.** Fingerprinting each record, mapping changes to the analyses that read them, rerunning against stated tolerances and giving each question its own verdict all work the same way whatever the data measures.
- **Labels that contradict the data.** The receptor check above has direct counterparts elsewhere. In cardiology, a "heart failure with reduced ejection fraction" label on a patient whose recorded ejection fraction is normal, or an atrial fibrillation diagnosis with no atrial fibrillation on the ECG, is the same kind of quietly mislabelled training example.

Supporting a new domain means describing its files, analyses and question cards. The verdict rules, evidence, human review and `findings.json` stay the same. This hasn't been built or tested outside TCGA-BRCA yet.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Anything at all | `python -m driftwire doctor`: it names the problem and the command that fixes it |
| "challenge repo not found" | Clone it next to this repo (step 1), or set `TRIPWIRE_CHALLENGE_DIR` to its path |
| "release A not fetched" or a checksum mismatch | `python ../oncosys-challenge/data/tcga-brca/fetch.py --no-rna` |
| Mac: `SSL: CERTIFICATE_VERIFY_FAILED` while fetching | Python from python.org ships without certificates. Run `/Applications/Python 3.x/Install Certificates.command` once, or fetch with `SSL_CERT_FILE="$(python -c 'import certifi; print(certifi.where())')"` in front of the command. Certificate checks stay on either way |
| `streamlit: command not found` | `python -m streamlit run app/dashboard.py` |
| Windows: `UnicodeEncodeError` when unsealing directly | Use `python -m driftwire envelope …`, which handles it. Running `unseal.py` yourself needs `PYTHONUTF8=1` |
| An envelope "doesn't open" | Check the number and the four words. Hyphens or spaces both work, and capitals don't matter |

No API key is needed: nothing in Driftwire calls an AI service.

## For developers

```bash
python -m pytest -q
```

Driftwire's working name was Tripwire, so the code lives in the `tripwire/` package. `python -m driftwire` and `python -m tripwire` run the same tool.

| Part | Where |
| --- | --- |
| Shared change contract | `tripwire/contract.py`, documented in `docs/CONTRACT.md` |
| Detection (Role 1) | `tripwire/detect/`: every file in both releases; swaps, copies, membership, IDs, sample-type codes, clinical values, value shifts |
| Impact, verdicts, questions, findings (Role 2) | `tripwire/analyses.py`, `impact.py`, `verdicts.py`, `questions.py`, `findings.py`, `report.py` |
| Mutation Lab (Role 3) | `tripwire/mutation_lab/` (`core.py`, `extended.py`), documented in `docs/MUTATION_LAB.md` |
| Dashboard and review (Role 4) | `app/dashboard.py`, `app/mutation_tab.py`, `tripwire/review.py` |

Two safety nets:
- **Verification rerun:** Driftwire also reruns the analyses its impact map calls unaffected. If one moved anyway, it's **Blocked** and every changed sample is listed, so a detector miss can't become a false "Ready".
- **Readiness checks:** a check that hasn't been built shows as unavailable and never counts as a pass.

## Demo video

**Demo video:** _link added before the Saturday 2:15 PM ET code freeze._

## Team: Skill issue

| Member | Role |
| --- | --- |
| Adhithyan Aravind (@Adhithyan245) | Impact, verdicts, research questions and `findings.json` |
| Madhan (@MadhanJ05) | Change detection |
| Hemnaath (@hemnaath04) | Mutation Lab and QA |
| Annamayya Vennelakanti (@Annamayya9) | Dashboard, review and the demo |

The plan is in [PLAN.md](PLAN.md); how we work is in [CONTRIBUTING.md](CONTRIBUTING.md).

## AI use

Driftwire has **no AI features** and calls no AI service, so no API key is needed. Every verdict, finding and next step comes from deterministic code over the event data, and each one cites the rule that produced it.

## Data and credits

- **TCGA-BRCA** open-access data from the UCSC Xena TCGA hub, fetched by the challenge repo's `fetch.py` and checked against its pinned checksums (`python -m driftwire doctor` verifies them). It is never committed here. Credit: the TCGA Research Network; UCSC Xena; survival data from the TCGA Pan-Cancer Clinical Data Resource (Liu et al., *Cell* 2018). See the challenge repo's `DATA_LICENSES.md`.
- **Slide links** in the evidence point to NCI Imaging Data Commons' public viewer, taken from the challenge repo's `slide_manifest.csv` (slides CC BY 3.0; credit the TCGA Research Network and NCI Imaging Data Commons). Nothing is downloaded.
- No other data is used. Judged results use the frozen release only.

## Third-party code and licenses

Driftwire's own code is in this repo. It runs the organizers' `envelopes/unseal.py`, `format/validate.py` and `reference_analyses.py` from the challenge repo, unchanged and not copied here. Python packages (`requirements.txt`):

| Package | License |
| --- | --- |
| pandas | BSD-3-Clause |
| NumPy | BSD-3-Clause |
| jsonschema | MIT |
| Streamlit | Apache-2.0 |
| cryptography (needed by the organizers' unsealer) | Apache-2.0 or BSD-3-Clause |
| pytest (tests only) | MIT |

*Research use only. Driftwire makes no diagnosis, treatment advice, risk score, or claim of clinical validity, regulatory compliance or production readiness.*
