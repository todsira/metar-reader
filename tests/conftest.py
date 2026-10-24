"""Shared fixtures: mock METAR records in the aviationweather.gov JSON shape."""

import time

import pytest

from app import app as flask_app


def make_metar(**overrides):
    """Return a calm, clear-sky METAR record, with any fields overridden."""
    metar = {
        "icaoId": "KTST",
        "name": "Test Field, OR, US",
        "obsTime": int(time.time()) - 600,  # observed 10 minutes ago
        "temp": 20.0,
        "dewp": 10.0,
        "wdir": 0,
        "wspd": 0,
        "visib": "10+",
        "altim": 1013.2,
        "rawOb": "METAR KTST 000000Z 00000KT 10SM CLR 20/10 A2992",
        "cover": "CLR",
        "clouds": [],
        "fltCat": "VFR",
    }
    metar.update(overrides)
    return metar


class FakeResponse:
    """Minimal stand-in for requests.Response."""

    def __init__(self, payload):
        self._payload = payload
        self.content = b"x" if payload is not None else b""

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


@pytest.fixture
def mock_api(monkeypatch):
    """Patch requests.get to return the given payload; records call args."""
    calls = []

    def install(payload):
        def fake_get(url, params=None, timeout=None):
            calls.append({"url": url, "params": params, "timeout": timeout})
            return FakeResponse(payload)

        monkeypatch.setattr("app.requests.get", fake_get)
        return calls

    return install
