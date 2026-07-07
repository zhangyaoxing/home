import logging
from datetime import datetime as dt

import plotext as plt
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


class WeatherMetricChart(Static):
    def __init__(self, label, key, color, ylim):
        super().__init__(classes="weather_metric_chart")
        self._label = label
        self._key = key
        self._color = color
        self._ylim = ylim
        self._hourly = None

    def refresh_data(self, hourly):
        self._hourly = hourly
        self._render_chart()

    def on_resize(self):
        self._render_chart()

    def _render_chart(self):
        hourly = self._hourly
        if not hourly or not hourly.get("hours"):
            self.update("No data")
            return
        if self.size.width < 10 or self.size.height < 4:
            return
        width = max(self.size.width - 1, 10)
        height = max(self.size.height - 1, 4)
        plt.clear_data()
        plt.plotsize(width, height)
        x = list(range(len(hourly["hours"])))
        plt.plot(x, hourly[self._key], color=self._color)
        plt.ylim(*self._ylim)
        tick_step = max(len(x) // 2, 1)
        ticks = {i: hourly["hours"][i] for i in range(0, len(x), tick_step)}
        plt.xticks(list(ticks.keys()), list(ticks.values()))
        plt.grid(True, False)

        chart = Text(self._label + "\n")
        chart.append_text(Text.from_ansi(plt.build()))
        self.update(chart)


class WeatherChart(Static):
    _metrics = None
    _hourly_days = None
    _day_index = 0

    def on_mount(self):
        self.border_title = "Details"
        self._metrics = [
            WeatherMetricChart("Temp °C", "temp", (255, 100, 100), (0, 35)),
            WeatherMetricChart("Humidity %", "humidity", (100, 100, 255), (0, 100)),
            WeatherMetricChart("Rain %", "precip_probability", (100, 200, 255), (0, 100)),
            WeatherMetricChart("Snow %", "frozen_probability", (200, 200, 255), (0, 100)),
            WeatherMetricChart("Thunder %", "thunderstorm_probability", (255, 255, 100), (0, 100)),
        ]
        for metric in self._metrics:
            self.mount(metric)
        self.set_interval(30, self.show_next_day)
        if self._hourly_days is not None:
            self.refresh_data(self._hourly_days)

    def refresh_data(self, hourly_days):
        self._hourly_days = hourly_days or []
        self._day_index = 0
        self._show_current_day()

    def show_next_day(self):
        if not self._hourly_days:
            return
        self._day_index = (self._day_index + 1) % len(self._hourly_days)
        self._show_current_day()

    def _show_current_day(self):
        if self._metrics is None:
            return
        if not self._hourly_days:
            for metric in self._metrics:
                metric.refresh_data(None)
            return
        hourly = self._hourly_days[self._day_index]
        day_label = self._format_day_label(hourly.get("date"), self._day_index)
        self.border_title = f"Details {day_label}"
        self.border_subtitle = ""
        for metric in self._metrics:
            metric.refresh_data(hourly)

    @staticmethod
    def _format_day_label(date, index):
        if index == 0:
            return "Today"
        if not date:
            return ""
        return dt.strptime(date, "%Y-%m-%d").strftime("%a")


class Weather(Static):
    _weather_next = None
    _weather_chart = None
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
            self._weather_chart.refresh_data(data.get("hourlyDetails"))
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
        self._weather_chart = WeatherChart(id="weather_chart")
        self.mount(self._weather_next)
        self.mount(self._weather_chart)

        self.set_timer(1, self.refresh_data)
        self.set_interval(config["weatherRefreshInterval"], self.refresh_data)
