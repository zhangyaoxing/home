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
        and monotonic() - _cached_at < config["homeassistant"]["sensorRefreshInterval"]
    ):
        return None, _cached_data

    headers = {
        "Authorization": f'Bearer {config["haKey"]}',
        "Content-Type": "application/json",
    }
    data = {sensor_type: [] for sensor_type in config["homeassistant"]["sensors"]}
    data["sensors"] = []

    try:
        result = requests.get(
            f'{config["homeassistant"]["apiUrl"]}/api/states',
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
    for sensor_type, entities in config["homeassistant"]["sensors"].items():
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


def api_ha_lights():
    """Fetch light, switch, and scene states for configured areas from Home Assistant.

    Reads area→entity mappings and scene list from config.json and looks up
    current state for each entity via /api/states.
    """
    areas_config = config["homeassistant"].get("areas", {})
    scenes_config = config["homeassistant"].get("scenes", [])
    if not areas_config and not scenes_config:
        return None, {"rooms": [], "scenes": []}

    headers = {
        "Authorization": f'Bearer {config["haKey"]}',
        "Content-Type": "application/json",
    }

    try:
        result = requests.get(
            f'{config["homeassistant"]["apiUrl"]}/api/states',
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        if not 200 <= result.status_code < 300:
            logger.error(
                "Failed to get HA states for lights: %s %s",
                result.status_code,
                result.text,
            )
            return Exception("Error accessing Home Assistant API."), None
        states_json = result.json()
    except (requests.RequestException, ValueError) as error:
        logger.error("Exception when accessing HA lights: %s", error)
        return error, None

    states_by_id = {
        state["entity_id"]: state
        for state in states_json
        if "entity_id" in state
    }

    rooms = []
    for area_name, entity_ids in areas_config.items():
        lights = []
        for entity_id in entity_ids:
            state_json = states_by_id.get(entity_id)
            if state_json is None:
                logger.warning("HA entity missing: %s", entity_id)
                continue
            lights.append(
                {
                    "entity_id": entity_id,
                    "name": state_json["attributes"].get(
                        "friendly_name", entity_id
                    ),
                    "state": state_json["state"],
                }
            )
        if lights:
            rooms.append({"area": area_name, "lights": lights})

    scenes = []
    for entity_id in scenes_config:
        state_json = states_by_id.get(entity_id)
        name = entity_id
        if state_json:
            name = state_json["attributes"].get("friendly_name", entity_id)
        scenes.append({"entity_id": entity_id, "name": name})

    return None, {"rooms": rooms, "scenes": scenes}


def api_ha_toggle_light(entity_id):
    """Toggle a single light or switch entity via Home Assistant."""
    domain = entity_id.split(".")[0] if "." in entity_id else "light"
    headers = {
        "Authorization": f'Bearer {config["haKey"]}',
        "Content-Type": "application/json",
    }
    try:
        result = requests.post(
            f'{config["homeassistant"]["apiUrl"]}/api/services/{domain}/toggle',
            json={"entity_id": entity_id},
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        if not 200 <= result.status_code < 300:
            logger.error(
                "Failed to toggle %s: %s %s",
                entity_id,
                result.status_code,
                result.text,
            )
            return Exception("Error toggling light.")
        return None
    except requests.RequestException as error:
        logger.error("Exception when toggling %s: %s", entity_id, error)
        return error


def api_ha_activate_scene(entity_id):
    """Activate a scene via Home Assistant."""
    headers = {
        "Authorization": f'Bearer {config["haKey"]}',
        "Content-Type": "application/json",
    }
    try:
        result = requests.post(
            f'{config["homeassistant"]["apiUrl"]}/api/services/scene/turn_on',
            json={"entity_id": entity_id},
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        if not 200 <= result.status_code < 300:
            logger.error(
                "Failed to activate scene %s: %s %s",
                entity_id,
                result.status_code,
                result.text,
            )
            return Exception("Error activating scene.")
        return None
    except requests.RequestException as error:
        logger.error(
            "Exception when activating scene %s: %s", entity_id, error
        )
        return error
