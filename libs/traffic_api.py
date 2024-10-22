import requests
import logging
from libs.utils import load_config
from datetime import datetime

logger = logging.getLogger(__name__)
config = load_config()

# TODO: Make the request async.
url = config["trainApiUrl"]

# Check whether the call to API is throttled.
# True: Yes (Shouldn't call API)
# False: No (You can call API)
def is_freq_throttled(last_call_time):
    now = datetime.now()
    hour = now.hour
    cfg = [cfg for cfg in config["apiFreqControl"] if hour >= cfg["from"] and hour < cfg["to"]][0]
    interval = cfg["intervalMin"]
    delta = (now - last_call_time).total_seconds() / 60
    return delta < interval

def api_request(body):
    headers = {'Content-Type': 'application/xml'}
    request_xml = "<REQUEST><LOGIN authenticationkey='{key}'/>{body}</REQUEST>".format(key=config["trainKey"], body=body)
    try:
        result = requests.post(url, data=request_xml, headers=headers)
        code = result.status_code
        json = result.json()
        logger.debug(json)
        if code >= 200 and code < 300:
            return None, json
        else:
            return Exception("Error accessing API."), None
    except BaseException as error:
        return error, None

def api_train_stations():
    reqBody = """<QUERY objecttype='TrainStation' schemaversion='1'>
      <FILTER>
        <EQ name='CountryCode' value='SE' />
      </FILTER>
      <INCLUDE>Prognosticated</INCLUDE>
      <INCLUDE>AdvertisedLocationName</INCLUDE>
      <INCLUDE>LocationSignature</INCLUDE>
</QUERY>"""
    return api_request(reqBody)

def api_train_message():
    reqBody = """<QUERY objecttype="TrainStationMessage" schemaversion="1" limit="10">
    <FILTER>
      <AND>
        <EQ name="Deleted" value="false"></EQ>
        <EQ name="LocationCode" value="{code}"></EQ>
        <EQ name="MediaType" value="Monitor"></EQ>
      </AND>
    </FILTER>
    <INCLUDE>StartDateTime</INCLUDE>
    <INCLUDE>EndDateTime</INCLUDE>
    <INCLUDE>FreeText</INCLUDE>
    <INCLUDE>Status</INCLUDE>
    <INCLUDE>ActiveDays</INCLUDE>
  </QUERY>""".format(code=config["myStationCode"])
    return api_request(reqBody)

def api_train_announcement():
    reqBody = """<QUERY objecttype='TrainAnnouncement' 
      orderby='AdvertisedTimeAtLocation' schemaversion='1' limit="20">
      <FILTER>
      <AND>
          <OR>
              <AND>
                  <GT name='AdvertisedTimeAtLocation' 
                              value='$dateadd(-00:05:00)' />
                  <LT name='AdvertisedTimeAtLocation' 
                              value='$dateadd(12:00:00)' />
              </AND>
              <GT name='EstimatedTimeAtLocation' value='$now' />
          </OR>
          <EQ name='LocationSignature' value='{code}' />
          <EQ name='ActivityType' value='Avgang' />
      </AND>
      </FILTER>
      <INCLUDE>InformationOwner</INCLUDE>
      <INCLUDE>AdvertisedTimeAtLocation</INCLUDE>
      <INCLUDE>TrackAtLocation</INCLUDE>
      <INCLUDE>FromLocation</INCLUDE>
      <INCLUDE>ToLocation</INCLUDE>
  </QUERY>""".format(code=config["myStationCode"])
    return api_request(reqBody)