"""A check of the app on a real desktop (PLAN item 64).

    python -m modeler desktop-check [--out FOLDER] [--keep-open]

Opens the real window and goes through what most often goes wrong on a new computer,
by itself, in about half a minute: the 3D view draws (not a black or empty square),
a click with the mouse picks the face under it at this screen's scaling, dragging
turns the view and the wheel zooms, a project saves and opens again in a folder with
spaces and non-English letters, a drawing and a STEP file are written there, text
uses a font, the themes switch, the assistant panel opens and the window closes
cleanly. Each step says ok or what failed.

It writes FOLDER/report.md (and report.json, and a picture of the window) to attach to
a problem report; the checks a person has to do by hand are in docs/site/desktop-check.md (the website's
Desktop check page).
"""

from __future__ import annotations

import json
import os
import platform
import sys
import tempfile
import time
import traceback
from dataclasses import asdict, dataclass

# a folder name that trips up code that is not careful with paths
AWKWARD = "Prüfung ü 文件 test"


@dataclass
class Step:
    name: str
    ok: bool
    detail: str = ""
    seconds: float = 0.0


def _facts() -> dict:
    import OCP
    import PySide6
    from PySide6.QtGui import QGuiApplication

    from . import __version__

    out = {
        "app": __version__,
        "python": platform.python_version(),
        "system": f"{platform.system()} {platform.release()} ({platform.version()})",
        "machine": platform.machine(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "PySide6": PySide6.__version__,
        "OCP": getattr(OCP, "__version__", "unknown"),
        "qt_platform": QGuiApplication.platformName(),
        "screens": [],
    }
    for s in QGuiApplication.screens():
        g = s.geometry()
        out["screens"].append(f"{s.name()}: {g.width()}x{g.height()} at scale {s.devicePixelRatio():g}, "
                              f"{s.logicalDotsPerInch():.0f} dpi")
    return out


def _opengl(view) -> str:
    """What OCCT says about the graphics card and driver."""
    try:
        from OCP.Graphic3d import Graphic3d_DiagnosticInfo
        from OCP.OCP.collections import IndexedDataMap_TCollection_AsciiString_TCollection_AsciiString as Map

        info = Map()
        view.DiagnosticInformation(info, Graphic3d_DiagnosticInfo.Graphic3d_DiagnosticInfo_Basic)
        rows = {}
        for i in range(1, info.Extent() + 1):
            rows[info.FindKey(i).ToCString()] = info.FindFromIndex(i).ToCString()
        keep = ("GLvendor", "GLdevice", "GLversion", "GLSLversion")
        return "; ".join(f"{k} {rows[k]}" for k in keep if k in rows) or "no details"
    except Exception as exc:  # noqa: BLE001
        return f"unknown ({type(exc).__name__})"


def _picture_has_content(png: bytes) -> tuple[bool, str]:
    """Not one flat colour: the model is drawn over the background."""
    from PySide6.QtGui import QImage

    img = QImage.fromData(png)
    if img.isNull():
        return False, "the picture could not be read"
    colours = set()
    for y in range(0, img.height(), max(1, img.height() // 40)):
        for x in range(0, img.width(), max(1, img.width() // 40)):
            colours.add(img.pixel(x, y))
    dark = sum(1 for c in colours if (c & 0xFFFFFF) == 0)
    if len(colours) < 4:
        return False, f"only {len(colours)} colours: the view looks empty" + (" (black)" if dark else "")
    return True, f"{len(colours)} colours in a {img.width()}x{img.height()} picture"


def run(out_dir: str, keep_open: bool = False, log=print) -> list[Step]:
    if sys.platform.startswith("linux") and os.environ.get("WAYLAND_DISPLAY"):
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    from PySide6.QtCore import QPoint, QSettings, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from .gui.main_window import MainWindow

    os.makedirs(out_dir, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    steps: list[Step] = []
    facts = _facts()
    state: dict = {}

    def step(name):
        def wrap(fn):
            t0 = time.perf_counter()
            try:
                ok, detail = fn()
            except Exception as exc:  # noqa: BLE001
                ok, detail = False, f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=4)}"
            s = Step(name, bool(ok), str(detail), round(time.perf_counter() - t0, 3))
            steps.append(s)
            log(f"  {'ok  ' if s.ok else 'FAIL'} {name}: {s.detail.splitlines()[0] if s.detail else ''}")
            return fn
        return wrap

    def pump(n=5):
        for _ in range(n):
            app.processEvents()

    log("3Dmodeling desktop check")
    settings = QSettings(os.path.join(out_dir, "settings.ini"), QSettings.IniFormat)
    w = MainWindow(settings=settings, autosave=os.path.join(out_dir, "autosave.m3d"))
    w.resize(1280, 820)

    @step("the window opens and the 3D view starts")
    def _():
        t0 = time.perf_counter()
        w.show()
        while not w.viewport._initialized and time.perf_counter() - t0 < 20:
            pump(1)
            time.sleep(0.02)
        if not w.viewport._initialized:
            return False, "the 3D view did not start within 20 s"
        state["gl"] = _opengl(w.viewport.view)
        return True, f"in {time.perf_counter() - t0:.2f} s; {state['gl']}"

    ready = steps[-1].ok
    if ready:
        @step("a model is built and drawn")
        def _():
            for line in ("BLOCK, 0,0,0, 40, 30, 10", "CYL, 20, 15, 10, 6, 10", "UNION, 1, 2",
                         "SEL, S, EDGE, LOC, Z, 0", "FILLET, 1", "VIEW, ISO", "FIT"):
                r = w.execute(line)
                if not r.ok:
                    return False, f"{line}: {r.message}"
            pump()
            png = w.viewport.snapshot(800, 500)
            if not png:
                return False, "no picture of the view could be taken"
            with open(os.path.join(out_dir, "view.png"), "wb") as f:
                f.write(png)
            return _picture_has_content(png)

        @step("a mouse click picks the face under it (screen scaling)")
        def _():
            from OCP.BRepGProp import BRepGProp
            from OCP.GProp import GProp_GProps

            vp, m = w.viewport, w.processor.model
            w.execute("SEL, S, FACE, NORMAL, 0,0,1")
            top = [g for g in m.selection if m.entity_shape("FACE", g) is not None]
            w.execute("SEL, NONE")
            g = GProp_GProps()
            BRepGProp.SurfaceProperties_s(m.entity_shape("FACE", top[-1]), g)
            c = g.CentreOfMass()
            px, py = vp.view.Convert(c.X(), c.Y(), c.Z())  # device pixels
            r = vp.devicePixelRatioF()
            pos = QPoint(int(px / r), int(py / r))  # where the mouse goes, in Qt's units
            vp.set_pick_mode("FACE")
            QTest.mouseMove(vp, pos)
            pump()
            QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, pos)
            pump()
            got = list(m.selection)
            ok = got == [top[-1]]
            return ok, (f"picked face {got} at ({pos.x()}, {pos.y()}) with scale {r:g}" if ok else
                        f"wanted face {top[-1]}, got {got or 'nothing'} at ({pos.x()}, {pos.y()}), scale {r:g}")

        @step("dragging turns the view, the wheel zooms")
        def _():
            vp = w.viewport
            before = vp.view.Camera().Direction()
            a = QPoint(vp.width() // 2, vp.height() // 2)
            QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, a)
            for i in range(1, 11):
                QTest.mouseMove(vp, a + QPoint(12 * i, 4 * i))
                pump(1)
            QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, a + QPoint(120, 40))
            after = vp.view.Camera().Direction()
            turned = before.Angle(after) > 0.05
            scale = vp.view.Scale()
            from PySide6.QtCore import QPointF
            from PySide6.QtGui import QWheelEvent

            ev = QWheelEvent(QPointF(a), QPointF(vp.mapToGlobal(a)), QPoint(0, 0), QPoint(0, 240),
                             Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
            QApplication.sendEvent(vp, ev)
            pump()
            zoomed = abs(vp.view.Scale() - scale) > 1e-9
            t0 = time.perf_counter()
            for _ in range(30):
                vp.view.Redraw()
            fps = 30 / max(time.perf_counter() - t0, 1e-6)
            return turned and zoomed, (f"turned {before.Angle(after) * 57.3:.0f} degrees, zoom "
                                       f"{'changed' if zoomed else 'did NOT change'}, {fps:.0f} redraws a second")

        @step("save and open in a folder with spaces and non-English letters")
        def _():
            folder = os.path.join(out_dir, AWKWARD)
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, "model ü.m3d").replace("\\", "/")
            vol = w.processor.evaluate("VOL(LAST)")
            for line in (f'SAVE, "{path}"', "NEW", f'OPEN, "{path}"'):
                r = w.execute(line)
                if not r.ok:
                    return False, f"{line}: {r.message}"
            again = w.processor.evaluate("VOL(LAST)")
            return abs(again - vol) < 1e-6 * vol, f"saved and opened {os.path.getsize(path)} bytes; volume {again:.2f}"

        @step("a drawing (PDF) and a STEP file are written there")
        def _():
            folder = os.path.join(out_dir, AWKWARD).replace("\\", "/")
            for line in (f'DRAWING, "{folder}/drawing ü.pdf", STANDARD, , ALL', f'EXPORT, STEP, "{folder}/part ü.step"'):
                r = w.execute(line)
                if not r.ok:
                    return False, f"{line}: {r.message}"
            sizes = [os.path.getsize(os.path.join(folder, n)) for n in ("drawing ü.pdf", "part ü.step")]
            return all(sizes), f"{sizes[0]} and {sizes[1]} bytes"

        @step("text is made with a font")
        def _():
            r = w.execute('TEXT, "Ab1", 0, 0, 30, 8, 2')
            return r.ok, r.message

    @step("the themes switch")
    def _():
        from .gui import prefs

        for name in ("dark", "light", "system"):
            prefs.apply_theme(w, name, remember=False)
            pump()
        return True, "dark, light and the system's"

    @step("the assistant panel opens")
    def _():
        dock = getattr(w, "assistant_dock", None)
        if dock is None:
            return False, "there is no assistant panel"
        dock.show()
        pump()
        return dock.isVisible(), "shown (signing in is checked by hand)"

    @step("a picture of the whole window")
    def _():
        pump()
        path = os.path.join(out_dir, "window.png")
        return save_window_picture(w, path), path

    if not keep_open:
        @step("the window closes")
        def _():
            w.shell.ask_unsaved = lambda *_: "discard"
            ok = w.close()
            pump()
            return ok, "closed"
    write_report(out_dir, facts, state, steps)
    return steps


def save_window_picture(w, path: str) -> bool:
    """The whole window, with the 3D view painted in (a window grab leaves OpenGL black)."""
    from PySide6.QtCore import QPoint, QRect
    from PySide6.QtGui import QImage, QPainter

    pix = w.grab()
    vp = w.viewport
    if vp._initialized:
        r = pix.devicePixelRatio()
        png = vp.snapshot(int(vp.width() * r), int(vp.height() * r))
        if png:
            img = QImage.fromData(png)
            top_left = vp.mapTo(w, QPoint(0, 0))
            painter = QPainter(pix)
            painter.drawImage(QRect(top_left, vp.size()), img)
            painter.end()
    return pix.save(path)


def write_report(out_dir: str, facts: dict, state: dict, steps: list[Step]) -> None:
    facts = dict(facts, opengl=state.get("gl", "unknown"))
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump({"facts": facts, "steps": [asdict(s) for s in steps]}, f, indent=1, ensure_ascii=False)
    failed = [s for s in steps if not s.ok]
    lines = ["# 3Dmodeling desktop check", "",
             f"**{len(steps) - len(failed)} of {len(steps)} steps ok**" + (
                 f", {len(failed)} failed: " + ", ".join(s.name for s in failed) if failed else ""), "",
             "| | Step | Result | Seconds |", "|-|------|--------|---------|"]
    for s in steps:
        first = s.detail.splitlines()[0] if s.detail else ""
        lines.append(f"| {'ok' if s.ok else '**FAIL**'} | {s.name} | {first.replace('|', '/')} | {s.seconds:.2f} |")
    lines += ["", "## This computer", ""] + [f"- {k}: {v}" for k, v in facts.items() if k != "screens"]
    lines += [f"- screen {s}" for s in facts["screens"]]
    for s in failed:
        if "\n" in s.detail:
            lines += ["", f"## {s.name}", "", "```", s.detail, "```"]
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _say(text: str) -> None:
    """print, but a console that cannot show some letters (Windows' cp1252) gets '?' instead of a crash."""
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(text.encode(enc, errors="replace").decode(enc, errors="replace"))


def main(args: list[str]) -> int:
    out = args[args.index("--out") + 1] if "--out" in args else os.path.join(
        tempfile.gettempdir(), f"3dmodeling-desktop-check-{time.strftime('%Y%m%d-%H%M%S')}")
    steps = run(out, keep_open="--keep-open" in args, log=_say)
    bad = sum(not s.ok for s in steps)
    _say(f"{len(steps) - bad} of {len(steps)} steps ok. The report is in {os.path.join(out, 'report.md')}")
    _say("Next: the checks by hand, on the user guide website's Desktop check page "
          "(https://shashanksingh097.github.io/3Dmodeling/desktop-check/).")
    if "--keep-open" in args:
        from PySide6.QtWidgets import QApplication

        return QApplication.instance().exec()
    return 1 if bad else 0
