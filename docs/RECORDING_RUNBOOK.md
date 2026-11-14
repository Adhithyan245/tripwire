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

## 4. Record our 90-second film: “One release. Two decisions.”

The creative idea is a question, not a feature tour: a researcher asks two different questions of the same release, and the evidence leads to two different decisions. Start with the contrast, then show the evidence and the human who acts on it. Use the local dashboard for the actual comparison. Record at 1080p with readable browser zoom and notifications hidden; use short, steady cuts, minimal on-screen text and clear narration. No fabricated alerts, sample results or historical-incident claims.

| Time | Show | Narration |
| --- | --- | --- |
| 0:00–0:10 | Open on the practice **Verdicts** tab; frame the Ready subtype question and Blocked protein-model question | “One dataset. Two research questions. One is ready; the other is blocked. Why?” |
| 0:10–0:24 | Move to **Findings & evidence** and open the swap | “A new release can keep the same sample count while profiles move between samples. Driftwire compares the releases and shows the evidence behind the warning.” |
| 0:24–0:38 | Show A1’s before/after values and return briefly to the two question verdicts | “The ER-alpha difference moves from 3.051 to 3.019, within our prototype’s 5% tolerance. But a model trained on swapped profiles risks learning from the wrong labels.” |
| 0:38–0:53 | Open **Review** for the swap; show the preview and record a reasoned decision | “A curator sees the proposed action, its preview and the uncertainty. The decision is recorded; Driftwire never applies the repair.” |
| 0:53–1:08 | Sidebar **View → Mutation Lab**; choose `mixed_changes`, seed 42, press **Plant and detect** | “We can challenge our detector: plant a swap, duplicate, missing profile and label change, then compare what it finds with known truth.” Show the actual score. |
| 1:08–1:22 | Terminal: run the `verify` command from step 2 | “Every result carries a receipt. Someone with the same inputs can rerun the comparison and check the result.” |
| 1:22–1:30 | Return to **What Driftwire can't see** | “A comparison still depends on a trusted baseline. Driftwire makes the next decision visible—and leaves it with a person.” |

If timing is tight, record the Mutation Lab separately and cut it into the video. Do not describe it as the judges' unseen test or claim it proves real-world accuracy.

## 5. Judge-day envelope

Before Q&A, have the fetched, checksum-verified release A and the current organizer repository ready. Once the judge gives the actual number and four words, run:

```bash
python -m driftwire envelope <number> <word1> <word2> <word3> <word4>
```

The angle-bracketed entries are placeholders: replace them with the judge's actual number and words without typing the brackets. Use the output path the command prints, validate that file with `python ../oncosys-challenge/format/validate.py <output-path>`, and explain the observed results. Do not promise a particular verdict in advance. The practice code above opens only the public practice envelope.

## 6. Before submission

Export the video, watch the full export with sound, and add its accessible link to the README. Ensure judges can access the submitted repository and that the commit used in the demo matches the submitted commit. After the final code change, rerun the relevant tests, organizer validator and Gitleaks on that exact commit. The code-freeze deadline is **Saturday 2:15 PM ET**; presentations start at 2:30 PM ET.
