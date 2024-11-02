#!/usr/bin/env python3
from textual.app import App
from textual.containers import ScrollableContainer
from textual.widgets import *
from libs.utils import *
from train import Train
from weather import Weather

logger = logging.getLogger(__name__)

class HomeApp(App):
    BINDINGS = [
        ("d", "toggle_dark_mode" ,"Toggle dark mode"),
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh")
    ]
    CSS_PATH = "style.css"

    def on_mount(self):
        self.title = config["title"]

    def compose(self):
        # yield Header(show_clock=True)
        yield Train(id="train")
        yield Weather(id="weather")
        # yield Footer()

    def action_toggle_dark_mode(self):
        self.dark = not self.dark

    def action_quit(self):
        exit()
    
    def action_refresh(self):
        self.query_one("TrainStationMessage").refresh_message()
        # TODO: refresh train schedule
        # TODO: refresh weather

if __name__ == "__main__":
    HomeApp().run()