# -*- coding: utf-8 -*-
"""Click-through, semi-transparent highlight layer over the screen.

Each highlight is its own borderless window with real per-window ``-alpha``
transparency, plus the WS_EX_TRANSPARENT / WS_EX_NOACTIVATE extended styles so
the layer never swallows clicks or steals focus from the game.
"""
import ctypes
import tkinter as tk

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
_TRANSPARENT_COLOR = "magenta"


def _click_through(hwnd):
    user32 = ctypes.windll.user32
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(
        hwnd, GWL_EXSTYLE,
        style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE,
    )


class _Pane(tk.Toplevel):
    """One borderless, click-through, translucent rectangle."""

    def __init__(self, root, x, y, w, h, color, alpha, transparent=False):
        super().__init__(root)
        self.overrideredirect(True)
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass
        if transparent:
            self.configure(bg=_TRANSPARENT_COLOR)
            self.attributes("-transparentcolor", _TRANSPARENT_COLOR)
        else:
            self.configure(bg=color)
        self.geometry(f"{max(1, int(w))}x{max(1, int(h))}+{int(x)}+{int(y)}")
        try:
            self.attributes("-alpha", max(0.05, min(1.0, float(alpha))))
        except tk.TclError:
            pass
        self.update_idletasks()
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            if hwnd:
                _click_through(hwnd)
        except Exception:
            pass

    def destroy_safe(self):
        try:
            self.destroy()
        except tk.TclError:
            pass


class Overlay:
    """Manages the highlight panes. Must be created on the Tk main thread."""

    def __init__(self, root=None):
        self._owns_root = root is None
        self.root = root or tk.Tk()
        if self._owns_root:
            self.root.withdraw()
        self._panes = {}
        self._closed = False

    # --- primitives ---------------------------------------------------
    def fill(self, key, box, color, alpha=0.45):
        x, y, w, h = box
        self._replace(key, _Pane(self.root, x, y, w, h, color, alpha))

    def ring(self, key, box, color, alpha=0.95, thickness=4):
        """Hollow border so the piece underneath stays visible."""
        x, y, w, h = box
        t = max(2, int(thickness))
        self._replace(key + ".n", _Pane(self.root, x, y, w, t, color, alpha))
        self._replace(key + ".s", _Pane(self.root, x, y + h - t, w, t, color, alpha))
        self._replace(key + ".w", _Pane(self.root, x, y, t, h, color, alpha))
        self._replace(key + ".e", _Pane(self.root, x + w - t, y, t, h, color, alpha))

    def arrow(self, key, frm, to, color, alpha=0.75, width=6):
        """Translucent arrow from the centre of ``frm`` to the centre of ``to``."""
        fx, fy, fw, fh = frm
        tx, ty, tw, th = to
        x1, y1 = fx + fw / 2.0, fy + fh / 2.0
        x2, y2 = tx + tw / 2.0, ty + th / 2.0
        # Trim the tail so it starts at the square edge, not the piece centre.
        import math
        dx, dy = x2 - x1, y2 - y1
        dist = math.hypot(dx, dy) or 1.0
        ux, uy = dx / dist, dy / dist
        start = min(fw, fh) * 0.32
        end = min(tw, th) * 0.30
        sx, sy = x1 + ux * start, y1 + uy * start
        ex, ey = x2 - ux * end, y2 - uy * end

        pad = 12
        bx0 = int(min(sx, ex) - pad)
        by0 = int(min(sy, ey) - pad)
        bw = int(abs(ex - sx) + pad * 2)
        bh = int(abs(ey - sy) + pad * 2)
        if bw < 4 or bh < 4:
            return
        pane = _Pane(self.root, bx0, by0, bw, bh, color, alpha, transparent=True)
        canvas = tk.Canvas(
            pane, width=bw, height=bh, bg=_TRANSPARENT_COLOR,
            highlightthickness=0, bd=0,
        )
        canvas.pack()
        sxp, syp, exp, eyp = sx - bx0, sy - by0, ex - bx0, ey - by0
        canvas.create_line(sxp, syp, exp, eyp, fill=color, width=width,
                           capstyle=tk.ROUND)
        head = max(10, width * 3)
        canvas.create_polygon(
            exp, eyp,
            exp - ux * head - uy * head * 0.5, eyp - uy * head + ux * head * 0.5,
            exp - ux * head + uy * head * 0.5, eyp - uy * head - ux * head * 0.5,
            fill=color, outline=color,
        )
        self._replace(key, pane)

    def grid(self, key, x, y, size, color="#2ea87c", alpha=0.85, thickness=2):
        """Live 8x8 grid preview used while calibrating."""
        step = size / 8.0
        t = thickness
        self.clear(key)
        for i in range(9):
            off = int(i * step)
            self._replace(f"{key}.v{i}", _Pane(self.root, x + off - t // 2, y, t, size, color, alpha))
            self._replace(f"{key}.h{i}", _Pane(self.root, x, y + off - t // 2, size, t, color, alpha))
        self._replace(f"{key}.frame", _Pane(self.root, x - t, y - t, size + 2 * t, size + 2 * t, color, alpha, transparent=True))

    # --- lifecycle ----------------------------------------------------
    def _replace(self, key, pane):
        old = self._panes.pop(key, None)
        if old:
            old.destroy_safe()
        self._panes[key] = pane

    def clear(self, key=None):
        if key is None:
            for p in list(self._panes.values()):
                p.destroy_safe()
            self._panes.clear()
            return
        for k in [k for k in self._panes if k == key or k.startswith(key + ".")]:
            self._panes.pop(k).destroy_safe()

    def pulse(self):
        """Pump Tk events; call from the main thread loop."""
        try:
            self.root.update_idletasks()
            self.root.update()
        except tk.TclError:
            pass

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.clear()
        if not self._owns_root:
            return  # the owner (App) destroys the shared root itself
        try:
            self.root.destroy()
        except tk.TclError:
            pass
