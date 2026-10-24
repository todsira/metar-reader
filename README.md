# ✈️ METAR Reader

A small Flask web app that turns cryptic aviation weather reports into plain English.

A **METAR** is a standardised weather report issued by airports, written in a compact code like:

```
METAR KHIO 240853Z AUTO 00000KT 10SM CLR 02/01 A3030 RMK AO2 SLP260
```

Type in an airport code and METAR Reader fetches the latest report and tells you what it means:

> **Clear, 35°F**
> - Temperature 35°F (2°C), feels damp and humid
> - Calm winds
> - Clear skies
> - Visibility is excellent (10+ miles)
> - Pressure 30.30 inHg (1026 hPa)

## Features

- Decodes temperature, wind (speed, compass direction, gusts), cloud layers, precipitation, fog, visibility and pressure
- Uses familiar units: °F (with °C), mph, miles and inHg
- Accepts 4-letter ICAO codes (`KHIO`, `EGLL`) and 3-letter US codes (`HIO` becomes `KHIO`)
- Shows how old the observation is, the flight category (VFR/IFR) and the raw METAR
- Friendly errors for unknown codes or an unreachable weather service

## Installation

Requires Python 3.9 or newer.

```bash
git clone https://github.com/todsira/metar-reader.git
cd metar-reader

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

```bash
python app.py
```

Open <http://127.0.0.1:5000> and enter an airport code.

You can also link straight to a result: <http://127.0.0.1:5000/?code=KHIO>

> `app.py` runs Flask's development server with debug mode on. For a public deployment, use a production server such as [gunicorn](https://gunicorn.org/) (`gunicorn app:app`) and do not enable debug mode.

## Configuration

Settings are read from environment variables. All are optional.

| Variable         | Default                                      | Description                                            |
|------------------|----------------------------------------------|--------------------------------------------------------|
| `METAR_API_URL`  | `https://aviationweather.gov/api/data/metar` | METAR API endpoint                                     |
| `METAR_TIMEOUT`  | `10`                                         | Seconds to wait for the weather service                |
| `HOST`           | `127.0.0.1`                                  | Interface the dev server binds to (`python app.py` only) |
| `PORT`           | `5000`                                       | Port the dev server listens on (`python app.py` only)  |
| `FLASK_DEBUG`    | `true`                                       | Debug mode for the dev server (`python app.py` only)   |

For example:

```bash
PORT=8080 METAR_TIMEOUT=5 python app.py
```

An invalid value, such as `METAR_TIMEOUT=abc`, stops the app at startup with a clear error.

## Data source

Weather data comes from the [Aviation Weather Center](https://aviationweather.gov/data/api/) API. No API key is required.

## Disclaimer

This app is for general interest only. **Do not use it for flight planning or any safety-critical decision.** Use official aviation weather sources instead.

## Project layout

```
app.py               Flask app and METAR-to-English logic
templates/index.html Page template
requirements.txt     Python dependencies
```

## License

Released under the [MIT License](LICENSE).
