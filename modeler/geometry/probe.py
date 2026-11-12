"""Probing space without a picture: rays, points, cross-sections and wall thickness.

Plain kernel work on shapes; the commands (PROBE, PROFILE, THICK) and the
AI tools add IDs and formatting. Faces come back as TopoDS faces for the
caller to look up.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
from OCP.BRepClass import BRepClass_FaceClassifier
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepGProp import BRepGProp, BRepGProp_Face
from OCP.BRepTools import BRepTools, BRepTools_WireExplorer
from OCP.GeomAbs import GeomAbs_CurveType
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Dir, gp_Lin, gp_Pnt, gp_Pnt2d, gp_Vec
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
from OCP.TopAbs import TopAbs_FACE, TopAbs_IN, TopAbs_ON, TopAbs_OUT, TopAbs_REVERSED, TopAbs_WIRE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Shape

from ..core import datum as dt
from . import features as ft
from . import robust

as_face = ft.as_face
as_edge = ft.as_edge
as_wire = getattr(TopoDS, "Wire_s", None) or TopoDS.Wire

P3 = tuple[float, float, float]


def _xyz(p) -> P3:
    return (p.X(), p.Y(), p.Z())


def _unit(d) -> P3:
    n = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)
    if n < 1e-15:
        raise ValueError("the direction cannot be (0, 0, 0)")
    return (d[0] / n, d[1] / n, d[2] / n)


# ---- rays ---------------------------------------------------------------------------


class Rays:
    """Cast many rays at one shape: the shape is prepared once."""

    def __init__(self, shape: TopoDS_Shape, tol: float = 1e-6) -> None:
        self.shape = shape
        self.tol = tol
        self._x = IntCurvesFace_ShapeIntersector()
        self._x.Load(shape, tol)

    def hits(self, origin: P3, d: P3, length: float = 1e9) -> list[dict]:
        """Every crossing of the half-line with a face, nearest first, with
        state "in" (entering material) or "out" (leaving). Duplicate hits where
        the ray passes through an edge are merged."""
        d = _unit(d)
        x = self._x
        x.Perform(gp_Lin(gp_Pnt(*origin), gp_Dir(*d)), -self.tol, length)
        out: list[dict] = []
        if not x.IsDone():
            return out
        for i in range(1, x.NbPnt() + 1):
            face = x.Face(i)
            g = BRepGProp_Face(face)
            pp, n = gp_Pnt(), gp_Vec()
            g.Normal(x.UParameter(i), x.VParameter(i), pp, n)
            dot = n.X() * d[0] + n.Y() * d[1] + n.Z() * d[2]
            state = "in" if dot < 0 else "out"
            out.append({"t": x.WParameter(i), "point": _xyz(x.Pnt(i)), "face": face, "state": state,
                        "grazing": abs(dot) < 1e-9 * max(1.0, n.Magnitude())})
        out.sort(key=lambda h: h["t"])
        merged: list[dict] = []
        for h in out:
            if merged and abs(h["t"] - merged[-1]["t"]) <= 10 * self.tol and h["state"] == merged[-1]["state"]:
                merged[-1].setdefault("also", []).append(h["face"])
                continue
            merged.append(h)
        return merged


def material_spans(hits: list[dict], starts_inside: bool) -> list[tuple[float, float]]:
    """Stretches of the ray inside material, as (from t, to t)."""
    spans = []
    start = 0.0 if starts_inside else None
    for h in hits:
        if h.get("grazing"):
            continue
        if h["state"] == "in" and start is None:
            start = h["t"]
        elif h["state"] == "out" and start is not None:
            spans.append((start, h["t"]))
            start = None
    return spans


# ---- points ---------------------------------------------------------------------------


def classify(shape: TopoDS_Shape, point: P3, tol: float = 1e-6) -> str:
    """inside, outside or on (the surface of) a solid."""
    c = BRepClass3d_SolidClassifier(shape, gp_Pnt(*point), tol)
    st = c.State()
    return {TopAbs_IN: "inside", TopAbs_OUT: "outside", TopAbs_ON: "on"}.get(st, "unknown")


def nearest(shape: TopoDS_Shape, point: P3) -> tuple[float, P3, TopoDS_Shape | None]:
    """(distance, nearest point, the face it is on or None) from a point to the
    surface of a shape (also from inside a solid, where the solid itself is 0 away)."""
    v = BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex()
    d = BRepExtrema_DistShapeShape(v, _skin(shape))
    if not d.IsDone() or d.NbSolution() == 0:
        raise ValueError("the kernel could not measure that distance")
    face = None
    for i in range(1, d.NbSolution() + 1):
        sup = d.SupportOnShape2(i)
        if sup.ShapeType() == TopAbs_FACE:
            face = sup
            break
    if face is None:  # nearest to an edge or vertex: the face that is nearest the point itself
        best = None
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        while exp.More():
            got = BRepExtrema_DistShapeShape(v, exp.Current())
            if got.IsDone() and (best is None or got.Value() < best[0] - 1e-9):
                best = (got.Value(), exp.Current())
            exp.Next()
        face = best[1] if best else None
    return d.Value(), _xyz(d.PointOnShape2(1)), face


def _skin(shape: TopoDS_Shape) -> TopoDS_Shape:
    """The faces of a shape as a compound, so distances are measured to its surface."""
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound

    comp = TopoDS_Compound()
    b = BRep_Builder()
    b.MakeCompound(comp)
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    n = 0
    while exp.More():
        b.Add(comp, exp.Current())
        n += 1
        exp.Next()
    return comp if n else shape


# ---- cross-sections ---------------------------------------------------------------------


@dataclass
class Loop:
    outer: bool
    segments: list[dict] = field(default_factory=list)  # in plane coordinates (u, v)
    area: float = 0.0


@dataclass
class Section:
    loops: list[Loop]
    area: float
    centre: tuple[float, float] | None  # in plane coordinates


def section(shape: TopoDS_Shape, plane: dt.Datum, around: P3, size: float) -> Section:
    """The cut of a solid by a plane, as flat loops of lines, arcs and curves
    in the plane's own u, v coordinates (u along its x, v along its y).
    ``around`` is a point the cut should centre on (the body's middle) and
    ``size`` the half width of the cutting square."""
    face = ft.plane_face(plane, around, size)
    common = BRepAlgoAPI_Common(shape, face)
    if not common.IsDone():
        raise ValueError("the kernel could not cut the body")
    cut = common.Shape()
    loops: list[Loop] = []
    total, mu, mv = 0.0, 0.0, 0.0
    exp = TopExp_Explorer(cut, TopAbs_FACE)
    while exp.More():
        f = as_face(exp.Current())
        g = GProp_GProps()
        BRepGProp.SurfaceProperties_s(f, g)
        a = g.Mass()
        if a > 1e-12:
            c = _xyz(g.CentreOfMass())
            u, v, _ = plane.local(c)
            total += a
            mu += u * a
            mv += v * a
            outer = BRepTools.OuterWire_s(f)
            wexp = TopExp_Explorer(f, TopAbs_WIRE)
            while wexp.More():
                w = as_wire(wexp.Current())
                is_outer = w.IsSame(outer)
                loops.append(Loop(is_outer, _segments(w, f, plane), a if is_outer else 0.0))
                wexp.Next()
        exp.Next()
    centre = (mu / total, mv / total) if total > 0 else None
    return Section(loops, total, centre)


def _segments(w, face, plane: dt.Datum) -> list[dict]:
    segs: list[dict] = []
    it = BRepTools_WireExplorer(w, face)
    while it.More():
        e = it.Current()
        c = BRepAdaptor_Curve(e)
        t0, t1 = c.FirstParameter(), c.LastParameter()
        reversed_ = e.Orientation() == TopAbs_REVERSED
        a, b = _xyz(c.Value(t0)), _xyz(c.Value(t1))
        if reversed_:
            a, b = b, a
        ua, ub = plane.local(a)[:2], plane.local(b)[:2]
        kind = c.GetType()
        if kind == GeomAbs_CurveType.GeomAbs_Line:
            segs.append({"line": [ua, ub]})
        elif kind == GeomAbs_CurveType.GeomAbs_Circle:
            circ = c.Circle()
            cu = plane.local(_xyz(circ.Location()))[:2]
            full = abs((t1 - t0) - 2 * math.pi) < 1e-9
            if full:
                segs.append({"circle": {"c": cu, "r": circ.Radius()}})
            else:
                segs.append({"arc": {"c": cu, "r": circ.Radius(), "from": ua, "to": ub,
                                     "deg": math.degrees(t1 - t0)}})
        else:
            n = 8
            pts = [plane.local(_xyz(c.Value(t0 + (t1 - t0) * k / n)))[:2] for k in range(n + 1)]
            if reversed_:
                pts.reverse()
            g = GProp_GProps()
            BRepGProp.LinearProperties_s(e, g)
            segs.append({"curve": {"points": pts, "length": g.Mass()}})
        it.Next()
    return _join_lines(segs)


def _join_lines(segs: list[dict]) -> list[dict]:
    """Lines that continue each other in a straight line become one."""
    out: list[dict] = []
    for s in segs:
        if out and "line" in s and "line" in out[-1]:
            (a, b), (c, d) = out[-1]["line"], s["line"]
            if _close(b, c) and abs(_cross(_sub2(b, a), _sub2(d, c))) <= 1e-9 * (1 + _len2(_sub2(b, a)) * _len2(_sub2(d, c))):
                out[-1] = {"line": [a, d]}
                continue
        out.append(s)
    if len(out) > 1 and "line" in out[0] and "line" in out[-1]:
        (a, b), (c, d) = out[-1]["line"], out[0]["line"]
        if _close(b, c) and abs(_cross(_sub2(b, a), _sub2(d, c))) <= 1e-9 * (1 + _len2(_sub2(b, a)) * _len2(_sub2(d, c))):
            out[0] = {"line": [a, d]}
            out.pop()
    return out


def _sub2(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _cross(a, b) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _len2(a) -> float:
    return math.hypot(a[0], a[1])


def _close(a, b, tol: float = 1e-6) -> bool:
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


# ---- wall thickness ----------------------------------------------------------------------


@dataclass
class Spot:
    thickness: float
    face: TopoDS_Shape  # where the ray started
    point: P3
    other: TopoDS_Shape | None  # the face it met on the other side
    other_point: P3


def wall_thickness(shape: TopoDS_Shape, per_face: int = 5) -> list[Spot]:
    """Thickness measured straight in from points spread over every face:
    each ray goes from the surface into the material and stops where it
    leaves. Returns the thinnest spot found on each face, thinnest first."""
    rays = Rays(shape, 1e-7)
    spots: list[Spot] = []
    diag = robust.diagonal(shape)
    eps = 1e-7 * max(1.0, diag)
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    seen = []
    while exp.More():
        f = as_face(exp.Current())
        exp.Next()
        if any(f.IsSame(s) for s in seen):
            continue
        seen.append(f)
        best: Spot | None = None
        for (u, v) in _samples(f, per_face):
            g = BRepGProp_Face(f)
            p, n = gp_Pnt(), gp_Vec()
            g.Normal(u, v, p, n)
            if n.Magnitude() < 1e-12:
                continue
            inward = _unit((-n.X(), -n.Y(), -n.Z()))
            start = _xyz(p)
            for h in rays.hits(start, inward, 2 * diag + 1):
                if h["t"] <= eps or h["face"].IsSame(f) and h["t"] <= 10 * eps:
                    continue
                if h["state"] == "out" and not h.get("grazing") and (best is None or h["t"] < best.thickness):
                    best = Spot(h["t"], f, start, h["face"], h["point"])
                break  # only the first crossing counts
        if best is not None:
            spots.append(best)
    spots.sort(key=lambda s: s.thickness)
    # the same wall seen from both sides is one wall
    out: list[Spot] = []
    for sp in spots:
        if any(sp.other is not None and sp.other.IsSame(o.face) and sp.face.IsSame(o.other)
               and abs(sp.thickness - o.thickness) <= 1e-6 * max(1.0, o.thickness) for o in out):
            continue
        out.append(sp)
    return out


def _samples(face, n: int) -> list[tuple[float, float]]:
    """n x n parameter points spread inside the face (only those really on it)."""
    u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
    out = []
    for i in range(n):
        for j in range(n):
            u = u0 + (u1 - u0) * (i + 0.5) / n
            v = v0 + (v1 - v0) * (j + 0.5) / n
            cl = BRepClass_FaceClassifier(face, gp_Pnt2d(u, v), 1e-7)
            if cl.State() == TopAbs_IN:
                out.append((u, v))
    return out
