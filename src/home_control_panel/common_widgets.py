from textual.widgets import Label
from home_control_panel.libs.utils import config

class ScrollingLabel(Label):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._position = config["train"]["message"]["margin"]
        self._last_offset = 0
        self._last_parent_width = None
        self._last_text_width = None

    def reset_scroll(self):
        self._position = config["train"]["message"]["margin"]
        self.styles.offset = 0, 0
        self._last_offset = 0

    def scroll(self):
        margin = config["train"]["message"]["margin"]
        parent = self.parent
        if parent is None:
            return
        content_w = parent.size.width  # pyright: ignore[reportAttributeAccessIssue]
        text_w = self.content_size.width or self.size.width
        if (content_w, text_w) != (self._last_parent_width, self._last_text_width):
            self.reset_scroll()
            self._last_parent_width = content_w
            self._last_text_width = text_w
        if text_w <= content_w:
            self.reset_scroll()
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
        self.set_interval(config["train"]["message"]["scrollSpeed"], self.scroll)

    def on_resize(self):
        self.reset_scroll()
        self.scroll()
