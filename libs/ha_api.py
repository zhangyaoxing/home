import logging
from time import monotonic

import requests

from libs.utils import load_config

logger = logging.getLogger(__name__)
config = load_config()
_cached_at = 0
_cached_data = None


def api_ha():
    global _cached_at, _cached_data
    if (
        _cached_data is not None
        and monotonic() - _cached_at < config["weatherRefreshInterval"]
    ):
        return None, _cached_data

    headers = {
        "Authorization": f'Bearer {config["haKey"]}',
        "Content-Type": "application/json",
    }
    data = {sensor_type: [] for sensor_type in config["sensors"]}
    data["sensors"] = []

    for sensor_type, entities in config["sensors"].items():
        for entity_id in entities:
            try:
                result = requests.get(
                    f'{config["haApiUrl"]}/api/states/{entity_id}',
                    headers=headers,
                    timeout=10,
                )
                state_json = result.json()
                logger.debug(state_json)
                if not 200 <= result.status_code < 300:
                    logger.error(
                        "Failed to get sensor %s: %s %s",
                        entity_id,
                        result.status_code,
                        state_json,
                    )
                    return Exception("Error accessing Home Assistant API."), None

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
            except (requests.RequestException, ValueError) as error:
                logger.error("Exception when accessing %s: %s", entity_id, error)
                return error, None

    _cached_at = monotonic()
    _cached_data = data
    return None, data
