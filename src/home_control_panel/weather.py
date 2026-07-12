import logging
from datetime import datetime as dt, timedelta

from rich.text import Text
from textual.widgets import DataTable, Static
from textual_hires_canvas import Canvas, HiResMode, TextAlign

from home_control_panel.libs.cache import (
    CacheChanged,
    cache_mtime,
    format_cache_time,
    read_cache,
)
from home_control_panel.libs.utils import load_config

logger = logging.getLogger(__name__)
config = load_config()
WIND_DIRECTIONS = ("↓", "↙", "←", "↖", "↑", "↗", "→", "↘")
PROB_THRESHOLDS = config["weather"]["probabilityWarningThreshold"]
PROB_WARNING_LOOKAHEAD_HOURS = 6
CHART_AXIS_STYLE = "#666666"


def _prob_level(value):
    if value > PROB_THRESHOLDS[2]:
        return 3
    if value > PROB_THRESHOLDS[1]:
        return 2
    if value > PROB_THRESHOLDS[0]:
        return 1
    return 0


def winddir(angle):
    return WIND_DIRECTIONS[int((angle + 22.5) // 45) % len(WIND_DIRECTIONS)]


def _fmt_prob(value):
    level = _prob_level(value)
    colors = {1: "green", 2: "yellow", 3: "red"}
    style = f"bold {colors[level]}" if level else ""
    return Text(f"{value:.0f}%", style=style)


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


def _format_forecast_day_label(date, index):
    return _format_day_label_with_weekday(date, index, "%a")


def _format_day_label_with_weekday(date, index, weekday_format):
    if index == 0:
        return "Today"
    if not date:
        return ""
    return f"{dt.strptime(date, '%Y-%m-%d').strftime(weekday_format)} +{index}"


class WeatherNext(Static):
    _table: DataTable | None = None

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
        if self._table is None:
            return
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
        if self._table is None:
            return
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
        self._hourly: dict | None = None

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
        axis_right_x = 0
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
                    assert self._right_ylim is not None
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
        non_empty = [(i, h) for i, h in enumerate(hours) if h]
        if not non_empty:
            return
        for index, label in non_empty:
            normalized = index / max(len(hours) - 1, 1)
            x = round(plot_left + normalized * (plot_right - plot_left))
            self.set_pixel(x, plot_bottom, char="┬", style=CHART_AXIS_STYLE)
            self.write_text(x, self.size.height - 1, f"[dim]{label}[/]", align=TextAlign.CENTER)

    @staticmethod
    def _tick_values(start, end, count):
        if count <= 1:
            return [start]
        step = (end - start) / (count - 1)
        return [start + step * i for i in range(count)]


class WeatherChart(Static):
    _metrics: list[WeatherMetricChart] | None = None
    _hourly_days: list[dict] | None = None

    def on_mount(self):
        self.border_title = "Weather Charts"
        self._metrics = [
            WeatherMetricChart(
                [
                    {"label": "Temp °C", "key": "temp", "color": (255, 100, 100)},
                    {"label": "Humidity %", "key": "humidity", "color": (100, 100, 255), "axis": "right"},
                ],
                (0, 45),
                right_ylim=(0, 100),
            ),
            WeatherMetricChart(
                [
                    {"label": "Rain %", "key": "precip_probability", "color": (100, 200, 255)},
                    {"label": "Snow %", "key": "frozen_probability", "color": (200, 200, 255)},
                    {"label": "Thunder %", "key": "thunderstorm_probability", "color": (255, 255, 100)},
                ],
                (0, 100),
            ),
        ]
        for metric in self._metrics:
            self.mount(metric)
        if self._hourly_days is not None:
            self.refresh_data(self._hourly_days)

    def refresh_data(self, hourly_days):
        self._hourly_days = hourly_days or []
        self._show_all_days()

    def _show_all_days(self):
        if self._metrics is None:
            return
        if not self._hourly_days:
            for metric in self._metrics:
                metric.refresh_data(None)
            return
        combined = self._merge_days(self._hourly_days)
        self.border_subtitle = ""
        for metric in self._metrics:
            metric.refresh_data(combined)

    @staticmethod
    def _merge_days(hourly_days):
        keys = ["temp", "precip_probability", "frozen_probability", "thunderstorm_probability", "humidity"]
        merged = {"hours": [], "datetimes": []}
        for k in keys:
            merged[k] = []
        for day_index, day in enumerate(hourly_days):
            date = day.get("date", "")
            if day_index == 0:
                day_name = "Today"
            elif date:
                day_name = dt.strptime(date, "%Y-%m-%d").strftime("%a")
            else:
                day_name = ""
            hours = day.get("hours", [])
            for i, h in enumerate(hours):
                label = WeatherChart._hour_label(day_index, day_name, h, i == 0)
                merged["hours"].append(label)
            merged["datetimes"].extend(day.get("datetimes", []))
            for k in keys:
                merged[k].extend(day.get(k, []))
        return merged

    @staticmethod
    def _hour_label(day_index, day_name, hour_str, is_first):
        if day_index >= 3:
            return day_name if is_first else ""
        hour = int(hour_str.split(":")[0])
        if hour == 0:
            return day_name if is_first or hour_str == "00:00" else ""
        if is_first or hour % 6 == 0:
            return hour_str
        return ""


class Weather(Static):
    CACHE_FILE = "weather.json"
    _weather_next: WeatherNext | None = None
    _weather_chart: WeatherChart | None = None
    _last_error = False
    _cache_mtime = 0

    def _check_cache(self):
        mtime = cache_mtime(self.CACHE_FILE)
        if mtime <= self._cache_mtime:
            return
        self._cache_mtime = mtime
        logger.info("Reloading weather from cache")

        cached = read_cache(self.CACHE_FILE)
        if cached is None:
            if not self._last_error:
                logger.error("Weather cache unavailable")
            self._last_error = True
            if self._weather_next is not None:
                self._weather_next.show_error()
            self.set_loading(False)
            return

        data = cached["data"]
        self._last_error = False
        ts = f"[dim]Updated {format_cache_time(cached)}[/]"
        if self._weather_next is not None:
            self._weather_next.refresh_data(data)
            self._weather_next.border_subtitle = ts
        if self._weather_chart is not None:
            self._weather_chart.refresh_data(data.get("hourlyDetails"))
            self._weather_chart.border_subtitle = ts
        self._check_probability_warning(data)
        self.set_loading(False)

    def _check_probability_warning(self, data):
        prob_keys = [
            ("precip_probability", "\u2614\ufe0f"),
            ("frozen_probability", "\u2744\ufe0f"),
            ("thunderstorm_probability", "\u26a1\ufe0f"),
        ]
        hourly_details = data.get("hourlyDetails", [])
        messages = []
        level = 0
        for key, icon in prob_keys:
            next_max = self._max_in_next_hours(
                hourly_details, key, PROB_WARNING_LOOKAHEAD_HOURS
            )
            prob_level = _prob_level(next_max)
            if prob_level:
                messages.append(
                    f"{icon} {next_max:.0f}% next {PROB_WARNING_LOOKAHEAD_HOURS}h"
                )
                level = max(level, prob_level)
        self.app.warning_manager.update(  # pyright: ignore[reportAttributeAccessIssue]
            "weather", messages, level=level if level > 0 else 3,
        )

    @staticmethod
    def _max_in_next_hours(hourly_details, key, hours):
        max_value = 0
        for hourly in hourly_details:
            datetimes = hourly.get("datetimes", [])
            values = hourly.get(key, [])
            for time, value in zip(datetimes, values):
                try:
                    forecast_time = dt.fromisoformat(time)
                except ValueError:
                    continue
                now = dt.now(forecast_time.tzinfo) if forecast_time.tzinfo else dt.now()
                window_end = now + timedelta(hours=hours)
                if now <= forecast_time <= window_end and value > max_value:
                    max_value = value
        return max_value

    def on_mount(self):
        self._weather_next = self.app.query_one("#weather_next", WeatherNext)
        self._weather_chart = self.app.query_one("#weather_chart", WeatherChart)

        self._check_cache()
        self.set_interval(config["tuiRefreshInterval"], self._check_cache)

    def refresh_data(self):
        self._cache_mtime = 0
        self._check_cache()

    def on_cache_changed(self, event: CacheChanged):
        if event.cache_name == self.CACHE_FILE:
            self.refresh_data()
