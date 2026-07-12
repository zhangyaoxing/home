import logging
from datetime import datetime

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Checkbox, Static
from textual import work
from textual.message import Message

from home_control_panel.libs.ha_api import api_ha_lights, api_ha_toggle_light
from home_control_panel.libs.utils import config

logger = logging.getLogger(__name__)


class LightCheckbox(Checkbox):
    """A checkbox wired to toggle a Home Assistant light entity."""

    def __init__(self, entity_id, label, state, *args, **kwargs):
        self._toggling = False
        state_class = "light-on" if state == "on" else "light-off"
        classes = kwargs.pop("classes", "")
        merged = f"{classes} {state_class}".strip()
        super().__init__(
            label,
            value=(state == "on"),
            classes=merged,
            *args,
            **kwargs,
        )
        self.entity_id = entity_id

    def watch_value(self, value: bool) -> None:
        self.set_class(value, "light-on")
        self.set_class(not value, "light-off")
        if not self.is_mounted or self._toggling:
            return
        self._toggling = True
        try:
            self.run_worker(
                lambda v=value: self._toggle_light(v),
                exclusive=True,
                thread=True,
            )
        finally:
            self._toggling = False

    def _toggle_light(self, turn_on: bool):
        error = api_ha_toggle_light(self.entity_id)
        if error:
            logger.warning("Failed to toggle %s: %s", self.entity_id, error)
            self.app.call_from_thread(setattr, self, "value", not turn_on)
        else:
            self.app.call_from_thread(self.post_message, RefreshRequest())


class RoomSection(Vertical):
    """A subsection showing one room name and its light checkboxes."""

    def __init__(self, room_data, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.room_data = room_data

    def compose(self) -> ComposeResult:
        for light in self.room_data["lights"]:
            yield LightCheckbox(
                light["entity_id"],
                escape(light["name"]),
                light["state"],
                classes="light-row",
            )

    def on_mount(self):
        self.border_title = self.room_data["area"]


class RefreshRequest(Message):
    """Posted when a toggle succeeds — triggers immediate re-fetch."""


class Lights(Static):
    """Widget that fetches and displays HA lights/switches directly."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._data_signature = None
        self._last_fetch_at = None

    def compose(self) -> ComposeResult:
        yield Static()

    @property
    def _fetch_interval(self) -> int:
        return config["homeassistant"]["lightsRefreshInterval"]

    def _render_rooms(self, rooms):
        sig = tuple(
            (light["entity_id"], light["state"])
            for room in rooms
            for light in room["lights"]
        )
        if sig != self._data_signature:
            self.remove_children()
            for room in rooms:
                self.mount(RoomSection(room))
            self._data_signature = sig

        self._last_fetch_at = datetime.now()
        self.set_loading(False)
        ts = self._last_fetch_at.strftime("%H:%M")
        self.border_subtitle = f"[dim]Updated {ts}[/]"

    @work(thread=True, exclusive=True)
    async def _fetch(self) -> None:
        error, rooms = api_ha_lights()
        if error or rooms is None:
            logger.warning("Failed to fetch HA lights: %s", error)
            self.app.call_from_thread(self._set_error)
            return
        self.app.call_from_thread(self._render_rooms, rooms)

    def _set_error(self):
        self.remove_children()
        self.mount(Static("Unavailable", classes="light-error"))
        self.set_loading(False)

    def on_mount(self):
        self.border_title = "Lights & Switches"
        self.set_loading(True)
        self._fetch()
        self.set_interval(self._fetch_interval, self._fetch)

    def refresh_lights(self):
        self.set_loading(True)
        self._fetch()

    def on_click(self, event):
        if event.widget is not self:
            return
        self.border_subtitle = "[dim]Refreshing...[/]"
        self.set_loading(True)
        self._fetch()

    def on_refresh_request(self, event: RefreshRequest):
        self.set_loading(True)
        self._fetch()
