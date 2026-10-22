# -*- coding: utf-8 -*-
"""Global configuration for Chess Live Analyzer.

Values are persisted to ``config.json`` next to the project root so a built
``.exe`` keeps the user's settings (Stockfish path, hotkeys, timings) between
runs without any installer.
"""
import json
import sys
from pathlib import Path

# When frozen, __file__ points into PyInstaller's temp extraction dir, which is
# wiped after every run — that would silently lose config.json and logs.
# Anchor everything next to the executable instead.
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
TEMPLATE_DIR = PROJECT_ROOT / "templates"
CONFIG_FILE = PROJECT_ROOT / "config.json"

LOG_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_STOCKFISH = (
    r"C:\Users\Storm\Downloads\LucasChessR\bin\OS\win32\Engines\stockfish"
    r"\stockfish-windows-x86-64-universal.exe"
)

DEFAULTS = {
    "stockfish_path": DEFAULT_STOCKFISH,
    "movetime_ms": 300,
    "depth": 18,
    "threads": 2,
    "hash_mb": 128,
    "multipv": 3,
    "poll_interval_s": 0.20,
    "monitor": 1,
    "my_color": "white",
    "hotkey_combo": ["ctrl_l", "shift", "s"],
    "mouse_hotkey": "button.middle",
    "min_confidence": 0.55,
    "board_x": 0,
    "board_y": 0,
    "board_size": 0,
}

_config = dict(DEFAULTS)
if CONFIG_FILE.exists():
    try:
        _config.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass


def get(key, default=None):
    return _config.get(key, DEFAULTS.get(key, default))


def set(key, value):
    _config[key] = value
    save()
    return value


def update(**kwargs):
    _config.update(kwargs)
    save()
    return _config


def save():
    try:
        CONFIG_FILE.write_text(
            json.dumps(_config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


# Convenience flat names (kept for modules that just want a value).
STOCKFISH_PATH = get("stockfish_path")
MOVETIME_MS = get("movetime_ms")
DEPTH = get("depth")
THREADS = get("threads")
HASH_MB = get("hash_mb")
MULTIPV = get("multipv")
POLL_INTERVAL_S = get("poll_interval_s")
DEFAULT_MONITOR = get("monitor")
HOTKEY_COMBO = get("hotkey_combo")
MOUSE_HOTKEY = get("mouse_hotkey")

# Palette: off-black neutrals + a single emerald accent. No pure #000/#fff.
BG = "#0e1116"
BG_RAISED = "#161b22"
BG_INSET = "#0a0d11"
BORDER = "#232a33"
FG = "#e6edf3"
FG_MUTED = "#8b98a5"
ACCENT = "#2ea87c"
ACCENT_DIM = "#1c6d52"
WARN = "#c9884a"
ERROR = "#c25450"
