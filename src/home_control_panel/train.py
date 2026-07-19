import logging
import time
from datetime import datetime

import pytz
from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Rule, Static

from home_control_panel.common_widgets import ScrollingLabel
from home_control_panel.libs.cache import (
    CacheChanged,
    cache_mtime,
    format_cache_time,
    read_cache,
    touch_trigger,
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
        self._data_signature = None

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
        sig = tuple(
            (_normalize_message(m["raw"].get("FreeText", "")), m["raw"].get("Status"))
            for m in messages
        )

        if sig != self._data_signature:
            self._data_signature = sig
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

        station_name = cached["data"].get("station_name", "")
        self.border_subtitle = f"{station_name}  [dim]Updated {format_cache_time(cached)}[/]"
        self.set_loading(False)

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

    def on_click(self, event):
        if event.widget is not self:
            return
        if time.time() - cache_mtime(self.CACHE_FILE) < 60:
            return
        self.border_subtitle = "[dim]Refreshing...[/]"
        touch_trigger("_trigger_train_messages")


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

    def refresh_time(self):
        row = self.schedule
        advertised_time = datetime.fromisoformat(row["AdvertisedTimeAtLocation"])
        now = datetime.now(tz=pytz.UTC)
        delta = (advertised_time - now).total_seconds()
        departure = f"{int(delta / 60)} min"
        self.query_one(".schedule-time", Static).update(departure)

    def is_past(self):
        row = self.schedule
        advertised_time = datetime.fromisoformat(row["AdvertisedTimeAtLocation"])
        return datetime.now(tz=pytz.UTC) > advertised_time


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
        self._data_signature = None

    def compose(self) -> ComposeResult:
        yield Vertical(id="schedule-entries")
        yield Static("\u25b8 Notices", id="notice-toggle")

    def _check_cache(self):
        mtime = cache_mtime(self.CACHE_FILE)
        if mtime > self._cache_mtime:
            self._cache_mtime = mtime
            logger.info("Reloading train schedule from cache")

            cached = read_cache(self.CACHE_FILE)
            if cached is None:
                self.set_loading(False)
            else:
                data = cached["data"]
                schedules = data.get("announcements", [])

                sig = tuple(
                    (s.get("AdvertisedTimeAtLocation"), s.get("TrackAtLocation"),
                     tuple(s.get("ToLocation", [])), s.get("Line", ""),
                     tuple(_as_list(s.get("Deviation"))),
                     tuple(_as_list(s.get("OtherInformation"))))
                    for s in schedules
                )

                if sig != self._data_signature:
                    self._data_signature = sig
                    self.stations = data.get("station_names", {})
                    station = self.stations.get(config["train"]["stationCode"], "")

                    now = datetime.now(tz=pytz.UTC)
                    entries = self.query_one("#schedule-entries", Vertical)
                    entries.remove_children()
                    entries.mount(
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
                        entries.mount(ScheduleEntry(schedule, self.stations))

                    for line in self.query(ScheduleLine):
                        line.refresh_data()

                station = self.stations.get(config["train"]["stationCode"], "")
                self.border_subtitle = f"{station}  [dim]Updated {format_cache_time(cached)}[/]"
                self.set_loading(False)

        else:
            for line in list(self.query(ScheduleLine)):
                if line.is_past():
                    line.parent.remove()
                else:
                    line.refresh_time()

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

    def on_click(self, event):
        if event.widget.id == "notice-toggle":
            self.app.push_screen(NoticesScreen())
            return
        if event.widget is not self:
            return
        if time.time() - cache_mtime(self.CACHE_FILE) < 60:
            return
        self.border_subtitle = "[dim]Refreshing...[/]"
        touch_trigger("_trigger_train_schedule")


class NoticesScreen(ModalScreen):
    """Modal screen that displays Station Notices at 2/3 size, centered."""

    CACHE_FILE = "train_messages.json"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache_mtime = 0
        self._station_name = ""
        self._cache_label = ""
        self._remaining = 30

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-container"):
            yield Static("Loading notices...", id="modal-status")

    def _load_notices(self):
        mtime = cache_mtime(self.CACHE_FILE)
        if mtime <= self._cache_mtime:
            return
        self._cache_mtime = mtime

        container = self.query_one("#modal-container", Vertical)
        container.border_title = "Station Notices"

        cached = read_cache(self.CACHE_FILE)
        if cached is None:
            self.query_one("#modal-status", Static).update("No notices available.")
            return

        messages = cached["data"].get("messages", [])
        if not messages:
            self.query_one("#modal-status", Static).update("No notices at this time.")
            self._station_name = cached["data"].get("station_name", "")
            self._cache_label = ""
            self._update_subtitle()
            return

        self._station_name = cached["data"].get("station_name", "")
        self._cache_label = f"[dim]Updated {format_cache_time(cached)}[/]"
        self._update_subtitle()

        messages = sorted(
            messages,
            key=lambda m: m["raw"].get("Status") != "Lag",
        )

        container.remove_children()
        for entry in messages:
            message = entry["raw"]
            display_text = entry["summary"]
            status_class = "lag" if message.get("Status") == "Lag" else "normal"
            container.mount(
                ScrollingLabel(display_text, classes=status_class)
            )
            container.mount(Rule())

    def _update_subtitle(self):
        container = self.query_one("#modal-container", Vertical)
        parts = [f"[bold yellow]{self._remaining}s[/]"]
        if self._station_name:
            parts.insert(0, self._station_name)
        if self._cache_label:
            parts.insert(1, self._cache_label)
        container.border_subtitle = "  ".join(parts)

    def _tick(self):
        if self._remaining <= 0:
            return
        self._remaining -= 1
        if self._remaining <= 0:
            self.dismiss()
            return
        self._update_subtitle()

    def on_mount(self):
        self._load_notices()
        self._update_subtitle()
        self.set_interval(config["tuiRefreshInterval"], self._load_notices)
        self.set_interval(1, self._tick)

    def on_click(self, event):
        modal = self.query_one("#modal-container")
        # Check if click is inside the modal container
        widget = event.widget
        inside = False
        while widget is not None:
            if widget is modal:
                inside = True
                break
            widget = widget.parent

        if not inside:
            self.dismiss()
            return

        # Click inside modal → refresh (with 60s throttle)
        if time.time() - cache_mtime(self.CACHE_FILE) < 60:
            return
        container = self.query_one("#modal-container", Vertical)
        container.border_subtitle = "[dim]Refreshing...[/]"
        touch_trigger("_trigger_train_messages")
        self._cache_mtime = 0

    def on_key(self, event):
        if event.key == "escape":
            self.dismiss()


class Train(Static):
    def compose(self):
        yield TrainSchedule(id="schedule")
        yield TrainStationMessage(id="message")
        self.border_title = "Train Information"
