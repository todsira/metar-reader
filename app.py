import re
from datetime import datetime, timezone

import requests
from flask import Flask, render_template, request

app = Flask(__name__)

API_URL = "https://aviationweather.gov/api/data/metar"

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

COMPASS = ["north", "north-northeast", "northeast", "east-northeast", "east",
           "east-southeast", "southeast", "south-southeast", "south",
           "south-southwest", "southwest", "west-southwest", "west",
           "west-northwest", "northwest", "north-northwest"]


def c_to_f(c):
    return c * 9 / 5 + 32


def knots_to_mph(kt):
    return kt * 1.15078


def describe_weather(wx):
    """Turn a present-weather string like '-RA BR' into plain English."""
    phrases = []
    for token in wx.split():
        m = re.fullmatch(r"([-+]|VC)?((?:[A-Z]{2})+)", token)
        if not m:
            continue
        intensity, codes = m.groups()
        words = [WX_CODES.get(codes[i:i + 2], "") for i in range(0, len(codes), 2)]
        text = " ".join(w for w in words if w)
        prefix = {"-": "light ", "+": "heavy "}.get(intensity, "")
        suffix = " in the vicinity" if intensity == "VC" else ""
        phrases.append(f"{prefix}{text}{suffix}".strip())
    return phrases


def describe_wind(m):
    wspd, wdir, wgst = m.get("wspd") or 0, m.get("wdir"), m.get("wgst")
    if wspd == 0:
        return "Calm winds"
    mph = round(knots_to_mph(wspd))
    if wdir == "VRB" or wdir is None:
        text = f"Wind {mph} mph from a variable direction"
    else:
        # Wind direction is where the wind comes FROM.
        name = COMPASS[round(wdir / 22.5) % 16]
        text = f"Wind {mph} mph from the {name} ({wdir}°)"
    if wgst:
        text += f", gusting to {round(knots_to_mph(wgst))} mph"
    return text


def describe_clouds(m):
    clouds = m.get("clouds") or []
    if not clouds:
        return COVER.get(m.get("cover"), "clear skies").capitalize()
    parts = []
    for layer in clouds:
        what = COVER.get(layer.get("cover"), layer.get("cover", "clouds"))
        base = layer.get("base")
        parts.append(f"{what} at {base:,} ft" if base else what)
    return "Sky: " + ", ".join(parts)


def describe_visibility(visib):
    if visib is None:
        return None
    if isinstance(visib, str) and visib.endswith("+"):
        return f"Visibility is excellent ({visib.rstrip('+')}+ miles)"
    miles = float(visib)
    quality = "poor" if miles < 3 else "reduced" if miles < 5 else "good"
    return f"Visibility is {quality} ({visib} miles)"


def summarize(m):
    temp_c = m.get("temp")
    lines = []
    if temp_c is not None:
        line = f"Temperature {round(c_to_f(temp_c))}°F ({round(temp_c)}°C)"
        if m.get("dewp") is not None:
            spread = temp_c - m["dewp"]
            if spread <= 2:
                line += ", feels damp and humid"
        lines.append(line)
    lines.append(describe_wind(m))
    lines.append(describe_clouds(m))
    for phrase in describe_weather(m.get("wxString") or ""):
        lines.append(phrase.capitalize())
    vis = describe_visibility(m.get("visib"))
    if vis:
        lines.append(vis)
    if m.get("altim"):
        lines.append(f"Pressure {m['altim'] * 0.02953:.2f} inHg ({round(m['altim'])} hPa)")

    wx = describe_weather(m.get("wxString") or "")
    cover = m.get("cover") or ((m.get("clouds") or [{}])[0].get("cover"))
    if wx:
        headline = wx[0].capitalize()
    else:
        headline = {"CLR": "Clear", "SKC": "Clear", "NSC": "Mostly clear",
                    "FEW": "Mostly clear", "SCT": "Partly cloudy",
                    "BKN": "Mostly cloudy", "OVC": "Overcast"}.get(cover, "Fair")
    if temp_c is not None:
        headline += f", {round(c_to_f(temp_c))}°F"
    return headline, lines


FLIGHT_CAT = {
    "VFR": "Good flying conditions (VFR)",
    "MVFR": "Marginal flying conditions (MVFR)",
    "IFR": "Poor flying conditions (IFR)",
    "LIFR": "Very poor flying conditions (LIFR)",
}


@app.route("/", methods=["GET"])
def index():
    code = request.args.get("code", "").strip().upper()
    ctx = {"code": code}
    if not code:
        return render_template("index.html", **ctx)
    if not re.fullmatch(r"[A-Z0-9]{3,4}", code):
        ctx["error"] = "Please enter a 3 or 4 character airport code, like KHIO."
        return render_template("index.html", **ctx)
    # US airports are often typed without the K prefix (e.g. HIO, JFK).
    ident = "K" + code if len(code) == 3 else code
    try:
        resp = requests.get(API_URL, params={"ids": ident, "format": "json"}, timeout=10)
        resp.raise_for_status()
        data = resp.json() if resp.content else []
    except (requests.RequestException, ValueError):
        ctx["error"] = "Couldn't reach the weather service. Please try again shortly."
        return render_template("index.html", **ctx)
    if not data:
        ctx["error"] = f"No METAR found for {ident}. Check the code and try again."
        return render_template("index.html", **ctx)

    m = data[0]
    headline, lines = summarize(m)
    obs = datetime.fromtimestamp(m["obsTime"], tz=timezone.utc)
    mins = int((datetime.now(timezone.utc) - obs).total_seconds() // 60)
    ctx.update(
        station=m.get("name", ident), ident=ident, headline=headline, lines=lines,
        raw=m.get("rawOb"), flight=FLIGHT_CAT.get(m.get("fltCat")),
        observed=obs.strftime("%H:%M UTC"), age=mins,
    )
    return render_template("index.html", **ctx)


if __name__ == "__main__":
    app.run(debug=True)
