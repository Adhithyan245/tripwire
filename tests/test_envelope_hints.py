"""The envelope command's last line must point at the real fix, and a failed unseal must not look like an answer."""
from tripwire.__main__ import ENVELOPE_FAILED, unseal_hint


def test_missing_release_a_points_to_fetch_not_to_the_code():
    out = "  ✗ Release A isn't here yet. Run  python data/tcga-brca/fetch.py  first, then try again."
    h = unseal_hint(out)
    assert "fetch.py" in h and "four words" not in h


def test_changed_release_a_points_to_fetch():
    h = unseal_hint("clinical.tsv in data/tcga-brca/raw/ is missing or doesn't match the published fingerprint.")
    assert "fetch.py" in h


def test_wrong_code_points_to_number_and_words():
    assert "four words" in unseal_hint("That code doesn't open envelope E07. Check the envelope number and the four words.")
    assert "four words" in unseal_hint("'x7' isn't an envelope number. Use the number on your card, for example 07.")


def test_stale_challenge_repo_points_to_git_pull():
    assert "git pull" in unseal_hint("E07.sealed doesn't match its published fingerprint. Pull the latest repo (git pull) and retry.")


def test_missing_package():
    assert "requirements.txt" in unseal_hint("ModuleNotFoundError: No module named 'cryptography'")


def test_failed_envelope_has_its_own_exit_code():
    assert ENVELOPE_FAILED not in (0, 1)


def test_unknown_envelope_number():
    h = unseal_hint("There's no envelope E99. Pull the latest repo (git pull), and check the number on your card.")
    assert "number on your card" in h and "git pull" in h
