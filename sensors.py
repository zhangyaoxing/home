import logging

from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static

from libs.ha_api import api_ha
from libs.utils import config

logger = logging.getLogger(__name__)
HUMIDITY_WARNING_THRESHOLD = 35


def low_humidity_sensors(data):
    humidity_entities = set(config["sensors"]["hum"])
    low_sensors = []
    for sensor in data["sensors"]:
        if sensor["entity_id"] not in humidity_entities:
            continue
        try:
            humidity = float(sensor["state"])
        except (TypeError, ValueError):
            continue
        if humidity <= HUMIDITY_WARNING_THRESHOLD:
            low_sensors.append(sensor)
    return low_sensors


class HumidityWarningPanel(Static):
    def __init__(self, sensors):
        super().__init__(id="humidity-warning")
        self.sensors = sensors

    def compose(self) -> ComposeResult:
        yield Static("LOW HUMIDITY", classes="humidity-warning-title")
        yield Static(id="humidity-warning-readings")

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


class HumidityWarningScreen(ModalScreen):
    BINDINGS = [
        Binding("q", "app.quit", "Quit", priority=True),
    ]

    def __init__(self, sensors):
        super().__init__()
        self.sensors = sensors

    def compose(self) -> ComposeResult:
        yield HumidityWarningPanel(self.sensors)

    def refresh_data(self):
        error, data = api_ha()
        if error is not None:
            logger.error(
                "Can't refresh humidity warning from Home Assistant: %s",
                error,
            )
            return

        low_sensors = low_humidity_sensors(data)
        if not low_sensors:
            self.dismiss()
            return
        self.query_one(HumidityWarningPanel).update_sensors(low_sensors)

    def on_mount(self):
        self.set_interval(config["sensorRefreshInterval"], self.refresh_data)


class SensorRow(Horizontal):
    def __init__(self, sensor):
        super().__init__(classes="sensor-row")
        self.sensor = sensor

    def compose(self) -> ComposeResult:
        yield Static(
            escape(self.sensor["name"]),
            classes="sensor-name",
        )
        yield Static(
            f'{escape(str(self.sensor["state"]))}{escape(str(self.sensor["unit"]))}',
            classes="sensor-value",
        )


class Sensors(Static):
    def refresh_data(self):
        error, data = api_ha()
        if error is not None:
            logger.error("Can't access Home Assistant API: %s", error)
            self.remove_children()
            self.mount(Static("Unavailable", classes="sensor-error"))
            self.set_loading(False)
            return

        self.remove_children()
        for sensor in data["sensors"]:
            self.mount(SensorRow(sensor))
        self.set_loading(False)

        low_sensors = low_humidity_sensors(data)
        warning_screen = next(
            (
                screen
                for screen in self.app.screen_stack
                if isinstance(screen, HumidityWarningScreen)
            ),
            None,
        )
        if low_sensors and warning_screen is None:
            self.app.push_screen(HumidityWarningScreen(low_sensors))
        elif low_sensors:
            warning_screen.query_one(HumidityWarningPanel).update_sensors(
                low_sensors
            )

    def on_mount(self):
        self.border_title = "Sensors"
        self.set_loading(True)
        self.set_timer(1, self.refresh_data)
        self.set_interval(config["sensorRefreshInterval"], self.refresh_data)
