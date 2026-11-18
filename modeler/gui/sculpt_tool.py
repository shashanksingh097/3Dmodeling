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
    detail: float = 0.0  # 0: keep the triangles; more: split edges near the stroke down to this length


# ---- where the mouse ray meets a mesh ----------------------------------------------------------
INDEX_FROM = 60_000  # from this many triangles, rays first look for the boxes they pass through
CHUNK = 2048  # triangles per box


class RayIndex:
    """Boxes round runs of nearby triangles, so a ray only tests the triangles in the boxes it
    passes through. The order (triangles sorted along a space-filling curve) is kept while the
    triangles stay the same; the boxes are worked out again when the points move."""

    def __init__(self, tris: np.ndarray, pts: np.ndarray):
        self.tris = tris
        c = pts[tris].mean(axis=1)
        lo, hi = c.min(axis=0), c.max(axis=0)
        q = ((c - lo) / np.maximum(hi - lo, 1e-12) * 1023).astype(np.int64)
        code = np.zeros(len(c), dtype=np.int64)
        for bit in range(10):  # interleave the bits of x, y and z (Morton order)
            for k in range(3):
                code |= ((q[:, k] >> bit) & 1) << (3 * bit + k)
        self.order = np.argsort(code, kind="stable")
        self.sorted = tris[self.order]
        self.starts = np.arange(0, len(tris), CHUNK)
        self.pts = None
        self.boxes = None

    def boxes_for(self, pts: np.ndarray):
        if self.pts is not pts:
            corner = pts[self.sorted].reshape(-1, 3)  # every corner of every triangle, in order
            at = self.starts * 3
            self.boxes = (np.minimum.reduceat(corner, at, axis=0), np.maximum.reduceat(corner, at, axis=0))
            self.pts = pts
        return self.boxes

    def candidates(self, pts: np.ndarray, o: np.ndarray, d: np.ndarray, grow: float = 0.0) -> np.ndarray:
        lo, hi = self.boxes_for(pts)
        if grow:
            lo, hi = lo - grow, hi + grow
        with np.errstate(divide="ignore", invalid="ignore"):
            inv = 1.0 / np.where(np.abs(d) < 1e-15, 1e-15, d)
            t1, t2 = (lo - o) * inv, (hi - o) * inv
        near = np.minimum(t1, t2).max(axis=1)
        far = np.maximum(t1, t2).min(axis=1)
        pad = 1e-9 * (1 + np.abs(near))
        hit = np.flatnonzero((far + pad >= np.maximum(near, 0)))
        if not len(hit):
            return self.sorted[:0]
        idx = np.concatenate([np.arange(s, min(s + CHUNK, len(self.sorted))) for s in self.starts[hit]])
        return self.sorted[idx]


_INDEX: list = []  # [(tris, RayIndex)], newest first


def _index(pts: np.ndarray, tris: np.ndarray) -> RayIndex:
    for t, ix in _INDEX:
        if t is tris:
            return ix
    ix = RayIndex(tris, pts)
    _INDEX.insert(0, (tris, ix))
    del _INDEX[4:]
    return ix


def ray_hit(pts: np.ndarray, tris: np.ndarray, origin, direction, with_normal: bool = False,
            base: np.ndarray | None = None, grow: float = 0.0):
    """The nearest point where the ray meets the triangles (Moller-Trumbore, all at once), or None.
    ``with_normal``: (point, unit normal of the triangle hit). On a big mesh only the triangles in
    the boxes the ray passes through are tried (RayIndex). ``base`` and ``grow``: no point of
    ``pts`` is further than ``grow`` from where it is in ``base`` (a drag in progress), so the boxes
    of ``base``, grown, still hold every triangle and need not be worked out again."""
    if len(tris) >= INDEX_FROM:
        o = np.asarray(origin, dtype=float)
        d = np.asarray(direction, dtype=float)
        d = d / (np.linalg.norm(d) or 1.0)
        ref = pts if base is None else base
        tris = _index(ref, tris).candidates(ref, o, d, grow if base is not None else 0.0)
        if not len(tris):
            return None
    return _ray_hit_all(pts, tris, origin, direction, with_normal)


def _ray_hit_all(pts: np.ndarray, tris: np.ndarray, origin, direction, with_normal: bool = False):
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
    if with_normal:
        n = np.cross(e1[i], e2[i])
        n = n / (np.linalg.norm(n) or 1.0)
        return o + d * t[i], n
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
    brush, strength = brush_for(s, invert, smooth)
    sym = "".join(a for a in "XYZ" if a in s.sym)
    text = f"SCULPT, {body}, {brush}, {r}, {fmt_num(round(strength, 4))}, {name}"
    if s.detail > 0:
        return text + f", {sym}, {fmt_num(round(s.detail, 4))}"
    return text + (f", {sym}" if sym else "")


def brush_for(s: Settings, invert: bool = False, smooth: bool = False) -> tuple[str, float]:
    """The brush and signed strength a drag with these keys uses (MASK when it paints the mask)."""
    if s.brush == "MASK" and not smooth:
        return "MASK", s.strength
    brush = "SMOOTH" if smooth else s.brush
    strength = -s.strength if invert and brush not in ("SMOOTH", "FLATTEN", "GRAB") else s.strength
    return brush, strength


class LiveStroke:
    """A stroke being dragged: each time the mouse has gone a quarter of the radius, the brush runs on
    a working copy of the points, so the view can show the surface moving. Rays hit the working
    surface. On release the real SCULPT command runs from the body as it was, with the same points."""

    def __init__(self, body: int, shape, s: Settings, invert: bool = False, smooth: bool = False, topo=None):
        self.body, self.shape = body, shape
        self.pts0, self.tris = mb.arrays(shape)
        self.work = self.pts0
        self.brush, self.strength = brush_for(s, invert, smooth)
        self.radius = s.radius
        self.sym = "".join(a for a in "XYZ" if a in s.sym)
        self.mask = None
        self.topo = topo
        self.hits: list[np.ndarray] = []
        self._last = None
        self.changed = False
        self._moved = None  # indices of the points moved so far
        self._grow = 0.0  # no point is further than this from where it started
        self._grid = None

    BIG = 150_000  # from this many triangles, rays look near the last hit first and the view shows a patch

    def hit(self, origin, direction):
        """Where the mouse ray meets the working surface. On a big mesh the boxes of the starting
        points, grown by how far any point has moved, pick the triangles to try."""
        return ray_hit(self.work, self.tris, origin, direction, base=self.pts0, grow=self._grow)

    def _candidates(self, a: np.ndarray, b: np.ndarray) -> np.ndarray | None:
        """The points the segment a-b can reach, with its mirror copies (big meshes only)."""
        if len(self.tris) < self.BIG:
            return None
        if self._grid is None:
            self._grid = sc.PointGrid(self.pts0, 2 * self.radius)
        reach = self.radius + self._grow + 1e-9
        out = []
        for s in sc._mirrors(self.sym):
            p, q = a * s, b * s
            out.append(self._grid.inside(np.minimum(p, q) - reach, np.maximum(p, q) + reach))
        return np.unique(np.concatenate(out))

    def patch(self):
        """Only the triangles that moved, as a shape for drawing over the body (for big meshes,
        where redrawing the whole body at every mouse move would be slow); None if nothing moved."""
        if self._moved is None or not len(self._moved):
            return None
        if self.topo is None:
            self.topo = sc.Topology.of(self.tris, len(self.pts0))
        used, inv = np.unique(self.tris[self.topo.triangles_of(self._moved)], return_inverse=True)
        return mb.make_shape(self.work[used], inv.reshape(-1, 3), remember=False)

    def add(self, point) -> bool:
        """One more point under the mouse; True when the working surface moved."""
        q = np.asarray(point, dtype=float)
        self.hits.append(q)
        if self._last is None:
            self._last = q
            return False
        if np.linalg.norm(q - self._last) < self.radius * sc.SPACING:
            return False
        if self.brush == "MASK":
            self._last = q
            return False
        if self.topo is None:
            self.topo = sc.Topology.of(self.tris, len(self.pts0))
        try:
            new, rep = sc.stroke(self.work, self.tris, self.brush, self.radius, self.strength,
                                 np.vstack([self._last, q]), self.sym, self.mask, self.topo,
                                 self._candidates(self._last, q))
        except sc.SculptError:
            return False
        self._last = q
        if rep.moved:
            self.work, self.changed = new, True
            self._moved = rep.points if self._moved is None else np.union1d(self._moved, rep.points)
            m = self._moved
            self._grow = float(np.sqrt(np.einsum("ij,ij->i", new[m] - self.pts0[m], new[m] - self.pts0[m]).max()))
        return bool(rep.moved)

    def preview(self):
        """A shape of the working surface, for drawing only (not cached)."""
        return mb.moved_shape(self.shape, self.work, remember=False)


def mask_overlay(pts: np.ndarray, tris: np.ndarray, mask) -> tuple[np.ndarray, np.ndarray] | None:
    """The frozen triangles (mask above one half on average), lifted a hair off the surface so they
    draw over it; None when nothing is frozen or the mask no longer fits the mesh."""
    if mask is None or len(mask) != len(pts):
        return None
    keep = np.asarray(mask)[tris].mean(axis=1) > 0.5
    if not keep.any():
        return None
    sub = tris[keep]
    used, inv = np.unique(sub, return_inverse=True)
    q = pts[used]
    t = inv.reshape(-1, 3)
    size = float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0))) or 1.0
    return q + sc.vertex_normals(q, t) * size * 1e-3, t


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
    vp.sculpt_settings = s

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
    tbs.action(win, tb, "Fit surface", "sc_fit",
               "Fit a smooth NURBS surface to the picked mesh body (the masked region if it has a mask), "
               "in a form to set the tolerance\nRuns: FITSURF, b, region, tolerance", lambda: fit_surface(win))

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
    tb.addWidget(QLabel(" Detail "))
    win.detail_box = QDoubleSpinBox()
    win.detail_box.setDecimals(3)
    win.detail_box.setRange(0.0, 1e6)
    win.detail_box.setSpecialValueText("off")
    win.detail_box.setValue(s.detail)
    win.detail_box.setToolTip("Dynamic detail: before each stroke, split the triangles near it until no edge there "
                              "is longer than this, so fine shapes come out sharp (off: keep the triangles)")
    win.detail_box.valueChanged.connect(lambda v: setattr(s, "detail", float(v)))
    tb.addWidget(win.detail_box)
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
        b = sculpt_target(win)
        if b is not None:  # build the big-mesh ray boxes now, not at the first mouse move
            pts, tris = mb.arrays(win.processor.model.bodies[b].shape)
            if len(tris) >= INDEX_FROM:
                _index(pts, tris).boxes_for(pts)
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


def fit_surface(win):
    """The FITSURF form for the picked mesh body, with MASK as region when it has a mask."""
    m = win.processor.model
    b = sculpt_target(win)
    if b is None:
        win.statusBar().showMessage("Fit surface: pick one mesh body first (Body pick mode)", 6000)
        return None
    region = "MASK" if m.masks.get(b) is not None else "ALL"
    return win.open_form("FITSURF", f"FITSURF, {b}, {region}")


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
