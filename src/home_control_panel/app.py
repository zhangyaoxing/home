#!/usr/bin/env python3
import logging

from dotenv import load_dotenv

load_dotenv()

from textual.app import App
from textual.binding import Binding
from textual.containers import Horizontal

from home_control_panel.libs.utils import config
from home_control_panel.bus import BusSchedule
from home_control_panel.metro import MetroSchedule
from home_control_panel.sensors import Sensors
from home_control_panel.train import TrainSchedule, TrainStationMessage
from home_control_panel.warning import WarningManager
from home_control_panel.weather import Weather, WeatherChart, WeatherNext

logger = logging.getLogger(__name__)

class HomeApp(App):
    BINDINGS = [
        ("d", "toggle_dark_mode" ,"Toggle dark mode"),
        Binding("q", "quit", "Quit", priority=True),
        ("r", "refresh", "Refresh")
    ]
    CSS_PATH = "assets/style.css"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.warning_manager = WarningManager(
            self, config["warningInterval"],
        )

    def on_mount(self):
        self.title = config["title"]

    def compose(self):
        # yield Header(show_clock=True)
        yield TrainSchedule(id="schedule")
        with Horizontal(id="right_panel"):
            yield TrainStationMessage(id="message")
            yield BusSchedule(id="bus")
            yield MetroSchedule(id="metro")
        yield WeatherNext(id="weather_next")
        yield Sensors(id="sensors")
        yield WeatherChart(id="weather_chart")
        yield Weather(id="weather")
        # yield Footer()

    def action_toggle_dark_mode(self):
        self.dark = not self.dark

    def action_refresh(self):
        self.query_one("#message", TrainStationMessage).refresh_message()
        self.query_one("#schedule", TrainSchedule).refresh_schedule()
        self.query_one("#metro", MetroSchedule).refresh_metro()
        self.query_one("#bus", BusSchedule).refresh_bus()
        self.query_one("#weather", Weather).refresh_data()
        self.query_one("#sensors", Sensors).refresh_data()

def main():
    logger.info("Starting HomeApp...")
    HomeApp().run()

if __name__ == "__main__":
    main()
