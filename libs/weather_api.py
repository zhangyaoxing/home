import requests
import logging
from libs.utils import *

logger = logging.getLogger(__name__)
config = load_config()
                
def api_weather():
    key = config["weatherKey"]
    url = config["weatherApiUrl"].format(key=key)
    try:
        result = requests.request("GET", url)
        code = result.status_code
        json = result.json()
        logger.debug(json)
        if code >= 200 and code < 300:
            return None, json
        else:
            return Exception("Error accessing weather API."), None
    except BaseException as error:
        return error, None