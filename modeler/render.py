"""Pictures of a model made by a script, the way the app draws it.

    python -m modeler render part.cmd part.png [--view ISO] [--size 1600x1000] [-D NAME=value ...]
    python -m modeler render part.cmd --shots shots.txt OUTDIR [--size 1600x1000]
    python -m modeler render part.cmd --motion A 0 90 18 OUTDIR [--view ISO]

``--motion`` saves one picture per position of a moving assembly (DRIVE, A, value for A = 0, 5
... 90) as OUTDIR/a_000.png, a_001.png ...: a picture sequence to make a film or GIF from. The
camera is fitted once, wide enough for the position that needs the most room, so the parts
move and the view stands still.

The script runs in the real window (so colours, layers, see-through
materials and hidden bodies look as they do in the app), every body is
meshed again finely, and the 3D view is saved as a PNG at the given size.

A shots file takes several pictures of one model. Each line is

    file.png | command; command; ... | view

The commands run first (ISOLATE a part, MOVE parts apart, LAYER ... OFF),
then the view is set and the picture saved. ``view`` is a named view (ISO,
TOP, FRONT, RIGHT, ...) or a direction ``dx,dy,dz`` from the model towards
the eye, with z kept up. Lines starting with # are skipped; ``file.png``
may contain a folder.

Picks and selections are cleared before the pictures so nothing is drawn
highlighted. On Linux without a screen, run under Xvfb:
``xvfb-run -a -s "-screen 0 1920x1200x24" python -m modeler render ...``.
"""

from __future__ import annotations

import math
import os
import sys
import time
from dataclasses import dataclass


@dataclass
class Shot:
    file: str
    commands: list[str]
    view: str = "ISO"
    fit: bool = True  # False: keep the camera of the shot before (frames of a motion)
    # set: try each command list, fit the camera, and keep the widest fit (a motion's whole range)
    prefit: list | None = None


def parse_shots(text: str) -> list[Shot]:
    shots = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [s.strip() for s in line.split("|")]
        parts += [""] * (3 - len(parts))
        cmds = [c.strip() for c in parts[1].split(";") if c.strip()]
        shots.append(Shot(parts[0], cmds, parts[2] or "ISO"))
    return shots


def _set_view(win, vp, view: str) -> None:
    if "," in view:
        dx, dy, dz = (float(v) for v in view.split(","))
        vp.view.SetProj(dx, dy, dz)
        vp.view.SetUp(0, 0, 1)
    else:
        win.execute("VIEW, " + view.upper())


def motion_shots(name: str, start: float, end: float, steps: int, view: str = "ISO") -> list[Shot]:
    """Shots for a picture sequence: one frame per position, the camera fitted once (the widest
    fit over the positions) and kept; a last shot (not saved) lets the parameter go."""
    vals = [start + (end - start) * i / steps for i in range(steps + 1)]
    key = name.lower()
    shots = []
    for i, v in enumerate(vals):
        shots.append(Shot(f"{key}_{i:03d}.png", [f"DRIVE, {name}, {v:.10g}"], view, fit=False))
    shots[0].prefit = [[f"DRIVE, {name}, {v:.10g}"] for v in vals]
    shots.append(Shot("", [f"DRIVE, {name}"], view, fit=False))  # let go at the end (not saved)
    return shots


def render(script_text: str, shots: list[Shot], outdir: str = ".", size: tuple[int, int] = (1600, 1000),
           overrides: dict | None = None, log=print) -> list[str]:
    """Run the script in a window and save each shot. Returns the saved paths;
    raises RuntimeError if the script or a shot command fails."""
    from OCP.Aspect import Aspect_TOD_RELATIVE
    from OCP.Image import Image_AlienPixMap
    from OCP.TCollection import TCollection_AsciiString
    from PySide6.QtWidgets import QApplication

    from .commands import Processor
    from .gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    win = MainWindow(Processor(overrides=overrides or {}), autosave="off")
    win.resize(1200, 800)
    win.show()

    def pump(n: int = 5) -> None:
        for _ in range(n):
            app.processEvents()

    for _ in range(100):
        pump(1)
        if win.viewport._initialized:
            break
    vp = win.viewport
    try:
        drawer = vp.context.DefaultDrawer()
        drawer.SetTypeOfDeflection(Aspect_TOD_RELATIVE)
        drawer.SetDeviationCoefficient(0.002)  # coarse (fast) while the script runs
        drawer.SetDeviationAngle(math.radians(12))
        t = time.time()
        results = win.processor.run_script(script_text)
        bad = [r for r in results if not r.ok]
        if bad:
            raise RuntimeError(f"the script failed at {bad[0].line.splitlines()[0]!r}: {bad[0].message}")
        log(f"script ran in {time.time() - t:.1f} s: {len(win.processor.model.bodies)} bodies")

        drawer.SetDeviationCoefficient(0.0003)  # fine, for smooth curved faces
        drawer.SetDeviationAngle(math.radians(4))
        for ais in list(vp._ais.values()):
            vp.context.Redisplay(ais, False, True)
        win.execute("SEL, NONE")

        saved = []
        for shot in shots:
            for c in shot.commands:
                r = win.execute(c)
                if not r.ok:
                    raise RuntimeError(f"{shot.file}: {c}: {r.message}")
            vp.context.ClearSelected(False)
            pump()
            if shot.prefit:
                widest = None
                for cmds in shot.prefit:
                    for c in cmds:
                        win.execute(c)
                    pump()
                    _set_view(win, vp, shot.view)
                    vp.view.FitAll(0.06, False)
                    if widest is None or vp.view.Scale() < widest[0]:
                        widest = (vp.view.Scale(), cmds)
                for c in widest[1]:
                    win.execute(c)
                pump()
                _set_view(win, vp, shot.view)
                vp.view.FitAll(0.06, False)
                for c in shot.commands:
                    win.execute(c)
                pump()
            elif shot.fit:
                if "," in shot.view:
                    dx, dy, dz = (float(v) for v in shot.view.split(","))
                    vp.view.SetProj(dx, dy, dz)
                    vp.view.SetUp(0, 0, 1)
                else:
                    win.execute("VIEW, " + shot.view.upper())
                vp.view.FitAll(0.06, False)
            vp.view.Redraw()
            pump()
            if not shot.file:
                continue
            path = os.path.join(outdir, shot.file)
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            pix = Image_AlienPixMap()
            if not (vp.view.ToPixMap(pix, size[0], size[1]) and pix.Save(TCollection_AsciiString(path))):
                raise RuntimeError(f"could not save {path}")
            log(f"saved {path}")
            saved.append(path)
        return saved
    finally:
        win.close()
        pump()


def main(args: list[str]) -> int:
    from .lang.expr import Evaluator, ExprError

    size, view, shots_file, overrides, pos, motion = (1600, 1000), "ISO", None, {}, [], None
    it = iter(args)
    try:
        for a in it:
            if a == "--size":
                w, _, h = next(it).lower().partition("x")
                size = (int(w), int(h))
            elif a == "--view":
                view = next(it)
            elif a == "--shots":
                shots_file = next(it)
            elif a == "--motion":
                motion = (next(it), float(next(it)), float(next(it)), int(next(it)))
            elif a.startswith("-D"):
                spec = a[2:] or next(it)
                name, _, value = spec.partition("=")
                overrides[name] = Evaluator(lambda k: (_ for _ in ()).throw(KeyError(k))).eval(value)
            else:
                pos.append(a)
    except (StopIteration, ValueError, ExprError) as exc:
        print(f"bad arguments: {exc}\n{__doc__}")
        return 2
    if len(pos) != 2:
        print(__doc__)
        return 2
    script, out = pos
    with open(script, encoding="utf-8") as f:
        text = f.read()
    if motion:
        shots, outdir = motion_shots(*motion, view), out
    elif shots_file:
        with open(shots_file, encoding="utf-8") as f:
            shots, outdir = parse_shots(f.read()), out
    else:
        shots, outdir = [Shot(os.path.basename(out), [], view)], os.path.dirname(out) or "."
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        print("no screen: run under Xvfb, e.g. xvfb-run -a python -m modeler render ...")
        return 2
    try:
        render(text, shots, outdir, size, overrides)
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1
    return 0
