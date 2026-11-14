"""Run the organizers' envelopes/unseal.py unchanged, but with pandas writing LF line endings.

On Windows pandas writes CRLF by default, so the files unseal.py rebuilds differ by line endings only, and its own
fingerprint check then reports a false mismatch ("Tell a judge right away"). On macOS and Linux pandas already writes
LF. Forcing LF here reproduces exactly what the organizers' script produces there; the check itself is untouched.

The organizers fixed this upstream on Nov 12 (challenge repo d0fbebd: unseal.py now passes lineterminator='
'
itself). setdefault() leaves their explicit value alone, so this shim is harmless on the fixed version and still
protects older clones.

Run from the challenge repo root: python -m tripwire.unseal_lf <envelope> <four words>
"""
import runpy
import sys

import pandas as pd

_to_csv = pd.DataFrame.to_csv


def _to_csv_lf(self, *args, **kwargs):
    kwargs.setdefault("lineterminator", "\n")
    return _to_csv(self, *args, **kwargs)


if __name__ == "__main__":
    pd.DataFrame.to_csv = _to_csv_lf
    sys.argv = ["envelopes/unseal.py"] + sys.argv[1:]
    runpy.run_path("envelopes/unseal.py", run_name="__main__")
