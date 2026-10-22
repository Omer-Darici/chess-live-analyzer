# -*- coding: utf-8 -*-
"""Remappable keyboard + mouse hotkeys."""
import threading

from pynput import keyboard, mouse

from . import config


def key_name(key):
    """Normalise a pynput key to a stable string."""
    try:
        ch = key.char
        if ch:
            return ch.lower()
    except AttributeError:
        pass
    name = getattr(key, "name", None)
    if name:
        return name
    return str(key).replace("Key.", "")


def parse_mouse(spec):
    """'button.middle' -> mouse.Button.middle (unknown -> middle)."""
    name = str(spec).split(".")[-1].strip().lower()
    return getattr(mouse.Button, name, mouse.Button.middle)


def mouse_name(btn):
    return "button." + str(btn).split(".")[-1].strip().lower()


_MOD_ORDER = [
    "ctrl_l", "ctrl_r", "ctrl",
    "shift_l", "shift_r", "shift",
    "alt_l", "alt_r", "alt",
    "cmd_l", "cmd_r", "cmd",
]


def combo_label(keys):
    """['ctrl_l','shift','s'] -> 'Ctrl+Shift+S' (modifiers first, readable)."""
    pretty = {
        "ctrl_l": "Ctrl", "ctrl_r": "Ctrl", "ctrl": "Ctrl",
        "shift_l": "Shift", "shift_r": "Shift", "shift": "Shift",
        "alt_l": "Alt", "alt_r": "Alt", "alt": "Alt",
        "cmd_l": "Win", "cmd_r": "Win", "cmd": "Win",
        "space": "Space", "esc": "Esc", "tab": "Tab",
        "enter": "Enter", "backspace": "Backspace", "delete": "Del",
        "page_up": "PgUp", "page_down": "PgDn",
        "up": "Up", "down": "Down", "left": "Left", "right": "Right",
    }
    keys = list(keys)
    keys.sort(key=lambda k: (_MOD_ORDER.index(k) if k in _MOD_ORDER else 99, k))
    return "+".join(pretty.get(k, k.upper() if len(k) == 1 else k.title())
                    for k in keys)


class HotkeyManager:
    """Fires ``on_trigger`` when the bound combo is completed."""

    def __init__(self, on_trigger):
        self.on_trigger = on_trigger
        self._combo = set(config.get("hotkey_combo") or [])
        self._mouse_btn = parse_mouse(config.get("mouse_hotkey", "button.middle"))
        self._pressed = set()
        self._lock = threading.Lock()
        self._recording = False
        self._on_recorded = None
        self._kb = None
        self._ms = None
        self._suppress_until = 0.0

    # --- callbacks ----------------------------------------------------
    def _fire(self):
        try:
            self.on_trigger()
        except Exception:
            pass

    def _handle_key(self, name, is_press):
        if self._recording:
            if is_press and name not in ("ctrl_l", "ctrl_r", "shift_l", "shift_r",
                                         "alt_l", "alt_r", "cmd_l", "cmd_r"):
                self._recording = False
                if self._on_recorded:
                    self._on_recorded(sorted(self._pressed))
            return
        with self._lock:
            if is_press:
                self._pressed.add(name)
                fire = bool(self._combo) and self._combo <= self._pressed
            else:
                self._pressed.discard(name)
                fire = False
        if fire:
            self._fire()

    def _handle_mouse(self, btn, is_press):
        if self._recording:
            if is_press:
                self._recording = False
                if self._on_recorded:
                    self._on_recorded(mouse_name(btn))
            return
        if is_press and btn == self._mouse_btn:
            self._fire()

    # --- listeners ----------------------------------------------------
    def start(self):
        if self._kb is not None:
            return
        self._kb = keyboard.Listener(
            on_press=lambda k: self._handle_key(key_name(k), True),
            on_release=lambda k: self._handle_key(key_name(k), False),
        )
        self._ms = mouse.Listener(
            on_click=lambda x, y, btn, pressed: self._handle_mouse(btn, pressed),
        )
        self._kb.daemon = True
        self._ms.daemon = True
        self._kb.start()
        self._ms.start()

    # --- remapping ----------------------------------------------------
    def record_combo(self, on_done):
        """Arm capture; the next non-modifier key press becomes the combo."""
        self._on_recorded = on_done
        self._recording = True
        self._pressed.clear()

    def record_mouse(self, on_done):
        self._on_recorded = on_done
        self._recording = True

    def set_combo(self, keys):
        self._combo = set(keys)
        config.set("hotkey_combo", list(keys))

    def set_mouse_button(self, spec):
        self._mouse_btn = parse_mouse(spec)
        config.set("mouse_hotkey", mouse_name(self._mouse_btn))

    def label(self):
        return combo_label(sorted(self._combo))

    def mouse_label(self):
        return mouse_name(self._mouse_btn).split(".")[-1].title()

    def stop(self):
        self._recording = False
        for lst in (self._kb, self._ms):
            if lst:
                try:
                    lst.stop()
                except Exception:
                    pass
        self._kb = self._ms = None
