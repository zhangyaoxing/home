#!/usr/bin/env python3
import logging

from dotenv import load_dotenv

load_dotenv()

from textual.app import App
from textual.binding import Binding

from home_control_panel.libs.utils import config
from home_control_panel.sensors import Sensors
from home_control_panel.train import Train, TrainSchedule, TrainStationMessage
from home_control_panel.weather import Weather

logger = logging.getLogger(__name__)

class HomeApp(App):
    BINDINGS = [
        ("d", "toggle_dark_mode" ,"Toggle dark mode"),
        Binding("q", "quit", "Quit", priority=True),
        ("r", "refresh", "Refresh")
    ]
    CSS_PATH = "assets/style.css"

    def on_mount(self):
        self.title = config["title"]

    def compose(self):
        # yield Header(show_clock=True)
        yield Train(id="train")
        yield Sensors(id="sensors")
        yield Weather(id="weather")
        # yield Footer()

    def action_toggle_dark_mode(self):
        self.dark = not self.dark

    def action_quit(self):
        self.exit()
    
    def action_refresh(self):
        self.query_one("#message", TrainStationMessage).refresh_message()
        self.query_one("#schedule", TrainSchedule).refresh_schedule()
        self.query_one("#weather", Weather).refresh_data()
        self.query_one("#sensors", Sensors).refresh_data()

def main():
    logger.info("Starting HomeApp...")
    HomeApp().run()

if __name__ == "__main__":
    main()
