"""Editing in a cross-section (PLAN item 96): the lines where a plane cuts a solid, each tied to
the face of the solid it comes from.

``cut_lines(shape, origin, z, x)`` gives one CutLine per edge of the cut: its kind (line, arc or
curve), its ends, its length, an arc's centre and radius, the face behind it and the way that face
moves in the plane when it is pushed out (``push``: the face's outward normal at the line's middle,
laid into the plane). Moving the line by d along ``push`` is PUSHPULL d on that face, so editing in
the section writes ordinary steps. No Qt here, so it is tested headless.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
from OCP.GCPnts import GCPnts_AbscissaPoint
from OCP.GeomAbs import GeomAbs_CurveType
from OCP.gp import gp_Ax3, gp_Dir, gp_Pln, gp_Pnt
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Shape

from . import robust
from .feature_finder import _normal_at
from .recognize import _static

P3 = tuple[float, float, float]
_as_edge = _static(TopoDS, "Edge")
_as_face = _static(TopoDS, "Face")


@dataclass
class CutLine:
    index: int  # 1, 2 ... in the order of the cut
    face: object  # the solid's face behind the line (TopoDS_Face)
    edge: object  # the line itself (TopoDS_Edge, on the plane)
    kind: str  # "line", "arc" or "curve"
    start: P3
    end: P3
    mid: P3
    length: float
    push: P3 | None  # the face's outward normal at mid, laid into the plane (None: across the plane)
    centre: P3 | None = None  # arcs
    radius: float = 0.0
    uv_start: tuple[float, float] = (0.0, 0.0)  # in the plane's own x, y
    uv_end: tuple[float, float] = (0.0, 0.0)


class SectionError(Exception):
    pass


def _xyz(p) -> P3:
    return (p.X(), p.Y(), p.Z())


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _uv(p: P3, origin: P3, x: P3, y: P3) -> tuple[float, float]:
    d = (p[0] - origin[0], p[1] - origin[1], p[2] - origin[2])
    return (_dot(d, x), _dot(d, y))


def _cross(a, b) -> P3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def cut_lines(shape, origin: P3, z: P3, x: P3) -> list[CutLine]:
    """The edges where the plane through ``origin`` with normal ``z`` (and in-plane x axis ``x``)
    cuts ``shape``, each with the face it lies on. An empty list when the plane misses."""
    if not robust.solids(shape):
        raise SectionError("only solids can be edited in a section")
    pln = gp_Pln(gp_Ax3(gp_Pnt(*origin), gp_Dir(*z), gp_Dir(*x)))
    sec = BRepAlgoAPI_Section(shape, pln, False)
    sec.ComputePCurveOn1(True)
    sec.Approximation(True)
    sec.Build()
    if not sec.IsDone():
        raise SectionError("the kernel could not cut the solid with that plane")
    y = _cross(z, x)
    out: list[CutLine] = []
    ex = TopExp_Explorer(sec.Shape(), TopAbs_EDGE)
    while ex.More():
        edge = _as_edge(ex.Current())
        ex.Next()
        anc = TopoDS_Shape()
        if not sec.HasAncestorFaceOn1(edge, anc) or anc.IsNull():
            continue
        face = _as_face(anc)
        c = BRepAdaptor_Curve(edge)
        t0, t1 = c.FirstParameter(), c.LastParameter()
        a, b, m = _xyz(c.Value(t0)), _xyz(c.Value(t1)), _xyz(c.Value((t0 + t1) / 2))
        length = GCPnts_AbscissaPoint.Length_s(c)
        if length < 1e-9:
            continue
        kind, centre, radius = "curve", None, 0.0
        ct = c.GetType()
        if ct == GeomAbs_CurveType.GeomAbs_Line:
            kind = "line"
        elif ct == GeomAbs_CurveType.GeomAbs_Circle:
            circ = c.Circle()
            kind, centre, radius = "arc", _xyz(circ.Location()), circ.Radius()
        n = _normal_at(face, m)
        push = None
        if n is not None:
            k = _dot(n, z)
            q = (n[0] - k * z[0], n[1] - k * z[1], n[2] - k * z[2])
            ln = math.sqrt(_dot(q, q))
            if ln > 1e-6:
                push = (q[0] / ln, q[1] / ln, q[2] / ln)
        out.append(CutLine(len(out) + 1, face, edge, kind, a, b, m, length, push, centre, radius,
                           _uv(a, origin, x, y), _uv(b, origin, x, y)))
    return out


def lines_as_data(lines: list[CutLine], face_id, digits: int = 6) -> list[dict]:
    """The cut as plain data for reports and the assistant. ``face_id(face)`` gives a face's ID."""
    r = lambda v: [round(c, digits) + 0.0 for c in v]  # noqa: E731
    out = []
    for ln in lines:
        d = {"line": ln.index, "face": face_id(ln.face), "kind": ln.kind, "from": r(ln.start), "to": r(ln.end),
             "length": round(ln.length, digits)}
        if ln.kind == "arc":
            d["centre"], d["radius"] = r(ln.centre), round(ln.radius, digits)
        if ln.push is not None:
            d["push"] = r(ln.push)
        out.append(d)
    return out


def nearest(lines: list[CutLine], x: float, y: float, to_pixel, within: float = 9.0) -> CutLine | None:
    """The cut line nearest the mouse (pixels), when it is within ``within`` pixels."""
    best, best_d = None, within
    for ln in lines:
        c = BRepAdaptor_Curve(ln.edge)
        t0, t1 = c.FirstParameter(), c.LastParameter()
        pts = [to_pixel(_xyz(c.Value(t0 + (t1 - t0) * k / 16))) for k in range(17)]
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            d = _seg_px(x, y, ax, ay, bx, by)
            if d < best_d:
                best, best_d = ln, d
    return best


def _seg_px(x, y, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    t = 0.0 if ll < 1e-12 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / ll))
    px, py = ax + t * dx - x, ay + t * dy - y
    return math.hypot(px, py)
