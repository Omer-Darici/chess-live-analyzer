# -*- coding: utf-8 -*-
"""Entry point for both source runs and the PyInstaller build.

PyInstaller executes the entry script as a *top-level* module, so relative
imports (``from .ui import run``) raise "attempted relative import with no
known parent package" and the windowed exe dies silently. Keeping the entry
at the project root with absolute ``src.*`` imports works in every context.

An excepthook writes ``logs/crash.log`` next to the executable so a windowed
build never fails invisibly.
"""
import os
import sys
import traceback

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

if hasattr(sys.stdout, "reconfigure"):
    # Windows console defaults to a legacy code page that mangles Turkish.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _install_crash_log():
    """Route uncaught exceptions to a file (a windowed exe has no stderr)."""
    if getattr(sys, "frozen", False):
        root = os.path.dirname(os.path.abspath(sys.executable))
    else:
        root = BASE
    logdir = os.path.join(root, "logs")
    target = os.path.join(logdir, "crash.log")

    def hook(exc_type, exc, tb):
        try:
            os.makedirs(logdir, exist_ok=True)
            with open(target, "a", encoding="utf-8") as f:
                f.write("=" * 70 + "\n")
                f.write(f"{__import__('datetime').datetime.now():%Y-%m-%d %H:%M:%S}\n")
                traceback.print_exception(exc_type, exc, tb, file=f)
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = hook


_install_crash_log()

from src.main import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
