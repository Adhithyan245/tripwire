# Driftwire recording and live-demo runbook

This guide uses the **local dashboard** for real computation and the public website for a recorded practice replay. The practice data is research-only; a planted mutation is a simulation, not a historical incident or clinical decision. Recheck the output and use the actual values if a later commit changes them.

## 1. Set up the recording machine

Clone the organizer challenge and Driftwire repositories as siblings, install Python 3.11+ and follow the project's README through the data fetch. On this Mac the existing checkout is ready:

```bash
cd ~/Codex-sessions/tripwire-qa/repo
source ../preview-venv/bin/activate
python -m driftwire doctor
```

For another machine, use the README's `.venv` setup rather than this Mac-specific environment. If macOS data fetching reports `CERTIFICATE_VERIFY_FAILED`, use the README's documented certifi certificate-bundle workaround, with certificate verification enabled. Doctor must show that release A's five no-RNA files match the frozen checksums.

## 2. Prepare the practice data and verify the output

From the repository root with the environment activated:

```bash
python -m driftwire envelope practice orange meadow pilot lantern
python ../oncosys-challenge/format/validate.py out/findings-practice.json
python -m driftwire verdicts ../oncosys-challenge/data/tcga-brca/raw ../oncosys-challenge/envelopes/opened/practice/release
python -m driftwire verify out/findings-practice.json ../oncosys-challenge/data/tcga-brca/raw ../oncosys-challenge/envelopes/opened/practice/release
```

Expected checks on the tested practice release: validator prints `valid`, verify prints `identical`, A1 is Conditional, subtype mix is Ready, and protein-to-ER model training is Blocked. Practice may already be open, in which case unsealing is skipped; do not describe that as a timed fresh unseal.

## 3. Open the dashboard

```bash
streamlit run app/dashboard.py
```

Open <http://localhost:8501>, skip the tour if it appears, and press **Practice demo**. Wait for the result before recording. Release A should be the organizer's `data/tcga-brca/raw` and release B `envelope · practice`. You should see the overall Conditional result, five findings, and review tabs. Keep this terminal running. The dashboard compares data locally; its repairs are proposals and never change the release automatically.

The public site <https://driftwire.vercel.app/> replays recorded practice output. It does not run the detector in the browser. If recording it, say “recorded practice replay.” To run the same website locally, open a second terminal at the repository root and run `python -m http.server 8765 --directory site`, then visit <http://localhost:8765>.

## 4. Record a 90-second walkthrough

Record the screen at 1080p, with readable browser zoom and notifications hidden. Use the local dashboard for these steps:

| Time | Show | Narration |
| --- | --- | --- |
| 0:00–0:12 | Dashboard introduction; then press **Practice demo** | “The new release looks the same by count, but samples can move or disappear underneath. Driftwire checks what changed and which questions depend on it.” |
| 0:12–0:28 | Overall verdict and A1/A2 in **Verdicts** | “In this practice release, A1’s ER-alpha difference moves from 3.051 to 3.019, about 1%, within our prototype’s 5% tolerance. A1 is Conditional; the subtype analysis is Ready.” |
| 0:28–0:43 | In **Verdicts**, show subtype mix Ready and ER-from-protein training Blocked | “The same release can support one question and block another. A model trained on swapped or copied profiles risks learning from the wrong labels.” |
| 0:43–1:00 | **Findings & evidence**, then **Review** for the swap | “The findings show the affected files and evidence. A curator can approve, reject, or ask for evidence with a reason. Driftwire does not apply repairs.” |
| 1:00–1:14 | Sidebar **View → Mutation Lab**; select `mixed_changes`, seed 42, press **Plant and detect** | “In a controlled test we plant a swap, duplicate, missing profile and label change, then score detection against known truth.” Show the actual result and any misses. |
| 1:14–1:24 | Terminal: run the `verify` command from step 2 | “The receipt lets another person rerun the comparison and check that the result is reproducible.” |
| 1:24–1:30 | **What Driftwire can't see** | “A comparison needs a trusted baseline. Most errors already shared by both releases can remain invisible.” |

If timing is tight, record the Mutation Lab separately and cut it into the video. Do not describe it as the judges' unseen test or claim it proves real-world accuracy.

## 5. Judge-day envelope

Before Q&A, have the fetched, checksum-verified release A and the current organizer repository ready. Once the judge gives the actual number and four words, run:

```bash
python -m driftwire envelope <number> <word1> <word2> <word3> <word4>
```

The angle-bracketed entries are placeholders: replace them with the judge's actual number and words without typing the brackets. Use the output path the command prints, validate that file with `python ../oncosys-challenge/format/validate.py <output-path>`, and explain the observed results. Do not promise a particular verdict in advance. The practice code above opens only the public practice envelope.

## 6. Before submission

Export the video, watch the full export with sound, and add its accessible link to the README. Ensure judges can access the submitted repository and that the commit used in the demo matches the submitted commit. After the final code change, rerun the relevant tests, organizer validator and Gitleaks on that exact commit. The code-freeze deadline is **Saturday 2:15 PM ET**; presentations start at 2:30 PM ET.
