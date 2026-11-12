# Tripwire

**Same sample count, different data. Tripwire tells you what changed, what it breaks, and what it can't see.**

OncoSys AI Healthcare Hackathon, Nov 2026 · Track 1, Cohort Firewall · Product: Cohort Control Tower

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

## Team

See [PLAN.md](PLAN.md) for roles and [CONTRIBUTING.md](CONTRIBUTING.md) for how we work. `main` is locked; all work goes to `dev`.

## Data and licenses

TCGA-BRCA open-access data via the UCSC Xena TCGA hub, fetched by the challenge repo's `fetch.py` and checked against its pinned checksums. It is never committed here. Credit: TCGA Research Network; UCSC Xena; survival from the TCGA Pan-Cancer Clinical Data Resource (Liu et al., *Cell* 2018). See the challenge repo's `DATA_LICENSES.md`.
