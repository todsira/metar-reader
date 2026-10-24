"""METAR Reader: a small Flask app that turns METAR reports into plain English.

A METAR is a standardised, cryptic aviation weather report. This app looks up
the latest METAR for an airport from the aviationweather.gov API and
summarises it in a form anyone can read.
"""

import os
import re
from datetime import datetime, timezone

import requests
from flask import Flask, render_template, request

app = Flask(__name__)


def env_float(name, default):
    """Read a positive number from the environment, or return the default."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        raise SystemExit(f"{name} must be a number, got {raw!r}")
    if value <= 0:
        raise SystemExit(f"{name} must be greater than zero, got {raw!r}")
    return value


def env_bool(name, default):
    """Read a true/false flag (1/0, true/false, yes/no, on/off) from the environment."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    raise SystemExit(f"{name} must be true or false, got {raw!r}")


# Settings can be overridden with environment variables; see the README.
API_URL = os.environ.get("METAR_API_URL") or "https://aviationweather.gov/api/data/metar"
REQUEST_TIMEOUT_SECONDS = env_float("METAR_TIMEOUT", 10)

# Cloud cover abbreviations -> plain English.
COVER = {
    "CLR": "clear skies",
    "SKC": "clear skies",
    "NSC": "no significant clouds",
    "FEW": "a few clouds",
    "SCT": "scattered clouds",
    "BKN": "mostly cloudy",
    "OVC": "overcast",
    "VV": "sky obscured",
}

# Two-letter present-weather codes -> plain English.
WX_CODES = {
    "MI": "shallow", "BC": "patchy", "PR": "partial", "DR": "drifting",
    "BL": "blowing", "SH": "showers of", "TS": "thunderstorm with",
    "FZ": "freezing", "DZ": "drizzle", "RA": "rain", "SN": "snow",
    "SG": "snow grains", "IC": "ice crystals", "PL": "ice pellets",
    "GR": "hail", "GS": "small hail", "UP": "unknown precipitation",
    "BR": "mist", "FG": "fog", "FU": "smoke", "VA": "volcanic ash",
    "DU": "dust", "SA": "sand", "HZ": "haze", "PY": "spray",
    "PO": "dust whirls", "SQ": "squalls", "FC": "funnel cloud",
    "SS": "sandstorm", "DS": "duststorm",
}

# Sixteen-point compass rose, starting at north and moving clockwise.
COMPASS = ["north", "north-northeast", "northeast", "east-northeast", "east",
           "east-southeast", "southeast", "south-southeast", "south",
           "south-southwest", "southwest", "west-southwest", "west",
           "west-northwest", "northwest", "north-northwest"]

# Flight category codes -> plain English.
FLIGHT_CAT = {
    "VFR": "Good flying conditions (VFR)",
    "MVFR": "Marginal flying conditions (MVFR)",
    "IFR": "Poor flying conditions (IFR)",
    "LIFR": "Very poor flying conditions (LIFR)",
}

# Headline wording for the most significant cloud cover when nothing else
# (rain, fog, ...) is being reported.
SKY_HEADLINE = {
    "CLR": "Clear", "SKC": "Clear", "NSC": "Mostly clear",
    "FEW": "Mostly clear", "SCT": "Partly cloudy",
    "BKN": "Mostly cloudy", "OVC": "Overcast",
}


def c_to_f(celsius):
    """Convert degrees Celsius to degrees Fahrenheit."""
    return celsius * 9 / 5 + 32


def knots_to_mph(knots):
    """Convert knots to miles per hour."""
    return knots * 1.15078


def describe_weather(wx):
    """Convert a METAR present-weather string into plain-English phrases.

    Args:
        wx: Space-separated weather groups, e.g. ``"-RA BR"``.

    Returns:
        A list of phrases, e.g. ``["light rain", "mist"]``.
    """
    phrases = []
    for token in wx.split():
        # Optional intensity prefix, then one or more two-letter codes.
        match = re.fullmatch(r"([-+]|VC)?((?:[A-Z]{2})+)", token)
        if not match:
            continue
        intensity, codes = match.groups()
        words = [WX_CODES.get(codes[i:i + 2], "") for i in range(0, len(codes), 2)]
        text = " ".join(w for w in words if w)
        # "showers of" / "thunderstorm with" dangle when nothing follows (VCSH).
        for connector in (" of", " with"):
            text = text.removesuffix(connector)
        prefix = {"-": "light ", "+": "heavy "}.get(intensity, "")
        suffix = " in the vicinity" if intensity == "VC" else ""
        if text:  # skip tokens made only of unrecognised codes
            phrases.append(f"{prefix}{text}{suffix}".strip())
    return phrases


def describe_wind(metar):
    """Describe wind speed, direction and gusts in mph.

    Returns None when the wind speed is not reported.
    """
    speed = metar.get("wspd")
    if speed is None:
        return None
    direction = metar.get("wdir")
    gust = metar.get("wgst")

    if speed == 0:
        return "Calm winds"

    mph = round(knots_to_mph(speed))
    if direction == "VRB" or direction is None:
        text = f"Wind {mph} mph from a variable direction"
    else:
        # Meteorological convention: direction is where the wind blows FROM.
        name = COMPASS[round(direction / 22.5) % 16]
        text = f"Wind {mph} mph from the {name} ({direction}°)"
    if gust:
        text += f", gusting to {round(knots_to_mph(gust))} mph"
    return text


def describe_clouds(metar):
    """Describe cloud cover, including the height of each layer in feet."""
    clouds = metar.get("clouds") or []
    if not clouds:
        return COVER.get(metar.get("cover"), "clear skies").capitalize()

    parts = []
    for layer in clouds:
        what = COVER.get(layer.get("cover"), layer.get("cover", "clouds"))
        base = layer.get("base")
        parts.append(f"{what} at {base:,} ft" if base else what)
    return "Sky: " + ", ".join(parts)


def parse_miles(visib):
    """Parse a visibility value into ``(miles, is_less_than)``.

    Handles numbers (``0.5``), fractions (``"1/2"``), mixed numbers
    (``"1 1/2"``) and the ``M`` prefix meaning "less than" (``"M1/4"``).
    """
    text = str(visib).strip()
    less_than = text.startswith("M")
    miles = 0.0
    for part in text.lstrip("M").split():
        if "/" in part:
            numerator, denominator = part.split("/")
            miles += float(numerator) / float(denominator)
        else:
            miles += float(part)
    return miles, less_than


def describe_visibility(visib):
    """Describe visibility in statute miles, or return None if unreported.

    Args:
        visib: Miles as a number, or a string such as ``"10+"``, ``"1/2"``
            or ``"M1/4"``.
    """
    if visib is None:
        return None
    if isinstance(visib, str) and visib.endswith("+"):
        return f"Visibility is excellent ({visib.rstrip('+')}+ miles)"

    try:
        miles, less_than = parse_miles(visib)
    except ValueError:
        return None  # unparseable: omit the line rather than fail the report
    quality = "poor" if miles < 3 else "reduced" if miles < 5 else "good"
    shown = f"under {visib.lstrip('M')}" if less_than else f"{visib}"
    return f"Visibility is {quality} ({shown} miles)"


def summarize(metar):
    """Build a friendly summary from one decoded METAR record.

    Args:
        metar: A single observation dict from the aviationweather.gov JSON API.

    Returns:
        A ``(headline, lines)`` tuple: a short headline such as
        ``"Clear, 35°F"`` and a list of detail lines.
    """
    temp_c = metar.get("temp")
    dewpoint_c = metar.get("dewp")
    lines = []

    if temp_c is not None:
        line = f"Temperature {round(c_to_f(temp_c))}°F ({round(temp_c)}°C)"
        # A temperature within 2°C of the dew point means near-saturated air.
        if dewpoint_c is not None and temp_c - dewpoint_c <= 2:
            line += ", feels damp and humid"
        lines.append(line)

    wind = describe_wind(metar)
    if wind:
        lines.append(wind)
    lines.append(describe_clouds(metar))

    weather = describe_weather(metar.get("wxString") or "")
    lines.extend(phrase.capitalize() for phrase in weather)

    visibility = describe_visibility(metar.get("visib"))
    if visibility:
        lines.append(visibility)

    if metar.get("altim"):
        # The API reports altimeter setting in hPa; US readers expect inHg.
        lines.append(f"Pressure {metar['altim'] * 0.02953:.2f} inHg "
                     f"({round(metar['altim'])} hPa)")

    # Headline: significant weather wins; otherwise fall back to sky cover.
    if weather:
        headline = weather[0].capitalize()
    else:
        cover = metar.get("cover") or (metar.get("clouds") or [{}])[0].get("cover")
        headline = SKY_HEADLINE.get(cover, "Fair")
    if temp_c is not None:
        headline += f", {round(c_to_f(temp_c))}°F"
    return headline, lines


@app.route("/", methods=["GET"])
def index():
    """Render the search form and, when a code is given, the decoded report."""
    code = request.args.get("code", "").strip().upper()
    context = {"code": code}
    if not code:
        return render_template("index.html", **context)

    # ICAO codes are 4 letters; US IATA-style codes are 3.
    if not re.fullmatch(r"[A-Z0-9]{3,4}", code):
        context["error"] = "Please enter a 3 or 4 character airport code, like KHIO."
        return render_template("index.html", **context)

    # US airports are often typed without the K prefix (e.g. HIO, JFK).
    ident = "K" + code if len(code) == 3 else code

    try:
        response = requests.get(
            API_URL,
            params={"ids": ident, "format": "json"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        # The API returns an empty body when the station is unknown.
        data = response.json() if response.content else []
    except (requests.RequestException, ValueError):
        context["error"] = "Couldn't reach the weather service. Please try again shortly."
        return render_template("index.html", **context)

    if not data:
        context["error"] = f"No METAR found for {ident}. Check the code and try again."
        return render_template("index.html", **context)

    metar = data[0]
    headline, lines = summarize(metar)
    observed = datetime.fromtimestamp(metar["obsTime"], tz=timezone.utc)
    age_minutes = int((datetime.now(timezone.utc) - observed).total_seconds() // 60)
    context.update(
        station=metar.get("name", ident),
        ident=ident,
        headline=headline,
        lines=lines,
        raw=metar.get("rawOb"),
        flight=FLIGHT_CAT.get(metar.get("fltCat")),
        observed=observed.strftime("%H:%M UTC"),
        age=age_minutes,
    )
    return render_template("index.html", **context)


def main():
    """Run the Flask development server, configured from the environment."""
    # Debug mode is for local development only; never enable it in production.
    app.run(
        host=os.environ.get("HOST") or "127.0.0.1",
        port=int(env_float("PORT", 5000)),
        debug=env_bool("FLASK_DEBUG", True),
    )


if __name__ == "__main__":
    main()
