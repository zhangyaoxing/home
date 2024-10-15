from shutil import rmtree, move
import os
import json
import logging
from inspect import getsourcefile
from os.path import abspath, dirname
from pathlib import Path

def color_code(code): return f"\x1b[{code}m"
def colorize(code: int, s: str) -> str: return f"{color_code(code)}{str(s).replace(color_code(0), color_code(code))}{color_code(0)}"
def green(s: str) -> str: return colorize(32, s)
def yellow(s: str) -> str: return colorize(33, s)
def red(s: str) -> str: return colorize(31, s)
def cyan(s: str) -> str: return colorize(36, s)
def magenta(s: str) -> str: return colorize(35, s)
def bold(s: str) -> str: return colorize(1, s)
def dim(s: str) -> str: return colorize(2, s)
def italic(s: str) -> str: return colorize(3, s)
def underline(s: str) -> str: return colorize(4, s)
def blink(s: str) -> str: return colorize(5, s)
def reverse(s: str) -> str: return colorize(7, s)
def invisible(s: str) -> str: return colorize(8, s)
def get_script_path(filename = None):
    script_folder = Path(dirname(abspath(getsourcefile(lambda:0))))
    if filename == None:
        return str((script_folder / "..").resolve())
    else:
        return str((script_folder / ".." / filename).resolve())

config_path = get_script_path("config.json")
config = json.load(open(config_path))
config["authenticationkey"] = config.get("authenticationkey", os.environ.get("authenticationkey", None))
if config["authenticationkey"] == None:
    print(yellow("authenticationkey key is not configured."))
    exit()

def load_config():
    global config
    return config

levels = logging._nameToLevel
log_level = levels[config["logLevel"]]
logging.basicConfig(level = log_level)
logger = logging.getLogger(__name__)
logger.info("Log level: %s" % config["logLevel"])