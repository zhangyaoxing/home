#!/usr/bin/env python3
"""API service: fetches all external data and writes results to cache/ as JSON.

Start alongside the TUI app. Each widget watches its cache file for changes.
"""

import hashlib
import logging
import time
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()  # noqa: E402

from home_control_panel.libs.cache import read_cache, write_cache  # noqa: E402
from home_control_panel.libs.ha_api import api_ha  # noqa: E402
from home_control_panel.libs.traffic_api import (  # noqa: E402
    api_train_announcement,
    api_train_message,
    api_train_stations,
    is_freq_throttled,
    summarize_notice,
    translate_texts,
)
from home_control_panel.libs.sl_api import api_metro_departures  # noqa: E402
from home_control_panel.libs.utils import config  # noqa: E402
from home_control_panel.libs.weather_api import api_weather  # noqa: E402

logger = logging.getLogger("api_service")

_STATE_FILE = "_api_state.json"


def _load_state():
    state = read_cache(_STATE_FILE) or {}
    state.setdefault("seen_digests", [])
    state.setdefault("summaries", {})
    state.setdefault("translations", {})
    state.setdefault("station_names", {})
    state.setdefault("stations_updated", None)
    return state


def _save_state(state):
    slim = {
        "seen_digests": state.get("seen_digests", []),
        "summaries": state.get("summaries", {}),
        "translations": state.get("translations", {}),
        "station_names": state.get("station_names", {}),
        "stations_updated": state.get("stations_updated"),
    }
    write_cache(_STATE_FILE, slim)


def _normalize_message(text):
    return " ".join(text.split())


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _fetch_stations(state):
    error, data = api_train_stations()
    if error or not data:
        logger.warning("Failed to fetch train stations: %s", error)
        return
    stations = {}
    for s in data["RESPONSE"]["RESULT"][0]["TrainStation"]:
        stations[s["LocationSignature"]] = s["AdvertisedLocationName"]
    state["station_names"] = stations
    state["stations_updated"] = datetime.now().isoformat()
    logger.info("Stations updated: %d entries", len(stations))


def _fetch_schedule(state, last_train_call):
    if is_freq_throttled(last_train_call):
        return last_train_call
    error, data = api_train_announcement()
    now = datetime.now()
    if error or not data:
        logger.warning("Failed to fetch train schedule: %s", error)
        return last_train_call

    announcements = data["RESPONSE"]["RESULT"][0].get("TrainAnnouncement", [])
    old_translations = state["translations"]

    # Collect all untranslated Deviation and OtherInformation texts.
    new_texts = []
    for a in announcements:
        for field in ("Deviation", "OtherInformation"):
            new_texts.extend(_as_list(a.get(field)))

    new_texts = [_normalize_message(t) for t in new_texts if t]
    untranslated = [t for t in new_texts if t not in old_translations]

    if untranslated:
        translated = translate_texts(untranslated)
        if translated is not None:
            old_translations.update(translated)
            logger.info("Translated %d new texts", len(translated))

    # Attach translation maps to each announcement.
    for a in announcements:
        for field in ("Deviation", "OtherInformation"):
            raw = _as_list(a.get(field))
            raw = [_normalize_message(t) for t in raw if t]
            a[f"{field}_tr"] = {t: old_translations.get(t, t) for t in raw}

    write_cache(
        "train_schedule.json",
        {
            "timestamp": now.isoformat(),
            "data": {
                "announcements": announcements,
                "station_names": state.get("station_names", {}),
            },
        },
    )
    logger.info(
        "Train schedule updated: %d announcements",
        len(announcements),
    )
    return now


def _fetch_messages(state, last_train_call):
    if is_freq_throttled(last_train_call):
        return last_train_call
    error, data = api_train_message()
    now = datetime.now()
    if error or not data:
        logger.warning("Failed to fetch train messages: %s", error)
        return last_train_call

    messages = data["RESPONSE"]["RESULT"][0].get("TrainStationMessage", [])
    old_summaries = state["summaries"]
    current_digests = set()
    new_summaries = {}
    for message in messages:
        text = _normalize_message(message.get("FreeText", ""))
        if not text:
            continue
        digest = hashlib.md5(text.encode()).hexdigest()
        current_digests.add(digest)
        if digest not in old_summaries:
            new_summaries[digest] = summarize_notice(text)

    state["seen_digests"] = list(current_digests)
    # Drop summaries for messages no longer in the API response.
    state["summaries"] = {d: s for d, s in old_summaries.items() if d in current_digests}
    state["summaries"].update(new_summaries)

    enriched = []
    for message in messages:
        text = _normalize_message(message.get("FreeText", ""))
        digest = hashlib.md5(text.encode()).hexdigest() if text else ""
        enriched.append(
            {
                "raw": message,
                "summary": state["summaries"].get(digest, text),
            }
        )

    write_cache(
        "train_messages.json",
        {"timestamp": now.isoformat(), "data": {"messages": enriched}},
    )
    logger.info(
        "Train messages updated: %d total, %d new summaries",
        len(enriched),
        len(new_summaries),
    )
    return now


def _fetch_sensors():
    error, data = api_ha()
    if error or not data:
        logger.warning("Failed to fetch HA sensors: %s", error)
        return
    write_cache(
        "sensors.json",
        {"timestamp": datetime.now().isoformat(), "data": data},
    )
    logger.info("Sensors updated: %d entities", len(data["sensors"]))


def _fetch_weather():
    error, data = api_weather()
    if error or not data:
        logger.warning("Failed to fetch weather: %s", error)
        return
    write_cache(
        "weather.json",
        {"timestamp": datetime.now().isoformat(), "data": data},
    )
    logger.info(
        "Weather updated: %d days, %d hourly details",
        len(data.get("days", [])),
        len(data.get("hourlyDetails", [])),
    )


def _fetch_metro(state, last_call):
    if is_freq_throttled(last_call):
        return last_call
    error, result = api_metro_departures()
    now = datetime.now()
    if error or result is None:
        logger.warning("Failed to fetch metro departures: %s", error)
        return last_call

    departures = result.get("departures", [])
    station_name = result.get("name", "")
    old_translations = state["translations"]
    new_texts = []
    for d in departures:
        new_texts.extend(d.get("deviations", []))

    untranslated = [t for t in new_texts if t not in old_translations]
    if untranslated:
        translated = translate_texts(untranslated)
        if translated is not None:
            old_translations.update(translated)
            logger.info("Translated %d new metro texts", len(translated))

    for d in departures:
        raw = d.get("deviations", [])
        d["deviations_tr"] = {t: old_translations.get(t, t) for t in raw}

    write_cache(
        "metro_schedule.json",
        {
            "timestamp": now.isoformat(),
            "data": {
                "name": station_name,
                "departures": departures,
            },
        },
    )
    logger.info("Metro schedule updated: %d departures", len(departures))
    return now


def main():
    logger.info("API service starting...")

    state = _load_state()
    last_sensors = datetime.min
    last_weather = datetime.min
    last_messages = datetime.min
    last_schedule = datetime.min
    last_metro = datetime.min
    last_msg_call = datetime.min
    last_sched_call = datetime.min
    last_metro_call = datetime.min
    last_stations_check = (
        datetime.min
        if state.get("stations_updated") is None
        else datetime.fromisoformat(state["stations_updated"])
    )

    sensor_interval = config["homeassistant"]["refreshInterval"]
    weather_interval = config["weather"]["refreshInterval"]
    message_interval = config["train"]["message"]["updateIntervalMin"] * 60
    schedule_interval = config["train"]["apiFreqCheck"]
    metro_interval = config["train"]["apiFreqCheck"]
    station_interval = config["train"]["stationUpdateInterval"]

    while True:
        now = datetime.now()

        if (now - last_sensors).total_seconds() >= sensor_interval:
            _fetch_sensors()
            last_sensors = now

        if (now - last_weather).total_seconds() >= weather_interval:
            _fetch_weather()
            last_weather = now

        if (now - last_stations_check).total_seconds() >= station_interval:
            _fetch_stations(state)
            _save_state(state)
            last_stations_check = now

        if (now - last_messages).total_seconds() >= message_interval:
            result = _fetch_messages(state, last_msg_call)
            if result != last_msg_call:
                last_msg_call = result
            last_messages = now
            _save_state(state)

        if (now - last_schedule).total_seconds() >= schedule_interval:
            result = _fetch_schedule(state, last_sched_call)
            if result != last_sched_call:
                last_sched_call = result
            last_schedule = now
            _save_state(state)

        if (now - last_metro).total_seconds() >= metro_interval:
            result = _fetch_metro(state, last_metro_call)
            if result != last_metro_call:
                last_metro_call = result
            last_metro = now
            _save_state(state)

        time.sleep(1)


if __name__ == "__main__":
    main()
