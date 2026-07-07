import logging
from datetime import datetime as dt

from rich.text import Text
from textual import work
from textual.widgets import DataTable, Static
from textual_hires_canvas import Canvas, HiResMode, TextAlign

from home_control_panel.libs.weather_api import api_weather
from home_control_panel.libs.utils import load_config

logger = logging.getLogger(__name__)
config = load_config()
WIND_DIRECTIONS = ("↓", "↙", "←", "↖", "↑", "↗", "→", "↘")
PROB_THRESHOLD = config["probabilityWarningThreshold"]
CHART_AXIS_STYLE = "#666666"


def winddir(angle):
    return WIND_DIRECTIONS[int((angle + 22.5) // 45) % len(WIND_DIRECTIONS)]


def _fmt_prob(value):
    return Text(
        "{p:.0f}%".format(p=value), style="bold red" if value > PROB_THRESHOLD else ""
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


def _format_day_label(date, index):
    return _format_day_label_with_weekday(date, index, "%A")


def _format_forecast_day_label(date, index):
    return _format_day_label_with_weekday(date, index, "%a")


def _format_day_label_with_weekday(date, index, weekday_format):
    if index == 0:
        return "Today"
    if not date:
        return ""
    return f"{dt.strptime(date, '%Y-%m-%d').strftime(weekday_format)} +{index}"


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
                _format_forecast_day_label(day["date"], i),
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


class WeatherMetricChart(Canvas):
    def __init__(self, series, ylim, right_ylim=None):
        super().__init__(
            default_hires_mode=HiResMode.BRAILLE,
            classes="weather_metric_chart",
        )
        self._series = [
            {
                "label": s["label"],
                "key": s["key"],
                "style": "#{:02x}{:02x}{:02x}".format(*s["color"]),
                "axis": s.get("axis", "left"),
            }
            for s in series
        ]
        self._ylim = ylim
        self._right_ylim = right_ylim
        self._hourly = None

    def refresh_data(self, hourly):
        self._hourly = hourly
        self._render_chart()

    def on_resize(self):
        self._render_chart()

    def _render_chart(self):
        hourly = self._hourly
        self.reset(size=self.size, refresh=False)
        if not hourly or not hourly.get("hours"):
            self.refresh()
            return
        if self.size.width < 10 or self.size.height < 4:
            return

        series_data = []
        for s in self._series:
            values = hourly.get(s["key"])
            if values:
                series_data.append({**s, "values": values})

        if not series_data:
            self.refresh()
            return

        has_right_axis = self._right_ylim is not None
        axis_x = 4
        plot_left = axis_x + 1
        plot_right = self.size.width - 1
        if has_right_axis:
            plot_right = self.size.width - 5
        plot_top = 1
        plot_bottom = self.size.height - 2
        if plot_right <= plot_left or plot_bottom <= plot_top:
            self.refresh()
            return

        with self.batch_refresh():
            title_parts = []
            for s in series_data:
                v = s["values"]
                title_parts.append(f"[{s['style']}]{s['label']} {min(v):g}-{max(v):g}[/]")
            self.write_text(
                self.size.width // 2,
                0,
                " ".join(title_parts),
                align=TextAlign.CENTER,
            )
            self.draw_line(
                axis_x,
                plot_top,
                axis_x,
                plot_bottom,
                char="│",
                style=CHART_AXIS_STYLE,
            )
            if has_right_axis:
                axis_right_x = plot_right + 1
                self.draw_line(
                    axis_right_x,
                    plot_top,
                    axis_right_x,
                    plot_bottom,
                    char="│",
                    style=CHART_AXIS_STYLE,
                )
            self.draw_line(
                axis_x,
                plot_bottom,
                plot_right,
                plot_bottom,
                char="─",
                style=CHART_AXIS_STYLE,
            )
            self.set_pixel(
                axis_x,
                plot_bottom,
                char="└",
                style=CHART_AXIS_STYLE,
            )
            if has_right_axis:
                self.draw_line(
                    plot_right,
                    plot_bottom,
                    axis_right_x,
                    plot_bottom,
                    char="─",
                    style=CHART_AXIS_STYLE,
                )
                self.set_pixel(
                    axis_right_x,
                    plot_bottom,
                    char="┘",
                    style=CHART_AXIS_STYLE,
                )

            for s in series_data:
                values = s["values"]
                if s["axis"] == "right":
                    y_min, y_max = self._right_ylim
                else:
                    y_min, y_max = self._ylim
                y_span = y_max - y_min
                x_span = max(len(values) - 1, 1)
                points = []
                for i, value in enumerate(values):
                    x = plot_left + (i / x_span) * (plot_right - plot_left)
                    normalized = (value - y_min) / y_span if y_span else 0
                    normalized = min(max(normalized, 0), 1)
                    y = plot_bottom - normalized * (plot_bottom - plot_top)
                    points.append((x, y))

                lines = [
                    (x0, y0, x1, y1)
                    for (x0, y0), (x1, y1) in zip(points, points[1:])
                ]
                self.draw_hires_lines(lines, hires_mode=HiResMode.BRAILLE, style=s["style"])

            hours = hourly["hours"]
            self._draw_y_ticks(self._ylim, plot_top, plot_bottom, axis_x, "left")
            if has_right_axis:
                self._draw_y_ticks(self._right_ylim, plot_top, plot_bottom, axis_right_x, "right")
            self._draw_x_ticks(hours, plot_left, plot_right, plot_bottom)
        self.refresh()

    def _draw_y_ticks(self, ylim, plot_top, plot_bottom, axis_x, side):
        y_min, y_max = ylim
        for value in self._tick_values(y_min, y_max, 3):
            normalized = (value - y_min) / (y_max - y_min) if y_max != y_min else 0
            y = round(plot_bottom - normalized * (plot_bottom - plot_top))
            if side == "left":
                label = f"{value:g}".rjust(axis_x)
                self.write_text(0, y, f"[dim]{label}[/]")
                self.set_pixel(axis_x, y, char="┤", style=CHART_AXIS_STYLE)
            else:
                label = f"{value:g}".ljust(3)
                self.write_text(axis_x + 1, y, f"[dim]{label}[/]")
                self.set_pixel(axis_x, y, char="├", style=CHART_AXIS_STYLE)

    def _draw_x_ticks(self, hours, plot_left, plot_right, plot_bottom):
        if not hours:
            return
        for index in self._tick_indexes(len(hours), 4):
            normalized = index / max(len(hours) - 1, 1)
            x = round(plot_left + normalized * (plot_right - plot_left))
            self.set_pixel(x, plot_bottom, char="┬", style=CHART_AXIS_STYLE)
            align = TextAlign.CENTER
            if index == 0:
                align = TextAlign.LEFT
            elif index == len(hours) - 1:
                align = TextAlign.RIGHT
            self.write_text(x, self.size.height - 1, f"[dim]{hours[index]}[/]", align=align)

    @staticmethod
    def _tick_values(start, end, count):
        if count <= 1:
            return [start]
        step = (end - start) / (count - 1)
        return [start + step * i for i in range(count)]

    @staticmethod
    def _tick_indexes(length, count):
        if length <= 1:
            return [0]
        count = min(count, length)
        return sorted({round(i * (length - 1) / (count - 1)) for i in range(count)})


class WeatherChart(Static):
    _metrics = None
    _hourly_days = None
    _day_index = 0

    def on_mount(self):
        self.border_title = "Weather Details"
        self._metrics = [
            WeatherMetricChart(
                [
                    {"label": "Temp", "key": "temp", "color": (255, 100, 100)},
                    {"label": "Humidity", "key": "humidity", "color": (100, 100, 255), "axis": "right"},
                ],
                (0, 35),
                right_ylim=(0, 100),
            ),
            WeatherMetricChart(
                [
                    {"label": "Rain", "key": "precip_probability", "color": (100, 200, 255)},
                    {"label": "Snow", "key": "frozen_probability", "color": (200, 200, 255)},
                    {"label": "Thunder", "key": "thunderstorm_probability", "color": (255, 255, 100)},
                ],
                (0, 100),
            ),
        ]
        for metric in self._metrics:
            self.mount(metric)
        self.set_interval(config["weatherDetailsInterval"], self.show_next_day)
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
        self.border_title = f"Weather Details {day_label}"
        self.border_subtitle = ""
        for metric in self._metrics:
            metric.refresh_data(hourly)

    @staticmethod
    def _format_day_label(date, index):
        return _format_forecast_day_label(date, index)


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
        today_hourly = data.get("hourlyDetails", [{}])[0] if data.get("hourlyDetails") else {}
        messages = []
        for key, icon in prob_keys:
            today_max = self._max_after_now(today_hourly, key)
            if today_max > PROB_THRESHOLD:
                messages.append(f"{icon} {today_max:.0f}% today")
        self.app.warning_manager.update("weather", messages)

    @staticmethod
    def _max_after_now(hourly, key):
        datetimes = hourly.get("datetimes", [])
        values = hourly.get(key, [])
        max_value = 0
        for time, value in zip(datetimes, values):
            try:
                forecast_time = dt.fromisoformat(time)
            except ValueError:
                continue
            now = dt.now(forecast_time.tzinfo) if forecast_time.tzinfo else dt.now()
            if forecast_time >= now and value > max_value:
                max_value = value
        return max_value

    def on_mount(self):
        self._weather_next = self.app.query_one("#weather_next", WeatherNext)
        self._weather_chart = self.app.query_one("#weather_chart", WeatherChart)

        self.set_timer(1, self.refresh_data)
        self.set_interval(config["weatherRefreshInterval"], self.refresh_data)
