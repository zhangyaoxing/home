import logging

import requests

from home_control_panel.libs.utils import load_config

logger = logging.getLogger(__name__)
config = load_config()
REQUEST_TIMEOUT = (3.05, 15)


def api_bus_departures():
    """Fetch real-time bus departures from SL Transport API."""
    key = config.get("slKey")
    if not key:
        return Exception("slKey not configured"), None

    return _fetch_sl_departures(
        config["sl"]["busSiteId"],
        key,
        "BUS",
    )


def _fetch_sl_departures(site_id, key, transport):
    url = f"{config['sl']['apiUrl']}/sites/{site_id}/departures"
    params = {"transport": transport}
    try:
        result = requests.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {key}"},
            timeout=REQUEST_TIMEOUT,
        )
        if result.status_code < 200 or result.status_code >= 300:
            logger.error("SL API returned %s: %s", result.status_code, result.text[:200])
            return Exception(f"SL API error {result.status_code}"), None

        data = result.json()
        departures = data.get("departures", [])
        station_name = ""
        if departures:
            station_name = departures[0].get("stop_area", {}).get("name", "")
        filtered = []
        for d in departures:
            line = d.get("line", {})
            deviation_texts = [dev.get("message", "") for dev in d.get("deviations", [])]
            filtered.append({
                "line": line.get("designation", ""),
                "destination": d.get("destination", ""),
                "platform": d.get("stop_point", {}).get("designation", ""),
                "display": d.get("display", ""),
                "scheduled": d.get("scheduled", ""),
                "expected": d.get("expected", ""),
                "state": d.get("state", ""),
                "deviations": [m for m in deviation_texts if m],
            })
        return None, {"name": station_name, "departures": filtered}
    except (requests.RequestException, ValueError) as error:
        logger.error("SL API exception: %s", error)
        return error, None


def api_metro_departures():
    """Fetch real-time metro departures from SL Transport API.

    Returns (error, departures_list) where departures_list contains
    dicts with keys: line, destination, display, scheduled, expected,
    deviations, transport_mode.
    """
    key = config.get("slKey")
    if not key:
        return Exception("slKey not configured"), None

    return _fetch_sl_departures(
        config["sl"]["metroSiteId"],
        key,
        "METRO",
    )
