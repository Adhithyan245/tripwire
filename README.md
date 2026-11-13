# Tripwire

**Same sample count, different data. Tripwire tells you what changed, what it breaks, and what it can't see.**

OncoSys AI Healthcare Hackathon, Nov 2026 · Team **Skill issue** · Track 1, Cohort Firewall · Product: Cohort Control Tower

**User:** a research engineer who owns a dataset that gets new releases.
**Workflow:** point Tripwire at release A and release B. It finds swaps, duplicates and lost coverage, reruns only the analyses those changes touch, gives each one a verdict (Ready, Conditional, Blocked, Insufficient Evidence) and writes `findings.json` in the shared v0.2 format.

Research use only. Tripwire makes no diagnosis, treatment advice, risk score or clinical claim.

## Setup

Needs Python 3.11+ and the [challenge repo](https://github.com/disleveK/oncosys-hackathon-challenge) cloned next to this one:

```bash
git clone https://github.com/disleveK/oncosys-hackathon-challenge ../oncosys-challenge
pip install -r requirements.txt
python ../oncosys-challenge/data/tcga-brca/fetch.py --no-rna
```

## Run

```bash
python -m tripwire diff ../oncosys-challenge/data/tcga-brca/raw <release-B-folder> --out out/findings.json
python ../oncosys-challenge/format/validate.py out/findings.json
```

Judges' input on Saturday comes from a sealed envelope. Rehearse with the public practice one (on Windows, set `PYTHONUTF8=1` first or `unseal.py` crashes printing ✓):

```bash
PYTHONUTF8=1 python ../oncosys-challenge/envelopes/unseal.py practice orange meadow pilot lantern
python -m tripwire diff ../oncosys-challenge/data/tcga-brca/raw ../oncosys-challenge/envelopes/opened/practice/release
```

On Windows, `unseal.py` reports a fingerprint mismatch for `protein_rppa.tsv.gz`. The cause is CRLF line endings from pandas; the content is identical. Tripwire's content hashes normalise line endings, so ours match the organizers' published hashes on any OS.

## How the pieces plug together

| Role | Plug-in point |
| --- | --- |
| 1 · Detection | Implement `tripwire.detect.detect_changes(release_a, release_b) -> list[Change]` (currently a stub). `Change` is in `tripwire/contract.py`, documented in `docs/CONTRACT.md`. |
| 2 · Impact, verdicts, format | `tripwire/analyses.py` (A1, A2 and what each reads), `impact.py`, `verdicts.py`, `findings.py` |
| 3 · Mutation Lab | Feed your answer key straight in: `python -m tripwire diff A B --changes my_changes.json`, or call `tripwire.findings.build(changes, Release(a), Release(b))` |
| 4 · Interface | Read `findings.json`: `verdict`, `analyses[].verdict`, `.why` (verdict reason), `.impact` (why touched or left alone), `.before`/`.after`, `findings[]`, `repairs[]`, `settings` (stated tolerances). For the Question Gate, use `tripwire.verdicts.CheckResult` + `question_verdict`. |

Even without a detector, Tripwire reruns the analyses the impact map calls unaffected. If one moved anyway, it is **Blocked** and reported as an unexplained change. So a detector miss can't turn into a false "Ready".

```bash
python -m pytest -q
```

## Team

See [PLAN.md](PLAN.md) for roles and [CONTRIBUTING.md](CONTRIBUTING.md) for how we work. `main` is locked; all work goes to `dev`.

## Data and licenses

TCGA-BRCA open-access data via the UCSC Xena TCGA hub, fetched by the challenge repo's `fetch.py` and checked against its pinned checksums. It is never committed here. Credit: TCGA Research Network; UCSC Xena; survival from the TCGA Pan-Cancer Clinical Data Resource (Liu et al., *Cell* 2018). See the challenge repo's `DATA_LICENSES.md`.
