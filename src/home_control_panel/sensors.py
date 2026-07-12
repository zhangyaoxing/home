import logging
import time

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from home_control_panel.libs.cache import (
    CacheChanged,
    cache_mtime,
    format_cache_time,
    read_cache,
    touch_trigger,
)
from home_control_panel.libs.utils import config

logger = logging.getLogger(__name__)
HUMIDITY_ENTITY_IDS = set(config["homeassistant"]["sensors"]["hum"])
PLANT_HUMIDITY_ENTITY_IDS = set(config["homeassistant"]["sensors"]["plant_hum"])


def low_humidity_sensors(data):
    thresholds = config["homeassistant"]["humidityWarningThreshold"]
    low_sensors = []
    for sensor in data["sensors"]:
        if sensor["entity_id"] not in HUMIDITY_ENTITY_IDS:
            continue
        try:
            humidity = float(sensor["state"])
        except (TypeError, ValueError):
            continue
        if humidity < thresholds[2]:
            low_sensors.append((sensor, 3))
        elif humidity < thresholds[1]:
            low_sensors.append((sensor, 2))
        elif humidity < thresholds[0]:
            low_sensors.append((sensor, 1))
    return low_sensors


def _plant_hum_low(data):
    thresholds = config["homeassistant"]["plantHumWarningThreshold"]
    low = []
    for sensor in data["sensors"]:
        if sensor["entity_id"] not in PLANT_HUMIDITY_ENTITY_IDS:
            continue
        try:
            humidity = float(sensor["state"])
        except (TypeError, ValueError):
            continue
        if humidity < thresholds[2]:
            low.append((sensor, 3))
        elif humidity < thresholds[1]:
            low.append((sensor, 2))
        elif humidity < thresholds[0]:
            low.append((sensor, 1))
    return low


_LEVEL_COLORS = {1: "green", 2: "yellow", 3: "red"}


class SensorRow(Horizontal):
    def __init__(self, sensor, level=0):
        super().__init__(classes="sensor-row")
        self.sensor = sensor
        self.level = level

    def compose(self) -> ComposeResult:
        name = self.sensor["name"]
        value = f'{self.sensor["state"]}{self.sensor["unit"]}'
        if self.level:
            color = _LEVEL_COLORS.get(self.level, "red")
            yield Static(
                escape(name),
                classes="sensor-name",
            )
            yield Static(
                f"[bold {color}]{escape(value)}[/]",
                classes=f"sensor-value sensor-exceeded-{self.level}",
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
    CACHE_FILE = "sensors.json"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sensor_signature = None
        self._cache_mtime = 0

    def compose(self) -> ComposeResult:
        yield Static()

    def _apply_humidity_warning(self, data, low_sensors=None, plant_low=None):
        if low_sensors is None:
            low_sensors = low_humidity_sensors(data)
        if plant_low is None:
            plant_low = _plant_hum_low(data)

        messages = []
        level = 0
        for sensor, sensor_level in low_sensors:
            messages.append(
                f'{sensor["name"]}: {sensor["state"]}{sensor["unit"]}'
            )
            level = max(level, sensor_level)

        for sensor, plant_level in plant_low:
            messages.append(
                f'{sensor["name"]}: {sensor["state"]}{sensor["unit"]}'
            )
            level = max(level, plant_level)

        self.app.warning_manager.update(  # pyright: ignore[reportAttributeAccessIssue]
            "sensors", messages, level=level if level > 0 else 3,
        )

    def _check_cache(self):
        mtime = cache_mtime(self.CACHE_FILE)
        if mtime <= self._cache_mtime:
            return
        self._cache_mtime = mtime
        logger.info("Reloading sensors from cache")

        cached = read_cache(self.CACHE_FILE)
        if cached is None:
            self.remove_children()
            self.mount(Static("Unavailable", classes="sensor-error"))
            self.set_loading(False)
            return

        data = cached["data"]
        sensor_signature = tuple(
            (sensor["entity_id"], sensor["name"], sensor["state"], sensor["unit"])
            for sensor in data["sensors"]
        )
        low_sensors = low_humidity_sensors(data)
        plant_low = _plant_hum_low(data)
        if sensor_signature != self._sensor_signature:
            exceeded_levels = {s["entity_id"]: lvl for s, lvl in low_sensors}
            exceeded_levels.update({s["entity_id"]: lvl for s, lvl in plant_low})
            self.remove_children()
            for sensor in data["sensors"]:
                level = exceeded_levels.get(sensor["entity_id"], 0)
                self.mount(SensorRow(sensor, level=level))
            self._sensor_signature = sensor_signature

        self.set_loading(False)
        self.border_subtitle = f"[dim]Updated {format_cache_time(cached)}[/]"
        self._apply_humidity_warning(data, low_sensors, plant_low)

    def on_mount(self):
        self.border_title = "In-House Sensors"
        self.set_loading(True)
        self._check_cache()
        self.set_interval(config["tuiRefreshInterval"], self._check_cache)

    def refresh_data(self):
        self._cache_mtime = 0
        self._check_cache()

    def on_cache_changed(self, event: CacheChanged):
        if event.cache_name == self.CACHE_FILE:
            self.refresh_data()

    def on_click(self, event):
        if event.widget is not self or event.y != 0:
            return
        if time.time() - cache_mtime(self.CACHE_FILE) < 60:
            return
        self.border_subtitle = "[dim]Refreshing...[/]"
        touch_trigger("_trigger_sensors")
