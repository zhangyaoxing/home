import logging

from textual import work
from textual.widgets import Label, DataTable, Static

from home_control_panel.libs.weather_api import api_weather
from home_control_panel.libs.utils import load_config

logger = logging.getLogger(__name__)
config = load_config()
WIND_DIRECTIONS = ("↓", "↙", "←", "↖", "↑", "↗", "→", "↘")


class WeatherElement(Label):
    def __init__(self, label="", text="", **kwargs):
        super().__init__(**kwargs)
        self._label = Label(label, classes="label")
        self._text = Label(text, classes="text")
    def on_mount(self):
        self.mount(self._label)
        self.mount(self._text)

    @property
    def label(self):
        return self._label.renderable
    @label.setter
    def label(self, value):
        self._label.update(value)
    @property
    def text(self):
        return self._text.renderable
    @text.setter
    def text(self, value):
        self._text.update(value)

def winddir(angle):
    return WIND_DIRECTIONS[int((angle + 22.5) // 45) % len(WIND_DIRECTIONS)]

class WeatherToday(Static):
    _elements = {}
    def on_mount(self):
        self.border_title = "Current"
        self._elements = {
            "updated": WeatherElement(label="Updated: "),
            "conditions": WeatherElement(label="Conditions: "),
            "temp": WeatherElement(label="Temperature: "),
            "humidity": WeatherElement(label="Humidity: "),
            "windspeed": WeatherElement(label="Wind / Gust: "),
            "cloudcover": WeatherElement(label="Cloud cover: "),
        }
        for key in self._elements:
            elm = self._elements[key]
            self.mount(elm)

    def refresh_data(self, data):
        self._data = data
        current = self._data["currentConditions"]
        elms = self._elements
        elms["updated"].text = current["datetime"]
        elms["conditions"].text = current["conditions"]
        elms["temp"].text = "{temp}\u00B0C".format(temp=current["temp"])
        elms["humidity"].text = "{hum}%".format(hum=current["humidity"])
        elms["windspeed"].text = "{dir} {speed} / {gust} km/h".format(speed=current["windspeed"], gust=current["windgust"], dir=winddir(current["winddir"]))
        elms["cloudcover"].text = "{cloud}%".format(cloud=current["cloudcover"])

    def show_error(self):
        self._elements["updated"].text = "Unavailable"
        self._elements["conditions"].text = "Weather service unavailable"


class WeatherNext(Static):
    _table = None
    def on_mount(self):
        self.border_title = "Forecast"
        self._table = DataTable(classes="forecast")
        self._table.cursor_type = "none"
        self._table.add_columns(*("Day", "Condition", "Temp (Min~Max)", "Humidity", "Wind / Gust", "Cloud"))
        self.mount(self._table)

    def refresh_data(self, data):
        self._table.clear()
        i = 0
        for day in data["days"]:
            self._table.add_row(
                ("today" if i == 0 else "+{i}".format(i=i)),
                "{cond}".format(cond=day["conditions"]),
                "{temp}\u00B0C ({min}\u00B0C ~ {max}\u00B0C)".format(temp=day["temp"], min=day["tempmin"], max=day["tempmax"]),
                "{hum}%".format(hum=day["humidity"]),
                "{dir} {speed} / {gust} km/h".format(speed=day["windspeed"], gust=day["windgust"], dir=winddir(day["winddir"])),
                "{cloud}%".format(cloud=day["cloudcover"]),
            )
            i += 1

    def show_error(self):
        self._table.clear()
        self._table.add_row("Unavailable", "Weather service unavailable")


class Weather(Static):
    _weather_today = None
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
            self._weather_today.show_error()
            self._weather_next.show_error()
            self.set_loading(False)
        else:
            self._last_error = False
            self._weather_today.refresh_data(data)
            self._weather_next.refresh_data(data)
            self.set_loading(False)
        
    def on_mount(self):
        self.set_loading(True)
        self.border_title = "Weather Forecast"
        self.border_subtitle = "Stockholm"
        self._weather_today = WeatherToday(id="weather_today")
        self._weather_next = WeatherNext(id="weather_next")
        self.mount(self._weather_today)
        self.mount(self._weather_next)
        
        self.set_timer(1, self.refresh_data)
        self.set_interval(config["weatherRefreshInterval"], self.refresh_data)
