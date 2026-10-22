# -*- coding: utf-8 -*-
"""Board detection: auto grid fitting + per-square template matching.

Calibration learns one edge template per (piece, square-colour) pair from the
screen itself, so no bundled piece images are needed and any chess theme works.
Square colour matters: the same piece on a light vs dark square has a different
edge signature, so templates are keyed by both.
"""
import numpy as np
import chess

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


def _gray(img):
    if HAS_CV2:
        return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY).astype(np.float32)
    return img.mean(axis=2).astype(np.float32)


def _edges(img):
    g = _gray(img)
    if HAS_CV2:
        e = cv2.Canny(g.astype(np.uint8), 60, 160)
        return e.astype(np.float32) / 255.0
    gx = np.abs(np.diff(g, axis=1, prepend=g[:, :1]))
    gy = np.abs(np.diff(g, axis=0, prepend=g[:1, :]))
    return np.clip((gx + gy) / 60.0, 0, 1).astype(np.float32)


def _ncc(a, b):
    """Normalised cross-correlation of two flat arrays."""
    a = a.ravel().astype(np.float64)
    b = b.ravel().astype(np.float64)
    a -= a.mean()
    b -= b.mean()
    da = np.sqrt((a * a).sum())
    db = np.sqrt((b * b).sum())
    if da < 1e-6 or db < 1e-6:
        return 0.0
    return float((a * b).sum() / (da * db))


def fit_grid(frame, region, pad=0):
    """Snap a rough user-drawn region onto the real 8x8 board bounds.

    Falls back to the region itself when detection is not confident, so the
    user can always correct it numerically in the UI.
    """
    x0 = int(region["left"])
    y0 = int(region["top"])
    w = int(region["width"])
    h = int(region["height"])
    fallback = (x0, y0, min(w, h))
    if w < 40 or h < 40:
        return fallback
    sub = frame[y0:y0 + h, x0:x0 + w]
    if sub.size == 0 or not HAS_CV2:
        return fallback
    try:
        hsv = cv2.cvtColor(sub, cv2.COLOR_RGB2HSV)
        sat = hsv[:, :, 1]
        contrast = cv2.Laplacian(_gray(sub).astype(np.uint8), cv2.CV_8U)
        mask = (((sat > 45) | (contrast > 25)).astype(np.uint8)) * 255
        k = max(9, min(w, h) // 20 | 1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            return fallback
        c = max(cnts, key=cv2.contourArea)
        bx, by, bw, bh = cv2.boundingRect(c)
        if bw < 64 or bh < 64:
            return fallback
        size = int(min(bw, bh))
        if size < 64:
            return fallback
        return (x0 + bx, y0 + by, size)
    except Exception:
        return fallback


def validate(board):
    """Reject impossible positions (animation frames, partial reads)."""
    if board is None:
        return False
    if board.is_valid():
        return True
    # Tolerate "both kings gone" during a redraw, but nothing worse.
    return board.status() in (chess.STATUS_NO_KINGS,)


class BoardDetector:
    """Calibrate on a known position, then read positions frame by frame."""

    def __init__(self, margin_frac=0.07, min_score=0.55):
        self.margin_frac = margin_frac
        self.min_score = min_score
        self.templates = {}          # (symbol, is_light) -> edge template
        self.bg = {}                 # is_light -> mean empty-square edge map
        self.board_x = 0
        self.board_y = 0
        self.board_size = 0
        self.cell = 0.0
        self.calibrated = False

    # --- geometry -----------------------------------------------------
    def set_grid(self, x, y, size):
        self.board_x, self.board_y, self.board_size = int(x), int(y), int(size)
        self.cell = self.board_size / 8.0

    def grid(self):
        return (self.board_x, self.board_y, self.board_size)

    def _cells(self, frame):
        """Yield (row, col, crop) for each square, inset by the margin."""
        m = self.cell * self.margin_frac
        x0b, y0b = self.board_x, self.board_y
        for r in range(8):
            for c in range(8):
                x0 = int(x0b + c * self.cell + m)
                y0 = int(y0b + r * self.cell + m)
                x1 = int(x0b + (c + 1) * self.cell - m)
                y1 = int(y0b + (r + 1) * self.cell - m)
                if x1 <= x0 or y1 <= y0:
                    continue
                yield r, c, frame[y0:y1, x0:x1]

    def square_box(self, sq, inset=True):
        """Screen box (x, y, w, h) for a python-chess square."""
        col, row = sq % 8, 7 - sq // 8
        m = self.cell * (self.margin_frac if inset else 0.0)
        x = self.board_x + col * self.cell + m
        y = self.board_y + row * self.cell + m
        return (int(x), int(y), int(self.cell - 2 * m), int(self.cell - 2 * m))

    def square_name_at(self, px, py):
        """Board square under a screen point, or None."""
        if not self.cell:
            return None
        col = int((px - self.board_x) // self.cell)
        row = int((py - self.board_y) // self.cell)
        if not (0 <= col < 8 and 0 <= row < 8):
            return None
        return chess.square(col, 7 - row)

    # --- calibration --------------------------------------------------
    def calibrate(self, frame, fen=chess.STARTING_FEN):
        """Learn templates from a frame showing ``fen``. Returns count learned."""
        board = chess.Board(fen)
        self.templates.clear()
        empty = {True: [], False: []}
        n = 0
        for r, c, crop in self._cells(frame):
            if crop.size == 0:
                continue
            is_light = (r + c) % 2 == 0
            sq = chess.square(c, 7 - r)
            e = _edges(crop)
            piece = board.piece_at(sq)
            if piece is None:
                empty[is_light].append(e)
            else:
                self.templates[(piece.symbol(), is_light)] = e
                n += 1
        for light, lst in empty.items():
            self.bg[light] = np.mean(lst, axis=0) if lst else None
        self.calibrated = n > 0
        return n

    # --- detection ----------------------------------------------------
    def detect(self, frame, min_score=None):
        """Read a position. Returns (board | None, confidence 0..1)."""
        if not self.calibrated:
            return None, 0.0
        thr = self.min_score if min_score is None else min_score
        board = chess.Board(None)
        worst = 1.0
        for r, c, crop in self._cells(frame):
            if crop.size == 0:
                continue
            is_light = (r + c) % 2 == 0
            e = _edges(crop)
            bg = self.bg.get(is_light)
            resid = e
            if bg is not None and bg.shape == e.shape:
                resid = np.clip(e - bg, 0.0, 1.0)
            best_sym, best = None, -1.0
            for (sym, light), tpl in self.templates.items():
                if light != is_light or tpl.shape != resid.shape:
                    continue
                s = _ncc(resid, tpl)
                if s > best:
                    best_sym, best = sym, s
            if best_sym is not None and best >= thr:
                board.set_piece_at(
                    chess.square(c, 7 - r), chess.Piece.from_symbol(best_sym)
                )
                worst = min(worst, best)
            else:
                worst = min(worst, max(0.0, 1.0 - (thr - max(best, 0.0)) * 2.0))
        if not validate(board):
            return None, 0.0
        return board, worst
