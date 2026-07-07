from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen

from home_control_panel.sensors import HumidityWarningPanel


class WarningScreen(ModalScreen):
    BINDINGS = [
        Binding("q", "app.quit", "Quit", priority=True),
    ]

    def __init__(self, messages):
        super().__init__()
        self._messages = messages

    def compose(self) -> ComposeResult:
        yield HumidityWarningPanel(title="Warning", messages=self._messages)


class WarningManager:
    def __init__(self, app, interval):
        self._app = app
        self._interval = interval
        self._sources = {}
        self._timer = None

    def update(self, source, messages):
        if messages:
            self._sources[source] = messages
        else:
            self._sources.pop(source, None)

        if self._sources:
            if self._timer is None:
                self._toggle()
                self._timer = self._app.set_interval(self._interval, self._toggle)
        else:
            if self._timer is not None:
                self._timer.stop()
                self._timer = None
            self._dismiss()

    def _toggle(self):
        if self._active_screen() is None:
            all_messages = []
            for msgs in self._sources.values():
                all_messages.extend(msgs)
            self._app.push_screen(WarningScreen(all_messages))
        else:
            self._dismiss()

    def _active_screen(self):
        for screen in self._app.screen_stack:
            if isinstance(screen, WarningScreen):
                return screen
        return None

    def _dismiss(self):
        screen = self._active_screen()
        if screen is not None:
            screen.dismiss()
