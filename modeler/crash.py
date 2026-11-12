"""Crash handling for the desktop app.

Three things, so that a problem never just makes the window vanish:

* Python errors that reach the event loop (a bug in a button or a panel) are
  written to ``errors.log`` with the full traceback, and the window shows a
  message instead of failing silently. The app keeps running.
* Hard crashes inside the geometry kernel (a segmentation fault) cannot be
  caught, but ``faulthandler`` writes the Python stack to ``crash.log`` first.
* A ``running.lock`` file exists while the app is open. If it is still there
  at the next start, the last session ended without closing, so the window
  offers the autosave (``OPEN, AUTOSAVE``) and points at the logs.

The log folder is ``MODELER_LOG_DIR`` when set, otherwise ``logs`` in the
app's data folder (next to the autosave).
"""

from __future__ import annotations

import datetime as _dt
import faulthandler
import os
import sys
import traceback
from typing import Callable

from . import __version__


def default_log_dir() -> str:
    env = os.environ.get("MODELER_LOG_DIR")
    if env:
        return env
    try:
        from PySide6.QtCore import QStandardPaths

        base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    except Exception:  # pragma: no cover - Qt missing
        base = ""
    return os.path.join(base or os.path.expanduser("~/.modeler3d"), "logs")


class CrashGuard:
    """Install with ``CrashGuard(log_dir)``; call :meth:`clean_exit` when the
    app closes normally."""

    def __init__(self, log_dir: str | None = None, install: bool = True) -> None:
        self.log_dir = log_dir or default_log_dir()
        os.makedirs(self.log_dir, exist_ok=True)
        self.errors_path = os.path.join(self.log_dir, "errors.log")
        self.crash_path = os.path.join(self.log_dir, "crash.log")
        self.lock_path = os.path.join(self.log_dir, "running.lock")
        self.last_session_crashed = os.path.exists(self.lock_path)
        # called with (summary, details) for each error; the window sets it
        self.on_error: Callable[[str, str], None] | None = None
        self._reporting = False
        self._fault_file = None
        with open(self.lock_path, "w", encoding="utf-8") as f:
            f.write(f"pid {os.getpid()} started {_now()} version {__version__}\n")
        if install:
            self._fault_file = open(self.crash_path, "a", encoding="utf-8")  # noqa: SIM115 - kept open for faulthandler
            faulthandler.enable(self._fault_file)
            self._old_hook = sys.excepthook
            sys.excepthook = self.excepthook

    # ---- errors -------------------------------------------------------------
    def excepthook(self, exc_type, exc, tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        details = "".join(traceback.format_exception(exc_type, exc, tb))
        self.record(details)
        if sys.stderr is not None:  # None in a windowed build on Windows
            sys.stderr.write(details)
        summary = f"{exc_type.__name__}: {exc}"
        if self.on_error and not self._reporting:
            self._reporting = True
            try:
                self.on_error(summary, details)
            except Exception:  # never let the reporter itself loop
                pass
            finally:
                self._reporting = False

    def record(self, details: str) -> None:
        try:
            with open(self.errors_path, "a", encoding="utf-8") as f:
                f.write(f"--- {_now()} version {__version__}\n{details}\n")
        except OSError:
            pass

    # ---- shutdown -----------------------------------------------------------
    def clean_exit(self) -> None:
        try:
            os.remove(self.lock_path)
        except OSError:
            pass
        if self._fault_file is not None:
            faulthandler.disable()
            self._fault_file.close()
            self._fault_file = None
            sys.excepthook = self._old_hook


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")
