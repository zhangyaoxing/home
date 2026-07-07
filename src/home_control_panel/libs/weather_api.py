import requests
import logging
from home_control_panel.libs.utils import load_config

logger = logging.getLogger(__name__)
config = load_config()
REQUEST_TIMEOUT = (3.05, 15)
                
def api_weather():
    key = config["weatherKey"]
    url = config["weatherApiUrl"].format(key=key)
    try:
        result = requests.get(url, timeout=REQUEST_TIMEOUT)
        code = result.status_code
        json = result.json()
        logger.debug(json)
        if code >= 200 and code < 300:
            return None, json
        else:
            return Exception("Error accessing weather API."), None
    except BaseException as error:
        return error, None
