import logging
from time import monotonic

import requests

from home_control_panel.libs.utils import load_config

logger = logging.getLogger(__name__)
config = load_config()
REQUEST_TIMEOUT = (3.05, 15)
_cached_at = 0
_cached_data = None


def api_ha():
    global _cached_at, _cached_data
    if (
        _cached_data is not None
        and monotonic() - _cached_at < config["sensorRefreshInterval"]
    ):
        return None, _cached_data

    headers = {
        "Authorization": f'Bearer {config["haKey"]}',
        "Content-Type": "application/json",
    }
    data = {sensor_type: [] for sensor_type in config["sensors"]}
    data["sensors"] = []

    try:
        result = requests.get(
            f'{config["haApiUrl"]}/api/states',
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        states_json = result.json()
        logger.debug(states_json)
        if not 200 <= result.status_code < 300:
            logger.error(
                "Failed to get Home Assistant states: %s %s",
                result.status_code,
                states_json,
            )
            return Exception("Error accessing Home Assistant API."), None
    except (requests.RequestException, ValueError) as error:
        logger.error("Exception when accessing Home Assistant: %s", error)
        return error, None

    states_by_id = {
        state["entity_id"]: state
        for state in states_json
        if "entity_id" in state
    }
    for sensor_type, entities in config["sensors"].items():
        for entity_id in entities:
            state_json = states_by_id.get(entity_id)
            if state_json is None:
                logger.warning("Home Assistant sensor is missing: %s", entity_id)
                continue

            attributes = state_json.get("attributes", {})
            state = state_json.get("state", "")
            unit = attributes.get("unit_of_measurement", "")
            data[sensor_type].append(f"{state}{unit}")
            data["sensors"].append(
                {
                    "entity_id": entity_id,
                    "name": attributes.get("friendly_name", entity_id),
                    "state": state,
                    "unit": unit,
                }
            )

    _cached_at = monotonic()
    _cached_data = data
    return None, data
