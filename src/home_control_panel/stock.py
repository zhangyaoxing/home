import logging
import time

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from home_control_panel.libs.cache import (
    CacheChanged,
    cache_mtime,
    format_cache_time,
    read_cache,
    touch_trigger,
)
from home_control_panel.libs.utils import config

logger = logging.getLogger(__name__)


class StockQuote(Static):
    """Displays stock price with change, green for up, red for down."""

    CACHE_FILE = "stocks.json"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache_mtime = 0
        self._data_signature = None

    def compose(self) -> ComposeResult:
        yield Static()

    def _check_cache(self):
        mtime = cache_mtime(self.CACHE_FILE)
        if mtime > self._cache_mtime:
            self._cache_mtime = mtime

            cached = read_cache(self.CACHE_FILE)
            if cached is None:
                self.remove_children()
                self.mount(Static("Unavailable", classes="stock-error"))
                self.set_loading(False)
                return

            quotes = cached["data"].get("quotes", [])
            sig = tuple(
                (q.get("symbol"), q.get("current"), q.get("change"))
                for q in quotes
            )

            if sig != self._data_signature:
                self._data_signature = sig
                self.remove_children()
                for quote in quotes:
                    price = quote["current"]
                    change = quote["change"]
                    pct = quote["percent_change"]
                    symbol = quote["symbol"]
                    color = "green" if change >= 0 else "red"
                    sign = "+" if change >= 0 else ""
                    self.mount(
                        Horizontal(
                            Static(escape(symbol), classes="stock-symbol"),
                            Static(
                                f"[{color}]{price:.2f}  ({sign}{change:.2f} / {sign}{pct:.2f}%)[/]",
                                classes="stock-price",
                            ),
                            classes="stock-row",
                        )
                    )

            self.border_subtitle = f"[dim]Updated {format_cache_time(cached)}[/]"
            self.set_loading(False)
        else:
            # Refresh minute countdown — no structure change needed
            pass

    def on_mount(self):
        self.border_title = "Stocks"
        self.set_loading(True)
        self._check_cache()
        self.set_interval(config["tuiRefreshInterval"], self._check_cache)

    def refresh_stocks(self):
        self._cache_mtime = 0
        self._check_cache()

    def on_cache_changed(self, event: CacheChanged):
        if event.cache_name == self.CACHE_FILE:
            self.refresh_stocks()

    def on_click(self, event):
        if event.widget is not self and event.y != self.region.y:
            return
        if time.time() - cache_mtime(self.CACHE_FILE) < 60:
            return
        self.border_subtitle = "[dim]Refreshing...[/]"
        touch_trigger("_trigger_stocks")
