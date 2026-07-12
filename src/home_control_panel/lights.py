import logging
from datetime import datetime

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Checkbox, Static
from textual import work
from textual.message import Message

from home_control_panel.libs.ha_api import (
    api_ha_activate_scene,
    api_ha_lights,
    api_ha_toggle_light,
)
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


class SceneButton(Static):
    """A clickable scene name that activates the scene."""

    def __init__(self, scene, *args, **kwargs):
        super().__init__(escape(scene["name"]), *args, **kwargs)
        self.entity_id = scene["entity_id"]

    def on_click(self):
        self.run_worker(
            lambda: api_ha_activate_scene(self.entity_id),
            thread=True,
        )
        self.post_message(RefreshRequest())


class SceneSection(Vertical):
    """A bordered section showing scenes as clickable buttons."""

    def __init__(self, scenes_data, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.scenes_data = scenes_data

    def compose(self) -> ComposeResult:
        for scene in self.scenes_data:
            yield SceneButton(scene, classes="light-row")

    def on_mount(self):
        self.border_title = "Scenes"


class RefreshRequest(Message):
    """Posted when a toggle succeeds — triggers immediate re-fetch."""


class Lights(Static):
    """Widget that fetches and displays HA lights/switches directly."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._data_signature = None
        self._last_fetch_at = None
        self._checkboxes = {}

    def compose(self) -> ComposeResult:
        yield Static()

    @property
    def _fetch_interval(self) -> int:
        return config["homeassistant"]["lightsRefreshInterval"]

    def _render_data(self, data):
        rooms = data.get("rooms", [])
        scenes = data.get("scenes", [])
        sig = tuple(
            (light["entity_id"], light["state"])
            for room in rooms
            for light in room["lights"]
        )
        if sig != self._data_signature or not self._checkboxes:
            self.remove_children()
            self._checkboxes.clear()
            for room in rooms:
                section = RoomSection(room)
                self.mount(section)
                for cb in section.query(LightCheckbox):
                    self._checkboxes[cb.entity_id] = cb
            if scenes:
                self.mount(SceneSection(scenes))
            self._data_signature = sig
        else:
            for room in rooms:
                for light in room["lights"]:
                    cb = self._checkboxes.get(light["entity_id"])
                    if cb is None:
                        continue
                    on = light["state"] == "on"
                    if cb.value != on:
                        cb._toggling = True
                        cb.value = on
                        cb.set_class(on, "light-on")
                        cb.set_class(not on, "light-off")
                        cb._toggling = False

        self._last_fetch_at = datetime.now()
        self.set_loading(False)
        ts = self._last_fetch_at.strftime("%H:%M")
        self.border_subtitle = f"[dim]Updated {ts}[/]"

    @work(thread=True, exclusive=True)
    async def _fetch(self) -> None:
        error, data = api_ha_lights()
        if error or data is None:
            logger.warning("Failed to fetch HA lights: %s", error)
            self.app.call_from_thread(self._set_error)
            return
        self.app.call_from_thread(self._render_data, data)

    def _set_error(self):
        self.remove_children()
        self._checkboxes.clear()
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
