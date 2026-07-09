from textual.widgets import Label
from home_control_panel.libs.utils import config

class ScrollingLabel(Label):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._position = config["message"]["margin"]
        self._last_offset = 0

    def reset_scroll(self):
        self._position = config["message"]["margin"]
        if self._last_offset != 0:
            self.styles.offset = 0, 0
            self._last_offset = 0

    def scroll(self):
        margin = config["message"]["margin"]
        parent = self.parent
        if parent is None:
            return
        content_w = parent.size.width  # pyright: ignore[reportAttributeAccessIssue]
        text_w = self.size.width
        if text_w <= content_w:
            return
        self._position -= 1
        if self._position < 0 and text_w + self._position >= content_w:
            if self._position != self._last_offset:
                self.styles.offset = self._position, 0
                self._last_offset = self._position
        elif text_w + self._position < content_w - margin:
            self._position = margin
            if self._last_offset != 0:
                self.styles.offset = 0, 0
                self._last_offset = 0

    def on_mount(self):
        self.set_interval(config["message"]["scrollSpeed"], self.scroll)

    def on_resize(self):
        self.reset_scroll()
        self.scroll()
