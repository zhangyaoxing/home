from textual.widgets import *
from libs.utils import *

class ScrollingLabel(Label):
    position = config["message"]["margin"]
    def scroll(self):
        margin = config["message"]["margin"]
        content_w = self.parent.get_visible_size().width
        self.position -= 1
        if self.position < 0 and self.size.width + self.position >= content_w:
            self.styles.offset = self.position, 0
        if self.size.width + self.position < content_w - margin:
            self.styles.offset = 0, 0
            self.position = config["message"]["margin"]
    
    def on_mount(self):
        self.set_interval(config["message"]["scrollSpeed"], self.scroll)