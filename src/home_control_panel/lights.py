import logging
import time
from datetime import datetime

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Checkbox, RadioSet, RadioButton, Static
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
        self.can_focus = False
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


class RoomSection(Vertical):
    """A subsection showing one room name and its light checkboxes."""

    def __init__(self, room_data, checkboxes, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.room_data = room_data
        self._checkboxes = checkboxes

    def compose(self) -> ComposeResult:
        for cb in self._checkboxes:
            yield cb

    def on_mount(self):
        self.border_title = self.room_data["area"]


class SceneButton(Button):
    """A button that activates a Home Assistant scene."""

    def __init__(self, scene, *args, **kwargs):
        super().__init__(escape(scene["name"]), *args, **kwargs)
        self.entity_id = scene["entity_id"]


class SceneSection(Vertical):
    """A bordered section showing scenes as clickable buttons."""

    _DELAY_MAP = {"delay-now": 0, "delay-30s": 30, "delay-60s": 60}

    def __init__(self, scenes_data, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.scenes_data = scenes_data
        self._delay = 0

    def compose(self) -> ComposeResult:
        for scene in self.scenes_data:
            yield SceneButton(scene)
        with Horizontal(id="scene-delay-row"):
            yield RadioSet(
                RadioButton("Now", value=True, id="delay-now"),
                RadioButton("30s", id="delay-30s"),
                RadioButton("60s", id="delay-60s"),
                id="scene-delay",
            )

    def on_mount(self):
        self.border_title = "Scenes"
        self.query_one("#scene-delay", RadioSet).can_focus = False

    def on_radio_set_changed(self, event: RadioSet.Changed):
        self._delay = self._DELAY_MAP.get(event.pressed.id, 0)

    @work(thread=True)
    def _activate_scene(self, entity_id: str, delay: int):
        if delay > 0:
            self.app.call_from_thread(
                setattr, self, "border_subtitle", f"[dim]In {delay}s...[/]"
            )
            time.sleep(delay)
        api_ha_activate_scene(entity_id)
        self.app.call_from_thread(setattr, self, "border_subtitle", "")
        self.app.call_from_thread(self.post_message, RefreshRequest())

    def on_button_pressed(self, event: Button.Pressed):
        if not isinstance(event.button, SceneButton):
            return
        self._activate_scene(event.button.entity_id, self._delay)


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
            light["entity_id"]
            for room in rooms
            for light in room["lights"]
        )
        if sig != self._data_signature or not self._checkboxes:
            self.remove_children()
            self._checkboxes.clear()
            for room in rooms:
                checkboxes = [
                    LightCheckbox(
                        light["entity_id"],
                        escape(light["name"]),
                        light["state"],
                        classes="light-row",
                    )
                    for light in room["lights"]
                ]
                section = RoomSection(room, checkboxes)
                self.mount(section)
                for cb in checkboxes:
                    self._checkboxes[cb.entity_id] = cb
            if scenes:
                self.mount(SceneSection(scenes))
            self._data_signature = sig
        else:
            changed = False
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
                        changed = True
            if not changed:
                return

        self._last_fetch_at = datetime.now()
        self.set_loading(False)

    @work(thread=True, exclusive=True)
    def _fetch(self) -> None:
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
        self._fetch()

    def on_refresh_request(self, event: RefreshRequest):
        self._fetch()
