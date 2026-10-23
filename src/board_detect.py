# -*- coding: utf-8 -*-
"""Board detection: auto grid fitting + per-square template matching.

Calibration learns one template per piece from the screen itself, so no bundled
piece images are needed and any chess theme works. Each patch is reduced
against its own square's background first, which is what lets a template mean
the same thing on a light and a dark square — and therefore be keyed by symbol
alone, so a square colour the starting position never covers still has a
candidate.
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


def _patch(img):
    """Representative map for one square: plain grayscale as float32.

    Intensity rather than edges, deliberately. White and black pieces usually
    share a silhouette and differ only in fill, so a pure edge map produces
    near-identical templates for ``K`` and ``k`` — NCC subtracts the mean and
    is blind to absolute brightness. Grayscale keeps the fill information;
    subtracting the square's own background (see ``calibrate``) then removes
    the light/dark board difference on top of that.
    """
    if HAS_CV2:
        return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY).astype(np.float32)
    return img.mean(axis=2).astype(np.float32)


def _ncc(a, b):
    """Normalised cross-correlation of two flat arrays.

    A featureless square against a featureless template is a *perfect* match
    (both empty) — returning 0.0 there would drag confidence to zero on every
    unoccupied square. One flat and one detailed means they clearly do not
    match, so that stays 0.0.
    """
    a = a.ravel().astype(np.float64)
    b = b.ravel().astype(np.float64)
    a -= a.mean()
    b -= b.mean()
    da = np.sqrt((a * a).sum())
    db = np.sqrt((b * b).sum())
    if da < 1e-6 and db < 1e-6:
        return 1.0
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
        # On a brown/green board saturation carries this mask; on a grey theme
        # it is only the 1px grid lines. Bridge them with a kernel wider than
        # one square (8x8 board, so size//6 spans a whole square) *before*
        # opening — opening first simply erases every thin line and the
        # contour then matches a clump of pieces instead of the board.
        k = max(9, (min(w, h) // 6) | 1)
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
    """Reject impossible positions (animation frames, total misreads).

    A transient frame may miss a king because a piece was mid-move, so a
    missing king alone is tolerated. Material overflow, pawns on the back rank
    and bad castling rights mean the read is garbage.
    """
    if board is None:
        return False
    if board.is_valid():
        return True
    fatal_names = (
        "STATUS_EMPTY", "STATUS_TOO_MANY_KINGS",
        "STATUS_TOO_MANY_WHITE_PIECES", "STATUS_TOO_MANY_BLACK_PIECES",
        "STATUS_TOO_MANY_WHITE_PAWNS", "STATUS_TOO_MANY_BLACK_PAWNS",
        "STATUS_PAWNS_ON_BACKRANK", "STATUS_BAD_CASTLING_RIGHTS",
        "STATUS_INVALID_EP_SQUARE", "STATUS_OPPOSITE_CHECK",
    )
    fatal = 0
    for name in fatal_names:
        fatal |= int(getattr(chess, name, 0))
    return (int(board.status()) & fatal) == 0


def position_key(board):
    """Stable identity of a position.

    Placement, side to move and castling rights — not the halfmove/fullmove
    counters, which a screen read never knows (so comparing full FENs would
    report a change every tick and never match the tracked game), and not
    en passant, which is derived from the transition rather than the position
    itself: a double push always changes the placement, so it is always caught.
    """
    if board is None:
        return None
    return (board.board_fen(), board.turn, board.castling_rights)


def restore_castling(board):
    """Recover castling rights from piece placement.

    The screen only shows pieces, never the rights field, so a raw read always
    says ``- -``. That leaves Stockfish unable to consider a single castle and
    never matches the tracked game (which starts with ``KQkq``).

    A side keeps a right exactly while its king and rook are still home — the
    only arrangement python-chess accepts, so this cannot invent an illegal
    state. It cannot see that a rook left and came back, but silently losing
    castling in every opening is far the worse failure of the two.

    ``clean_castling_rights`` cannot be used here: it only *filters* rights
    that are already set, so it returns 0 for a fresh read.
    """
    home = 0
    if (board.piece_at(chess.E1) == chess.Piece(chess.KING, chess.WHITE)
            and board.piece_at(chess.H1) == chess.Piece(chess.ROOK, chess.WHITE)):
        home |= chess.BB_H1
    if (board.piece_at(chess.E1) == chess.Piece(chess.KING, chess.WHITE)
            and board.piece_at(chess.A1) == chess.Piece(chess.ROOK, chess.WHITE)):
        home |= chess.BB_A1
    if (board.piece_at(chess.E8) == chess.Piece(chess.KING, chess.BLACK)
            and board.piece_at(chess.H8) == chess.Piece(chess.ROOK, chess.BLACK)):
        home |= chess.BB_H8
    if (board.piece_at(chess.E8) == chess.Piece(chess.KING, chess.BLACK)
            and board.piece_at(chess.A8) == chess.Piece(chess.ROOK, chess.BLACK)):
        home |= chess.BB_A8
    board.castling_rights = home
    return board


def apply_transition(prev, cur):
    """Resolve what the screen cannot show: side to move and en passant.

    Neither is visible in a position read — ``detect`` can only ever build a
    board that starts white to move. But between two *different* reads exactly
    one move happened, which determines both:

    * the side that just moved hands over, so the new side to move is the flip
      of the previous one; when the placement is unchanged nothing was played,
      so the previous side is carried across instead of resetting to white;
    * a pawn that advanced two ranks leaves its en-passant square behind it,
      and that square is only discoverable from the transition.

    With ``prev is None`` (the first read of a session) there is no history to
    infer from, so the read stands as white to move — correct for a game
    calibrated at the starting position.
    """
    if prev is None:
        return cur
    changed = prev.board_fen() != cur.board_fen()
    turn = (not prev.turn) if changed else prev.turn

    parts = cur.fen().split(" ")
    parts[1] = "w" if turn else "b"
    # An en-passant square belongs to one position only. When the board moved
    # it must be cleared first — carrying the previous one forward left a stale
    # square python-chess rejects, and the fallback then threw away the side to
    # move that had just been worked out.
    if changed:
        parts[3] = "-"
    elif prev.ep_square is None:
        parts[3] = "-"
    else:
        parts[3] = chess.square_name(prev.ep_square)
    try:
        out = chess.Board(" ".join(parts))
    except ValueError:
        return cur
    if not validate(out):
        return cur

    if changed:
        ep = _double_push(prev, cur)
        if ep is not None:
            with_ep = list(parts)
            with_ep[3] = chess.square_name(ep)
            try:
                cand = chess.Board(" ".join(with_ep))
            except ValueError:
                cand = None
            # Only adopt it when python-chess agrees an enemy pawn really can
            # capture; an un-capturable square would mark the board invalid.
            if cand is not None and validate(cand):
                out = cand
    return out


def _double_push(prev, cur):
    """Square left behind by a two-square pawn advance, or None."""
    for sq in chess.SQUARES:
        p = prev.piece_at(sq)
        if p is None or p.piece_type != chess.PAWN or p.color != prev.turn:
            continue
        dest = sq + (16 if p.color == chess.WHITE else -16)
        skipped = sq + (8 if p.color == chess.WHITE else -8)
        if not (0 <= dest < 64):
            continue
        if (prev.piece_at(dest) is None and prev.piece_at(skipped) is None
                and cur.piece_at(dest) == p
                and cur.piece_at(skipped) is None):
            return skipped
    return None


class BoardDetector:
    """Calibrate on a known position, then read positions frame by frame."""

    def __init__(self, margin_frac=0.07, min_score=0.55):
        self.margin_frac = margin_frac
        self.min_score = min_score
        self.templates = {}          # symbol -> background-reduced patch
        self.bg = {}                 # is_light -> mean empty-square patch
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
        """Yield (row, col, crop) for each square, inset by the margin.

        The inset is computed once and applied to every square, and squares
        that would reach past the captured region are skipped. Truncating each
        edge independently made neighbouring crops differ by a pixel when the
        cell size was not whole, and clipped crops came back ragged —
        ``np.mean`` over those raises on inhomogeneous shapes.
        """
        h, w = frame.shape[:2]
        inset = int(round(self.cell * self.margin_frac))
        side = max(1, int(round(self.cell)) - 2 * inset)
        for r in range(8):
            for c in range(8):
                x0 = int(round(self.board_x + c * self.cell)) + inset
                y0 = int(round(self.board_y + r * self.cell)) + inset
                if x0 < 0 or y0 < 0 or x0 + side > w or y0 + side > h:
                    continue
                yield r, c, frame[y0:y0 + side, x0:x0 + side]

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
        """Learn templates from a frame showing ``fen``.

        Each patch is first reduced against its own square's background, then
        keyed by **symbol alone** rather than (symbol, square colour). Two
        reasons:

        * the starting position never covers all 20 pairs — the white king
          never stands on a light square, the queen never on a dark one — and
          a square whose pair was never trained had no candidate at all, so it
          fell through to whatever matched best and read as a wrong piece;
        * background subtraction makes a patch mean the same thing on a light
          and a dark square, so one template per piece covers both.

        Returns the number of piece templates learned.
        """
        board = chess.Board(fen)
        buckets = {}
        for r, c, crop in self._cells(frame):
            if crop.size == 0:
                continue
            is_light = (r + c) % 2 == 0
            sq = chess.square(c, 7 - r)
            piece = board.piece_at(sq)
            key = piece.symbol() if piece else "empty"
            buckets.setdefault((key, is_light), []).append(_patch(crop))
        means = {k: np.mean(v, axis=0) for k, v in buckets.items()}
        self.bg = {light: means.get(("empty", light)) for light in (True, False)}
        # Average every sample: a piece occurs on both square colours and
        # several times, which denoises the template.
        by_sym = {}
        for (sym, light), tpl in means.items():
            if sym == "empty":
                continue
            bg = self.bg.get(light)
            by_sym.setdefault(sym, []).append(
                tpl - bg if (bg is not None and bg.shape == tpl.shape) else tpl
            )
        self.templates = {s: np.mean(v, axis=0) for s, v in by_sym.items()}
        self.calibrated = bool(self.templates)
        return len(self.templates)

    # --- detection ----------------------------------------------------
    def detect(self, frame, min_score=None):
        """Read a position. Returns (board | None, confidence 0..1).

        Confidence is the mean best-match score over the squares that had any
        content. Taking the minimum meant one weak square rejected the whole
        frame; averaging in the featureless empty squares meant a misaligned
        grid still scored ~0.9 while reading garbage.
        """
        if not self.calibrated:
            return None, 0.0
        thr = self.min_score if min_score is None else min_score
        board = chess.Board(None)
        scores = []
        seen = 0
        for r, c, crop in self._cells(frame):
            seen += 1
            is_light = (r + c) % 2 == 0
            e = _patch(crop)
            bg = self.bg.get(is_light)
            resid = e - bg if (bg is not None and bg.shape == e.shape) else e
            if float(resid.std()) < 1e-6:
                # Featureless square: it only says "no piece here". Counting
                # those let a badly misaligned grid score ~0.9 while reading
                # garbage, because half the board is empty. Skipping them makes
                # confidence track the squares that actually carry a piece.
                continue
            best_sym, best = None, -1.0
            for sym, tpl in self.templates.items():
                if tpl.shape != resid.shape:
                    continue
                s = _ncc(resid, tpl)
                if s > best:
                    best_sym, best = sym, s
            if best_sym is None:
                continue
            scores.append(best)
            # NCC is scale-invariant, so a faint piece still scores like its
            # template while a low-amplitude residual of pure noise correlates
            # with nothing and lands well under the threshold.
            if best >= thr:
                board.set_piece_at(
                    chess.square(c, 7 - r), chess.Piece.from_symbol(best_sym)
                )
        conf = float(np.mean(scores)) if scores else 0.0
        if seen < 64:
            # A grid that reaches past the captured region drops whole files or
            # ranks, and validate() would happily accept the remainder — a
            # board missing its h-file is a perfectly legal position. Refuse
            # rather than analyse an incomplete read.
            return None, conf
        if not validate(board):
            return None, conf
        return restore_castling(board), conf
