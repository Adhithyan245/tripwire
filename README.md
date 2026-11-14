# Driftwire

**Same sample count, different data. Driftwire tells you what changed, what it breaks, and what it can't see.**

OncoSys AI Healthcare Hackathon, Nov 2026 · Team **Skill issue** · Track 1, Cohort Firewall · Product: Cohort Control Tower

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

On Windows: `py -3.11 -m venv .venv` then `.venv\Scriptsctivate`. Once it's active, `python` means the right
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
