# -*- coding: utf-8 -*-
"""Package-internal entry point.

``python -m src.main`` and the root ``main.py`` both land here. Imports are
absolute (``src.*``) so this module works whether it is loaded as part of the
``src`` package or imported after a ``sys.path`` bootstrap.
"""
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_here)
if _root not in sys.path:
    sys.path.insert(0, _root)

if hasattr(sys.stdout, "reconfigure"):
    # Windows console defaults to a legacy code page that mangles Turkish.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def smoke_test() -> int:
    """Verify engine + detection + logging without touching the screen."""
    import chess

    from src import config
    from src.board_detect import BoardDetector, validate
    from src.engine import Engine
    from src.logger import GameLogger, explain, move_label

    print(f"Stockfish : {config.get('stockfish_path')}")
    eng = Engine()
    if not eng.available():
        print("FAIL: Stockfish binary not found")
        return 1

    print("Starting engine ...")
    if not eng.start():
        print(f"FAIL: {eng.error}")
        return 1

    board = chess.Board()
    print(f"Position  : {board.fen()}")
    lines = eng.analyse(board, movetime_ms=400, depth=14, multipv=3)
    eng.stop()

    if not lines:
        print("FAIL: no lines returned")
        return 1
    for i, l in enumerate(lines, 1):
        print(f"  {i}. {move_label(board, l['move']):<18} "
              f"{l['score_cp'] / 100:+.2f}  depth {l['depth']}")

    text = explain(board, lines, "white")
    print(f"\nTurkish explanation:\n{text}")

    det = BoardDetector()
    assert not validate(None)
    assert validate(chess.Board())
    det.set_grid(0, 0, 320)
    assert det.calibrated is False
    print("\nDetector geometry OK (grid 320px, 40px cells).")

    log = GameLogger()
    log.new_game()
    log.record(board, lines, "white")
    path = log.save()
    print(f"Log written: {path}")
    if not path.exists() or path.stat().st_size < 50:
        print("FAIL: log file empty")
        return 1

    print("\nALL CHECKS PASSED")
    return 0


def main() -> int:
    if "--test" in sys.argv:
        return smoke_test()
    from src.ui import run
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
