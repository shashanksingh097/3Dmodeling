"""Dragging control points in the view: which point is under the mouse, where
a drag takes it, and the MOVEPT command it writes.

No Qt here, so it is tested headless. The viewport gives it two functions:
``to_pixel(xyz) -> (x, y)`` and ``ray(x, y) -> (origin, direction)``. A
dragged point moves in the plane through it that faces the screen, so it
follows the mouse whatever the view's direction.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..core.model import Model
from ..geometry import nurbs as nb
from ..lang.expr import fmt_num

Point = tuple[float, float, float]


@dataclass
class Drag:
    index: tuple[int, ...]
    start: Point  # where the point was
    now: Point  # where the mouse has taken it


class PointEditor:
    def __init__(self, model: Model, bid: int):
        self.model, self.bid = model, bid
        self.drag: Drag | None = None
        self.geometry = None
        self.refresh()

    def refresh(self) -> bool:
        """Read the control points again (after an edit). False when the body is gone or has none."""
        body = self.model.bodies.get(self.bid)
        if body is None:
            self.geometry = None
            return False
        try:
            self.geometry = nb.geometry_of(body.shape, need_whole=False)
        except nb.CurveError:
            self.geometry = None
            return False
        return True

    # ---- what to draw ----------------------------------------------------------
    def points(self) -> list[tuple[tuple[int, ...], Point]]:
        g = self.geometry
        if g is None:
            return []
        ps = nb.poles(g)
        if isinstance(g, nb.Geom_BSplineCurve):
            out = [((i,), q) for i, q in enumerate(ps, 1)]
        else:
            out = [((i, j), q) for i, row in enumerate(ps, 1) for j, q in enumerate(row, 1)]
        if self.drag is not None:
            out = [(k, self.drag.now if k == self.drag.index else q) for k, q in out]
        return out

    def lines(self) -> list[tuple[Point, Point]]:
        """The control polygon (curve) or net (surface), with a dragged point where it is now."""
        g = self.geometry
        if g is None:
            return []
        pts = dict(self.points())
        if isinstance(g, nb.Geom_BSplineCurve):
            n = g.NbPoles()
            segs = [(pts[(i,)], pts[(i + 1,)]) for i in range(1, n)]
            if g.IsPeriodic():
                segs.append((pts[(n,)], pts[(1,)]))
            return segs
        nu, nv = g.NbUPoles(), g.NbVPoles()
        segs = [(pts[(i, j)], pts[(i, j + 1)]) for i in range(1, nu + 1) for j in range(1, nv)]
        segs += [(pts[(i, j)], pts[(i + 1, j)]) for i in range(1, nu) for j in range(1, nv + 1)]
        return segs

    def preview(self):
        """The shape with the dragged point moved (None when nothing is dragged)."""
        if self.drag is None or self.geometry is None:
            return None
        g = nb.copy(self.geometry)
        try:
            nb.move_pole(g, self.drag.index, self.drag.now)
            return nb.shape_of(g)
        except Exception:  # noqa: BLE001 - a preview that cannot be made is just not shown
            return None

    # ---- mouse -----------------------------------------------------------------
    def hit(self, x: float, y: float, to_pixel: Callable[[Point], tuple[float, float]], radius: float = 10.0):
        """The control point within ``radius`` pixels of (x, y), nearest first; None if there is none."""
        best, best_d = None, radius * radius
        for idx, q in self.points():
            px, py = to_pixel(q)
            d = (px - x) ** 2 + (py - y) ** 2
            if d <= best_d:
                best, best_d = idx, d
        return best

    def press(self, x: float, y: float, to_pixel) -> bool:
        idx = self.hit(x, y, to_pixel)
        if idx is None:
            return False
        q = dict(self.points())[idx]
        self.drag = Drag(idx, q, q)
        return True

    def move(self, ray: tuple[Point, Point]) -> None:
        """Move the dragged point to where the mouse ray meets the plane through it facing the screen."""
        if self.drag is None:
            return
        (ox, oy, oz), (dx, dy, dz) = ray
        sx, sy, sz = self.drag.start
        den = dx * dx + dy * dy + dz * dz
        if den < 1e-18:
            return
        # the plane's normal is the ray itself (the view looks along it)
        t = ((sx - ox) * dx + (sy - oy) * dy + (sz - oz) * dz) / den
        self.drag.now = (ox + t * dx, oy + t * dy, oz + t * dz)

    def release(self) -> str | None:
        """The MOVEPT command for the drag (None when the point did not move)."""
        d, self.drag = self.drag, None
        if d is None:
            return None
        delta = tuple(b - a for a, b in zip(d.start, d.now))
        size = max(1.0, max(abs(c) for c in d.start))
        if max(abs(c) for c in delta) < 1e-9 * size:
            return None
        idx = str(d.index[0]) if len(d.index) == 1 else f"({d.index[0]}, {d.index[1]})"
        body = self.model.bodies[self.bid]
        name = body.name if body.name and not body.name.lower().startswith("body") else str(self.bid)
        nums = ", ".join(fmt_num(round(c, 4) + 0.0) for c in delta)
        return f"MOVEPT, {name}, {idx}, {nums}"

    def cancel(self) -> None:
        self.drag = None
