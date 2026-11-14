"""The public name: python -m driftwire runs the same tool as python -m tripwire."""
import subprocess
import sys


def _help(module):
    return subprocess.run([sys.executable, "-m", module, "--help"], capture_output=True, text=True, timeout=60)


def test_driftwire_command_runs():
    r = _help("driftwire")
    assert r.returncode == 0 and r.stdout.startswith("usage: driftwire")


def test_tripwire_command_still_works():
    assert _help("tripwire").returncode == 0


def test_mutation_lab_under_new_name():
    assert _help("driftwire.mutation_lab").returncode == 0
