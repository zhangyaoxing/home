import logging
from datetime import datetime

import pytz
from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Rule, Static

from home_control_panel.common_widgets import ScrollingLabel
from home_control_panel.libs.cache import (
    CacheChanged,
    cache_mtime,
    format_cache_time,
    read_cache,
)
from home_control_panel.libs.utils import config

logger = logging.getLogger(__name__)


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _normalize_message(message):
    return " ".join(str(message).split())


class TrainStationMessage(Static):
    CACHE_FILE = "train_messages.json"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache_mtime = 0

    def compose(self) -> ComposeResult:
        yield Static()

    def _check_cache(self):
        mtime = cache_mtime(self.CACHE_FILE)
        if mtime <= self._cache_mtime:
            return
        self._cache_mtime = mtime
        logger.info("Reloading station messages from cache")

        cached = read_cache(self.CACHE_FILE)
        if cached is None:
            self.set_loading(False)
            return

        messages = cached["data"]["messages"]
        station_name = cached["data"].get("station_name", "")
        messages = sorted(
            messages,
            key=lambda m: m["raw"].get("Status") != "Lag",
        )

        self.remove_children()
        for entry in messages:
            message = entry["raw"]
            display_text = entry["summary"]
            status_class = "lag" if message.get("Status") == "Lag" else "normal"
            self.mount(
                ScrollingLabel(
                    display_text,
                    classes=status_class,
                )
            )
            self.mount(Rule())

        self.set_loading(False)
        self.border_subtitle = f"{station_name}  [dim]Updated {format_cache_time(cached)}[/]"

    def on_mount(self):
        self.border_title = "Station Notices"
        self.set_loading(True)
        self._check_cache()
        self.set_interval(config["tuiRefreshInterval"], self._check_cache)

    def refresh_message(self):
        self._cache_mtime = 0
        self._check_cache()

    def on_cache_changed(self, event: CacheChanged):
        if event.cache_name == self.CACHE_FILE:
            self.refresh_message()


class ScheduleLine(Horizontal):
    def __init__(self, schedule, stations):
        super().__init__(classes="schedule-line")
        self.schedule = schedule
        self.stations = stations

    def compose(self) -> ComposeResult:
        yield Static(classes="schedule-route")
        yield Static(classes="schedule-track")
        yield Static(classes="schedule-time")

    def refresh_data(self):
        row = self.schedule
        advertised_time = datetime.fromisoformat(row["AdvertisedTimeAtLocation"])
        now = datetime.now(tz=pytz.UTC)
        track = row.get("TrackAtLocation", "")
        to_station = "/".join(
            f"[bold][green]{self.stations.get(location, location)}[/green][/bold]"
            for location in row.get("ToLocation", [])
        )
        route = f"→ {to_station}"
        line_no = row.get("Line", "")
        if line_no:
            route = f"{line_no}  {route}"
        delta = (advertised_time - now).total_seconds()
        departure = f"{int(delta / 60)} min"

        self.query_one(".schedule-route", Static).update(route)
        self.query_one(".schedule-track", Static).update(track)
        self.query_one(".schedule-time", Static).update(departure)

    def on_mount(self):
        self.refresh_data()


class ScheduleEntry(Static):
    def __init__(self, schedule, stations):
        super().__init__(classes="schedule-entry")
        self.schedule = schedule
        self.stations = stations

    def compose(self) -> ComposeResult:
        yield ScheduleLine(self.schedule, self.stations)

        for field, style in (
            ("Deviation", "bold yellow"),
            ("OtherInformation", "gray"),
        ):
            tr_map = self.schedule.get(f"{field}_tr", {})
            messages = []
            for raw_msg in _as_list(self.schedule.get(field)):
                normalized = _normalize_message(raw_msg)
                if not normalized:
                    continue
                display = tr_map.get(normalized, normalized)
                messages.append((display, style))

            if not messages:
                continue

            if field == "Deviation":
                short_train = next(
                    (m for m in messages if m[0].casefold() == "kort tåg"),
                    None,
                )
                door_range = next(
                    (m for m in messages if m[0].casefold() in {"dörr 2-13", "dörr 16-27"}),
                    None,
                )
                grouped = {short_train, door_range} - {None}
                if short_train is not None and door_range is not None:
                    yield Static(
                        self._format_messages((short_train, door_range)),
                        classes="schedule-message schedule-message-pair",
                    )
                else:
                    grouped.clear()

                remaining = [m for m in messages if m not in grouped]
                if remaining:
                    yield ScrollingLabel(
                        self._format_messages(remaining),
                        classes="schedule-message schedule-message-scroll",
                    )
            else:
                yield ScrollingLabel(
                    self._format_messages(messages),
                    classes="schedule-message schedule-message-scroll",
                )

    @staticmethod
    def _format_messages(messages):
        return " · ".join(
            f"[{style}]{escape(message)}[/]" for message, style in messages
        )


class TrainSchedule(Static):
    CACHE_FILE = "train_schedule.json"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stations = {}
        self._cache_mtime = 0

    def compose(self) -> ComposeResult:
        yield Static()

    def _check_cache(self):
        mtime = cache_mtime(self.CACHE_FILE)
        if mtime <= self._cache_mtime:
            return
        self._cache_mtime = mtime
        logger.info("Reloading train schedule from cache")

        cached = read_cache(self.CACHE_FILE)
        if cached is None:
            self.set_loading(False)
            return

        data = cached["data"]
        self.stations = data.get("station_names", {})
        station = self.stations.get(config["train"]["stationCode"], "")
        self.border_subtitle = f"{station}  [dim]Updated {format_cache_time(cached)}[/]"

        schedules = data.get("announcements", [])
        now = datetime.now(tz=pytz.UTC)
        self.remove_children()
        self.mount(
            Horizontal(
                Static("Line", classes="schedule-route"),
                Static("Track", classes="schedule-track"),
                Static("Time", classes="schedule-time"),
                classes="schedule-header",
            )
        )
        for schedule in schedules:
            advertised_time = datetime.fromisoformat(
                schedule["AdvertisedTimeAtLocation"]
            )
            if now > advertised_time:
                continue
            self.mount(ScheduleEntry(schedule, self.stations))

        self.set_loading(False)

    def on_mount(self):
        self.border_title = "Train"
        self.set_loading(True)
        self._check_cache()
        self.set_interval(config["tuiRefreshInterval"], self._check_cache)

    def refresh_schedule(self):
        self._cache_mtime = 0
        self._check_cache()

    def on_cache_changed(self, event: CacheChanged):
        if event.cache_name == self.CACHE_FILE:
            self.refresh_schedule()


class Train(Static):
    def compose(self):
        yield TrainSchedule(id="schedule")
        yield TrainStationMessage(id="message")
        self.border_title = "Train Information"
