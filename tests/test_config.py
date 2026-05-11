from cqw.config import Settings, generate_random_credential


def test_generate_random_credential():
    cred = generate_random_credential()
    assert len(cred) == 8
    assert cred.isalnum()

    cred2 = generate_random_credential(12)
    assert len(cred2) == 12


class _SettingsNoCLI(Settings):
    model_config = Settings.model_config | {"cli_parse_args": False}


def test_settings_defaults():
    settings = _SettingsNoCLI(forward="localhost:8080")
    assert settings.user is not None
    assert settings.password is not None
    assert len(settings.user) == 8
    assert len(settings.password) == 8
    assert settings.qr is True
    assert settings.verbose is False


def test_settings_explicit_credentials():
    settings = _SettingsNoCLI(forward="localhost:8080", user="admin", password="secret")
    assert settings.user == "admin"
    assert settings.password == "secret"


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("CQW_USER", "envuser")
    monkeypatch.setenv("CQW_PASS", "envpass")

    settings = _SettingsNoCLI(forward="localhost:8080")
    assert settings.user == "envuser"
    assert settings.password == "envpass"


def test_forward_url():
    settings1 = _SettingsNoCLI(forward="localhost:8080")
    assert settings1.forward_url == "http://localhost:8080"

    settings2 = _SettingsNoCLI(forward="http://example.com:9000")
    assert settings2.forward_url == "http://example.com:9000"

    settings3 = _SettingsNoCLI(forward="https://secure.example.com")
    assert settings3.forward_url == "https://secure.example.com"
