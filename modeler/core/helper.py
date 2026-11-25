"""The rebuild helper: a second process that re-runs the history, so the window
never freezes while it does.

Why a process and not a thread: the OCCT bindings keep Python's interpreter
lock for the whole of every kernel call (a 2 s mesh call blocks every other
Python thread for 2 s), so a worker thread would freeze the window just the
same. A process has its own lock.

How: the window sends the processor's whole state (``transfer.processor_state``,
shapes kept shared) and the command; the helper runs it on its own processor,
reports each step it re-runs, and sends the new state back, which the window
takes over. Cancel just stops the helper: the window's state was never
touched. The helper stays running between rebuilds, so only the first one
pays for starting it.

Messages on the pipes: 8 bytes of length, then ``transfer.dumps`` of a tuple
whose first item says what it is:

    window -> helper   ("run", state, text)  ·  ("quit",)
    helper -> window   ("ready",)  ·  ("progress", done, total, label)
                       ·  ("done", ok, line, message, warning, state)  ·  ("error", text)
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from typing import Any, BinaryIO

from . import transfer


def _send(out: BinaryIO, msg: tuple) -> None:
    data = transfer.dumps(msg)
    out.write(len(data).to_bytes(8, "little"))
    out.write(data)
    out.flush()


def _recv(inp: BinaryIO) -> tuple | None:
    head = inp.read(8)
    if len(head) < 8:
        return None
    n = int.from_bytes(head, "little")
    data = inp.read(n)
    if len(data) < n:
        return None
    return transfer.loads(data)


# ---- the helper's side --------------------------------------------------------------
def serve(inp: BinaryIO, out: BinaryIO) -> int:
    """The helper's loop: run what the window sends until it says quit."""
    from ..commands import Processor

    _send(out, ("ready",))
    while True:
        msg = _recv(inp)
        if msg is None or msg[0] == "quit":
            return 0
        if msg[0] != "run":
            continue
        _, state, text = msg[:3]
        try:
            if len(msg) > 3 and msg[3] is not None:
                # the window's plug-ins (modeler/plugins.py): the steps may use their commands
                from .. import plugins

                where, off = msg[3]
                plugins.configure(off)
                plugins.load_all(where)
            p = Processor()
            transfer.set_processor_state(p, state)

            def progress(done: int, total: int, label: str) -> bool:
                _send(out, ("progress", done, total, label))
                return True

            p.progress = progress
            res = p.run(text)
            _send(out, ("done", res.ok, res.line, res.message, res.warning, transfer.processor_state(p)))
        except Exception as exc:  # noqa: BLE001 - reported to the window, which runs it itself instead
            import traceback

            _send(out, ("error", "".join(traceback.format_exception(exc))))


def main() -> int:
    """``python -m modeler.core.helper`` or ``3Dmodeling-cli rebuild-helper``: serve on
    stdin/stdout (binary)."""
    # a windowed build has no sys.stdin/stdout objects, but the pipes are there
    inp = sys.stdin.buffer if sys.stdin is not None else os.fdopen(0, "rb")
    out = sys.stdout.buffer if sys.stdout is not None else os.fdopen(1, "wb")
    sys.stdout = sys.stderr  # anything printed goes to the log, not into the messages
    return serve(inp, out)


# ---- the window's side --------------------------------------------------------------
def command() -> list[str]:
    """How to start the helper: this Python with ``-m``, or the packaged app's console
    program (3Dmodeling-cli, next to the window program) with ``rebuild-helper``."""
    if getattr(sys, "frozen", False):
        here = os.path.dirname(sys.executable)
        cli = os.path.join(here, "3Dmodeling-cli" + (".exe" if os.name == "nt" else ""))
        return [cli if os.path.exists(cli) else sys.executable, "rebuild-helper"]
    return [sys.executable, "-m", "modeler.core.helper"]


class Helper:
    """The window's handle on the helper process. ``start()`` early so it is warm;
    ``submit(state, text)`` sends a job, whose messages then arrive on ``messages``
    (read by a thread, so nothing here blocks); ``cancel()`` stops it."""

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.messages: queue.Queue = queue.Queue()
        self.ready = threading.Event()
        self._reader: threading.Thread | None = None

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> None:
        if self.alive():
            return
        self.ready.clear()
        self.messages = queue.Queue()
        env = dict(os.environ)
        env.setdefault("QT_QPA_PLATFORM", "offscreen")  # it never shows anything
        self.proc = subprocess.Popen(command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, env=env,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self._reader = threading.Thread(target=self._read, args=(self.proc, self.messages), daemon=True,
                                        name="rebuild-helper")
        self._reader.start()

    def _read(self, proc: subprocess.Popen, box: queue.Queue) -> None:
        while True:
            try:
                msg = _recv(proc.stdout)
            except Exception as exc:  # noqa: BLE001 - a broken message ends this helper
                box.put(("error", f"could not read the helper's answer: {exc}"))
                return
            if msg is None:
                box.put(("gone",))
                return
            if msg[0] == "ready":
                self.ready.set()
                continue
            box.put(msg)

    def submit(self, state: dict, text: str) -> None:
        from .. import plugins

        self.start()
        # the plug-ins the window has loaded, so their commands run in the helper too
        info = (plugins.folder(), sorted(plugins._disabled)) if plugins.plugins() else None
        _send(self.proc.stdin, ("run", state, text, info))

    def cancel(self) -> None:
        """Stop the helper now (the next submit starts a fresh one)."""
        if self.proc is not None:
            try:
                self.proc.kill()
                self.proc.wait(5)
            except Exception:  # noqa: BLE001 - it is gone either way
                pass
            self.proc = None

    def close(self) -> None:
        if self.alive():
            try:
                _send(self.proc.stdin, ("quit",))
                self.proc.wait(2)
            except Exception:  # noqa: BLE001
                self.cancel()
        self.proc = None

    def wait(self, timeout: float | None = None) -> Any:
        """The next message (blocking): for scripts and tests without an event loop."""
        return self.messages.get(timeout=timeout)


if __name__ == "__main__":
    sys.exit(main())
