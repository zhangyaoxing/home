import json
import os
import tempfile
from pathlib import Path

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
