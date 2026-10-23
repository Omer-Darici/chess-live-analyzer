# -*- coding: utf-8 -*-
"""Background worker: capture -> detect -> analyse, at a fixed cadence."""
import queue
import threading
import time

import chess

from . import config
from .board_detect import apply_transition, position_key


class Analyzer(threading.Thread):
    """Polls the screen and publishes results through ``self.out`` (a Queue).

    The Tk main thread only ever reads the queue, so no cross-thread Tk calls
    happen.
    """

    def __init__(self, capture, detector, engine, logger=None):
        super().__init__(daemon=True, name="analyzer")
        self.capture = capture
        self.detector = detector
        self.engine = engine
        self.logger = logger
        self.out = queue.Queue()
        self._stop = threading.Event()
        self._force = threading.Event()
        self.paused = False
        self.last_key = None
        self._prev_board = None
        self.analysed = 0
        self.error = None

    # --- control ------------------------------------------------------
    def stop(self):
        self._stop.set()

    def request_analysis(self):
        """Hotkey: analyse the current position immediately."""
        self._force.set()

    def run(self):
        while not self._stop.is_set():
            if self.paused or not self.detector.calibrated:
                time.sleep(0.05)
                continue
            t0 = time.time()
            try:
                self._tick()
            except Exception as exc:
                self.error = str(exc)
                self.out.put({"kind": "error", "message": str(exc)})
                time.sleep(0.5)
            budget = float(config.get("poll_interval_s", 0.20))
            time.sleep(max(0.0, budget - (time.time() - t0)))

    def _tick(self):
        frame = self.capture.grab()
        if frame is None:
            return
        board, conf = self.detector.detect(frame)
        if board is None:
            self.out.put({"kind": "detect", "status": "unsure", "conf": conf})
            return

        # Neither side to move nor en passant is visible on screen; both come
        # from how this position differs from the previous accepted one.
        board = apply_transition(self._prev_board, board)
        key = position_key(board)
        fen_key = board.fen()

        changed = key != self.last_key
        if not changed and not self._force.is_set():
            return
        self._force.clear()

        min_conf = float(config.get("min_confidence", 0.55))
        if conf < min_conf:
            self.out.put({"kind": "detect", "status": "low_conf",
                          "conf": conf, "fen": fen_key})
            return

        self.out.put({"kind": "detect", "status": "ok", "conf": conf, "fen": fen_key})
        self.last_key = key
        # Only once a read is trusted: a rejected frame must not become the
        # reference the next transition is inferred from.
        self._prev_board = board

        lines = self.engine.analyse(board)
        if not lines:
            return
        self.analysed += 1

        reason = ""
        if self.logger is not None:
            reason = self.logger.record(board, lines)

        self.out.put({
            "kind": "analysis",
            "board": board,
            "lines": lines,
            "conf": conf,
            "reason": reason,
            "n": self.analysed,
        })

    # --- one-shot helpers --------------------------------------------
    def analyse_once(self, board):
        """Synchronous single analysis (used by the manual / FEN path)."""
        lines = self.engine.analyse(board)
        reason = ""
        if self.logger is not None and lines:
            reason = self.logger.record(board, lines)
        self.out.put({
            "kind": "analysis", "board": board, "lines": lines,
            "conf": 1.0, "reason": reason, "n": self.analysed + 1,
        })
        return lines
