import logging

from textual import work
from textual.widgets import DataTable, Static

from home_control_panel.libs.weather_api import api_weather
from home_control_panel.libs.utils import load_config

logger = logging.getLogger(__name__)
config = load_config()
WIND_DIRECTIONS = ("↓", "↙", "←", "↖", "↑", "↗", "→", "↘")


def winddir(angle):
    return WIND_DIRECTIONS[int((angle + 22.5) // 45) % len(WIND_DIRECTIONS)]


class WeatherNext(Static):
    _table = None

    def on_mount(self):
        self.border_title = "Forecast"
        self._table = DataTable(classes="forecast")
        self._table.cursor_type = "none"
        self._table.add_columns(
            *("\U0001F4C5", "\u26c5\ufe0f", "\U0001F321", "\U0001F4A7",
              "\U0001F4A8", "\u2601\ufe0f", "\U0001F441",
              "\u2614\ufe0f", "\u2744\ufe0f", "\u26a1\ufe0f")
        )
        self.mount(self._table)

    def refresh_data(self, data):
        self._table.clear()
        current = data["currentConditions"]
        self._table.add_row(
            "Now",
            current["conditions"],
            "{temp}\u00B0C".format(temp=current["temp"]),
            "{hum}%".format(hum=current["humidity"]),
            "{dir} {speed} / {gust} km/h".format(
                speed=current["windspeed"],
                gust=current["windgust"],
                dir=winddir(current["winddir"]),
            ),
            "{cloud}%".format(cloud=current["cloudcover"]),
            "{vis} km".format(vis=current["visibility"]),
            "{p}%".format(p=current["precip_probability"]),
            "{p}%".format(p=current["frozen_probability"]),
            "{p}%".format(p=current["thunderstorm_probability"]),
        )
        for i, day in enumerate(data["days"]):
            self._table.add_row(
                "today" if i == 0 else "+{i}".format(i=i),
                day["conditions"],
                "{temp}\u00B0C ({min}\u00B0C ~ {max}\u00B0C)".format(
                    temp=day["temp"], min=day["tempmin"], max=day["tempmax"],
                ),
                "{hum}%".format(hum=day["humidity"]),
                "{dir} {speed} / {gust} km/h".format(
                    speed=day["windspeed"],
                    gust=day["windgust"],
                    dir=winddir(day["winddir"]),
                ),
                "{cloud}%".format(cloud=day["cloudcover"]),
                "{vis} km".format(vis=day["visibility"]),
                "{p}%".format(p=day["precip_probability"]),
                "{p}%".format(p=day["frozen_probability"]),
                "{p}%".format(p=day["thunderstorm_probability"]),
            )

    def show_error(self):
        self._table.clear()
        self._table.add_row("Unavailable", "Weather service unavailable")


class Weather(Static):
    _weather_next = None
    _last_error = False

    @work(
        thread=True,
        group="weather-refresh",
        exclusive=True,
        exit_on_error=False,
    )
    def refresh_data(self):
        error, data = api_weather()
        self.app.call_from_thread(self._apply_refresh, error, data)

    def _apply_refresh(self, error, data):
        if error is not None:
            if not self._last_error:
                logger.error(
                    "Can't access weather API (%s)",
                    type(error).__name__,
                )
            self._last_error = True
            self._weather_next.show_error()
            self.set_loading(False)
        else:
            self._last_error = False
            self._weather_next.refresh_data(data)
            self.set_loading(False)

    def on_mount(self):
        self.set_loading(True)
        self.border_title = "Weather Forecast"
        self.border_subtitle = "Stockholm"
        self._weather_next = WeatherNext(id="weather_next")
        self.mount(self._weather_next)

        self.set_timer(1, self.refresh_data)
        self.set_interval(config["weatherRefreshInterval"], self.refresh_data)
