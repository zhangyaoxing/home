# Home Control Panel

A text-based (TUI) home dashboard for the Stockholm area. Built with [Textual](https://textual.textualize.io/) to stay lightweight enough for a Raspberry Pi.

## What it shows

| Widget | Data source | What you see |
| :--- | :--- | :--- |
| **Train schedule** | Trafikverket API | Upcoming departures from your station, with deviations translated to English via Google Translate |
| **Train messages** | Trafikverket API | Station-level service notices, summarised to English by DeepSeek LLM |
| **Metro** | SL Transport API v1 | Tunnelbana departures with line colours |
| **Bus** | SL Transport API v1 | Bus departures |
| **Weather** | SMHI open-data API | Current conditions, next-day forecast, and a multi-day temperature/probability chart |
| **Sensors** | Home Assistant | Temperature, humidity, plant moisture, and illuminance readings with warning thresholds |
| **Lights** | Home Assistant | Interactive toggles for lights/switches and scene buttons, grouped by area |

## Architecture

Three processes, coordinated by a watchdog:

```
watchdog  ──┬──  api_service   (polls external APIs → writes JSON to cache/)
            ├──  textual serve  (web-accessible TUI on port 8093)
            └──  app            (local TUI)
```

- **`api_service.py`** — A long-running loop that fetches data from Trafikverket, SL, SMHI, and Home Assistant on per-source intervals, then writes results to `cache/*.json`. TUI widgets poll these files for changes instead of calling APIs directly.
- **`app.py`** — The Textual app. Widgets watch their cache file via `FileWatcher` and re-render when content changes. Supports click-to-refresh (writes trigger files that the api_service picks up immediately).
- **`watchdog`** — Manages all three processes: restarts on crash, pulls git changes, reinstalls dependencies if `pyproject.toml` changed, and restarts everything after a pull.

## Dependencies

Requires Python ≥ 3.11.

```bash
pip install -e .
```

To include the Textual development tools (serve, dev console):

```bash
pip install -e ".[dev]"
```

## Configuration

### Keys (`.env`)

API keys are loaded from a `.env` file at the project root via `python-dotenv`:

| Key | Used by |
| :--- | :--- |
| `trainKey` | Trafikverket API (trains + metro) |
| `haKey` | Home Assistant REST API |
| `dsKey` | DeepSeek API (LLM summarisation of train notices) |
| `gcpKey` | Google Cloud Translation API v2 |

SMHI is free open data and needs no key.

### Settings (`src/home_control_panel/config.json`)

Top-level:

- `title` — Window title shown in the TUI.
- `serveHost` — Public URL for `textual serve`.
- `timezone` — e.g. `Europe/Stockholm`.
- `warningInterval` — Seconds between warning-panel refreshes.
- `tuiRefreshInterval` — Base polling interval for TUI widgets (seconds).

`train`:

- `apiUrl` — Trafikverket endpoint.
- `stationCode` — Your station's `LocationSignature` (find codes in `example_response/TrainStations.json`).
- `apiFreqCheck` — Seconds between checking whether the API should be called.
- `apiFreqControl` — Time-of-day frequency schedule to respect the monthly API quota:
  | Time | Interval (min) | Calls |
  | :---: | :---: | :---: |
  | 00:00–07:00 | 30 | 14 |
  | 07:00–09:00 | 2 | 60 |
  | 09:00–17:00 | 10 | 48 |
  | 17:00–19:00 | 2 | 60 |
  | 19:00–24:00 | 10 | 30 |
  | **Total** | | **212/day** |
- `stationUpdateInterval` — Station list refresh interval (seconds; default 86400 = daily).
- `message.updateIntervalMin` — How often train messages are fetched.
- `message.scrollSpeed` — Scroll speed for long messages (seconds per character shift).
- `message.margin` — Virtual padding characters at start/end so scrolling pauses.

`sl`:

- `apiUrl` — SL Transport API base URL.
- `metroSiteId` / `busSiteId` — SL site IDs for metro and bus stops.
- `refreshInterval` — Seconds between metro/bus fetches.
- `timeWindow` — Look-ahead window in minutes.
- `metroLineColors` — Map of line number → hex colour for display.

`weather`:

- `apiUrl` — SMHI forecast URL template (`{lon}` / `{lat}` placeholders).
- `lat` / `lon` — Coordinates for the forecast point.
- `refreshInterval` — Seconds between weather fetches.
- `detailsInterval` — Seconds each day is shown in the details chart before advancing.
- `probabilityWarningThreshold` — Three-level thresholds `[low, mid, high]` for precipitation-probability warnings.

`homeassistant`:

- `apiUrl` — Home Assistant base URL.
- `sensorRefreshInterval` — Seconds between sensor fetches.
- `areaRefreshInterval` — Seconds between area/entity list refreshes.
- `lightsRefreshInterval` — Seconds between light/switch state refreshes.
- `humidityWarningThreshold` — Three-level thresholds for room humidity.
- `plantHumWarningThreshold` — Three-level thresholds for plant moisture.
- `sensors` — Lists of Home Assistant entity IDs grouped by type (`temp`, `hum`, `plant_hum`, `illu`).
- `areas` — Map of area name → list of light/switch entity IDs, displayed as side-by-side columns.
- `scenes` — List of scene entity IDs rendered as buttons.

## Run

### Production (watchdog)

Starts serve, api_service, and the local app, then monitors for crashes and git updates:

```bash
./watchdog
```

### Development

Run the API service and TUI app separately for live reload:

```bash
# Terminal 1 — API service
python -m home_control_panel.api_service

# Terminal 2 — TUI app
python -m home_control_panel.app
```

Or serve the web version:

```bash
textual serve -h 0.0.0.0 --port 8093 src/home_control_panel/app.py
```

### Keyboard shortcuts

| Key | Action |
| :---: | :--- |
| `d` | Toggle dark / light mode |
| `r` | Refresh all widgets |
| `q` | Quit |
