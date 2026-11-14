"""The blind red-team runner: copy a release, run Driftwire on it, write results a non-developer can read."""
import importlib.util
import pathlib

from conftest import write

SPEC = importlib.util.spec_from_file_location("run_redteam", pathlib.Path(__file__).resolve().parents[1] / "redteam" / "run_redteam.py")


def test_copy_then_run_writes_readable_results(releases, tmp_path, monkeypatch):
    a, b, clinical, protein = releases
    write(b, clinical, protein)
    mod = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(mod)
    out = tmp_path / "results"
    monkeypatch.setattr(mod, "HERE", tmp_path)
    work = tmp_path / "work" / "release"
    assert mod.main(["copy", "--source", str(b), "--release", str(work)]) == 0
    assert mod.main(["copy", "--source", str(b), "--release", str(work)]) == 1   # never overwrites an edited copy
    assert mod.main(["run", "--trusted", str(a), "--release", str(work)]) == 0
    summary = (out / "summary.txt").read_text(encoding="utf-8")
    assert summary.startswith("Driftwire verdict:") and (out / "report.html").exists() and (out / "findings.json").exists()
