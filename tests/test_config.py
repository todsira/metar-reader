"""Configuration tests: environment variable parsing and the dev-server entry point."""

import importlib

import pytest

import app as app_module


@pytest.mark.parametrize("raw, expected", [
    (None, 10),
    ("", 10),
    ("  ", 10),
    ("2.5", 2.5),
    ("30", 30),
])
def test_env_float(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("X_NUM", raising=False)
    else:
        monkeypatch.setenv("X_NUM", raw)
    assert app_module.env_float("X_NUM", 10) == expected


@pytest.mark.parametrize("raw", ["abc", "0", "-3"])
def test_env_float_rejects_bad_values(monkeypatch, raw):
    monkeypatch.setenv("X_NUM", raw)
    with pytest.raises(SystemExit, match="X_NUM"):
        app_module.env_float("X_NUM", 10)


@pytest.mark.parametrize("raw, expected", [
    (None, True),
    ("", True),
    ("1", True),
    ("TRUE", True),
    ("on", True),
    ("0", False),
    ("False", False),
    ("no", False),
    ("off", False),
])
def test_env_bool(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("X_FLAG", raising=False)
    else:
        monkeypatch.setenv("X_FLAG", raw)
    assert app_module.env_bool("X_FLAG", True) is expected


def test_env_bool_rejects_bad_values(monkeypatch):
    monkeypatch.setenv("X_FLAG", "maybe")
    with pytest.raises(SystemExit, match="X_FLAG"):
        app_module.env_bool("X_FLAG", True)


def test_defaults_match_documented_values(monkeypatch):
    for name in ("METAR_API_URL", "METAR_TIMEOUT"):
        monkeypatch.delenv(name, raising=False)
    try:
        reloaded = importlib.reload(app_module)
        assert reloaded.API_URL == "https://aviationweather.gov/api/data/metar"
        assert reloaded.REQUEST_TIMEOUT_SECONDS == 10
    finally:
        importlib.reload(app_module)


def test_api_settings_read_from_environment(monkeypatch):
    monkeypatch.setenv("METAR_API_URL", "http://localhost:9999/metar")
    monkeypatch.setenv("METAR_TIMEOUT", "3")
    try:
        reloaded = importlib.reload(app_module)
        assert reloaded.API_URL == "http://localhost:9999/metar"
        assert reloaded.REQUEST_TIMEOUT_SECONDS == 3
    finally:
        monkeypatch.undo()
        importlib.reload(app_module)


def test_lookup_uses_configured_url_and_timeout(client, mock_api, monkeypatch):
    monkeypatch.setattr("app.API_URL", "http://example.test/metar")
    monkeypatch.setattr("app.REQUEST_TIMEOUT_SECONDS", 3)
    calls = mock_api([])
    client.get("/?code=KHIO")
    assert calls[0]["url"] == "http://example.test/metar"
    assert calls[0]["timeout"] == 3


def run_main(monkeypatch, **env):
    """Call main() with app.run stubbed out; return the kwargs it was given."""
    for name in ("HOST", "PORT", "FLASK_DEBUG"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    captured = {}
    monkeypatch.setattr(app_module.app, "run", lambda **kwargs: captured.update(kwargs))
    app_module.main()
    return captured


def test_main_defaults(monkeypatch):
    assert run_main(monkeypatch) == {"host": "127.0.0.1", "port": 5000, "debug": True}


def test_main_reads_environment(monkeypatch):
    kwargs = run_main(monkeypatch, HOST="0.0.0.0", PORT="8080", FLASK_DEBUG="0")
    assert kwargs == {"host": "0.0.0.0", "port": 8080, "debug": False}
