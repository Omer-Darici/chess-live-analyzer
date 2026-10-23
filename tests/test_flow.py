# -*- coding: utf-8 -*-
"""End-to-end: synthetic screen frames -> detector -> analyzer -> logger.

Exercises what the tool actually promises:

* every position produces an analysis (confidence used to sit at 0.0, so the
  worker never got past the low-confidence gate);
* castling rights come back (they were always "-" — invisible on screen);
* side to move alternates (a raw read can only ever be white to move);
* a double pawn push exposes its en-passant square;
* the tracked game records the moves that were *played*, not the ones the
  engine suggested, and the PGN replays to that same game.

Run from the project root:  python tests/test_flow.py
"""
import io
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chess
import chess.pgn

from src.analyzer import Analyzer
from src.board_detect import BoardDetector, apply_transition, position_key
from src.logger import GameLogger
from synth_board import CELL, synth

fails = []


def check(label, ok, extra=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {label}{('  ' + extra) if extra else ''}")
    if not ok:
        fails.append(label)


S = CELL

# ---- a real game: six moves, alternating, with a double push ---------------
PLAYED = ["e2e4", "d7d6", "e4e5", "f7f5", "g1f3", "b8c6"]
frames = [chess.Board()]
for uci in PLAYED:
    frames.append(frames[-1].copy())
    frames[-1].push_uci(uci)

ep_idx = PLAYED.index("f7f5") + 1          # 4...f7f5; 5.exf6 e.p. is legal
check("setup: en passant is legal after f7f5",
      frames[ep_idx].ep_square == chess.F6,
      f"ep={chess.square_name(frames[ep_idx].ep_square)}")
check("setup: sides really alternate",
      all(frames[i].turn != frames[i + 1].turn for i in range(len(frames) - 1)))

imgs = [synth(b.fen()) for b in frames]

# ---- detector: every frame readable, transitions resolving correctly -------
det = BoardDetector()
det.set_grid(0, 0, S * 8)
n = det.calibrate(imgs[0])
check("calibrated one template per piece", n == 12, f"templates={n}")

resolved, bad = [], []
prev = None
for i, img in enumerate(imgs):
    raw, conf = det.detect(img)
    if raw is None:
        bad.append((i, "frame rejected", conf, None))
        continue
    got = apply_transition(prev, raw)
    if position_key(got) != position_key(frames[i]):
        played = frames[i].move_stack[-1].uci() if frames[i].move_stack else "start"
        bad.append((i, played, conf, got.fen()))
    resolved.append(got)
    prev = got
check("every frame reads correctly (placement, turn, castling)",
      not bad, f"{len(frames) - len(bad)}/{len(frames)}")
for i, what, conf, fen in bad:
    print(f"      frame {i} ({what}): conf={conf:.3f} got={fen}")

_, read_conf = det.detect(imgs[0])
check("calibration read-back clears the confidence gate", read_conf >= 0.55,
      f"conf={read_conf:.4f}")

# ---- en passant, resolved through the real chain ---------------------------
check("en passant inferred from the transition",
      len(resolved) > ep_idx and resolved[ep_idx].ep_square == chess.F6,
      f"ep={chess.square_name(resolved[ep_idx].ep_square)}")

if len(resolved) > ep_idx:
    reread = apply_transition(resolved[ep_idx], det.detect(imgs[ep_idx])[0])
    check("re-reading the same position changes nothing",
          position_key(reread) == position_key(resolved[ep_idx])
          and reread.ep_square == resolved[ep_idx].ep_square)
    check("unchanged transition keeps the side to move",
          apply_transition(resolved[ep_idx], resolved[ep_idx]).turn
          == resolved[ep_idx].turn)


# ---- the analyzer loop -----------------------------------------------------
class FakeCapture:
    """Hands out one frame per poll, then holds the last one."""

    def __init__(self, images):
        self.images = list(images)
        self.i = 0

    def grab(self):
        img = self.images[min(self.i, len(self.images) - 1)]
        self.i = min(self.i + 1, len(self.images) - 1)
        return img


class StubEngine:
    """Deliberately offers moves *other* than the ones played, so the record
    can only be right if it derives the move from the screen, not from us."""

    def __init__(self):
        self.calls = []

    def analyse(self, board):
        self.calls.append(board.fen())
        legal = list(board.legal_moves)
        if not legal:
            return []
        ordered = ([m for m in legal if m.uci() not in PLAYED]
                   + [m for m in legal if m.uci() in PLAYED])
        return [{"move": m, "score_cp": 30 - 10 * i, "depth": 18,
                 "pv": [m], "mate": None} for i, m in enumerate(ordered[:3])]


outdir = tempfile.mkdtemp(prefix="cla-test-")
engine = StubEngine()
logger = GameLogger(path=Path(outdir) / "game.jsonl")
an = Analyzer(FakeCapture(imgs), det, engine, logger)
an.paused = False
an.start()
deadline = time.time() + 20
while an.analysed < len(imgs) and time.time() < deadline:
    time.sleep(0.05)
time.sleep(0.4)
an.stop()
an.join(timeout=3)

check("one analysis per position", an.analysed >= len(imgs),
      f"analysed={an.analysed} of {len(imgs)}")
check("engine saw every position", len(engine.calls) >= len(imgs),
      f"calls={len(engine.calls)}")
check("no worker errors", an.error is None, str(an.error))

# ---- the record ------------------------------------------------------------
entries = []
for p in Path(outdir).glob("*.jsonl"):
    entries += [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()
                if l.strip()]
check("JSONL entries written", len(entries) >= len(imgs), f"entries={len(entries)}")
if entries:
    check("every entry carries a Turkish reason", all(e.get("reason") for e in entries))
    check("every entry lists candidates",
          all(len(e.get("candidates", [])) > 1 for e in entries))
    check("entries name the side to move correctly",
          [e["side_to_move"] for e in entries[:len(frames)]]
          == ["white" if b.turn else "black" for b in frames])

check("tracked game followed the moves that were played",
      position_key(logger._board) == position_key(frames[-1]),
      f"tracked={logger._board.fen()}")
check("move list is the real game, not the engine's suggestions",
      logger._moves == PLAYED, f"moves={logger._moves}")

saved = logger.save()
check("Markdown written", Path(saved).exists(), str(saved))
pgn = Path(saved).with_suffix(".pgn")
pgn_moves = []
if pgn.exists():
    import io as _io
    game = chess.pgn.read_game(_io.StringIO(pgn.read_text(encoding="utf-8")))
    node = game
    while node.variations:
        node = node.variation(0)
        pgn_moves.append(node.move.uci())
check("PGN replays to the exact game that was played", pgn_moves == PLAYED,
      f"pgn={pgn_moves}")

shutil.rmtree(outdir, ignore_errors=True)
print("\n" + ("ALL PASSED" if not fails else f"FAILED: {fails}"))
sys.exit(1 if fails else 0)
