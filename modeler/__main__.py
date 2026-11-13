"""Entry point.

    python -m modeler                 open the GUI
    python -m modeler script.cmd      open the GUI and run a script
    python -m modeler model.m3d       open the GUI with a saved project
    python -m modeler run script.cmd [-D NAME=value ...] [-q]
                                      run a script headless; -D fixes a parameter
                                      (the script's own NAME = ... keeps that value),
                                      -q prints only errors and *MSG output
    python -m modeler check           print versions and test the 3D view setup
    python -m modeler --version       print the version
    python -m modeler tools           the AI assistant's tool definitions, as JSON
    python -m modeler tool [--script file.cmd] NAME ['{"arg": value}']
                                      call one tool headless and print its JSON answer;
                                      NAME - reads "name {json}" lines from stdin, one
                                      answer per line, sharing one sandbox
"""

from __future__ import annotations

import os
import sys


def _run_headless(args: list[str]) -> int:
    from .commands import Processor
    from .lang.expr import Evaluator, ExprError

    path, overrides, quiet = None, {}, False
    it = iter(args)
    for a in it:
        if a == "-D" or a.startswith("-D"):
            spec = a[2:] or next(it, "")
            name, _, value = spec.partition("=")
            if not name or not value:
                print(f"bad -D {spec!r}: use -D NAME=value")
                return 2
            try:
                overrides[name] = Evaluator(lambda k: (_ for _ in ()).throw(KeyError(k))).eval(value)
            except ExprError as exc:
                print(f"bad -D {spec!r}: {exc}")
                return 2
        elif a == "-q":
            quiet = True
        elif path is None:
            path = a
        else:
            print(__doc__)
            return 2
    if path is None:
        print(__doc__)
        return 2
    p = Processor(overrides=overrides)
    with open(path, encoding="utf-8") as f:
        results = p.run_script(f.read())
    for r in results:
        if not quiet or not r.ok:
            print(f"> {r.line}")
        if r.message and (not quiet or not r.ok or r.line.lstrip().upper().startswith("*MSG")):
            if r.ok:
                print(r.message)
            else:  # a block's message is what its lines did, ending with the error: mark that line
                *done, err = r.message.split("\n")
                print("\n".join([*done, "ERROR: " + err]))
    ok = all(r.ok for r in results)
    print(f"{'done' if ok else 'FAILED'}: {len(p.history)} history entries, {len(p.model.bodies)} bodies")
    return 0 if ok else 1


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

    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from . import __version__
    from .crash import CrashGuard
    from .gui.main_window import MainWindow

    QApplication.setOrganizationName("3Dmodeling")
    QApplication.setApplicationName("3Dmodeling")
    QApplication.setApplicationVersion(__version__)
    app = QApplication(sys.argv)
    guard = CrashGuard()
    win = MainWindow(settings=QSettings(), guard=guard)
    app.aboutToQuit.connect(guard.clean_exit)
    win.show()
    if script and script.lower().endswith(".m3d"):  # a project, e.g. opened from the file manager
        path = os.path.abspath(script).replace("\\", "/")
        win.viewport.call_when_ready(lambda: (win.execute(f'OPEN, "{path}"'), win.execute("FIT")))
    elif script:
        with open(script, encoding="utf-8") as f:
            text = f.read()
        # run after the view exists so FIT/VIEW apply
        win.viewport.call_when_ready(lambda: win.processor.run_script(text))
    return app.exec()


def _tool(args: list[str]) -> int:
    import json

    from .ai.tools import Toolbox
    from .commands import Processor

    p = Processor()
    if args[:1] == ["--script"] and len(args) >= 2:
        with open(args[1], encoding="utf-8") as f:
            bad = [r for r in p.run_script(f.read()) if not r.ok]
        if bad:
            print(json.dumps({"error": f"the script failed: {bad[0].line}: {bad[0].message}"}))
            return 1
        args = args[2:]
    if not args:
        print(__doc__)
        return 2
    box = Toolbox(p)
    if args[0] == "-":
        for line in sys.stdin:
            name, _, rest = line.strip().partition(" ")
            if name:
                print(box.call_json(name, rest), flush=True)
        return 0
    out = box.call_json(args[0], args[1] if len(args) > 1 else "")
    print(out)
    return 1 if '"error"' in out[:10] else 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] in (["--version"], ["-V"]):
        from . import __version__

        print(f"3Dmodeling {__version__}")
        return 0
    if args[:1] == ["tools"]:
        import json

        from .ai.tools import Toolbox
        from .commands import Processor

        print(json.dumps(Toolbox(Processor()).definitions(), indent=1))
        return 0
    if args[:1] == ["tool"]:
        return _tool(args[1:])
    if args[:1] == ["run"] and len(args) >= 2:
        return _run_headless(args[1:])
    if args[:1] == ["check"]:
        return _check()
    if len(args) > 1 or (args and args[0].startswith("-")):
        print(__doc__)
        return 2
    return _gui(args[0] if args else None)


if __name__ == "__main__":
    sys.exit(main())
