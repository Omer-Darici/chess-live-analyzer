# -*- coding: utf-8 -*-
"""Stockfish wrapper (python-chess UCI)."""
import threading

import chess
import chess.engine

from . import config


def _score_cp(score):
    """ScoreInfo -> centipawns from White's point of view."""
    w = score.white()
    if w.is_mate():
        m = w.mate()
        # Mate distance sign; keep it far outside normal cp range.
        return (100000 - abs(m) * 100) * (1 if m and m > 0 else -1)
    cp = w.score()
    return float(cp) if cp is not None else 0.0


class Engine:
    """Thread-safe wrapper: analyse() may be called from the worker thread."""

    def __init__(self, path=None):
        self.path = path or config.get("stockfish_path")
        self._eng = None
        self._lock = threading.Lock()
        self.error = None

    def start(self):
        with self._lock:
            if self._eng is not None:
                return True
            try:
                eng = chess.engine.SimpleEngine.popen_uci(self.path)
                eng.configure({
                    "Threads": int(config.get("threads", 2)),
                    "Hash": int(config.get("hash_mb", 128)),
                })
                self._eng = eng
                self.error = None
                return True
            except Exception as exc:
                self.error = str(exc)
                self._eng = None
                return False

    def available(self):
        import os
        return os.path.isfile(self.path)

    def stop(self):
        with self._lock:
            if self._eng is not None:
                try:
                    self._eng.quit()
                except Exception:
                    pass
                self._eng = None

    def analyse(self, board, movetime_ms=None, depth=None, multipv=None):
        """Return ranked lines: [{move, score_cp, mate, depth, pv}]."""
        if not self.start():
            raise RuntimeError(self.error or "Stockfish baslatilamadi")
        limit = chess.engine.Limit(
            time=(movetime_ms or config.get("movetime_ms", 300)) / 1000.0,
            depth=depth or config.get("depth", 18),
        )
        pv_n = int(multipv or config.get("multipv", 3))
        with self._lock:
            res = self._eng.analyse(board, limit, multipv=pv_n)
        if isinstance(res, dict):
            res = [res]

        lines = []
        for info in res:
            pv = info.get("pv") or []
            if not pv:
                continue
            score = info["score"]
            lines.append({
                "move": pv[0],
                "score_cp": _score_cp(score),
                "mate": score.white().mate(),
                "depth": int(info.get("depth", 0)),
                "pv": pv,
            })
        lines.sort(key=lambda d: -d["score_cp"])
        return lines
