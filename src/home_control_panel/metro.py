import logging
from datetime import datetime

import pytz
from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from home_control_panel.common_widgets import ScrollingLabel
from home_control_panel.libs.cache import cache_mtime, format_cache_time, read_cache
from home_control_panel.libs.utils import config

logger = logging.getLogger(__name__)
TZ = pytz.timezone(config["timezone"])


class MetroLine(Horizontal):
    def __init__(self, entry):
        super().__init__(classes="schedule-line")
        self.entry = entry

    def compose(self) -> ComposeResult:
        yield Static(classes="schedule-route")
        yield Static(classes="schedule-track")
        yield Static(classes="schedule-time")

    def refresh_data(self):
        entry = self.entry
        line = entry.get("line", "")
        dest = entry.get("destination", "")
        expected = entry.get("expected", "") or entry.get("scheduled", "")
        cancelled = entry.get("state") == "CANCELLED"

        if expected:
            dt = TZ.localize(datetime.fromisoformat(expected))
            now = datetime.now(tz=pytz.UTC)
            delta = int((dt - now).total_seconds() / 60)
            mins = "Nu" if delta <= 0 else f"{delta} min"
        else:
            mins = ""

        if cancelled:
            route = f"[strike bold blue]{line}[/]  [strike green]{dest}[/]"
            time_display = f"[strike]{mins}[/]"
        else:
            route = f"[bold blue]{line}[/]  [green]{dest}[/]"
            time_display = mins

        self.query_one(".schedule-route", Static).update(route)
        self.query_one(".schedule-track", Static).update("")
        self.query_one(".schedule-time", Static).update(time_display)

    def on_mount(self):
        self.refresh_data()


class MetroEntry(Static):
    def __init__(self, entry):
        super().__init__(classes="schedule-entry")
        self.entry = entry

    def compose(self) -> ComposeResult:
        yield MetroLine(self.entry)
        tr_map = self.entry.get("deviations_tr", {})
        messages = []
        for raw_msg in self.entry.get("deviations", []):
            if not raw_msg:
                continue
            display = tr_map.get(raw_msg, raw_msg)
            messages.append((display, "bold yellow"))
        if messages:
            yield ScrollingLabel(
                " · ".join(
                    f"[{style}]{escape(msg)}[/]" for msg, style in messages
                ),
                classes="schedule-message schedule-message-scroll",
            )


class MetroSchedule(Static):
    CACHE_FILE = "metro_schedule.json"

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
        logger.info("Reloading metro schedule from cache")

        cached = read_cache(self.CACHE_FILE)
        if cached is None:
            self.set_loading(False)
            return

        departures = cached["data"].get("departures", [])
        station_name = cached["data"].get("name", "")
        now = datetime.now(tz=pytz.UTC)

        self.remove_children()
        self.mount(
            Horizontal(
                Static("Line", classes="schedule-route"),
                Static("", classes="schedule-track"),
                Static("Time", classes="schedule-time"),
                classes="schedule-header",
            )
        )
        for entry in departures[:5]:
            expected = entry.get("expected", "") or entry.get("scheduled", "")
            if expected:
                dt = TZ.localize(datetime.fromisoformat(expected))
                if now > dt:
                    continue
            self.mount(MetroEntry(entry))

        self.border_subtitle = (
            f"{station_name}  [dim]Updated {format_cache_time(cached)}[/]"
        )
        self.set_loading(False)

    def on_mount(self):
        self.border_title = "Metro"
        self.set_loading(True)
        self._check_cache()
        self.set_interval(5, self._check_cache)

    def refresh_metro(self):
        self._cache_mtime = 0
        self._check_cache()
