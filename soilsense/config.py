"""
Where the database lives.

The Neon connection string is read from (first match wins):
  1. the SOILSENSE_DATABASE_URL environment variable
  2. config.ini next to main.py  →  [database] url = postgresql://...
If neither exists, the app asks for it on first launch and saves config.ini.
The password never goes into the code — keep config.ini out of zips and GitHub.
"""
import configparser
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.ini"


def database_url():
    env = os.environ.get("SOILSENSE_DATABASE_URL", "").strip()
    if env:
        return env
    if CONFIG_PATH.exists():
        cp = configparser.ConfigParser(interpolation=None)
        cp.read(CONFIG_PATH, encoding="utf-8")
        return cp.get("database", "url", fallback="").strip()
    return ""


def save_database_url(url):
    cp = configparser.ConfigParser(interpolation=None)
    cp["database"] = {"url": url.strip()}
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write("# SoilSense desktop — private, do not share or upload this file\n")
        cp.write(f)
