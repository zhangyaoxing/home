from textual.widgets import *
from libs.weather_api import api_weather
from libs.ha_api import api_ha
from libs.utils import *

config = load_config()
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
    if angle < 22.5 or angle >= 337.5: return "↓"
    if angle >= 22.5 and angle < 67.5: return "↙️"
    if angle >= 67.5 and angle < 112.5: return "←"
    if angle >= 112.5 and angle < 157.5: return "↖️"
    if angle >= 157.5 and angle < 202.5: return "↑"
    if angle >= 202.5 and angle < 247.5: return "↗️"
    if angle >= 247.5 and angle < 292.5: return "→"
    if angle >= 292.5 and angle < 337.5: return "↘️"

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
            "sunrise": WeatherElement(label="Sunrise / Sunset: "),
            "temp_in": WeatherElement(label="Temperature (Room): "),
            "hum_in": WeatherElement(label="Humidity (Room): "),
            "illu_in": WeatherElement(label="Illuminance (Room): ")
        }
        for key in self._elements:
            elm = self._elements[key]
            self.mount(elm)

    def refresh_data(self, data, in_data):
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
        if in_data is not None:
            # Sometimes the in_data returned is None. Not sure why.
            elms["temp_in"].text = ",".join(in_data["temp"])
            elms["hum_in"].text = ",".join(in_data["hum"])
            elms["illu_in"].text = ",".join(in_data["illu"])

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

class Weather(Static):
    _weather_today = None
    _weather_next = None
    def refresh_data(self):
        error, data = api_weather()
        if error == None:
            error, in_data = api_ha()
            self._weather_today.refresh_data(data, in_data)
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