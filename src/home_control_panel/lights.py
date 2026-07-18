import logging
from datetime import datetime

import pyfiglet
from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
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
        self.scene_name = scene["name"]


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
    def _apply_scene(self, entity_id: str):
        api_ha_activate_scene(entity_id)
        self.app.call_from_thread(self.post_message, RefreshRequest())

    def on_button_pressed(self, event: Button.Pressed):
        if not isinstance(event.button, SceneButton):
            return
        entity_id = event.button.entity_id
        if self._delay > 0:
            def on_done(apply):
                if apply:
                    self._apply_scene(entity_id)
            self.app.push_screen(
                SceneCountdownScreen(event.button.scene_name, self._delay),
                on_done,
            )
        else:
            self._apply_scene(entity_id)


class SceneCountdownScreen(ModalScreen):
    """Modal that counts down before applying a scene; closing cancels it."""

    _FIGLET_FONT = "doh"

    def __init__(self, scene_name, delay, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._scene_name = scene_name
        self._remaining = delay
        self._finished = False
        self._blink_on = True

    def compose(self) -> ComposeResult:
        with Vertical(id="scene-countdown-container"):
            yield Static("[bold]Blow up the house in[/]", id="sc-title")
            yield Static(self._figlet_text(), id="sc-time")
            yield Static(escape(self._scene_name), id="sc-name")
            yield Static("[dim]Esc or click outside to cancel[/]", id="sc-hint")

    def _figlet_text(self) -> str:
        raw = pyfiglet.figlet_format(
            str(self._remaining), font=self._FIGLET_FONT,
        ).rstrip("\n")
        lines = raw.split("\n")
        while lines and not lines[-1].strip():
            lines.pop()
        # Pad each line to uniform width so the block centres cleanly
        lines = [ln.rstrip() for ln in lines]
        max_w = max(len(ln) for ln in lines)
        lines = [ln.ljust(max_w) for ln in lines]
        color = "red" if self._blink_on else "white"
        return f"[{color}]" + "\n".join(lines) + f"[/{color}]"

    def _refresh_time(self):
        try:
            self.query_one("#sc-time", Static).update(self._figlet_text())
        except Exception:
            pass

    def _blink_toggle(self):
        self._blink_on = not self._blink_on
        self._refresh_time()

    def on_mount(self):
        self._refresh_time()
        self.set_interval(1, self._tick)
        self.set_interval(0.5, self._blink_toggle)

    def _tick(self):
        if self._finished:
            return
        self._remaining -= 1
        if self._remaining <= 0:
            self._finish(apply=True)
            return
        self._refresh_time()

    def _finish(self, apply: bool):
        if self._finished:
            return
        self._finished = True
        self.dismiss(apply)

    def on_key(self, event):
        if event.key == "escape":
            self._finish(apply=False)

    def on_click(self, event):
        modal = self.query_one("#scene-countdown-container")
        widget = event.widget
        inside = False
        while widget is not None:
            if widget is modal:
                inside = True
                break
            widget = widget.parent
        if not inside:
            self._finish(apply=False)


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
