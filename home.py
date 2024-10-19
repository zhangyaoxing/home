from textual.app import App
from textual.containers import ScrollableContainer
from textual.widgets import *
from libs.utils import *
from train import TrainSchedule, TrainStationMessage

logger = logging.getLogger(__name__)

class HomeApp(App):
    BINDINGS = [
        ("d", "toggle_dark_mode" ,"Toggle dark mode"),
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh")
    ]
    CSS_PATH = "train_info.css"

    def on_mount(self):
        self.title = config["title"]

    def compose(self):
        yield Header(show_clock=True)
        with ScrollableContainer(id="layout"):
            yield TrainSchedule(id="schedule")
            yield TrainStationMessage(id="message")
        yield Footer()

    def action_toggle_dark_mode(self):
        self.dark = not self.dark

    def action_quit(self):
        exit()
    
    def action_refresh(self):
        self.query_one("TrainStationMessage").refresh_message()

if __name__ == "__main__":
    HomeApp().run()