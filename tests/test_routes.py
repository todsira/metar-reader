"""Route tests: the Flask view with the aviationweather.gov API mocked."""

import time

import pytest
import requests

from tests.conftest import make_metar


def test_empty_form(client, mock_api):
    calls = mock_api([])
    html = client.get("/").get_data(as_text=True)
    assert "METAR Reader" in html
    assert calls == []  # no lookup without a code


def test_successful_lookup(client, mock_api):
    calls = mock_api([make_metar(
        temp=15, wspd=10, wdir=270,
        clouds=[{"cover": "BKN", "base": 5000}], cover="BKN")])
    html = client.get("/?code=ktst").get_data(as_text=True)
    assert "Test Field, OR, US" in html
    assert "Mostly cloudy, 59°F" in html
    assert "Wind 12 mph from the west (270°)" in html
    assert "Good flying conditions (VFR)" in html
    assert "METAR KTST" in html  # raw report is shown
    assert "10 min ago" in html
    assert calls[0]["params"] == {"ids": "KTST", "format": "json"}


def test_three_letter_code_gets_k_prefix(client, mock_api):
    calls = mock_api([make_metar()])
    client.get("/?code=hio")
    assert calls[0]["params"]["ids"] == "KHIO"


def test_four_letter_code_unchanged(client, mock_api):
    calls = mock_api([make_metar()])
    client.get("/?code=EGLL")
    assert calls[0]["params"]["ids"] == "EGLL"


def test_invalid_code_rejected_without_lookup(client, mock_api):
    calls = mock_api([make_metar()])
    html = client.get("/?code=!!").get_data(as_text=True)
    assert "3 or 4 character airport code" in html
    assert calls == []


def test_too_long_code_rejected(client, mock_api):
    calls = mock_api([make_metar()])
    html = client.get("/?code=ABCDE").get_data(as_text=True)
    assert "3 or 4 character airport code" in html
    assert calls == []


def test_unknown_station(client, mock_api):
    mock_api(None)  # API returns an empty body
    html = client.get("/?code=ZZZZ").get_data(as_text=True)
    assert "No METAR found for ZZZZ" in html


def test_empty_list_from_api(client, mock_api):
    mock_api([])
    html = client.get("/?code=ZZZZ").get_data(as_text=True)
    assert "No METAR found for ZZZZ" in html


def test_service_unreachable(client, monkeypatch):
    def boom(*args, **kwargs):
        raise requests.ConnectionError("down")

    monkeypatch.setattr("app.requests.get", boom)
    html = client.get("/?code=KHIO").get_data(as_text=True)
    assert "reach the weather service" in html


def test_service_returns_bad_json(client, monkeypatch):
    class BadResponse:
        content = b"<html>oops</html>"

        def raise_for_status(self):
            pass

        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr("app.requests.get", lambda *a, **k: BadResponse())
    html = client.get("/?code=KHIO").get_data(as_text=True)
    assert "weather service" in html


def test_fractional_visibility_does_not_crash(client, mock_api):
    mock_api([make_metar(visib="1/2", wxString="FG")])
    response = client.get("/?code=KTST")
    assert response.status_code == 200
    assert "Visibility is poor (1/2 miles)" in response.get_data(as_text=True)


@pytest.mark.parametrize("seconds_ago, expected", [
    (5, "0 min ago"),
    (59 * 60, "59 min ago"),
    (3 * 3600, "180 min ago"),
])
def test_observation_age(client, mock_api, seconds_ago, expected):
    mock_api([make_metar(obsTime=int(time.time()) - seconds_ago)])
    html = client.get("/?code=KTST").get_data(as_text=True)
    assert expected in html


def test_missing_wind_not_shown_as_calm(client, mock_api):
    metar = make_metar()
    del metar["wspd"]
    mock_api([metar])
    html = client.get("/?code=KTST").get_data(as_text=True)
    assert "Calm winds" not in html
