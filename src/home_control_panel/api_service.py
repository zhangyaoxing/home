#!/usr/bin/env python3
"""API service: fetches all external data and writes results to cache/ as JSON.

Start alongside the TUI app. Each widget watches its cache file for changes.
"""

import hashlib
import logging
import os
import random
import time
from datetime import UTC, datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

os.environ["LOG_FILE"] = "api-service.log"

from home_control_panel.libs.cache import (
    CACHE_DIR,
    read_cache,
    write_cache,
)
from home_control_panel.libs.ha_api import api_ha
from home_control_panel.libs.sl_api import api_bus_departures
from home_control_panel.libs.stock_api import api_stock_quotes
from home_control_panel.libs.traffic_api import (
    api_train_announcement,
    api_train_message,
    api_train_stations,
    is_freq_throttled,
    summarize_notice,
    translate_texts,
)
from home_control_panel.libs.utils import config
from home_control_panel.libs.weather_api import api_weather

logger = logging.getLogger("api_service")

_STATE_FILE = "_api_state.json"
_SUMMARY_VERSION = 5


def _load_state():
    state = read_cache(_STATE_FILE) or {}
    state.setdefault("summaries", {})
    state.setdefault("translations", {})
    state.setdefault("station_names", {})
    state.setdefault("stations_updated", None)
    if state.get("summary_version") != _SUMMARY_VERSION:
        state["summaries"] = {}
        state["translations"] = {}
        state["summary_version"] = _SUMMARY_VERSION
    return state


def _save_state(state):
    slim = {
        "summaries": state.get("summaries", {}),
        "translations": state.get("translations", {}),
        "station_names": state.get("station_names", {}),
        "stations_updated": state.get("stations_updated"),
        "summary_version": state.get("summary_version"),
    }
    write_cache(_STATE_FILE, slim)


def _clear_trigger(name):
    """Delete a trigger file if it exists."""
    path = CACHE_DIR / name
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


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
    state["stations_updated"] = datetime.now(tz=UTC).isoformat()
    logger.info("Stations updated: %d entries", len(stations))


def _fetch_schedule(state, last_train_call):
    if is_freq_throttled(last_train_call):
        return last_train_call
    if not state.get("station_names"):
        _fetch_stations(state)
    error, data = api_train_announcement()
    now = datetime.now(tz=UTC)
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
        # Extract line number from ProductInformation
        products = a.get("ProductInformation", [])
        for item in reversed(products):
            if isinstance(item, str) and item.strip().isdigit():
                a["Line"] = item
                break

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
    if not state.get("station_names"):
        _fetch_stations(state)
    error, data = api_train_message()
    now = datetime.now(tz=UTC)
    if error or not data:
        logger.warning("Failed to fetch train messages: %s", error)
        return last_train_call

    messages = data["RESPONSE"]["RESULT"][0].get("TrainStationMessage", [])
    old_summaries = state["summaries"]
    new_summaries = {}
    current_digests = set()
    for message in messages:
        text = _normalize_message(message.get("FreeText", ""))
        if not text:
            continue
        digest = hashlib.md5(text.encode()).hexdigest()
        current_digests.add(digest)
        if digest not in old_summaries and digest not in new_summaries:
            summary = summarize_notice(text)
            if summary:
                new_summaries[digest] = summary

    # Keep only active messages; merge new translations.
    state["summaries"] = {d: old_summaries[d] for d in current_digests if d in old_summaries}
    state["summaries"].update(new_summaries)

    enriched = []
    for message in messages:
        text = _normalize_message(message.get("FreeText", ""))
        if not text:
            continue
        digest = hashlib.md5(text.encode()).hexdigest()
        enriched.append(
            {
                "digest": digest,
                "raw": message,
                "summary": state["summaries"].get(digest, text),
            }
        )

    write_cache(
        "train_messages.json",
        {
            "timestamp": now.isoformat(),
            "data": {
                "station_name": state["station_names"].get(
                    config["train"]["stationCode"], ""
                ),
                "messages": enriched,
            },
        },
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
        {"timestamp": datetime.now(tz=UTC).isoformat(), "data": data},
    )
    logger.info("Sensors updated: %d entities", len(data["sensors"]))


def _fetch_weather():
    error, data = api_weather()
    if error or not data:
        logger.warning("Failed to fetch weather: %s", error)
        return
    write_cache(
        "weather.json",
        {"timestamp": datetime.now(tz=UTC).isoformat(), "data": data},
    )
    logger.info(
        "Weather updated: %d days, %d hourly details",
        len(data.get("days", [])),
        len(data.get("hourlyDetails", [])),
    )


def _fetch_bus(state):
    error, result = api_bus_departures()
    now = datetime.now(tz=UTC)
    if error or result is None:
        logger.warning("Failed to fetch bus departures: %s", error)
        return

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
            logger.info("Translated %d new bus texts", len(translated))

    for d in departures:
        raw = d.get("deviations", [])
        d["deviations_tr"] = {t: old_translations.get(t, t) for t in raw}

    write_cache(
        "bus_schedule.json",
        {
            "timestamp": now.isoformat(),
            "data": {
                "name": station_name,
                "departures": departures,
            },
        },
    )
    logger.info("Bus schedule updated: %d departures", len(departures))
    return now


def _fetch_stocks():
    error, quotes = api_stock_quotes()
    now = datetime.now(tz=UTC)
    if error:
        logger.warning("Failed to fetch stock quotes: %s", error)
        return
    if quotes is None:
        return
    write_cache(
        "stocks.json",
        {
            "timestamp": now.isoformat(),
            "data": {"quotes": quotes},
        },
    )
    logger.info("Stocks updated: %d quotes", len(quotes))


def main():
    logger.info("API service starting...")

    state = _load_state()

    sensor_interval = config["homeassistant"]["sensorRefreshInterval"]
    weather_interval = config["weather"]["refreshInterval"]
    message_interval = config["train"]["message"]["updateIntervalMin"] * 60
    schedule_interval = config["train"]["apiFreqCheck"]
    bus_interval = config["sl"]["refreshInterval"]
    stock_interval = config["stocks"]["refreshInterval"]
    station_interval = config["train"]["stationUpdateInterval"]

    now = datetime.now(tz=UTC)

    def _jitter(interval):
        return now - timedelta(seconds=interval - random.uniform(0, 5))

    last_sensors = _jitter(sensor_interval)
    last_weather = _jitter(weather_interval)
    last_messages = _jitter(message_interval)
    last_schedule = _jitter(schedule_interval)
    last_bus = _jitter(bus_interval)
    last_stocks = _jitter(stock_interval)
    last_msg_call = datetime.min.replace(tzinfo=UTC)
    last_sched_call = datetime.min.replace(tzinfo=UTC)
    last_stations_check = (
        _jitter(station_interval)
        if state.get("stations_updated") is None
        else datetime.fromisoformat(state["stations_updated"])
    )
    if last_stations_check.tzinfo is None:
        last_stations_check = last_stations_check.replace(tzinfo=UTC)

    min_dt = datetime.min.replace(tzinfo=UTC)

    while True:
        now = datetime.now(tz=UTC)

        if (CACHE_DIR / "_trigger_sensors").exists():
            _clear_trigger("_trigger_sensors")
            last_sensors = min_dt

        if (now - last_sensors).total_seconds() >= sensor_interval:
            _fetch_sensors()
            last_sensors = now

        if (CACHE_DIR / "_trigger_weather").exists():
            _clear_trigger("_trigger_weather")
            last_weather = min_dt

        if (now - last_weather).total_seconds() >= weather_interval:
            _fetch_weather()
            last_weather = now

        if (now - last_stations_check).total_seconds() >= station_interval:
            _fetch_stations(state)
            _save_state(state)
            last_stations_check = now

        if (CACHE_DIR / "_trigger_train_messages").exists():
            _clear_trigger("_trigger_train_messages")
            last_messages = min_dt
            last_msg_call = min_dt

        if (now - last_messages).total_seconds() >= message_interval:
            result = _fetch_messages(state, last_msg_call)
            if result != last_msg_call:
                last_msg_call = result
            last_messages = now
            _save_state(state)

        if (CACHE_DIR / "_trigger_train_schedule").exists():
            _clear_trigger("_trigger_train_schedule")
            last_schedule = min_dt
            last_sched_call = min_dt

        if (now - last_schedule).total_seconds() >= schedule_interval:
            result = _fetch_schedule(state, last_sched_call)
            if result != last_sched_call:
                last_sched_call = result
            last_schedule = now
            _save_state(state)

        if (CACHE_DIR / "_trigger_bus").exists():
            _clear_trigger("_trigger_bus")
            last_bus = min_dt
        if (now - last_bus).total_seconds() >= bus_interval:
            _fetch_bus(state)
            last_bus = now
            _save_state(state)

        if (CACHE_DIR / "_trigger_stocks").exists():
            _clear_trigger("_trigger_stocks")
            last_stocks = min_dt
        if (now - last_stocks).total_seconds() >= stock_interval:
            _fetch_stocks()
            last_stocks = now

        time.sleep(1)


if __name__ == "__main__":
    main()
