# Security and data handling

Research use only. This page covers what Driftwire reads and writes, its network access, secrets, the dependency audit, and how to report a vulnerability.

## Data handled

- Open-access, de-identified TCGA-BRCA data only, as published by the organizers (UCSC Xena exports and the sealed practice and judging envelopes). No protected health information (PHI).
- Driftwire is not designed or validated for identifiable patient data. Don't point it at PHI.

## What it reads and writes

- **Reads:** the two release folders you name (or one opened envelope plus release A). It also runs, unchanged, the organizers' `envelopes/unseal.py` and `format/validate.py` from the challenge repo.
- **Writes:** `findings.json` and an HTML report to the `--out` path you give, which defaults to `out/`. Opening an envelope writes it to `envelopes/opened/<n>/release` in the challenge repo, as the organizers' script does.
  - The dashboard's "Run on your data" view writes to a temporary folder on the same machine.
  - The "Prepare data with AI" view writes a renamed-header copy and `mapping_record.json`, never back over the source file.
- **Doesn't change:** your input files. Repairs are proposals and are never applied.

## Network access

- Comparisons, verdicts, reports and the dashboard make no network calls.
- The only network step is the organizers' data fetch (`data/tcga-brca/fetch.py`), run once during setup.
- The "Prepare data with AI" view is opt-in. It sends column names and file metadata only (never rows), and only when a suggestion backend is installed. No backend ships in this repo, and no API key is read or stored.
- The public site (driftwire.vercel.app) is static. Its "Ask about this run" box answers from the loaded `findings.json` in the browser.

## Secrets policy

- No tokens, keys or passwords in the repo. Deploys use the platform's own integration or CI secrets.
- An expired development token was found in a commit that is no longer reachable from any branch. The token has been revoked. GitHub may still hold the unreachable commit until GitHub Support purges it; ask them to before making the repo public.

## Dependency audit

`pip-audit -r requirements.txt`, run on 2026-11-14 with pip-audit installed in the dev environment:

| Package | Version | Result |
| --- | --- | --- |
| cryptography | 49.0.0 | **1 known vulnerability:** PYSEC-2026-3552 (GHSA-g6cj-pr64-35w5, CVE-2026-69247), fixed in 50.0.0 |
| pandas, numpy, jsonschema, streamlit, pytest | pinned versions | no known vulnerabilities |

The cryptography issue is in PKCS#7 decryption (`pkcs7_decrypt_der`, `pkcs7_decrypt_pem` and `pkcs7_decrypt_smime`), where the outcome of decrypting attacker-supplied data can leak information.
- Driftwire never calls those functions. cryptography is used only by the organizers' `unseal.py`, which uses AES-GCM.
- The pin was left at 49.0.0 for the judging-day freeze. Bump it to 50.0.0 (the challenge repo allows `cryptography>=41`) and rerun the tests after judging.

## Licenses of direct dependencies

| Package | License |
| --- | --- |
| pandas | BSD-3-Clause |
| numpy | BSD-3-Clause |
| jsonschema | MIT |
| cryptography | Apache-2.0 OR BSD-3-Clause |
| streamlit | Apache-2.0 |
| pytest (tests only) | MIT |

## Reporting a vulnerability

Open a private GitHub security advisory on this repository (Security → Report a vulnerability), or contact the team privately. Please don't open a public issue. We aim to reply within 3 working days during the hackathon period.
