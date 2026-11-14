from tripwire import doctor


def test_doctor_passes_here_or_names_the_fix(capsys):
    code = doctor.run()
    out = capsys.readouterr().out
    assert "Driftwire doctor" in out
    assert (code == 0 and "All set" in out) or (code == 1 and "fix:" in out)


def test_doctor_reports_missing_challenge_repo_with_the_clone_command(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(doctor, "challenge_dir", lambda explicit=None: None)
    assert doctor.run() == 1
    assert "git clone https://github.com/disleveK/oncosys-hackathon-challenge" in capsys.readouterr().out


def test_doctor_does_not_report_ready_without_envelope_dependency(capsys, monkeypatch):
    real_find_spec = doctor.importlib.util.find_spec
    monkeypatch.setattr(doctor.importlib.util, "find_spec",
                        lambda name: None if name == "cryptography" else real_find_spec(name))
    assert doctor.run() == 1
    out = capsys.readouterr().out
    assert "cryptography" in out
    assert "pip install -r requirements.txt" in out
    assert "All set" not in out
