# -*- coding: utf-8 -*-
"""Unit tests for board detection.

Run from the project root:  python tests/test_detect.py
"""
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import chess

from src.board_detect import BoardDetector, fit_grid, validate
from synth_board import CELL, position_key, synth

fails = []


def check(label, ok, extra=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {label}{('  ' + extra) if extra else ''}")
    if not ok:
        fails.append(label)


S = CELL
f0 = synth()

# 1) self-read right after calibration
d = BoardDetector()
d.set_grid(0, 0, S * 8)
n = d.calibrate(f0)
b, conf = d.detect(f0)
got = b.fen() if b else None
check("self-read", got == chess.STARTING_FEN and conf >= 0.55,
      f"conf={conf:.4f} templates={n}")
if got != chess.STARTING_FEN:
    print(f"      expected {chess.STARTING_FEN}\n      got      {got}")

# 2) after two real moves
b1 = chess.Board()
b1.push_uci("e2e4")
b1.push_uci("g8f6")
b2, conf2 = d.detect(synth(b1.fen()))
check("2 moves", b2 is not None and position_key(b2) == position_key(b1),
      f"conf={conf2:.4f}")

# 3) a mid-game position
b3 = chess.Board("r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")
b4, conf4 = d.detect(synth(b3.fen()))
check("mid-game position", b4 is not None and position_key(b4) == position_key(b3),
      f"conf={conf4:.4f}")

# 4) piece/square-colour pairs the starting position never covers: the white
#    king on a light square, the black king on a dark one, both queens swapped
#    to the "wrong" colour. These read as *wrong pieces* once templates are
#    keyed by (symbol, square colour), because no such template was ever trained.
for label, fen in (
        ("white king on a light square", "4k3/8/8/8/8/8/4K3/8 w - - 0 1"),
        ("black king on a dark square", "8/4k3/8/8/8/8/8/4K3 w - - 0 1"),
        ("all four untrained pairs", "8/4k3/8/3q4/8/8/4K3/2Q5 w - - 0 1")):
    ref = chess.Board(fen)
    bb, cc = d.detect(synth(fen))
    check(label, bb is not None and position_key(bb) == position_key(ref),
          f"conf={cc:.4f}")

# 5) a totally wrong frame is rejected, not analysed
junk = np.random.RandomState(0).randint(0, 255, (S * 8, S * 8, 3), dtype=np.uint8)
bj, cj = d.detect(junk)
check("random frame rejected", bj is None, f"conf={cj:.2f}")

# 6) validate() must never raise (it once used a constant python-chess lacks)
raised = False
for fen in (chess.STARTING_FEN, "8/8/8/8/8/8/8/8 w - - 0 1",
            "4k3/8/8/8/8/8/8/4K3 w - - 0 1", "8/8/8/8/8/8/8/8 w - - 0 2"):
    try:
        validate(chess.Board(fen))
    except Exception as exc:
        raised = True
        print("      raised:", repr(exc))
check("validate() safe", not raised)

# 7) an unconfigured detector answers (None, 0.0) rather than crashing
b7, c7 = BoardDetector().detect(f0)
check("uncalibrated", b7 is None and c7 == 0.0)

# 8) a badly misaligned grid must not produce a confident read
d_off = BoardDetector()
d_off.set_grid(20, 20, S * 8)
d_off.calibrate(f0)
b8, c8 = d_off.detect(synth(b1.fen()))
ok8 = (b8 is None) or (c8 < 0.55) or (position_key(b8) == position_key(b1))
check("half-cell offset never reads confidently wrong", ok8, f"conf={c8:.4f}")

# 9) fit_grid must recover the board on a *grey* theme too: saturation is zero
#    there, so only the square grid lines are available as structure.
big = np.full((760, 1400, 3), (34, 36, 40), np.uint8)
src = synth()
ox, oy = 233, 111
big[oy:oy + src.shape[0], ox:ox + src.shape[1]] = src
x, y, side = fit_grid(big, {"left": ox - 40, "top": oy - 40,
                            "width": src.shape[1] + 80,
                            "height": src.shape[0] + 80})
check("fit_grid recovers an offset board",
      abs(x - ox) <= 8 and abs(y - oy) <= 8 and abs(side - S * 8) <= 8,
      f"x={x} y={y} side={side}")

# 10) repeated reads stay stable
b10, c10 = d.detect(synth(b1.fen()))
check("repeat detection stable",
      b10 is not None and position_key(b10) == position_key(b1), f"conf={c10:.4f}")

print("\n" + ("ALL PASSED" if not fails else f"FAILED: {fails}"))
sys.exit(1 if fails else 0)
