import logging
from datetime import datetime as dt

from rich.text import Text
from textual import work
from textual.widgets import DataTable, Static

from home_control_panel.libs.weather_api import api_weather
from home_control_panel.libs.utils import load_config

logger = logging.getLogger(__name__)
config = load_config()
WIND_DIRECTIONS = ("↓", "↙", "←", "↖", "↑", "↗", "→", "↘")
PROB_THRESHOLD = config["probabilityWarningThreshold"]


def winddir(angle):
    return WIND_DIRECTIONS[int((angle + 22.5) // 45) % len(WIND_DIRECTIONS)]


def _fmt_prob(value):
    return Text(
        "{p:.0f}%".format(p=value), style="red" if value > PROB_THRESHOLD else ""
    )


def _fmt_temp(t):
    return "{t:05.2f}\u00b0C".format(t=t)


def _fmt_hum(h):
    return "{h:2.0f}%".format(h=h)


def _fmt_wind(speed, gust, wdir):
    return "{dir} {speed:04.1f} / {gust:04.1f} km/h".format(
        dir=winddir(wdir), speed=speed, gust=gust
    )


def _fmt_cloud(c):
    return "{c:3.0f}%".format(c=c)


def _fmt_vis(v):
    return "{v:04.1f} km".format(v=v)


class WeatherNext(Static):
    _table = None

    def on_mount(self):
        self.border_title = "Forecast"
        self._table = DataTable(classes="forecast")
        self._table.cursor_type = "none"
        self._table.add_columns(
            *(
                "\U0001f4c5",
                "\u26c5\ufe0f",
                "\U0001f321",
                "\U0001f4a7",
                "\U0001f4a8",
                "\u2601\ufe0f",
                "\U0001f441",
                "\u2614\ufe0f",
                "\u2744\ufe0f",
                "\u26a1\ufe0f",
            )
        )
        self.mount(self._table)

    def refresh_data(self, data):
        self._table.clear()
        current = data["currentConditions"]
        self._table.add_row(
            "Now",
            current["conditions"],
            _fmt_temp(current["temp"]),
            _fmt_hum(current["humidity"]),
            _fmt_wind(current["windspeed"], current["windgust"], current["winddir"]),
            _fmt_cloud(current["cloudcover"]),
            _fmt_vis(current["visibility"]),
            _fmt_prob(current["precip_probability"]),
            _fmt_prob(current["frozen_probability"]),
            _fmt_prob(current["thunderstorm_probability"]),
        )
        for i, day in enumerate(data["days"]):
            self._table.add_row(
                "Today" if i == 0 else dt.strptime(day["date"], "%Y-%m-%d").strftime("%a"),
                day["conditions"],
                "{t} ({tmin} ~ {tmax})".format(
                    t=_fmt_temp(day["temp"]),
                    tmin=_fmt_temp(day["tempmin"]),
                    tmax=_fmt_temp(day["tempmax"]),
                ),
                _fmt_hum(day["humidity"]),
                _fmt_wind(day["windspeed"], day["windgust"], day["winddir"]),
                _fmt_cloud(day["cloudcover"]),
                _fmt_vis(day["visibility"]),
                _fmt_prob(day["precip_probability"]),
                _fmt_prob(day["frozen_probability"]),
                _fmt_prob(day["thunderstorm_probability"]),
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
            self._check_probability_warning(data)
            self.set_loading(False)

    def _check_probability_warning(self, data):
        prob_keys = [
            ("precip_probability", "\u2614\ufe0f"),
            ("frozen_probability", "\u2744\ufe0f"),
            ("thunderstorm_probability", "\u26a1\ufe0f"),
        ]
        current = data["currentConditions"]
        today = data["days"][0] if data["days"] else {}
        messages = []
        for key, icon in prob_keys:
            if current.get(key, 0) > PROB_THRESHOLD:
                messages.append(f"{icon} {current[key]:.0f}% now")
            elif today.get(key, 0) > PROB_THRESHOLD:
                messages.append(f"{icon} {today[key]:.0f}% today")
        self.app.warning_manager.update("weather", messages)

    def on_mount(self):
        self.set_loading(True)
        self.border_title = "Weather Forecast"
        self.border_subtitle = "Stockholm"
        self._weather_next = WeatherNext(id="weather_next")
        self.mount(self._weather_next)

        self.set_timer(1, self.refresh_data)
        self.set_interval(config["weatherRefreshInterval"], self.refresh_data)
