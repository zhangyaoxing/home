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
    def __init__(self, sensors):
        super().__init__(id="humidity-warning")
        self.sensors = sensors
        self._blink_timer = None

    def compose(self) -> ComposeResult:
        yield Static("LOW HUMIDITY", classes="humidity-warning-title")
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

    def __init__(self, sensors):
        super().__init__()
        self.sensors = sensors

    def compose(self) -> ComposeResult:
        yield HumidityWarningPanel(self.sensors)

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
        self._low_sensors = []
        self._warning_timer = None
        self._sensor_signature = None

    def _warning_screen(self):
        return next(
            (
                screen
                for screen in self.app.screen_stack
                if isinstance(screen, HumidityWarningScreen)
            ),
            None,
        )

    def _schedule_warning_toggle(self):
        self._warning_timer = self.set_timer(
            config["humidityWarningInterval"],
            self._toggle_warning,
        )

    def _toggle_warning(self):
        self._warning_timer = None
        if not self._low_sensors:
            return

        warning_screen = self._warning_screen()
        if warning_screen is None:
            self.app.push_screen(HumidityWarningScreen(self._low_sensors))
        else:
            warning_screen.dismiss()
        self._schedule_warning_toggle()

    def _stop_warning_cycle(self):
        if self._warning_timer is not None:
            self._warning_timer.stop()
            self._warning_timer = None

    def _apply_humidity_warning(self, data, low_sensors=None):
        if low_sensors is None:
            low_sensors = low_humidity_sensors(data)
        self._low_sensors = low_sensors
        warning_screen = self._warning_screen()
        if not low_sensors:
            if warning_screen is not None:
                warning_screen.dismiss()
            self._stop_warning_cycle()
        elif warning_screen is not None:
            warning_screen.query_one(HumidityWarningPanel).update_sensors(
                low_sensors
            )
        elif self._warning_timer is None:
            self.app.push_screen(HumidityWarningScreen(low_sensors))
            self._schedule_warning_toggle()

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
