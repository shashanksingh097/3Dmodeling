"""Sculpting with the mouse (M7): the Sculpt tab and strokes in the 3D view.

With **Sculpt** on, a left drag over a mesh body records where the mouse
ray hits the surface. On release the points are stored as a stroke (S1,
S2 ...) and one command runs, so every stroke is a history step that Undo
takes back and a project replays:

    SCULPT, body, brush, radius, strength, S7 [, sym]

Ctrl while dragging works the other way (DRAW digs, MASK erases), Shift
smooths. The Mask brush paints frozen regions: MASK, body, PAINT, 0,0,0,
radius, 1, S8.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDoubleSpinBox, QLabel

from ..geometry import meshbody as mb
from ..geometry import sculpt as sc
from ..lang.expr import fmt_num

BRUSH_BUTTONS = [
    ("DRAW", "Draw", "sc_draw", "Raise the surface along the stroke (Ctrl: dig in)"),
    ("CLAY", "Clay", "sc_clay", "Build up flat layers, like adding clay (Ctrl: scrape away)"),
    ("INFLATE", "Inflate", "sc_inflate", "Puff the surface out along its own normals (Ctrl: deflate)"),
    ("SMOOTH", "Smooth", "sc_smooth", "Even out bumps (Shift with any brush smooths too)"),
    ("FLATTEN", "Flatten", "sc_flatten", "Press the surface towards a flat plane"),
    ("PINCH", "Pinch", "sc_pinch", "Pull the surface in towards the stroke: sharpens ridges"),
    ("CREASE", "Crease", "sc_crease", "Cut a sharp groove along the stroke"),
    ("GRAB", "Grab", "sc_grab", "Drag what is under the press point to where you let go"),
    ("MASK", "Mask", "sc_mask", "Paint a frozen region that the other brushes leave alone (Ctrl: unfreeze)"),
]


@dataclass
class Settings:
    brush: str = "DRAW"
    radius: float = 3.0
    strength: float = 0.5
    sym: set = field(default_factory=set)


# ---- where the mouse ray meets a mesh ----------------------------------------------------------
def ray_hit(pts: np.ndarray, tris: np.ndarray, origin, direction) -> np.ndarray | None:
    """The nearest point where the ray meets the triangles (Moller-Trumbore, all at once), or None."""
    o = np.asarray(origin, dtype=float)
    d = np.asarray(direction, dtype=float)
    d = d / (np.linalg.norm(d) or 1.0)
    v0 = pts[tris[:, 0]]
    e1 = pts[tris[:, 1]] - v0
    e2 = pts[tris[:, 2]] - v0
    pv = np.cross(d, e2)
    det = np.einsum("ij,ij->i", e1, pv)
    ok = np.abs(det) > 1e-14
    inv = np.zeros_like(det)
    inv[ok] = 1.0 / det[ok]
    tv = o - v0
    u = np.einsum("ij,ij->i", tv, pv) * inv
    qv = np.cross(tv, e1)
    v = (qv @ d) * inv
    t = np.einsum("ij,ij->i", e2, qv) * inv
    hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 0)
    if not hit.any():
        return None
    i = np.flatnonzero(hit)[np.argmin(t[hit])]
    return o + d * t[i]


def thin(points: list, spacing: float, limit: int = 400) -> np.ndarray:
    """Points at least ``spacing`` apart (the last one kept), at most ``limit`` of them."""
    if not points:
        return np.zeros((0, 3))
    out = [np.asarray(points[0], dtype=float)]
    for q in points[1:]:
        q = np.asarray(q, dtype=float)
        if np.linalg.norm(q - out[-1]) >= spacing:
            out.append(q)
    last = np.asarray(points[-1], dtype=float)
    if len(points) > 1 and np.linalg.norm(last - out[-1]) > 1e-9:
        out.append(last)
    arr = np.vstack(out)
    if len(arr) > limit:
        arr = arr[np.linspace(0, len(arr) - 1, limit).round().astype(int)]
    return arr


def stroke_command(p, body: int, points, s: Settings, invert: bool = False, smooth: bool = False) -> str | None:
    """Store the stroke and give the command for it (None when there is nothing to do)."""
    from ..commands.sculpt_handlers import new_stroke_name

    pts = thin(list(points), max(s.radius * 0.1, 1e-6))
    if len(pts) == 0:
        return None
    name = new_stroke_name(p)
    p.strokes[name] = pts
    r = fmt_num(round(s.radius, 4))
    if s.brush == "MASK" and not smooth:
        return f"MASK, {body}, {'ERASE' if invert else 'PAINT'}, 0, 0, 0, {r}, 1, {name}"
    brush = "SMOOTH" if smooth else s.brush
    strength = -s.strength if invert and brush not in ("SMOOTH", "FLATTEN", "GRAB") else s.strength
    sym = "".join(a for a in "XYZ" if a in s.sym)
    return f"SCULPT, {body}, {brush}, {r}, {fmt_num(round(strength, 4))}, {name}" + (f", {sym}" if sym else "")


def default_radius(shape) -> float:
    """A brush about 1/20 of the body's size."""
    pts, _ = mb.arrays(shape)
    size = float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0)))
    return float(fmt_num(round(max(size / 20, 1e-3), 3)))


# ---- the Sculpt tab -----------------------------------------------------------------------------
def build(win) -> None:
    """The Sculpt ribbon tab: on/off, the brushes, size and strength, symmetry, mask tools."""
    from PySide6.QtGui import QActionGroup

    from . import toolbars as tbs

    s = win.sculpt_settings = Settings()
    vp = win.viewport

    tb = tbs.group(win, "Sculpt", "sculpt", "Sculpt")
    on = tbs.action(win, tb, "Sculpt", "sc_sculpt",
                    "Sculpt the mesh body you drag over (or the picked one): each stroke runs SCULPT (Ctrl: the "
                    "other way, Shift: smooth; Esc ends it)", checkable=True)
    on.toggled.connect(lambda checked: set_on(win, checked))
    vp.sculpt_changed.connect(lambda v: on.setChecked(v) if on.isChecked() != v else None)
    win.sculpt_action = on
    tbs.action(win, tb, "Make sculptable", "sc_mesh",
               "Turn the picked body into a mesh body with even, fine triangles to sculpt\n"
               "Runs: TOMESH, b then REMESH, b, size/150", lambda: make_sculptable(win))

    tb = tbs.group(win, "Brush", "sculpt_brushes", "Sculpt")
    group = QActionGroup(win)
    group.setExclusive(True)
    win.brush_actions = {}
    for key, label, icon, tip in BRUSH_BUTTONS:
        a = tbs.action(win, tb, label, icon, tip + ("\nRuns: SCULPT, body, " + key + ", radius, strength, stroke"
                                                   if key != "MASK" else "\nRuns: MASK, body, PAINT, ..., stroke"),
                       checkable=True)
        group.addAction(a)
        a.triggered.connect(lambda _=False, k=key: set_brush(win, k))
        win.brush_actions[key] = a
    win.brush_actions[s.brush].setChecked(True)

    tb = tbs.group(win, "Size and symmetry", "sculpt_settings", "Sculpt")
    tb.addWidget(QLabel(" Radius "))
    win.radius_box = QDoubleSpinBox()
    win.radius_box.setDecimals(3)
    win.radius_box.setRange(0.001, 1e6)
    win.radius_box.setValue(s.radius)
    win.radius_box.setToolTip("The brush radius, in model units ([ and ] change it)")
    win.radius_box.valueChanged.connect(lambda v: setattr(s, "radius", float(v)))
    tb.addWidget(win.radius_box)
    tb.addWidget(QLabel(" Strength "))
    win.strength_box = QDoubleSpinBox()
    win.strength_box.setDecimals(2)
    win.strength_box.setRange(0.01, 1.0)
    win.strength_box.setSingleStep(0.05)
    win.strength_box.setValue(s.strength)
    win.strength_box.setToolTip("How far one dab moves, as a part of the radius")
    win.strength_box.valueChanged.connect(lambda v: setattr(s, "strength", float(v)))
    tb.addWidget(win.strength_box)
    win.sym_actions = {}
    for axis in "XYZ":
        a = tbs.action(win, tb, f"Mirror {axis}", "sc_sym",
                       f"Mirror every stroke in the plane {axis.lower()} = 0", checkable=True)
        a.toggled.connect(lambda checked, ax=axis: (s.sym.add(ax) if checked else s.sym.discard(ax)))
        win.sym_actions[axis] = a

    tb = tbs.group(win, "Mask", "sculpt_mask", "Sculpt")
    tbs.action(win, tb, "Clear mask", "sc_mask", "Unfreeze everything\nRuns: MASK, body, CLEAR",
               lambda: mask_all(win, "CLEAR"))
    tbs.action(win, tb, "Invert mask", "sc_mask", "Swap frozen and free\nRuns: MASK, body, INVERT",
               lambda: mask_all(win, "INVERT"))

    vp.sculpt_stroke.connect(lambda body, pts, mods: run_stroke(win, body, pts, mods))
    from PySide6.QtGui import QAction, QKeySequence

    for key, factor in (("[", 1 / 1.25), ("]", 1.25)):
        a = QAction(win)
        a.setShortcut(QKeySequence(key))
        a.triggered.connect(lambda _=False, f=factor: win.radius_box.setValue(win.radius_box.value() * f)
                            if win.viewport.sculpt_on else None)
        win.addAction(a)


def set_brush(win, key: str) -> None:
    win.sculpt_settings.brush = key
    if not win.viewport.sculpt_on:
        set_on(win, True)


def set_on(win, on: bool) -> None:
    vp = win.viewport
    if on and not vp.sculpt_on:
        b = sculpt_target(win)
        if b is not None and win.radius_box.value() == Settings().radius:
            win.radius_box.setValue(default_radius(win.processor.model.bodies[b].shape))
    if vp.sculpt_on != on:
        vp.set_sculpt(on)
    if on:
        win.statusBar().showMessage("Sculpt: drag over a mesh body. Ctrl: the other way, Shift: smooth, "
                                    "[ ]: brush size, Esc: stop", 8000)


def sculpt_target(win) -> int | None:
    """The picked mesh body, else the only mesh body."""
    m = win.processor.model
    if m.selection_kind == "BODY" and len(m.selection) == 1 and mb.is_mesh(m.bodies[m.selection[0]].shape):
        return m.selection[0]
    meshes = [b for b, body in m.bodies.items() if mb.is_mesh(body.shape)]
    return meshes[0] if len(meshes) == 1 else None


def run_stroke(win, body: int, points, mods) -> None:
    p = win.processor
    invert = bool(mods & Qt.ControlModifier)
    smooth = bool(mods & Qt.ShiftModifier)
    text = stroke_command(p, body, points, win.sculpt_settings, invert, smooth)
    if text is None:
        return
    name = [w.strip() for w in text.split(",")][-1 if text.startswith("MASK") else 5]
    r = win.execute(text)
    if not r.ok:
        p.strokes.pop(name, None)  # nothing uses it


def make_sculptable(win):
    from ..geometry.meshbody import is_mesh

    m = win.processor.model
    if not (m.selection_kind == "BODY" and len(m.selection) == 1):
        win.statusBar().showMessage("Make sculptable: pick one body first (Body pick mode)", 6000)
        return []
    b = m.selection[0]
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(m.bodies[b].shape, box, True)
    lo, hi = box.CornerMin(), box.CornerMax()
    size = ((hi.X() - lo.X()) ** 2 + (hi.Y() - lo.Y()) ** 2 + (hi.Z() - lo.Z()) ** 2) ** 0.5
    cmds = [] if is_mesh(m.bodies[b].shape) else [f"TOMESH, {b}"]
    cmds.append(f"REMESH, {b}, {fmt_num(round(size / 150, 4))}")
    for c in cmds:
        if not win.execute(c).ok:
            break
    return []


def mask_all(win, mode: str):
    b = sculpt_target(win)
    if b is None:
        win.statusBar().showMessage("Mask: pick the mesh body first", 6000)
        return []
    win.execute(f"MASK, {b}, {mode}")
    return []


def describe_brush(s: Settings) -> str:
    return f"{s.brush.title()} r {fmt_num(s.radius)} strength {fmt_num(s.strength)}" + (
        f" mirror {''.join(sorted(s.sym))}" if s.sym else "")


__all__ = ["ray_hit", "thin", "stroke_command", "build", "Settings", "sc"]
