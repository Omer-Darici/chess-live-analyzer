# -*- coding: utf-8 -*-
"""A synthetic chess board good enough to exercise the real detector.

The point is realism where the detector is sensitive to it:

* every piece gets a dark outline, and white pieces are light-filled while
  black pieces are near-black — real sets differ in *fill*, not in silhouette,
  and an edge-only representation cannot tell ``K`` from ``k``;
* squares are flat, because a real board theme is flat inside a square;
* both square colours are present, so calibration learns two backgrounds.

Used by ``tests/test_detect.py`` and ``tests/test_flow.py``.
"""
import cv2
import numpy as np
import chess

CELL = 40

_SHAPES = {
    chess.PAWN: 0, chess.KNIGHT: 1, chess.BISHOP: 2,
    chess.ROOK: 3, chess.QUEEN: 4, chess.KING: 5,
}


def synth(fen=chess.STARTING_FEN, cell=CELL):
    """Render ``fen`` as an RGB frame of 8x8 ``cell``-pixel squares."""
    img = np.zeros((cell * 8, cell * 8, 3), np.uint8)
    board = chess.Board(fen)
    yy, xx = np.mgrid[0:cell, 0:cell]
    m = cell // 2
    rad = cell // 2 - 4
    d2 = (yy - m) ** 2 + (xx - m) ** 2

    for r in range(8):
        for c in range(8):
            base = 220 if (r + c) % 2 == 0 else 150
            y0, x0 = r * cell, c * cell
            sub = img[y0:y0 + cell, x0:x0 + cell]
            sub[:] = (base, base, base)
            piece = board.piece_at(chess.square(c, 7 - r))
            if piece is None:
                continue

            k = _SHAPES[piece.piece_type]
            if k == 0:
                mask = d2 <= rad * rad * 0.35
            elif k == 1:
                mask = (np.abs(yy - m) + np.abs(xx - m)) <= rad
            elif k == 2:
                mask = ((np.abs(yy - xx) <= rad // 2)
                        & (np.abs(yy - (cell - 1 - xx)) <= rad // 2))
            elif k == 3:
                mask = (np.abs(yy - m) <= rad // 2) | (np.abs(xx - m) <= rad // 2)
            elif k == 4:
                mask = d2 <= rad * rad
            else:
                mask = (d2 <= rad * rad) & (d2 >= (rad // 2) ** 2)

            sub[mask] = (245, 245, 245) if piece.color else (18, 18, 18)
            inner = cv2.erode(mask.astype(np.uint8),
                              np.ones((3, 3), np.uint8)).astype(bool)
            sub[mask & ~inner] = (25, 25, 25)
    return img


def position_key(board):
    """Identity used by the tests: placement, side, castling — no counters."""
    if board is None:
        return None
    return (board.board_fen(), board.turn, board.castling_rights)
