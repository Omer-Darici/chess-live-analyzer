# -*- coding: utf-8 -*-
"""Control panel UI.

Design read: desktop utility panel, dark "cockpit" language — off-black zinc
neutrals, a single emerald accent locked across the whole panel, monospace for
every number, one 6px corner radius everywhere, no pure black/white and no
neon glow.
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import chess

from . import config, hotkeys as hk
from .board_detect import fit_grid
from .engine import Engine
from .logger import fmt_cp, move_label, explain
from .overlay import Overlay
from .region_select import select_region
from .screen_capture import ScreenCapture

R = 6                      # single corner-radius scale, used everywhere
FONT = "Segoe UI"
MONO = "Consolas"


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a, b, t):
    ca, cb = _hex_to_rgb(a), _hex_to_rgb(b)
    return "#%02x%02x%02x" % tuple(int(ca[i] + (cb[i] - ca[i]) * t) for i in range(3))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Chess Live Analyzer")
        self.configure(bg=config.BG)
        self.geometry("940x680")
        self.minsize(880, 620)

        self.capture = ScreenCapture(monitor=config.get("monitor", 1))
        from .board_detect import BoardDetector
        self.detector = BoardDetector(
            min_score=float(config.get("min_confidence", 0.55))
        )
        self.engine = Engine()
        self.logger = None
        self.overlay = Overlay(self)
        self.worker = None
        self.hotkey = None
        self.grid_preview_on = False
        self.region = None
        self.current_lines = []
        self.current_board = None

        self._build_style()
        self._build_layout()
        self._init_hotkey()
        self._tick()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # --- theming ------------------------------------------------------
    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TSpinbox", fieldbackground=config.BG_INSET,
                        background=config.BG_RAISED, foreground=config.FG,
                        arrowcolor=config.FG_MUTED, borderwidth=0,
                        insertcolor=config.FG, padding=3)
        style.configure("TCombobox", fieldbackground=config.BG_INSET,
                        background=config.BG_RAISED, foreground=config.FG,
                        arrowcolor=config.FG_MUTED, borderwidth=0, padding=3)
        style.configure("Horizontal.TScale", background=config.BG,
                        troughcolor=config.BG_INSET, borderwidth=0)
        style.configure("TEntry", fieldbackground=config.BG_INSET,
                        foreground=config.FG, borderwidth=0, insertcolor=config.FG)
        style.configure("Vertical.TScrollbar", background=config.BG_RAISED,
                        troughcolor=config.BG_INSET, arrowcolor=config.FG_MUTED,
                        bordercolor=config.BORDER, borderwidth=0, relief="flat")
        style.map("Vertical.TScrollbar",
                  background=[("active", _mix(config.BG_RAISED, "#ffffff", 0.10))])

    # --- widgets ------------------------------------------------------
    def _btn(self, parent, text, cmd=None, primary=False, width=None):
        bg = config.ACCENT if primary else config.BG_RAISED
        fg = "#0a0d11" if primary else config.FG
        b = tk.Button(
            parent, text=text, command=cmd, bg=bg, fg=fg,
            activebackground=_mix(bg, "#ffffff", 0.12) if primary else _mix(bg, "#ffffff", 0.06),
            activeforeground=fg, relief="flat", bd=0, padx=14, pady=7,
            font=(FONT, 10, "bold" if primary else "normal"), cursor="hand2",
            highlightthickness=0,
        )
        if width:
            b.configure(width=width)
        b.bind("<Enter>", lambda e, x=b, v=bg: x.configure(bg=_mix(v, "#ffffff", 0.10)))
        b.bind("<Leave>", lambda e, x=b, v=bg: x.configure(bg=v))
        b.bind("<ButtonPress-1>", lambda e, x=b, v=bg: x.configure(bg=_mix(v, "#000000", 0.18)))
        b.bind("<ButtonRelease-1>", lambda e, x=b, v=bg: x.configure(bg=_mix(v, "#ffffff", 0.10)))
        return b

    def _label(self, parent, text, size=10, muted=False, mono=False, bold=False):
        return tk.Label(
            parent, text=text, bg=parent.cget("bg"),
            fg=config.FG_MUTED if muted else config.FG,
            font=(MONO if mono else FONT, size, "bold" if bold else "normal"),
            anchor="w",
        )

    def _card(self, parent, title):
        f = tk.Frame(parent, bg=config.BG_RAISED, highlightthickness=1,
                     highlightbackground=config.BORDER)
        if title:
            tk.Label(f, text=title, bg=config.BG_RAISED, fg=config.FG_MUTED,
                     font=(FONT, 9, "bold"), anchor="w", padx=12, pady=8
                     ).pack(fill=tk.X)
        return f

    # --- layout -------------------------------------------------------
    def _build_layout(self):
        # Header
        head = tk.Frame(self, bg=config.BG_RAISED, height=52,
                        highlightthickness=1, highlightbackground=config.BORDER)
        head.pack(fill=tk.X)
        head.pack_propagate(False)
        tk.Label(head, text="Chess Live Analyzer", bg=config.BG_RAISED,
                 fg=config.FG, font=(FONT, 14, "bold")).pack(side=tk.LEFT, padx=14)
        self.status_dot = tk.Label(head, text="●  hazırlanıyor", bg=config.BG_RAISED,
                                   fg=config.WARN, font=(FONT, 10))
        self.status_dot.pack(side=tk.RIGHT, padx=14)

        body = tk.Frame(self, bg=config.BG)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        # --- left sidebar: setup ---
        side = tk.Frame(body, bg=config.BG, width=290)
        side.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))
        side.pack_propagate(False)

        c1 = self._card(side, "01 — TAHTA")
        c1.pack(fill=tk.X, pady=(0, 10))
        inner = tk.Frame(c1, bg=config.BG_RAISED)
        inner.pack(fill=tk.X, padx=12, pady=(0, 12))
        self._btn(inner, "Bölge Seç…", self._pick_region, primary=True
                  ).pack(fill=tk.X, pady=(0, 8))

        self.region_info = self._label(inner, "henüz seçilmedi", 9, muted=True, mono=True)
        self.region_info.pack(fill=tk.X, pady=(0, 6))

        grid_row = tk.Frame(inner, bg=config.BG_RAISED)
        grid_row.pack(fill=tk.X, pady=(0, 6))
        self.vars = {k: tk.IntVar(value=0) for k in ("gx", "gy", "gs")}
        for i, (lab, key, lo, hi) in enumerate([
            ("X", "gx", -4000, 4000), ("Y", "gy", -4000, 4000), ("Kenar", "gs", 64, 3000)
        ]):
            cell = tk.Frame(grid_row, bg=config.BG_RAISED)
            cell.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 4))
            grid_row.columnconfigure(i, weight=1)
            tk.Label(cell, text=lab, bg=config.BG_RAISED, fg=config.FG_MUTED,
                     font=(FONT, 8)).pack(anchor="w")
            tk.Spinbox(cell, from_=lo, to=hi, textvariable=self.vars[key],
                       width=6, command=self._apply_grid,
                       bg=config.BG_INSET, fg=config.FG, buttonbackground=config.BG_RAISED,
                       relief="flat", font=(MONO, 10), bd=4, highlightthickness=0
                       ).pack(fill=tk.X)

        row = tk.Frame(inner, bg=config.BG_RAISED)
        row.pack(fill=tk.X, pady=(4, 0))
        self._btn(row, "Otomatik Hizala", self._auto_fit).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 3))
        self._btn(row, "Izgarayı Göster", self._toggle_grid).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(3, 0))

        self._btn(inner, "Kalibre Et", self._calibrate, primary=True
                  ).pack(fill=tk.X, pady=(8, 0))
        self.calib_info = self._label(inner, "kalibre edilmedi", 9, muted=True, mono=True)
        self.calib_info.pack(fill=tk.X, pady=(6, 0))

        c2 = self._card(side, "02 — MOTOR")
        c2.pack(fill=tk.X, pady=(0, 10))
        inner2 = tk.Frame(c2, bg=config.BG_RAISED)
        inner2.pack(fill=tk.X, padx=12, pady=(0, 12))
        self.engine_rows = []
        for lab, key, lo, hi, unit in [
            ("Süre (ms)", "movetime_ms", 50, 3000, ""),
            ("Derinlik", "depth", 5, 40, ""),
            ("Aday (PV)", "multipv", 1, 5, ""),
        ]:
            r = tk.Frame(inner2, bg=config.BG_RAISED)
            r.pack(fill=tk.X, pady=3)
            tk.Label(r, text=lab, bg=config.BG_RAISED, fg=config.FG,
                     font=(FONT, 10), anchor="w").pack(side=tk.LEFT)
            var = tk.IntVar(value=int(config.get(key)))
            sb = tk.Spinbox(r, from_=lo, to=hi, textvariable=var, width=6,
                            command=lambda k=key, v=var: self._set_num(k, v),
                            bg=config.BG_INSET, fg=config.FG, relief="flat",
                            font=(MONO, 10), bd=3, highlightthickness=0)
            sb.pack(side=tk.RIGHT)
            sb.bind("<Return>", lambda e, k=key, v=var: self._set_num(k, v))
            sb.bind("<FocusOut>", lambda e, k=key, v=var: self._set_num(k, v))
            self.engine_rows.append((key, var))

        path_row = tk.Frame(inner2, bg=config.BG_RAISED)
        path_row.pack(fill=tk.X, pady=(8, 0))
        self._btn(path_row, "Stockfish Yolu…", self._pick_engine).pack(fill=tk.X)
        self.engine_info = self._label(inner2, "", 8, muted=True, mono=True)
        self.engine_info.pack(fill=tk.X, pady=(6, 0))
        self._refresh_engine_info()

        # --- right: analysis ---
        right = tk.Frame(body, bg=config.BG)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Big readout
        top = tk.Frame(right, bg=config.BG_RAISED, highlightthickness=1,
                       highlightbackground=config.BORDER)
        top.pack(fill=tk.X, pady=(0, 10))
        lft = tk.Frame(top, bg=config.BG_RAISED)
        lft.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=16, pady=14)
        tk.Label(lft, text="PUAN", bg=config.BG_RAISED, fg=config.FG_MUTED,
                 font=(FONT, 8, "bold"), anchor="w").pack(anchor="w")
        self.eval_lbl = tk.Label(lft, text="—", bg=config.BG_RAISED,
                                 fg=config.FG, font=(MONO, 34, "bold"), anchor="w")
        self.eval_lbl.pack(anchor="w")
        self.eval_sub = tk.Label(lft, text="motor bekleniyor", bg=config.BG_RAISED,
                                 fg=config.FG_MUTED, font=(FONT, 9), anchor="w")
        self.eval_sub.pack(anchor="w", pady=(2, 0))

        rgt = tk.Frame(top, bg=config.BG_RAISED)
        rgt.pack(side=tk.RIGHT, padx=16, pady=14)
        tk.Label(rgt, text="EN İYİ HAMLE", bg=config.BG_RAISED, fg=config.FG_MUTED,
                 font=(FONT, 8, "bold")).pack(anchor="e")
        self.best_lbl = tk.Label(rgt, text="—", bg=config.BG_RAISED, fg=config.ACCENT,
                                 font=(MONO, 26, "bold"))
        self.best_lbl.pack(anchor="e")
        self.turn_lbl = tk.Label(rgt, text="", bg=config.BG_RAISED, fg=config.FG_MUTED,
                                 font=(FONT, 9))
        self.turn_lbl.pack(anchor="e")

        # Candidates
        cand = self._card(right, "03 — ADAY HAMLELER")
        cand.pack(fill=tk.X, pady=(0, 10))
        self.cand_box = tk.Frame(cand, bg=config.BG_RAISED)
        self.cand_box.pack(fill=tk.X, padx=12, pady=(0, 12))
        self.cand_rows = []
        self.cand_empty = tk.Label(
            self.cand_box,
            text="Analiz bekleniyor — bölgeyi seçip kalibre edin; "
                 "pozisyon değişince en iyi 3 hamle burada listelenir.",
            bg=config.BG_RAISED, fg=config.FG_MUTED, font=(FONT, 9),
            anchor="w", justify="left", wraplength=520, pady=8,
        )
        self.cand_empty.pack(fill=tk.X)

        # Reason
        reason = self._card(right, "04 — NEDEN BU HAMLE")
        reason.pack(fill=tk.BOTH, expand=True)
        txt_wrap = tk.Frame(reason, bg=config.BG_RAISED)
        txt_wrap.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        self.reason = tk.Text(
            txt_wrap, wrap=tk.WORD, bg=config.BG_INSET, fg=config.FG,
            font=(FONT, 11), relief="flat", bd=0, padx=12, pady=10,
            insertbackground=config.FG, selectbackground=config.ACCENT_DIM,
            state="disabled", height=7,
        )
        self.reason.tag_configure("ph", foreground=config.FG_MUTED,
                                  font=(FONT, 10, "italic"))
        sb = ttk.Scrollbar(txt_wrap, orient="vertical", command=self.reason.yview,
                           style="Vertical.TScrollbar")
        self.reason.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.reason.pack(fill=tk.BOTH, expand=True)
        self._set_reason("")

        # --- footer ---
        foot = tk.Frame(self, bg=config.BG_RAISED, height=58,
                        highlightthickness=1, highlightbackground=config.BORDER)
        foot.pack(fill=tk.X, side=tk.BOTTOM)
        foot.pack_propagate(False)

        left = tk.Frame(foot, bg=config.BG_RAISED)
        left.pack(side=tk.LEFT, padx=12)
        self.start_btn = self._btn(left, "Canlı Başlat", self._toggle_live, primary=True)
        self.start_btn.pack(side=tk.LEFT, pady=11)
        self._btn(left, "Kaydı Bitir ve Kaydet", self._save_game).pack(side=tk.LEFT, padx=(8, 0), pady=11)

        mid = tk.Frame(foot, bg=config.BG_RAISED)
        mid.pack(side=tk.LEFT, padx=14)
        tk.Label(mid, text="Renk", bg=config.BG_RAISED, fg=config.FG_MUTED,
                 font=(FONT, 9)).pack(side=tk.LEFT)
        self.color_var = tk.StringVar(value=config.get("my_color", "white"))
        cb = ttk.Combobox(mid, textvariable=self.color_var, values=("white", "black"),
                          width=7, state="readonly", font=(MONO, 10))
        cb.pack(side=tk.LEFT, padx=(6, 0))
        cb.bind("<<ComboboxSelected>>", lambda e: config.set("my_color", self.color_var.get()))

        right_f = tk.Frame(foot, bg=config.BG_RAISED)
        right_f.pack(side=tk.RIGHT, padx=12)
        self.hk_lbl = tk.Label(right_f, text="", bg=config.BG_RAISED, fg=config.FG,
                               font=(MONO, 10))
        self.hk_lbl.pack(anchor="e")
        self._btn(right_f, "Hotkey Değiştir…", self._remap_hotkey).pack(anchor="e")

        # Status bar
        self.status = tk.Label(self, text="Hazır — önce tahta bölgesini seçin.",
                               bg=config.BG, fg=config.FG_MUTED, font=(FONT, 9),
                               anchor="w", padx=14, pady=6)
        self.status.pack(fill=tk.X, side=tk.BOTTOM)

    # --- helpers ------------------------------------------------------
    def _set_status(self, text, tone="muted"):
        colors = {"muted": config.FG_MUTED, "ok": config.ACCENT,
                  "warn": config.WARN, "error": config.ERROR}
        self.status.configure(text=text, fg=colors.get(tone, config.FG_MUTED))

    def _set_num(self, key, var):
        try:
            config.set(key, int(var.get()))
        except Exception:
            pass

    def _refresh_engine_info(self):
        ok = self.engine.available()
        name = config.get("stockfish_path", "").split("\\")[-1]
        self.engine_info.configure(
            text=("✓ " if ok else "✗ ") + (name[:34] or "yol seçilmedi"),
            fg=config.ACCENT if ok else config.ERROR,
        )

    def _pick_engine(self):
        p = filedialog.askopenfilename(
            title="Stockfish çalıştırılabilir dosyasını seç",
            filetypes=[("Çalıştırılabilir", "*.exe"), ("Tüm dosyalar", "*.*")],
        )
        if p:
            config.set("stockfish_path", p)
            self.engine.path = p
            self.engine.stop()
            self._refresh_engine_info()

    # --- region / grid ------------------------------------------------
    def _pick_region(self):
        self.overlay.clear()
        self.grid_preview_on = False
        reg = select_region(self)
        if not reg:
            self._set_status("Bölge seçimi iptal edildi.", "warn")
            return
        self.region = reg
        self.capture.set_region(reg)
        self.vars["gx"].set(0)
        self.vars["gy"].set(0)
        self.vars["gs"].set(min(reg["width"], reg["height"]))
        self.region_info.configure(
            text=f'{reg["left"]},{reg["top"]}  {reg["width"]}×{reg["height"]}',
            fg=config.FG,
        )
        self._auto_fit()

    def _auto_fit(self):
        if not self.region:
            self._set_status("Önce bölge seçin.", "warn")
            return
        frame = self.capture.grab()
        if frame is None:
            self._set_status("Ekran yakalanamadı.", "error")
            return
        rel = {"left": 0, "top": 0,
               "width": self.region["width"], "height": self.region["height"]}
        gx, gy, size = fit_grid(frame, rel)
        self.vars["gx"].set(int(gx))
        self.vars["gy"].set(int(gy))
        self.vars["gs"].set(int(size))
        self._apply_grid()
        self._set_status("Izgara hizalandı. Tahtayı başlatma pozisyonuna getirip "
                         "“Kalibre Et”e basın.", "ok")

    def _apply_grid(self, *_):
        if not self.region:
            return
        self.detector.set_grid(
            int(self.vars["gx"].get()), int(self.vars["gy"].get()),
            int(self.vars["gs"].get()),
        )
        if self.grid_preview_on:
            self._draw_grid()

    def _toggle_grid(self):
        if not self.region:
            self._set_status("Önce bölge seçin.", "warn")
            return
        self.grid_preview_on = not self.grid_preview_on
        if self.grid_preview_on:
            self._draw_grid()
        else:
            self.overlay.clear("g")

    def _draw_grid(self):
        if not self.region:
            return
        self._apply_grid_quiet()
        ax = self.region["left"] + int(self.vars["gx"].get())
        ay = self.region["top"] + int(self.vars["gy"].get())
        self.overlay.grid("g", ax, ay, int(self.vars["gs"].get()))

    def _apply_grid_quiet(self):
        self.detector.set_grid(
            int(self.vars["gx"].get()), int(self.vars["gy"].get()),
            int(self.vars["gs"].get()),
        )

    def _calibrate(self):
        if not self.region:
            self._set_status("Önce bölge seçin.", "warn")
            return
        self._apply_grid_quiet()
        frame = self.capture.grab()
        if frame is None:
            self._set_status("Ekran yakalanamadı.", "error")
            return
        n = self.detector.calibrate(frame)
        if not n:
            self._set_status("Kalibrasyon başarısız — ızgarayı tahtaya hizalayın.", "error")
            return
        self.calib_info.configure(text=f"✓ {n}/12 taş şablonu öğrenildi", fg=config.ACCENT)
        if self.grid_preview_on:
            self.overlay.clear("g")
            self.grid_preview_on = False
        # Sanity read-back on the very same frame.
        board, conf = self.detector.detect(frame)
        if board is None:
            self._set_status("Kalibre edildi ama ilk okuma tutarsız — ızgarayı dengeleyin.",
                             "warn")
        else:
            self._set_status(
                f"Kalibre edildi · güven {conf:.2f} · {board.fen()}", "ok")
        self._set_board(board)
        self._init_logger()
        if self.worker is None or not self.worker.is_alive():
            self._start_worker(paused=True)

    # --- engine / logger ---------------------------------------------
    def _init_logger(self):
        if self.logger is None:
            from .logger import GameLogger
            self.logger = GameLogger()
        else:
            self.logger.new_game()

    def _start_worker(self, paused=True):
        from .analyzer import Analyzer
        if self.worker is not None and self.worker.is_alive():
            self.worker.paused = paused
            return
        self.worker = Analyzer(self.capture, self.detector, self.engine, self.logger)
        self.worker.paused = paused
        self.worker.start()

    def _toggle_live(self):
        if self.worker is None or not self.worker.is_alive():
            if not self.detector.calibrated:
                self._set_status("Önce bölge seçip kalibre edin.", "warn")
                return
            self._start_worker(paused=False)
            self.overlay.clear()
            self.start_btn.configure(text="Canlıyı Durdur", bg=config.ERROR, fg="#f2f5f7")
            self._set_status("Canlı analiz çalışıyor — tahtayı izliyorum.", "ok")
            return
        if self.worker.paused:
            self.worker.paused = False
            self.start_btn.configure(text="Canlıyı Durdur", bg=config.ERROR, fg="#f2f5f7")
            self._set_status("Canlı analiz devam ediyor.", "ok")
        else:
            self.worker.paused = True
            self.start_btn.configure(text="Canlı Başlat", bg=config.ACCENT, fg="#0a0d11")
            self.overlay.clear()
            self._set_status("Canlı analiz duraklatıldı.", "warn")

    def _save_game(self):
        if self.logger is None or not self.logger._entries:
            messagebox.showinfo("Kayıt", "Kaydedilecek analiz yok.")
            return
        path = self.logger.save()
        self._set_status(f"Kaydedildi: {path}", "ok")

    # --- hotkeys ------------------------------------------------------
    def _init_hotkey(self):
        self.hotkey = hk.HotkeyManager(self._on_hotkey)
        try:
            self.hotkey.start()
            self.hk_lbl.configure(
                text=f"Klavye: {self.hotkey.label()}   ·   Fare: {self.hotkey.mouse_label()}"
            )
        except Exception as exc:
            self.hk_lbl.configure(text=f"Hotkey devre dışı: {exc}")

    def _on_hotkey(self):
        # Called from the listener thread -> marshal onto Tk.
        self.after(0, self._hotkey_action)

    def _hotkey_action(self):
        if not self.detector.calibrated:
            self._set_status("Hotkey: henüz kalibre değil.", "warn")
            return
        if self.worker is None or not self.worker.is_alive():
            self._start_worker(paused=False)
        self.worker.request_analysis()
        self.overlay.clear()
        self._set_status("Hotkey: anlık analiz istendi…", "ok")

    def _remap_hotkey(self):
        if self.hotkey is None:
            return
        self._set_status("Yeni tuş kombinasyonuna basın (modifiye tuş + bir tuş)…", "warn")

        def done(keys):
            self.after(0, lambda: self._hotkey_done(keys))

        self.hotkey.record_combo(done)

    def _hotkey_done(self, keys):
        self.hotkey.set_combo(keys)
        self.hk_lbl.configure(
            text=f"Klavye: {self.hotkey.label()}   ·   Fare: {self.hotkey.mouse_label()}"
        )
        self._set_status(f"Hotkey güncellendi: {self.hotkey.label()}", "ok")

    # --- results ------------------------------------------------------
    def _set_board(self, board):
        self.current_board = board
        if board is None:
            self.turn_lbl.configure(text="")
            return
        side = "Beyaz" if board.turn else "Siyah"
        self.turn_lbl.configure(text=f"sıra: {side}")

    def _show_lines(self, board, lines, conf, reason):
        self.current_lines = lines
        self._set_board(board)
        if not lines:
            self.eval_lbl.configure(text="—", fg=config.FG)
            self.eval_sub.configure(text="motor hamle üretmedi")
            self.best_lbl.configure(text="—")
            return
        best = lines[0]
        my = self.color_var.get()
        pov = best["score_cp"] if my == "white" else -best["score_cp"]
        if abs(best["score_cp"]) >= 90000:
            txt, sub, tone = "MAT", "mat programı", config.ACCENT
        else:
            txt = f"{pov / 100.0:+.2f}"
            if pov > 1.5:
                sub, tone = "kazançlı", config.ACCENT
            elif pov > 0.4:
                sub, tone = "hafif avantaj", config.ACCENT
            elif pov >= -0.4:
                sub, tone = "dengeli", config.FG
            elif pov >= -1.5:
                sub, tone = "hafif geride", config.WARN
            else:
                sub, tone = "riskli", config.ERROR
        self.eval_lbl.configure(text=txt, fg=tone)
        self.eval_sub.configure(
            text=f"{sub} · {my == 'white' and 'beyaz' or 'siyah'} açısından · güven {conf:.2f}"
        )
        self.best_lbl.configure(text=move_label(board, best["move"]))

        # Candidates
        self._clear_cand_empty()
        for w in self.cand_rows:
            w.destroy()
        self.cand_rows = []
        for i, l in enumerate(lines):
            row = tk.Frame(self.cand_box, bg=config.BG_RAISED, height=26)
            row.pack(fill=tk.X, pady=1)
            row.pack_propagate(False)
            is_best = i == 0
            tk.Label(row, text=str(i + 1), bg=config.BG_RAISED,
                     fg=config.ACCENT if is_best else config.FG_MUTED,
                     font=(MONO, 10, "bold"), width=3, anchor="w"
                     ).pack(side=tk.LEFT)
            tk.Label(row, text=move_label(board, l["move"]), bg=config.BG_RAISED,
                     fg=config.ACCENT if is_best else config.FG,
                     font=(MONO, 11, "bold" if is_best else "normal"), anchor="w"
                     ).pack(side=tk.LEFT, padx=(0, 10))
            pv = " ".join(m.uci() for m in l["pv"][1:5])
            tk.Label(row, text=pv, bg=config.BG_RAISED, fg=config.FG_MUTED,
                     font=(MONO, 9), anchor="w").pack(side=tk.LEFT, expand=True, fill=tk.X)
            tk.Label(row, text=fmt_cp(l["score_cp"]), bg=config.BG_RAISED,
                     fg=config.FG, font=(MONO, 11, "bold"), width=8, anchor="e"
                     ).pack(side=tk.RIGHT)
            tk.Label(row, text=f'd{l["depth"]}', bg=config.BG_RAISED,
                     fg=config.FG_MUTED, font=(MONO, 9), width=5, anchor="e"
                     ).pack(side=tk.RIGHT)
            self.cand_rows.append(row)

        if reason:
            self._set_reason(reason)
        self._draw_marks(board, lines)

    def _set_reason(self, text):
        self.reason.configure(state="normal")
        self.reason.delete("1.0", tk.END)
        if not text:
            self.reason.insert(
                "1.0",
                "Henüz analiz yok.\n\n"
                "Bölge seçip kalibre ettikten sonra tahtadaki her değişiklikte "
                "burada şunlar görünecek:\n"
                "  · neden bu hamlenin en iyi olduğu\n"
                "  · rakip adayların neden puan/derinlik açısından geride kaldığı\n"
                "  · motorun öngördüğü devam planı",
                "ph",
            )
        else:
            self.reason.insert("1.0", text)
        self.reason.configure(state="disabled")

    def _clear_cand_empty(self):
        if self.cand_empty.winfo_ismapped():
            self.cand_empty.pack_forget()

    def _draw_marks(self, board, lines):
        if not self.region or not lines:
            return
        self.overlay.clear("m")
        ox, oy = self.region["left"], self.region["top"]
        best = lines[0]["move"]
        orig = self.detector.square_box(best.from_square)
        dest = self.detector.square_box(best.to_square)
        box = lambda b: (b[0] + ox, b[1] + oy, b[2], b[3])
        # Yellow on the piece you should move, green ring on where it lands,
        # translucent arrow tying them together.
        self.overlay.fill("m.origin", box(orig), "#ffd23c", alpha=0.38)
        self.overlay.ring("m.dest", box(dest), "#2ea87c", alpha=0.98, thickness=4)
        self.overlay.arrow("m.arrow", box(orig), box(dest), "#2ea87c", alpha=0.72,
                           width=max(5, int(self.detector.cell * 0.10)))
        # Fainter marks on the rejected candidates.
        for l in lines[1:3]:
            b = self.detector.square_box(l["move"].to_square)
            self.overlay.ring("m.alt" + l["move"].uci(), box(b), "#c9884a",
                              alpha=0.6, thickness=2)

    # --- main loop ----------------------------------------------------
    def _tick(self):
        w = getattr(self, "worker", None)
        if w is not None:
            try:
                while True:
                    msg = w.out.get_nowait()
                    self._handle(msg)
            except Exception:
                pass
        self.overlay.pulse()
        self.after(45, self._tick)

    def _handle(self, msg):
        kind = msg.get("kind")
        if kind == "detect":
            st = msg.get("status")
            if st == "ok":
                self.status_dot.configure(text="●  izleniyor", fg=config.ACCENT)
            elif st == "low_conf":
                self.status_dot.configure(text="●  güven düşük", fg=config.WARN)
                self._set_status(
                    f'Tespit güveni {msg.get("conf", 0):.2f} — ızgarayı kontrol edin.',
                    "warn")
            elif st == "unsure":
                self.status_dot.configure(text="●  aranıyor", fg=config.WARN)
        elif kind == "analysis":
            self.status_dot.configure(text="●  analiz edildi", fg=config.ACCENT)
            self._show_lines(msg["board"], msg["lines"], msg.get("conf", 1.0),
                             msg.get("reason", ""))
            self._set_status(f'{msg.get("n", 0)}. analiz tamamlandı.', "ok")
        elif kind == "error":
            self.status_dot.configure(text="●  hata", fg=config.ERROR)
            self._set_status(f'Hata: {msg.get("message", "")}', "error")

    # --- shutdown -----------------------------------------------------
    def _on_close(self):
        if getattr(self, "_closing", False):
            return
        self._closing = True
        try:
            if self.worker:
                self.worker.stop()
        except Exception:
            pass
        try:
            if self.hotkey:
                self.hotkey.stop()
        except Exception:
            pass
        try:
            self.engine.stop()
        except Exception:
            pass
        try:
            self.overlay.close()
        except Exception:
            pass
        try:
            self.destroy()
        except tk.TclError:
            pass


def run():
    app = App()
    app.mainloop()
