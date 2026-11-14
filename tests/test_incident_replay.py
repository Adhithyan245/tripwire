"""Independent checks for the measured incident replay, using synthetic inputs."""
import numpy as np
import pandas as pd
import pytest

from conftest import write
from scripts.qa.incident_replay import replay
from tripwire.release import content_sha256
from tripwire.validate import challenge_dir


@pytest.mark.skipif(challenge_dir() is None, reason="organizer validator required")
def test_incident_scores_partners_and_preserves_source(releases, tmp_path):
    a, _, clinical, protein = releases
    extra = pd.DataFrame(np.random.default_rng(9).normal(size=(18, len(protein.columns))),
                         columns=protein.columns, index=[f"P{i}" for i in range(18)])
    protein = pd.concat([protein, extra])
    protein.index.name = "sample"
    write(a, clinical, protein)
    before = content_sha256(a / "protein_rppa.tsv.gz")
    result = replay(a, tmp_path / "evidence")
    swap = result["detection"]["by_change_type"][0]
    assert swap["true_positives"] == swap["partner_matches"] == 2
    assert swap["false_positives"] == swap["false_negatives"] == 0
    assert result["count_only_baseline"] == "no alarm"
    assert result["no_change_detector_reports"] == result["oracle_recovery_detector_reports"] == 0
    assert result["all_outputs_validate"] and result["source_unchanged"]
    assert before == content_sha256(a / "protein_rppa.tsv.gz")
    assert result["analyses"]["baseline"] == result["analyses"]["oracle-recovery"]


def test_replay_rejects_output_inside_source(releases):
    with pytest.raises(ValueError, match="outside"):
        replay(releases[0], releases[0] / "evidence")


def test_replay_does_not_overwrite_evidence(releases, tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(FileExistsError, match="never overwritten"):
        replay(releases[0], output)
