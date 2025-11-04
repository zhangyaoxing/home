import requests
import logging
from libs.utils import *

logger = logging.getLogger(__name__)
config = load_config()
                
def api_ha():
    key = config["haKey"]
    base_url = config["haApiUrl"]
    sensors = config["sensors"]
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    data = {
        "temp": [],
        "hum": [],
        "illu": []
    }
    for entity in sensors["temp"]:
        try:
            url = f"{base_url}/api/states/{entity}"
            result = requests.request("GET", url, headers=headers, timeout=10)
            code = result.status_code
            json = result.json()
            logger.debug(json)
            if code >= 200 and code < 300:
                data["temp"].append(f'{json["state"]}{json["attributes"]["unit_of_measurement"]}')
            else:
                logger.error(f"Failed to get temperature from {entity}: {code} {json}")
                return Exception("Error accessing Homeassistant API."), None
        except BaseException as error:
            logger.error(f"Exception when accessing {entity}: {error}")
            return error, None
    for entity in sensors["hum"]:
        try:
            url = f"{base_url}/api/states/{entity}"
            result = requests.request("GET", url, headers=headers, timeout=10)
            code = result.status_code
            json = result.json()
            logger.debug(json)
            if code >= 200 and code < 300:
                data["hum"].append(f'{json["state"]}{json["attributes"]["unit_of_measurement"]}')
            else:
                logger.error(f"Failed to get humidity from {entity}: {code} {json}")
                return Exception("Error accessing Homeassistant API."), None
        except BaseException as error:
            logger.error(f"Exception when accessing {entity}: {error}")
            return error, None
    for entity in sensors["illu"]:
        try:
            url = f"{base_url}/api/states/{entity}"
            result = requests.request("GET", url, headers=headers)
            code = result.status_code
            json = result.json()
            logger.debug(json)
            if code >= 200 and code < 300:
                data["illu"].append(f'{json["state"]}{json["attributes"]["unit_of_measurement"]}')
            else:
                logger.error(f"Failed to get illuminance from {entity}: {code} {json}")
                return Exception("Error accessing Homeassistant API."), None
        except BaseException as error:
            logger.error(f"Exception when accessing {entity}: {error}")
            return error, None
    return None, data