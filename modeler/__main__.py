"""Entry point.

    python -m modeler                 open the GUI
    python -m modeler script.cmd      open the GUI and run a script
    python -m modeler run script.cmd  run a script headless and print the log
    python -m modeler check           print versions and test the 3D view setup
"""

from __future__ import annotations

import os
import sys


def _run_headless(path: str) -> int:
    from .commands import Processor

    p = Processor()
    with open(path, encoding="utf-8") as f:
        results = p.run_script(f.read())
    for r in results:
        print(f"> {r.line}")
        if r.message:
            print(("" if r.ok else "ERROR: ") + r.message)
    return 0 if all(r.ok for r in results) else 1


def _check() -> int:
    import platform

    import OCP
    import PySide6

    print(f"python   {platform.python_version()} on {platform.system()} {platform.machine()}")
    print(f"PySide6  {PySide6.__version__}")
    print(f"OCP      {getattr(OCP, '__version__', 'unknown')}")
    from .commands import Processor

    r = Processor().run("BLOCK, 0,0,0, 1,1,1")
    print(f"kernel   {'ok' if r.ok else 'FAILED'}: {r.message}")
    return 0 if r.ok else 1


def _gui(script: str | None) -> int:
    # The OCCT view needs a native X11 window on Linux; Wayland sessions run
    # it through XWayland.
    if sys.platform.startswith("linux") and os.environ.get("WAYLAND_DISPLAY"):
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

    from PySide6.QtWidgets import QApplication

    from .gui.main_window import MainWindow

    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    if script:
        with open(script, encoding="utf-8") as f:
            text = f.read()
        # run after the view exists so FIT/VIEW apply
        win.viewport.call_when_ready(lambda: win.processor.run_script(text))
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["run"] and len(args) == 2:
        return _run_headless(args[1])
    if args[:1] == ["check"]:
        return _check()
    if len(args) > 1 or (args and args[0].startswith("-")):
        print(__doc__)
        return 2
    return _gui(args[0] if args else None)


if __name__ == "__main__":
    sys.exit(main())
