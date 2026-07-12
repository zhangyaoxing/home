import logging

import requests

from home_control_panel.libs.utils import load_config

logger = logging.getLogger(__name__)
config = load_config()
REQUEST_TIMEOUT = (3.05, 15)


def api_metro_departures():
    """Fetch real-time metro departures from SL Transport API.

    Returns (error, departures_list) where departures_list contains
    dicts with keys: line, destination, display, scheduled, expected,
    deviations, transport_mode.
    """
    key = config.get("slKey")
    if not key:
        return Exception("slKey not configured"), None

    url = f"{config['sl']['apiUrl']}/sites/{config['sl']['siteId']}/departures"
    params = {"timeWindow": config["sl"].get("timeWindow", 120), "transport": "METRO"}
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
        # Extract station name from first departure's stop_area
        station_name = ""
        if departures:
            station_name = departures[0].get("stop_area", {}).get("name", "")
        # Simplify structure
        filtered = []
        for d in departures:
            line = d.get("line", {})
            deviation_texts = [dev.get("message", "") for dev in d.get("deviations", [])]
            filtered.append({
                "line": line.get("designation", ""),
                "destination": d.get("destination", ""),
                "display": d.get("display", ""),
                "scheduled": d.get("scheduled", ""),
                "expected": d.get("expected", ""),
                "state": d.get("state", ""),
                "deviations": [m for m in deviation_texts if m],
                "transport_mode": line.get("transport_mode", ""),
                "group_of_lines": line.get("group_of_lines", ""),
            })
        return None, {"name": station_name, "departures": filtered}
    except (requests.RequestException, ValueError) as error:
        logger.error("SL API exception: %s", error)
        return error, None
