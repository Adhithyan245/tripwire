"""doctor names the macOS certificate problem with the exact one-line fix, and stays quiet elsewhere."""
from tripwire.doctor import macos_ssl_fix


def test_macos_without_certificates_gets_the_exact_command():
    fix = macos_ssl_fix(platform="darwin", ca_count=0, version=(3, 13))
    assert fix == 'open "/Applications/Python 3.13/Install Certificates.command"'


def test_macos_with_certificates_is_fine():
    assert macos_ssl_fix(platform="darwin", ca_count=140, version=(3, 13)) is None


def test_other_systems_are_never_flagged():
    assert macos_ssl_fix(platform="win32", ca_count=0) is None
    assert macos_ssl_fix(platform="linux", ca_count=0) is None
