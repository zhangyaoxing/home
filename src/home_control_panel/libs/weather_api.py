import logging
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from home_control_panel.libs.utils import load_config

logger = logging.getLogger(__name__)
config = load_config()
REQUEST_TIMEOUT = (3.05, 15)

SMHI_URL = (
    "https://opendata-download-metfcst.smhi.se/api/category/snow1g/version/1"
    "/geotype/point/lon/{lon}/lat/{lat}/data.json"
)

WSYMB2_MAP = {
    1: "Clear",
    2: "Nearly clear",
    3: "Variable cloudiness",
    4: "Halfclear",
    5: "Cloudy",
    6: "Overcast",
    7: "Fog",
    8: "Light rain showers",
    9: "Moderate rain showers",
    10: "Heavy rain showers",
    11: "Thunderstorm",
    12: "Light sleet showers",
    13: "Moderate sleet showers",
    14: "Heavy sleet showers",
    15: "Light snow showers",
    16: "Moderate snow showers",
    17: "Heavy snow showers",
    18: "Light rain",
    19: "Moderate rain",
    20: "Heavy rain",
    21: "Thunder",
    22: "Light sleet",
    23: "Moderate sleet",
    24: "Heavy sleet",
    25: "Light snowfall",
    26: "Moderate snowfall",
    27: "Heavy snowfall",
}

WSYMB2_ICON = {
    1: "\u2600\ufe0f", 2: "\U0001F324", 3: "\u26c5\ufe0f",
    4: "\U0001F325", 5: "\u2601\ufe0f", 6: "\u2601\ufe0f",
    7: "\U0001F32B",
    8: "\U0001F327", 9: "\U0001F327", 10: "\U0001F327",
    11: "\U0001F329",
    12: "\U0001F328", 13: "\U0001F328", 14: "\U0001F328",
    15: "\U0001F328", 16: "\U0001F328", 17: "\U0001F328",
    18: "\U0001F327", 19: "\U0001F327", 20: "\U0001F327",
    21: "\U0001F329",
    22: "\U0001F328", 23: "\U0001F328", 24: "\U0001F328",
    25: "\u2744\ufe0f", 26: "\u2744\ufe0f", 27: "\u2744\ufe0f",
}


def _group_by_day(time_series):
    days = defaultdict(list)
    tz = ZoneInfo(config["timezone"])
    for entry in time_series:
        dt = datetime.fromisoformat(entry["time"]).astimezone(tz)
        day_key = dt.strftime("%Y-%m-%d")
        days[day_key].append(entry)
    return days


def _aggregate_day(date, entries):
    temps = []
    humidities = []
    windspeeds = []
    winddirs = []
    gusts = []
    clouds = []
    symbols = []
    visibilities = []
    precip_probs = []
    frozen_probs = []
    thunder_probs = []
    snow = 0.0

    for entry in entries:
        d = entry["data"]
        t = d.get("air_temperature")
        ws = d.get("wind_speed")
        wd = d.get("wind_from_direction")
        gust = d.get("wind_speed_of_gust")
        r = d.get("relative_humidity")
        tcc = d.get("cloud_area_fraction")
        vis = d.get("visibility_in_air")
        wsymb = d.get("symbol_code")
        pmean = d.get("precipitation_amount_mean")
        pfrozen = d.get("precipitation_frozen_part", 0)
        precip = d.get("probability_of_precipitation")
        frozen = d.get("probability_of_frozen_precipitation")
        thunder = d.get("thunderstorm_probability")

        if t is not None:
            temps.append(t)
        if r is not None:
            humidities.append(r)
        if ws is not None:
            windspeeds.append(ws)
        if wd is not None:
            winddirs.append(wd)
        if gust is not None:
            gusts.append(gust)
        if tcc is not None:
            clouds.append(tcc)
        if vis is not None:
            visibilities.append(vis)
        if precip is not None:
            precip_probs.append(precip)
        if frozen is not None:
            frozen_probs.append(frozen)
        if thunder is not None:
            thunder_probs.append(thunder)
        if wsymb is not None:
            symbols.append(int(wsymb))

        if pmean is not None and pmean > 0 and pfrozen is not None and pfrozen > 0:
            snow += pmean

    if not temps:
        return None

    ws_avg = sum(windspeeds) / len(windspeeds) if windspeeds else 0
    wd_avg = sum(winddirs) / len(winddirs) if winddirs else 0
    gust_max = max(gusts) if gusts else 0

    mps_to_kmh = 3.6

    return {
        "date": date,
        "temp": round(sum(temps) / len(temps), 1),
        "tempmin": round(min(temps), 1),
        "tempmax": round(max(temps), 1),
        "feelslike": 0,
        "humidity": round(sum(humidities) / len(humidities)) if humidities else 0,
        "windspeed": round(ws_avg * mps_to_kmh, 1),
        "windgust": round(gust_max * mps_to_kmh, 1),
        "winddir": round(wd_avg),
        "cloudcover": round(sum(clouds) / len(clouds) * 12.5) if clouds else 0,
        "visibility": round(sum(visibilities) / len(visibilities), 1) if visibilities else 0,
        "precip_probability": max(precip_probs) if precip_probs else 0,
        "frozen_probability": max(frozen_probs) if frozen_probs else 0,
        "thunderstorm_probability": max(thunder_probs) if thunder_probs else 0,
        "snow": snow,
        "snowdepth": 0,
        "uvindex": 0,
        "sunrise": "—",
        "sunset": "—",
        "conditions": _dominant_symbol(symbols),
    }


def _build_hourly(entries):
    hours = []
    datetimes = []
    temps = []
    precip = []
    frozen = []
    thunder = []
    hums = []
    for entry in entries:
        d = entry["data"]
        dt = datetime.fromisoformat(entry["time"]).astimezone(ZoneInfo(config["timezone"]))
        hours.append(dt.strftime("%H:%M"))
        datetimes.append(entry["time"])
        t = d.get("air_temperature")
        temps.append(t if t is not None else 0)
        p = d.get("probability_of_precipitation", 0) or 0
        precip.append(p)
        f = d.get("probability_of_frozen_precipitation", 0) or 0
        frozen.append(f)
        th = d.get("thunderstorm_probability", 0) or 0
        thunder.append(th)
        h = d.get("relative_humidity")
        hums.append(h if h is not None else 0)
    return {
        "hours": hours,
        "datetimes": datetimes,
        "temp": temps,
        "precip_probability": precip,
        "frozen_probability": frozen,
        "thunderstorm_probability": thunder,
        "humidity": hums,
    }


def _dominant_symbol(symbols):
    if not symbols:
        return "—"
    counts = defaultdict(int)
    for s in symbols:
        counts[s] += 1
    code = max(counts, key=counts.get)
    return WSYMB2_ICON.get(code, "—")


def _build_current(entry):
    d = entry["data"]
    t = d.get("air_temperature") or 0
    ws = d.get("wind_speed") or 0
    gust = d.get("wind_speed_of_gust") or 0
    wd = d.get("wind_from_direction") or 0
    r = d.get("relative_humidity") or 0
    tcc = d.get("cloud_area_fraction") or 0
    vis = d.get("visibility_in_air") or 0
    wsymb = d.get("symbol_code")
    precip = d.get("probability_of_precipitation") or 0
    frozen = d.get("probability_of_frozen_precipitation") or 0
    thunder = d.get("thunderstorm_probability") or 0

    mps_to_kmh = 3.6
    return {
        "datetime": entry["time"],
        "conditions": WSYMB2_ICON.get(int(wsymb), "—") if wsymb else "—",
        "temp": t,
        "feelslike": 0,
        "humidity": r,
        "windspeed": round(ws * mps_to_kmh, 1),
        "windgust": round(gust * mps_to_kmh, 1),
        "winddir": wd,
        "cloudcover": round(tcc * 12.5),
        "visibility": round(vis, 1),
        "precip_probability": precip,
        "frozen_probability": frozen,
        "thunderstorm_probability": thunder,
        "uvindex": 0,
        "sunrise": "—",
        "sunset": "—",
    }


def api_weather():
    url = SMHI_URL.format(lon=config["weatherLon"], lat=config["weatherLat"])
    try:
        result = requests.get(url, timeout=REQUEST_TIMEOUT)
        if result.status_code < 200 or result.status_code >= 300:
            logger.error("SMHI API returned %s", result.status_code)
            return Exception(f"SMHI API status {result.status_code}"), None
        raw = result.json()
        logger.debug("SMHI response: %s", str(raw)[:500])
    except (requests.RequestException, ValueError) as error:
        logger.error("SMHI API error: %s", error)
        return error, None

    time_series = raw.get("timeSeries", [])
    if not time_series:
        return Exception("SMHI returned empty timeSeries"), None

    current = _build_current(time_series[0])
    days_by_key = _group_by_day(time_series)
    days = []
    day_keys = sorted(days_by_key.keys())
    tomorrow_hourly = None
    hourly_details = []
    for i, day_key in enumerate(day_keys):
        day_data = _aggregate_day(day_key, days_by_key[day_key])
        if day_data:
            days.append(day_data)
            hourly_details.append({
                "date": day_key,
                **_build_hourly(days_by_key[day_key]),
            })
        if i == 1:
            tomorrow_hourly = _build_hourly(days_by_key[day_key])

    return None, {
        "currentConditions": current,
        "days": days,
        "tomorrowHourly": tomorrow_hourly,
        "hourlyDetails": hourly_details,
    }
