"""Hosting only (branch `hosted`, used by driftwire.streamlit.app): fetch the organizers' public data on first start.

On a laptop the challenge repo sits next to this repo. A cloud host only has this repo, so here we download the
organizers' challenge repo at a pinned commit (as a zip, no git needed), run their own fetch.py to download release A
from the public UCSC Xena hub (checksums verified by their script; RNA skipped, as in the envelopes), and point
Driftwire at it with TRIPWIRE_CHALLENGE_DIR. Nothing here changes how Driftwire compares or decides.
"""
from __future__ import annotations

import io
import os
import pathlib
import shutil
import subprocess
import sys
import urllib.request
import zipfile

REPO = "disleveK/oncosys-hackathon-challenge"
COMMIT = "6e15a399a64ffbf80778db0b462ac239e70086b9"  # the challenge commit Driftwire was tested against
DEST = pathlib.Path(os.environ.get("DRIFTWIRE_DATA_HOME", pathlib.Path.home())) / "oncosys-challenge"


def ensure_challenge_repo() -> tuple[pathlib.Path | None, str]:
    """Returns (path, log). Never raises: on failure the dashboard shows its usual 'not found' message."""
    log = []
    try:
        if not (DEST / "format" / "validate.py").exists():
            url = f"https://codeload.github.com/{REPO}/zip/{COMMIT}"
            data = urllib.request.urlopen(url, timeout=120).read()
            tmp = DEST.with_name(DEST.name + ".part")
            shutil.rmtree(tmp, ignore_errors=True)
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                z.extractall(tmp)
            inner = next(tmp.iterdir())
            shutil.rmtree(DEST, ignore_errors=True)
            inner.rename(DEST)
            shutil.rmtree(tmp, ignore_errors=True)
            log.append(f"downloaded {REPO}@{COMMIT[:7]}")
        raw = DEST / "data" / "tcga-brca" / "raw"
        if not (raw / "clinical.tsv").exists():
            r = subprocess.run([sys.executable, "data/tcga-brca/fetch.py", "--no-rna"], cwd=DEST,
                               capture_output=True, text=True, timeout=600)
            log.append(r.stdout[-1500:] + r.stderr[-500:])
        os.environ["TRIPWIRE_CHALLENGE_DIR"] = str(DEST)
        return DEST, "\n".join(log)
    except Exception as e:  # noqa: BLE001  a failed download must not take the app down
        return None, "\n".join(log + [f"{type(e).__name__}: {e}"])
