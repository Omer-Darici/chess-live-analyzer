# -*- coding: utf-8 -*-
"""Drag-to-select a screen region across the whole virtual desktop.

Two things make this robust on Windows:

* A ``overrideredirect(True)`` window is not in the normal focus cycle, so
  Escape may never arrive. We force foreground via Win32, bind Escape at every
  level, and also expose a visible cancel button plus right-click.
* Completion always ``destroy()``s the overlay. ``quit()`` would tear down the
  application's outer mainloop instead of just the nested ``wait_window`` loop.
"""
import ctypes
import tkinter as tk

import mss


def select_region(root=None):
    """Modal drag selection. Returns {'left','top','width','height'} or None.

    Pass ``root`` to reuse an existing Tk instance; otherwise one is created.
    """
    own = root is None
    if own:
        root = tk.Tk()

    with mss.mss() as s:
        mon = s.monitors[0]  # virtual span covering every monitor

    win = root if own else tk.Toplevel(root)
    win.overrideredirect(True)
    try:
        win.attributes("-topmost", True)
    except tk.TclError:
        pass
    win.geometry(f"{mon['width']}x{mon['height']}+{mon['left']}+{mon['top']}")
    win.configure(bg="#0a0d11")
    try:
        win.attributes("-alpha", 0.45)
    except tk.TclError:
        pass

    canvas = tk.Canvas(win, highlightthickness=0, bg="#0a0d11", cursor="crosshair")
    canvas.pack(fill=tk.BOTH, expand=True)

    state = {"start": None, "rect": None, "done": False}

    # ---- visible instruction panel (also hosts a real cancel button) ----
    panel = tk.Frame(win, bg="#161b22", highlightthickness=1,
                     highlightbackground="#2ea87c", padx=20, pady=14)
    tk.Label(panel, text="Tahtanın çevresine sürükleyerek çerçeve seçin",
             bg="#161b22", fg="#e6edf3",
             font=("Segoe UI Semibold", 15)).pack(anchor="w")
    tk.Label(panel, text="Sürükleyip bırakın  ·  Vazgeç: Esc, sağ tık veya aşağıdaki düğme",
             bg="#161b22", fg="#8b98a5", font=("Segoe UI", 10)).pack(anchor="w", pady=(4, 0))
    tk.Button(panel, text="Vazgeç", command=lambda: finish(None), bg="#232a33",
              fg="#e6edf3", activebackground="#2c3540", activeforeground="#e6edf3",
              relief="flat", bd=0, padx=16, pady=6, font=("Segoe UI", 10, "bold"),
              cursor="hand2", highlightthickness=0).pack(anchor="w", pady=(10, 0))
    # place() keeps it above the canvas (created later = higher stacking order).
    panel.place(relx=0.5, rely=0.04, anchor="n")

    # ---- lifecycle -----------------------------------------------------
    def finish(result):
        if state["done"]:
            return
        state["done"] = True
        state["result"] = result
        try:
            win.grab_release()
        except tk.TclError:
            pass
        try:
            win.unbind_all("<Escape>")
        except tk.TclError:
            pass
        try:
            win.destroy()
        except tk.TclError:
            pass

    state["result"] = None

    def cancel(_event=None):
        finish(None)
        return "break"

    # ---- drawing -------------------------------------------------------
    def on_press(event):
        if event.num == 3:          # right click = cancel
            finish(None)
            return "break"
        state["start"] = (event.x_root, event.y_root)
        if state["rect"]:
            canvas.delete(state["rect"])
        state["rect"] = None

    def on_drag(event):
        if not state["start"]:
            return
        x0, y0 = state["start"]
        x1, y1 = event.x_root, event.y_root
        if state["rect"]:
            canvas.delete(state["rect"])
        state["rect"] = canvas.create_rectangle(
            x0, y0, x1, y1, outline="#2ea87c", width=3)

    def on_release(event):
        if not state["start"]:
            return
        x0, y0 = state["start"]
        x1, y1 = event.x_root, event.y_root
        state["start"] = None
        w, h = abs(x1 - x0), abs(y1 - y0)
        if w < 40 or h < 40:        # a stray click, not a selection
            return
        finish({"left": int(min(x0, x1)), "top": int(min(y0, y1)),
                "width": int(w), "height": int(h)})

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    canvas.bind("<ButtonPress-3>", on_press)
    # Bind at widget, window and application level — a borderless window may
    # not have focus, so events can arrive via any of these paths.
    for target in (canvas, win):
        target.bind("<Escape>", cancel)
    win.bind_all("<Escape>", cancel)

    # A borderless window is outside Windows' normal focus cycle; ask Win32
    # directly and fall back to Tk's own request.
    win.update_idletasks()
    try:
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
        ctypes.windll.user32.SetForegroundWindow(hwnd)
    except Exception:
        pass
    try:
        win.focus_force()
    except tk.TclError:
        pass
    canvas.focus_set()
    try:
        win.grab_set()
        win.grab_set_global()
    except tk.TclError:
        pass

    # ---- run (modal) ---------------------------------------------------
    try:
        if own:
            win.mainloop()            # destroyed by finish()
        else:
            win.wait_window()         # returns when finish() destroys win
    except tk.TclError:
        pass
    finally:
        if own:
            try:
                root.destroy()
            except tk.TclError:
                pass
        else:
            try:
                win.unbind_all("<Escape>")
            except tk.TclError:
                pass
            try:
                win.grab_release()
            except tk.TclError:
                pass

    return state["result"]
