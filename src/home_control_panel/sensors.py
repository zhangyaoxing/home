import logging

from rich.markup import escape
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static

from home_control_panel.libs.ha_api import api_ha
from home_control_panel.libs.utils import config

logger = logging.getLogger(__name__)
HUMIDITY_ENTITY_IDS = set(config["sensors"]["hum"])


def low_humidity_sensors(data):
    low_sensors = []
    for sensor in data["sensors"]:
        if sensor["entity_id"] not in HUMIDITY_ENTITY_IDS:
            continue
        try:
            humidity = float(sensor["state"])
        except (TypeError, ValueError):
            continue
        if humidity <= config["humidityWarningThreshold"]:
            low_sensors.append(sensor)
    return low_sensors


class HumidityWarningPanel(Static):
    def __init__(self, sensors=None, title=None, messages=None):
        super().__init__(id="humidity-warning")
        self.sensors = sensors
        self._title = title
        self._messages = messages
        self._blink_timer = None

    def compose(self) -> ComposeResult:
        title = self._title or "Warning"
        yield Static(title, classes="humidity-warning-title")
        yield Static(
            "██\n██\n██\n██\n\n██",
            id="humidity-warning-icon",
        )
        yield Static(id="humidity-warning-readings")

    def toggle_warning_icon(self):
        self.query_one("#humidity-warning-icon").toggle_class(
            "humidity-warning-icon-off"
        )

    def update_sensors(self, sensors):
        self.sensors = sensors
        readings = "\n".join(
            f'[bold]{escape(sensor["name"])}:[/] '
            f'{escape(str(sensor["state"]))}{escape(str(sensor["unit"]))}'
            for sensor in sensors
        )
        self.query_one("#humidity-warning-readings", Static).update(readings)

    def on_mount(self):
        if self._messages is not None:
            self.query_one("#humidity-warning-readings", Static).update(
                "\n".join(self._messages)
            )
        elif self.sensors is not None:
            self.update_sensors(self.sensors)
        self._blink_timer = self.set_interval(0.5, self.toggle_warning_icon)

    def on_unmount(self):
        if self._blink_timer is not None:
            self._blink_timer.stop()
            self._blink_timer = None


class HumidityWarningScreen(ModalScreen):
    BINDINGS = [
        Binding("q", "app.quit", "Quit", priority=True),
    ]

    def __init__(self, sensors=None, title=None, messages=None):
        super().__init__()
        self._sensors = sensors
        self._title = title
        self._messages = messages

    def compose(self) -> ComposeResult:
        yield HumidityWarningPanel(self._sensors, self._title, self._messages)

class SensorRow(Horizontal):
    def __init__(self, sensor, exceeded=False):
        super().__init__(classes="sensor-row")
        self.sensor = sensor
        self.exceeded = exceeded

    def compose(self) -> ComposeResult:
        name = self.sensor["name"]
        value = f'{self.sensor["state"]}{self.sensor["unit"]}'
        if self.exceeded:
            yield Static(
                f"[bold red]{escape(name)}[/]",
                classes="sensor-name sensor-exceeded",
            )
            yield Static(
                f"[bold red]{escape(value)}[/]",
                classes="sensor-value sensor-exceeded",
            )
        else:
            yield Static(
                escape(name),
                classes="sensor-name",
            )
            yield Static(
                escape(value),
                classes="sensor-value",
            )


class Sensors(Static):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sensor_signature = None

    def _apply_humidity_warning(self, data, low_sensors=None):
        if low_sensors is None:
            low_sensors = low_humidity_sensors(data)
        messages = []
        for sensor in low_sensors:
            messages.append(
                f'{sensor["name"]}: {sensor["state"]}{sensor["unit"]}'
            )
        self.app.warning_manager.update("sensors", messages)

    @work(
        thread=True,
        group="sensor-refresh",
        exclusive=True,
        exit_on_error=False,
    )
    def refresh_data(self):
        error, data = api_ha()
        self.app.call_from_thread(self._apply_refresh, error, data)

    def _apply_refresh(self, error, data):
        if error is not None:
            logger.error("Can't access Home Assistant API: %s", error)
            self.remove_children()
            self.mount(Static("Unavailable", classes="sensor-error"))
            self.set_loading(False)
            return

        sensor_signature = tuple(
            (
                sensor["entity_id"],
                sensor["name"],
                sensor["state"],
                sensor["unit"],
            )
            for sensor in data["sensors"]
        )
        low_sensors = low_humidity_sensors(data)
        if sensor_signature != self._sensor_signature:
            exceeded_ids = {s["entity_id"] for s in low_sensors}
            self.remove_children()
            for sensor in data["sensors"]:
                exceeded = sensor["entity_id"] in exceeded_ids
                self.mount(SensorRow(sensor, exceeded=exceeded))
            self._sensor_signature = sensor_signature

        self.set_loading(False)
        self._apply_humidity_warning(data, low_sensors)

    def on_mount(self):
        self.border_title = "Sensors"
        self.set_loading(True)
        self.set_timer(1, self.refresh_data)
        self.set_interval(config["sensorRefreshInterval"], self.refresh_data)
