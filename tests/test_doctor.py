from tripwire import doctor


def test_doctor_passes_here_or_names_the_fix(capsys):
    code = doctor.run()
    out = capsys.readouterr().out
    assert "Tripwire doctor" in out
    assert (code == 0 and "All set" in out) or (code == 1 and "fix:" in out)


def test_doctor_reports_missing_challenge_repo_with_the_clone_command(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(doctor, "challenge_dir", lambda explicit=None: None)
    assert doctor.run() == 1
    assert "git clone https://github.com/disleveK/oncosys-hackathon-challenge" in capsys.readouterr().out
