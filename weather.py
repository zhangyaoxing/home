from textual.widgets import *
from libs.weather_api import api_weather
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

class WeatherToday(Static):
    _elements = {}
    def on_mount(self):
        self._elements = {
            "updated": WeatherElement(label="Updated: "),
            "conditions": WeatherElement(label="Conditions: "),
            "temp": WeatherElement(label="Temperature: "),
            "humidity": WeatherElement(label="Humidity: "),
            "windspeed": WeatherElement(label="Wind (gust): "),
            "cloudcover": WeatherElement(label="Cloud cover: "),
            "uvindex": WeatherElement(label="UV Index: "),
            "sunrise": WeatherElement(label="Sunrise / Sunset: ")
        }
        for key in self._elements:
            elm = self._elements[key]
            self.mount(elm)

    def refresh_data(self, data):
        def winddir(angle):
            if angle < 22.5 or angle >= 337.5: return "↓"
            if angle >= 22.5 and angle < 67.5: return "↙️"
            if angle >= 67.5 and angle < 112.5: return "←"
            if angle >= 112.5 and angle < 157.5: return "↖️"
            if angle >= 157.5 and angle < 202.5: return "↑"
            if angle >= 202.5 and angle < 247.5: return "↗️"
            if angle >= 247.5 and angle < 292.5: return "→"
            if angle >= 292.5 and angle < 337.5: return "↘️"
        self._data = data
        current = self._data["currentConditions"]
        elms = self._elements
        elms["updated"].text = current["datetime"]
        elms["conditions"].text = current["conditions"]
        elms["temp"].text = "{temp}\u00B0C feels like {fl}\u00B0C".format(temp=current["temp"], fl=current["feelslike"])
        elms["humidity"].text = "{hum}%".format(hum=current["humidity"])
        elms["windspeed"].text = "{dir}{speed} km/h ({gust} km/h)".format(speed=current["windspeed"], gust=current["windgust"], dir=winddir(current["winddir"]))
        elms["cloudcover"].text = "{cloud}%".format(cloud=current["cloudcover"])
        elms["uvindex"].text = str(current["uvindex"])
        elms["sunrise"].text = "{rise} / {set}".format(rise=current["sunrise"], set=current["sunset"])

class Weather(Static):
    _weather = None
    def refresh_data(self):
        error, data = api_weather()
        if error == None:
            self._weather.refresh_data(data)
            # TODO: refresh forcast
    def on_mount(self):
        self.border_title = "Weather"
        self._weather = WeatherToday(id="weather_today")
        self.mount(self._weather)
        
        self.set_timer(1, self.refresh_data)
        self.set_interval(config["weatherRefreshInterval"], self.refresh_data)