"""Unit tests for the pure METAR-to-English functions."""

import pytest

from app import (c_to_f, describe_clouds, describe_visibility, describe_weather,
                 describe_wind, knots_to_mph, summarize)
from tests.conftest import make_metar


def test_unit_conversions():
    assert c_to_f(0) == 32
    assert c_to_f(100) == 212
    assert knots_to_mph(10) == pytest.approx(11.5078)


@pytest.mark.parametrize("metar, expected", [
    (dict(wspd=0, wdir=0), "Calm winds"),
    (dict(wspd=5, wdir=180), "Wind 6 mph from the south (180°)"),
    (dict(wspd=10, wdir=270), "Wind 12 mph from the west (270°)"),
    (dict(wspd=10, wdir=360), "Wind 12 mph from the north (360°)"),
    (dict(wspd=10, wdir=45), "Wind 12 mph from the northeast (45°)"),
    (dict(wspd=10, wdir=200, wgst=25),
     "Wind 12 mph from the south-southwest (200°), gusting to 29 mph"),
    (dict(wspd=4, wdir="VRB"), "Wind 5 mph from a variable direction"),
    (dict(wspd=4, wdir=None), "Wind 5 mph from a variable direction"),
    # Regression: unreported wind must not be presented as calm.
    ({}, None),
    (dict(wspd=None, wdir=180), None),
])
def test_describe_wind(metar, expected):
    assert describe_wind(metar) == expected


@pytest.mark.parametrize("wx, expected", [
    ("", []),
    ("RA", ["rain"]),
    ("-RA", ["light rain"]),
    ("+RA", ["heavy rain"]),
    ("-RA BR", ["light rain", "mist"]),
    ("TSRA", ["thunderstorm with rain"]),
    ("+TSRA", ["heavy thunderstorm with rain"]),
    ("-SHSN", ["light showers of snow"]),
    ("FZFG", ["freezing fog"]),
    ("HZ", ["haze"]),
    # Regression: connector words must not dangle when nothing follows.
    ("VCSH", ["showers in the vicinity"]),
    ("VCTS", ["thunderstorm in the vicinity"]),
    ("VCFG", ["fog in the vicinity"]),
    # Tokens that are not weather groups are ignored, not rendered blank.
    ("NSW", []),
    ("//", []),
    ("XX", []),
    ("XX RA", ["rain"]),
])
def test_describe_weather(wx, expected):
    assert describe_weather(wx) == expected


@pytest.mark.parametrize("metar, expected", [
    (dict(clouds=[], cover="CLR"), "Clear skies"),
    (dict(clouds=[{"cover": "FEW", "base": 3500}]),
     "Sky: a few clouds at 3,500 ft"),
    (dict(clouds=[{"cover": "SCT", "base": 2000}, {"cover": "OVC", "base": 8000}]),
     "Sky: scattered clouds at 2,000 ft, overcast at 8,000 ft"),
    # Vertical visibility layers may carry no base height.
    (dict(clouds=[{"cover": "VV"}]), "Sky: sky obscured"),
    (dict(clouds=[{"cover": "VV", "base": None}]), "Sky: sky obscured"),
    (dict(clouds=[], cover=None), "Clear skies"),
])
def test_describe_clouds(metar, expected):
    assert describe_clouds(metar) == expected


@pytest.mark.parametrize("visib, expected", [
    (None, None),
    ("10+", "Visibility is excellent (10+ miles)"),
    (10, "Visibility is good (10 miles)"),
    (4, "Visibility is reduced (4 miles)"),
    (0.5, "Visibility is poor (0.5 miles)"),
    # Regression: fractional strings used to raise ValueError.
    ("1/2", "Visibility is poor (1/2 miles)"),
    ("1 1/2", "Visibility is poor (1 1/2 miles)"),
    ("M1/4", "Visibility is poor (under 1/4 miles)"),
    ("3 1/2", "Visibility is reduced (3 1/2 miles)"),
    ("garbage", None),
])
def test_describe_visibility(visib, expected):
    assert describe_visibility(visib) == expected


class TestSummarize:
    def test_clear_calm_day(self):
        headline, lines = summarize(make_metar(temp=1.7, dewp=-5))
        assert headline == "Clear, 35°F"
        assert "Temperature 35°F (2°C)" in lines
        assert "Calm winds" in lines

    def test_humid_when_dewpoint_close(self):
        _, lines = summarize(make_metar(temp=2, dewp=1))
        assert "Temperature 36°F (2°C), feels damp and humid" in lines

    def test_not_humid_when_dewpoint_far(self):
        _, lines = summarize(make_metar(temp=20, dewp=5))
        assert not any("humid" in line for line in lines)

    def test_weather_overrides_sky_in_headline(self):
        headline, lines = summarize(make_metar(
            temp=10, wxString="-RA",
            clouds=[{"cover": "OVC", "base": 1200}]))
        assert headline == "Light rain, 50°F"
        assert "Light rain" in lines

    @pytest.mark.parametrize("cover, base, word", [
        ("FEW", 4000, "Mostly clear"),
        ("SCT", 4000, "Partly cloudy"),
        ("BKN", 4000, "Mostly cloudy"),
        ("OVC", 4000, "Overcast"),
    ])
    def test_headline_from_sky_cover(self, cover, base, word):
        headline, _ = summarize(make_metar(
            temp=20, cover=cover, clouds=[{"cover": cover, "base": base}]))
        assert headline == f"{word}, 68°F"

    def test_pressure_converted_to_inhg(self):
        _, lines = summarize(make_metar(altim=1026.2))
        assert "Pressure 30.30 inHg (1026 hPa)" in lines

    def test_missing_temperature(self):
        headline, lines = summarize(make_metar(temp=None, dewp=None))
        assert headline == "Clear"
        assert not any(line.startswith("Temperature") for line in lines)

    def test_empty_record_does_not_crash(self):
        headline, lines = summarize({})
        assert headline == "Fair"
        assert lines == ["Clear skies"]  # no bogus "Calm winds"

    def test_unknown_weather_code_adds_no_blank_line(self):
        _, lines = summarize(make_metar(wxString="XX"))
        assert "" not in lines
