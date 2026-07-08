WARNING_CLASSES = {
    1: "panel-warning-level1",
    2: "panel-warning-level2",
    3: "panel-warning-active",
}


class WarningManager:
    BLINK_INTERVAL = 1
    TARGETS = {
        "sensors": "#sensors",
        "weather": "#weather_next",
    }

    def __init__(self, app, interval):
        self._app = app
        self._interval = self.BLINK_INTERVAL
        self._sources = {}
        self._timer = None
        self._visible = False

    def update(self, source, messages, level=3):
        if messages:
            self._sources[source] = (messages, level)
        else:
            self._sources.pop(source, None)

        if self._sources:
            if self._timer is None:
                self._toggle()
                self._timer = self._app.set_interval(self._interval, self._toggle)
            elif self._visible:
                self._show()
        else:
            if self._timer is not None:
                self._timer.stop()
                self._timer = None
            self._dismiss()

    def _toggle(self):
        if self._visible:
            self._dismiss()
        else:
            self._show()

    def _show(self):
        self._dismiss_inactive()
        for source, (messages, level) in self._sources.items():
            selector = self.TARGETS.get(source)
            if selector is None:
                continue
            try:
                target = self._app.query_one(selector)
            except Exception:
                continue
            css_class = WARNING_CLASSES.get(level, WARNING_CLASSES[3])
            target.add_class(css_class)
        self._visible = True

    def _dismiss_inactive(self):
        for source, selector in self.TARGETS.items():
            if source in self._sources:
                continue
            try:
                target = self._app.query_one(selector)
            except Exception:
                continue
            for cls in WARNING_CLASSES.values():
                target.remove_class(cls)

    def _dismiss(self):
        for selector in self.TARGETS.values():
            try:
                target = self._app.query_one(selector)
            except Exception:
                continue
            for cls in WARNING_CLASSES.values():
                target.remove_class(cls)
        self._visible = False
