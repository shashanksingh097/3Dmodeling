"""Pipe, tube and cable routes (ROUTE).

A route follows the straight lines of a path. At each corner it bends with a
set radius: the two lines are cut back by R·tan(θ/2) (θ the turn) and an arc
joins them. A pipe is a ring (outside diameter and wall) swept along that
centreline; a cable is a round bundle whose diameter comes from the wires in
it. When a route starts or ends on another route's centreline, the two are
joined as a tee: the pipes fused and both bores cut again.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


class RouteError(ValueError):
    pass


@dataclass
class Route:
    kind: str  # PIPE or CABLE
    od: float
    wall: float  # 0: solid (a cable, a rod)
    radius: float  # bend radius, on the centreline
    straights: list[float] = field(default_factory=list)
    bends: list[float] = field(default_factory=list)  # the turn of each bend, degrees
    wires: tuple[int, float] | None = None  # a cable: (count, wire diameter)
    centrelines: list = field(default_factory=list)  # OCC wires, for tees and the bore
    tees: int = 0

    @property
    def length(self) -> float:
        return sum(self.straights) + sum(math.radians(a) * self.radius for a in self.bends)

    def size_text(self) -> str:
        if self.kind == "CABLE":
            n, d = self.wires or (1, self.od)
            return f"{n}x{d:g} (bundle {self.od:.3g})" if n > 1 else f"{self.od:g}"
        return f"{self.od:g}x{self.wall:g}" if self.wall else f"{self.od:g} solid"


def parse_size(kind: str, text: str) -> tuple[float, float, tuple[int, float] | None]:
    """PIPE: '22x1.5' (outside diameter x wall) or '12' (solid). CABLE: '7x2.5' (wires x diameter) or '12'."""
    parts = [q.strip() for q in str(text).lower().replace("*", "x").split("x") if q.strip()]
    try:
        vals = [float(q) for q in parts]
    except ValueError:
        raise RouteError(f"the size {text!r} is not like 22x1.5") from None
    if not vals or len(vals) > 2 or any(v <= 0 for v in vals):
        raise RouteError(f"the size {text!r} is not like 22x1.5 (positive numbers)")
    if kind == "CABLE":
        if len(vals) == 1:
            return vals[0], 0.0, (1, vals[0])
        n = vals[0]
        if n != int(n) or n < 1:
            raise RouteError("a cable's size is wires x wire diameter, like 7x2.5")
        return bundle(int(n), vals[1]), 0.0, (int(n), vals[1])
    if len(vals) == 1:
        return vals[0], 0.0, None
    od, wall = vals
    if wall * 2 >= od:
        raise RouteError(f"a wall of {wall:g} leaves no bore in a pipe {od:g} across")
    return od, wall, None


def bundle(n: int, d: float) -> float:
    """The diameter of a round bundle of n wires of diameter d (the circle that packs them)."""
    if n <= 1:
        return d
    # the smallest circle round n equal circles: exact for 2 to 7, the usual packing rule past that
    k = {2: 2.0, 3: 2.1547, 4: 2.4142, 5: 2.7013, 6: 3.0, 7: 3.0}
    return d * (k[n] if n in k else 1.1547 * math.sqrt(n) + 0.3)


def centreline(pts: list, radius: float) -> tuple[list, list[float], list[float]]:
    """The pieces of a bent centreline: [("LINE", a, b) | ("ARC", a, mid, b)], the straight lengths and the
    bend angles (degrees)."""
    P = [np.array(q, float) for q in pts]
    if len(P) < 2:
        raise RouteError("a route needs at least two points")
    cut = [0.0] * len(P)  # how far each corner cuts back the lines on both sides
    turns = [0.0] * len(P)
    for i in range(1, len(P) - 1):
        a, b = P[i] - P[i - 1], P[i + 1] - P[i]
        la, lb = np.linalg.norm(a), np.linalg.norm(b)
        if la < 1e-12 or lb < 1e-12:
            raise RouteError("two points of the path are the same")
        c = float(np.clip(np.dot(a, b) / (la * lb), -1.0, 1.0))
        th = math.acos(c)
        if th > math.radians(179):
            raise RouteError(f"the path turns back on itself at point {i + 1}")
        turns[i] = th
        cut[i] = radius * math.tan(th / 2)
    pieces, straights, bends = [], [], []
    start = P[0]
    for i in range(len(P) - 1):
        seg = P[i + 1] - P[i]
        ln = float(np.linalg.norm(seg))
        u = seg / ln
        if cut[i] + cut[i + 1] > ln * (1 + 1e-9):
            raise RouteError(f"the bend radius {radius:g} is too big for the piece from point {i + 1} to "
                             f"{i + 2} ({ln:.4g} long): it needs {cut[i] + cut[i + 1]:.4g}")
        end = P[i + 1] - u * cut[i + 1]
        if np.linalg.norm(end - start) > 1e-9:
            pieces.append(("LINE", start, end))
            straights.append(float(np.linalg.norm(end - start)))
        if i + 1 < len(P) - 1 and turns[i + 1] > 1e-9:
            nxt = P[i + 2] - P[i + 1]
            v = nxt / np.linalg.norm(nxt)
            after = P[i + 1] + v * cut[i + 1]
            bis = v - u
            bis = bis / np.linalg.norm(bis)
            centre = P[i + 1] + bis * radius / math.cos(turns[i + 1] / 2)
            m = (end + after) / 2 - centre
            mid = centre + m / np.linalg.norm(m) * radius
            pieces.append(("ARC", end, mid, after))
            bends.append(math.degrees(turns[i + 1]))
            start = after
        else:
            start = end
    return pieces, straights, bends


def _wire(pieces):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
    from OCP.GC import GC_MakeArcOfCircle, GC_MakeSegment
    from OCP.gp import gp_Pnt

    def P(q):
        return gp_Pnt(*map(float, q))

    mw = BRepBuilderAPI_MakeWire()
    for pc in pieces:
        if pc[0] == "LINE":
            e = BRepBuilderAPI_MakeEdge(GC_MakeSegment(P(pc[1]), P(pc[2])).Value()).Edge()
        else:
            e = BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(P(pc[1]), P(pc[2]), P(pc[3])).Value()).Edge()
        mw.Add(e)
    if not mw.IsDone():
        raise RouteError("the centreline could not be joined into one wire")
    return mw.Wire()


def _disc(centre, normal, r: float, hole: float = 0.0):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
    from OCP.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Pnt

    ax = gp_Ax2(gp_Pnt(*map(float, centre)), gp_Dir(*map(float, normal)))
    outer = BRepBuilderAPI_MakeWire(BRepBuilderAPI_MakeEdge(gp_Circ(ax, r)).Edge()).Wire()
    mf = BRepBuilderAPI_MakeFace(outer, True)
    if hole > 0:
        inner = BRepBuilderAPI_MakeWire(BRepBuilderAPI_MakeEdge(gp_Circ(ax, hole)).Edge()).Wire()
        inner.Reverse()
        mf.Add(inner)
    return mf.Face()


def _sweep(wire, start, direction, r: float, hole: float = 0.0):
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipe

    pipe = BRepOffsetAPI_MakePipe(wire, _disc(start, direction, r, hole))
    pipe.Build()
    if not pipe.IsDone():
        raise RouteError("the pipe could not be swept along the route")
    return pipe.Shape()


def build(pts: list, kind: str, od: float, wall: float, radius: float):
    """The route's solid, its centreline wire, the straight lengths and the bend angles."""
    if radius <= od / 2 * (1 + 1e-9):
        raise RouteError(f"the bend radius must be more than half the diameter ({od / 2:g})")
    pieces, straights, bends = centreline(pts, radius)
    wire = _wire(pieces)
    first = pieces[0]
    d0 = np.array(first[2] if first[0] == "LINE" else first[2], float) - np.array(first[1], float)
    shape = _sweep(wire, first[1], d0 / np.linalg.norm(d0), od / 2, od / 2 - wall if wall else 0.0)
    return shape, wire, straights, bends


def bore(wire, od: float, wall: float):
    """The empty inside of a pipe along a centreline (for cutting again after a tee)."""
    from OCP.BRepAdaptor import BRepAdaptor_CompCurve
    from OCP.gp import gp_Pnt, gp_Vec

    c = BRepAdaptor_CompCurve(wire)
    p, v = gp_Pnt(), gp_Vec()
    c.D1(c.FirstParameter(), p, v)
    d = np.array([v.X(), v.Y(), v.Z()])
    return _sweep(wire, (p.X(), p.Y(), p.Z()), d / np.linalg.norm(d), od / 2 - wall)


def on_line(wire, q, tol: float) -> bool:
    """Is the point on the centreline (between its ends, not at them)?"""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.gp import gp_Pnt

    v = BRepBuilderAPI_MakeVertex(gp_Pnt(*map(float, q))).Vertex()
    d = BRepExtrema_DistShapeShape(v, wire)
    return d.IsDone() and d.Value() <= tol


def _bop(cls, a, b):
    op = cls(a, b)
    op.Build()
    if not op.IsDone():
        raise RouteError("the pipes could not be joined")
    return op.Shape()


def tee(host, branch, bores: list):
    """Join a branch to a host route and cut the bores again (empty list: solid routes)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse

    out = _bop(BRepAlgoAPI_Fuse, host, branch)
    for b in bores:
        out = _bop(BRepAlgoAPI_Cut, out, b)
    return out
