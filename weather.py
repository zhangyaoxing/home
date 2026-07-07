import logging

from textual import work
from textual.widgets import Label, DataTable, Static

from libs.weather_api import api_weather
from libs.utils import load_config

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
            "uvindex": WeatherElement(label="UV Index: "),
            "sunrise": WeatherElement(label="Sunrise / Sunset: ")
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
        elms["temp"].text = "{temp}\u00B0C feels like {fl}\u00B0C".format(temp=current["temp"], fl=current["feelslike"])
        elms["humidity"].text = "{hum}%".format(hum=current["humidity"])
        elms["windspeed"].text = "{dir} {speed} / {gust} km/h".format(speed=current["windspeed"], gust=current["windgust"], dir=winddir(current["winddir"]))
        elms["cloudcover"].text = "{cloud}%".format(cloud=current["cloudcover"])
        elms["uvindex"].text = str(current["uvindex"])
        elms["sunrise"].text = "{rise}↑ {set}↓".format(rise=current["sunrise"], set=current["sunset"])

    def show_error(self):
        self._elements["updated"].text = "Unavailable"
        self._elements["conditions"].text = "Weather service unavailable"


class WeatherNext(Static):
    _table = None
    def on_mount(self):
        self.border_title = "Forecast"
        self._table = DataTable(classes="forecast")
        self._table.cursor_type = "none"
        self._table.add_columns(*("Day", "Condition", "Temperature / Feels Like", "Humidity", "Snow", "Wind / Gust", "Cloud", "UV", "Sun"))
        self.mount(self._table)

    def refresh_data(self, data):
        self._table.clear()
        i = 0
        for day in data["days"]:
            self._table.add_row(
                ("today" if i == 0 else "+{i}".format(i=i)),
                "{cond}".format(cond=day["conditions"]),
                "{temp}\u00B0C / {fl}\u00B0C ({min}\u00B0C ~ {max}\u00B0C)".format(temp=day["temp"], fl=day["feelslike"], min=day["tempmin"], max=day["tempmax"]),
                "{hum}%".format(hum=day["humidity"]),
                "{snow} / {depth}m".format(snow=day["snow"], depth=day["snowdepth"]),
                "{dir} {speed} / {gust} km/h".format(speed=day["windspeed"], gust=day["windgust"], dir=winddir(day["winddir"])),
                "{cloud}%".format(cloud=day["cloudcover"]),
                "{uv}".format(uv=day["uvindex"]),
                "{rise}↑ {set}↓".format(rise=day["sunrise"], set=day["sunset"])
            )
            i += 1

    def show_error(self):
        self._table.clear()
        self._table.add_row("Unavailable", "Weather service unavailable")


class Weather(Static):
    _weather_today = None
    _weather_next = None

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
            logger.error(
                "Can't access weather API (%s)",
                type(error).__name__,
            )
            self._weather_today.show_error()
            self._weather_next.show_error()
            self.set_loading(False)
        else:
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
