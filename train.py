from datetime import datetime
import logging

import pytz
from rich.markup import escape
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Rule, Static

from common_widgets import ScrollingLabel
from libs.traffic_api import (
    api_train_announcement,
    api_train_message,
    api_train_stations,
    is_freq_throttled,
)
from libs.utils import config

logger = logging.getLogger(__name__)


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _normalize_message(message):
    return " ".join(str(message).splitlines())


class TrainStationMessage(Static):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_refresh = datetime.min

    @work(
        thread=True,
        group="train-message-refresh",
        exclusive=True,
        exit_on_error=False,
    )
    def load_message(self):
        if is_freq_throttled(self.last_refresh):
            return

        error, messages_json = api_train_message()
        if error is not None:
            logger.error("Can't access API to get train messages.")
            return

        self.app.call_from_thread(self._apply_messages, messages_json)

    def _apply_messages(self, messages_json):
        messages = messages_json["RESPONSE"]["RESULT"][0]["TrainStationMessage"]
        messages = sorted(
            messages,
            key=lambda message: message.get("Status") != "Lag",
        )

        self.remove_children()
        for message in messages:
            status_class = "lag" if message.get("Status") == "Lag" else "normal"
            self.mount(
                ScrollingLabel(
                    _normalize_message(message.get("FreeText", "")),
                    classes=status_class,
                )
            )
            self.mount(Rule())

        self.set_loading(False)
        self.last_refresh = datetime.now()

    def on_mount(self):
        self.border_title = "Station Notices"
        self.set_loading(True)
        self.set_timer(1, self.load_message)
        self.set_interval(config["apiFreqCheck"], self.load_message)

    def refresh_message(self):
        self.load_message()


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
        from_station = "/".join(
            self.stations.get(location, location)
            for location in row.get("FromLocation", [])
        )

        if now > advertised_time:
            delta = (now - advertised_time).total_seconds()
            to_station = "/".join(
                self.stations.get(location, location)
                for location in row.get("ToLocation", [])
            )
            route = f"{from_station} → {to_station}"
            route = f"[#808080]{route}[/#808080]"
            track = f"[#808080]{track}[/#808080]"
            departure = f"[#808080]{int(delta / 60)}m ago[/#808080]"
        else:
            delta = (advertised_time - now).total_seconds()
            to_station = "/".join(
                f"[bold][green]{self.stations.get(location, location)}[/green][/bold]"
                for location in row.get("ToLocation", [])
            )
            route = f"{from_station} → {to_station}"
            departure = f"{int(delta / 60)} min"

        self.query_one(".schedule-route", Static).update(route)
        self.query_one(".schedule-track", Static).update(track)
        self.query_one(".schedule-time", Static).update(departure)

    def on_mount(self):
        self.refresh_data()
        self.set_interval(config["apiFreqCheck"], self.refresh_data)


class ScheduleEntry(Static):
    def __init__(self, schedule, stations):
        super().__init__(classes="schedule-entry")
        self.schedule = schedule
        self.stations = stations

    def compose(self) -> ComposeResult:
        yield ScheduleLine(self.schedule, self.stations)

        seen = set()
        messages = []
        for field, style in (
            ("Deviation", "bold yellow"),
            ("OtherInformation", "gray"),
        ):
            for message in _as_list(self.schedule.get(field)):
                normalized = _normalize_message(message)
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    messages.append((normalized, style))

        short_train = next(
            (
                message
                for message in messages
                if message[0].casefold() == "kort tåg"
            ),
            None,
        )
        door_range = next(
            (
                message
                for message in messages
                if message[0].casefold() in {"dörr 2-13", "dörr 16-27"}
            ),
            None,
        )

        grouped_messages = {short_train, door_range} - {None}
        if short_train is not None and door_range is not None:
            yield Static(
                self._format_messages((short_train, door_range)),
                classes="schedule-message schedule-message-pair",
            )
        else:
            grouped_messages.clear()

        remaining_messages = [
            message for message in messages if message not in grouped_messages
        ]
        if remaining_messages:
            yield ScrollingLabel(
                self._format_messages(remaining_messages),
                classes="schedule-message schedule-message-scroll",
            )

    @staticmethod
    def _format_messages(messages):
        return " · ".join(
            f"[{style}]{escape(message)}[/]" for message, style in messages
        )


class TrainSchedule(Static):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stations = {}
        self.last_refresh = datetime.min

    @work(
        thread=True,
        group="train-stations-refresh",
        exclusive=True,
        exit_on_error=False,
    )
    def load_stations(self):
        error, stations_json = api_train_stations()
        if error is not None:
            logger.error("Can't access API to get train stations.")
            self.app.call_from_thread(self._apply_stations, None)
            return

        self.app.call_from_thread(self._apply_stations, stations_json)

    def _apply_stations(self, stations_json):
        if stations_json is not None:
            for station in stations_json["RESPONSE"]["RESULT"][0]["TrainStation"]:
                self.stations[station["LocationSignature"]] = station[
                    "AdvertisedLocationName"
                ]
            logger.debug("Stations loaded: %s", self.stations)
            self.border_subtitle = self.stations.get(config["myStationCode"], "")

        # The initial schedule must not render before station codes can be
        # translated. If station loading failed, still show the schedule using
        # the codes rather than leaving the panel empty.
        if self.last_refresh == datetime.min:
            self.load_schedule()

    @work(
        thread=True,
        group="train-schedule-refresh",
        exclusive=True,
        exit_on_error=False,
    )
    def load_schedule(self):
        if is_freq_throttled(self.last_refresh):
            return

        error, schedule_json = api_train_announcement()
        if error is not None:
            logger.error("Can't access API to get train schedules.")
            return

        self.app.call_from_thread(self._apply_schedule, schedule_json)

    def _apply_schedule(self, schedule_json):
        schedules = schedule_json["RESPONSE"]["RESULT"][0]["TrainAnnouncement"]
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
            self.mount(ScheduleEntry(schedule, self.stations))

        self.set_loading(False)
        self.last_refresh = datetime.now()

    def on_mount(self):
        self.border_title = "Schedules"
        self.set_loading(True)
        self.set_timer(1, self.load_stations)
        self.set_interval(config["stationUpdateInterval"], self.load_stations)
        self.set_interval(config["apiFreqCheck"], self.load_schedule)


class Train(Static):
    def compose(self):
        yield TrainSchedule(id="schedule")
        yield TrainStationMessage(id="message")
        self.border_title = "Train Information"
