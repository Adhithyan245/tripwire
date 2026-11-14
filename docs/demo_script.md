# 90-second demo script

Screen recording at 1080p. Two windows are ready before you start:
- **A:** the Driftwire website (`driftwire.vercel.app` once it's live, or `python -m http.server 8765 --directory site` and open `http://localhost:8765`), on the Run screen.
- **B:** a terminal in `tripwire/` with the virtual environment active, and the practice envelope already opened once, so unsealing doesn't add time.

Every number in the narration was confirmed on November 14 against the organizers' practice envelope ([verdict table](verdict_table.md), [traced finding](trace_example.md), [fresh-clone run](clean_clone_run.md)).

| Time | Screen and clicks | Narration (say exactly) |
| --- | --- | --- |
| 0:00–0:10 | **A**, Run screen. Point at the two release cards: every file shows the same sample count (747 protein samples in both). | "A new data release lands. Same files, same sample counts as the one we trust. Every count check says it's fine." |
| 0:10–0:25 | Click **Run Tripwire**. The scan plays: the red line sweeps the protein samples, 12 light up, and curves flow into A1, which turns amber. | "Driftwire fingerprints every sample. Twelve trip the wire: two patients' profiles swapped, five copied, five that lost their data, all from one subtype." |
| 0:25–0:38 | Click **Findings**. Open **F1, Swapped profiles**. Point at the two sample chips. | "Here's the swap. The ER-positive tumor now carries ER-alpha of minus 1.07, and the ER-negative one carries 3.43. Every one of 131 proteins traded places. Train a model on this and it learns from swapped labels." |
| 0:38–0:55 | **B**: run `python -m driftwire verdicts ../oncosys-challenge/data/tcga-brca/raw ../oncosys-challenge/envelopes/opened/practice/release`. Point at three rows. | "Same release, seven questions, different answers. The subtype mix is Ready. The ER comparison is Conditional: it moved one percent, inside a five-percent tolerance. Training a model to predict ER from protein is Blocked. And predicting subtype from RNA is Blocked as circular, because the label was computed from RNA." |
| 0:55–1:10 | **A**: click **Review** on F1. The reviewer panel shows the repair preview. Type a reason, click **Approve**. | "Driftwire never changes the data. It proposes a repair and sizes it first: restoring the pair moves the A1 difference back to 3.054, within 0.1% of the trusted release. A person approves, with a role and a reason." |
| 1:10–1:22 | **B**: run `python -m driftwire verify out/findings-practice.json ../oncosys-challenge/data/tcga-brca/raw ../oncosys-challenge/envelopes/opened/practice/release`. It prints `identical`. | "Every result carries a receipt. Anyone with the same two releases re-runs it with one command and gets the identical result hash. We got the same hash from a brand-new clone." |
| 1:22–1:30 | **A**: click **Next steps**. Point at "What Driftwire can't tell you". | "What changed, what it breaks, whether your question still holds, what to do next, and what it can't tell you. That's Driftwire." |

## Before recording
- Run `python -m driftwire envelope practice orange meadow pilot lantern` once, so `out/findings-practice.json` exists for the `verify` step.
- The website keeps review decisions in the browser. For a clean take, open it in a private window so F1 starts unreviewed.
- If anything looks different from the narration, re-run the command and use what it prints. Don't use these numbers from memory.
