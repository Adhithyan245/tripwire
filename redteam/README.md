# Try to sneak a change past Driftwire

You don't need to know how Driftwire works. You'll edit a copy of a data release by hand, write down what you did, and then we see what Driftwire catches.

## What you need
- The two repos set up as in the main README's quickstart (`oncosys-challenge/` next to `tripwire/`, with release A downloaded and the practice envelope opened).
- A spreadsheet program or text editor. The files are tab-separated text; the `.gz` files are compressed (7-Zip on Windows can open them; on a Mac, double-click to decompress, then compress again with `gzip` when you're done).

## Steps
1. From the `tripwire` folder, make your own copy of the new release:
   ```bash
   python redteam/run_redteam.py copy
   ```
   Your copy is in `redteam/work/release/`. It holds five files: `clinical.tsv`, `survival.tsv`, `protein_rppa.tsv.gz`, `copy_number_gistic.tsv.gz` and `mutation_gene_level.tsv.gz`.
2. Copy `redteam/answer_key_TEMPLATE.md` to `redteam/answer_key.md` and keep it open.
3. **Change anything you like** in the files in `redteam/work/release/`, and write each change in your answer key as you go. Ideas, but don't limit yourself to these:
   - swap two patients' rows or columns;
   - copy one sample's values over another's;
   - delete a sample;
   - change a label (an ER status, a subtype);
   - nudge some numbers;
   - rename a sample ID (change its case, add a space, change the last digits);
   - duplicate a row;
   - delete a whole column or protein.

   Change a few things or many; make some subtle. Keep each file's format (tab-separated, same header line).
4. Run Driftwire on your copy:
   ```bash
   python redteam/run_redteam.py run
   ```
   Results go to `redteam/results/`: `summary.txt` (the short list), `report.html` (open it in a browser) and `findings.json`.
5. Only now share `redteam/answer_key.md` and `redteam/results/summary.txt` with the Driftwire team. We'll fill in `docs/blind_redteam.md` together: what was caught, what was missed and any false alarms.

Your edited copy and your answer key are ignored by git, so they can't be committed by accident. Delete `redteam/work/` when you're done.
