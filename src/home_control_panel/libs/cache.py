import json
import os
import tempfile
import threading
import time
from pathlib import Path

from textual.message import Message

CACHE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "cache"


def read_cache(name):
    path = CACHE_DIR / name
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def write_cache(name, data):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / name
    fd, tmp = tempfile.mkstemp(dir=CACHE_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, ensure_ascii=False, default=str)
        os.replace(tmp, path)
    except Exception:
        os.unlink(tmp)
        raise


def cache_mtime(name):
    path = CACHE_DIR / name
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return 0


def format_cache_time(cached):
    if cached is None:
        return ""
    try:
        ts = cached["timestamp"]
        return ts[11:16] if "T" in ts else ts[:5]
    except (KeyError, IndexError):
        return ""


def touch_trigger(name):
    """Create/update a trigger file to signal the api service."""
    (CACHE_DIR / name).touch(exist_ok=True)


class CacheChanged(Message):
    """Posted by FileWatcher when a watched cache file changes."""

    def __init__(self, name):
        super().__init__()
        self.cache_name = name


class FileWatcher:
    """Watch cache files in a background thread and post messages on change."""

    def __init__(self, app, interval=1):
        self._app = app
        self._interval = interval
        self._watched = {}
        self._running = False
        self._thread = None

    def watch(self, name):
        self._watched[name] = cache_mtime(name)

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _run(self):
        while self._running:
            for name in self._watched:
                mtime = cache_mtime(name)
                if mtime > self._watched[name]:
                    self._watched[name] = mtime
                    self._app.post_message(CacheChanged(name))
            time.sleep(self._interval)
