"""Lofts and sweeps.

Two engines:

* **Exact sweep** (``BRepOffsetAPI_MakePipeShell``) when one profile moves
  along the path unchanged.
* **Section sweep** when the profile changes on the way (twist, scale,
  stretch, offset laws, or several profiles to morph between): the profile
  is placed at ``n`` stations along the path and a smooth B-spline loft
  (``BRepOffsetAPI_ThruSections``) is fitted through them.

The moving frame at each station has three axes: *tangent* (along the path),
*side* and *up*. At the start, *up* is world +Z made perpendicular to the
path (world +Y if the path starts along Z), and *side* = up x tangent, so a
profile drawn with ``plane_axes(tangent)`` has its X along *side* and its Y
along *up*. Laws act in that frame: twist turns about the tangent, ``sx``
scales along *side*, ``sy`` along *up*, offsets slide along them.

Frame modes along the path:

* ``MINTWIST`` (default): rotation-minimizing frame, no flips on 3D curves;
* ``FRENET``: follows the curve's curvature (good for helices);
* ``FIXED``: the profile only translates, never turns.

Profiles keep their position relative to the start frame: draw the profile
where the path starts (any offset from the path is kept), and every station
gets the same relative placement, changed by the laws. For a morph, draw all
profiles at the start of the path; each one is reached at its station.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from OCP.BRepAdaptor import BRepAdaptor_CompCurve
from OCP.BRepBuilderAPI import BRepBuilderAPI_GTransform, BRepBuilderAPI_MakeWire, BRepBuilderAPI_Transform
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipeShell, BRepOffsetAPI_ThruSections
from OCP.GCPnts import GCPnts_AbscissaPoint
from OCP.gp import gp_Ax2, gp_Dir, gp_GTrsf, gp_Mat, gp_Pnt, gp_Trsf, gp_Vec, gp_XYZ
from OCP.TopAbs import TopAbs_EDGE, TopAbs_WIRE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Shape, TopoDS_Wire
from OCP.Law import Law_Interpol

try:  # OCP 8
    from OCP.collections import Array1_gp_Pnt2d as _ArrayPnt2d
except ImportError:  # OCP 7.x
    from OCP.TColgp import TColgp_Array1OfPnt2d as _ArrayPnt2d  # type: ignore[no-redef]
from OCP.gp import gp_Pnt2d

from .curves import CurveError, add, cross, dot, mul, norm, spline, sub, unit

_as_wire = getattr(TopoDS, "Wire_s", None) or TopoDS.Wire
_as_edge = getattr(TopoDS, "Edge_s", None) or TopoDS.Edge
_length = getattr(GCPnts_AbscissaPoint, "Length_s", None) or GCPnts_AbscissaPoint.Length

Law = Callable[[float], float]
MODES = ("MINTWIST", "FRENET", "FIXED")


# ---- shapes to wires ---------------------------------------------------------
def as_wire(shape: TopoDS_Shape, what: str) -> TopoDS_Wire:
    """The one wire of a curve body (an edge is wrapped in a wire)."""
    wires = []
    ex = TopExp_Explorer(shape, TopAbs_WIRE)
    while ex.More():
        wires.append(_as_wire(ex.Current()))
        ex.Next()
    if len(wires) == 1:
        return wires[0]
    if not wires:
        edges = []
        ex = TopExp_Explorer(shape, TopAbs_EDGE)
        while ex.More():
            edges.append(_as_edge(ex.Current()))
            ex.Next()
        if edges:
            mk = BRepBuilderAPI_MakeWire()
            for e in edges:
                mk.Add(e)
            if mk.IsDone():
                return mk.Wire()
    raise CurveError(f"{what} must be a single curve (a path or profile body), not a body with {len(wires)} wires")


# ---- path sampling and frames ------------------------------------------------
@dataclass
class Frame:
    o: tuple  # point on the path
    side: tuple
    up: tuple
    tan: tuple


class PathSampler:
    def __init__(self, wire: TopoDS_Wire):
        self.curve = BRepAdaptor_CompCurve(wire)
        self.u0 = self.curve.FirstParameter()
        self.u1 = self.curve.LastParameter()
        self.length = _length(self.curve)
        if self.length < 1e-9:
            raise CurveError("the path has zero length")
        self.closed = wire.Closed()

    def at(self, s: float):
        """(point, unit tangent) at arc length s."""
        if s <= 0:
            u = self.u0
        elif s >= self.length:
            u = self.u1
        else:
            ap = GCPnts_AbscissaPoint(self.curve, s, self.u0)
            u = ap.Parameter() if ap.IsDone() else self.u0 + (self.u1 - self.u0) * s / self.length
        p, v = gp_Pnt(), gp_Vec()
        self.curve.D1(u, p, v)
        if v.Magnitude() < 1e-12:  # a cusp: step a little
            self.curve.D1(min(self.u1, u + 1e-6 * (self.u1 - self.u0)), p, v)
        return (p.X(), p.Y(), p.Z()), unit((v.X(), v.Y(), v.Z()), "path tangent")

    def curvature_normal(self, s: float):
        u = self.u0 + (self.u1 - self.u0) * min(max(s / self.length, 0), 1)
        ap = GCPnts_AbscissaPoint(self.curve, s, self.u0) if 0 < s < self.length else None
        if ap is not None and ap.IsDone():
            u = ap.Parameter()
        p, v1, v2 = gp_Pnt(), gp_Vec(), gp_Vec()
        self.curve.D2(u, p, v1, v2)
        d1, d2 = (v1.X(), v1.Y(), v1.Z()), (v2.X(), v2.Y(), v2.Z())
        t = unit(d1, "path tangent")
        n = sub(d2, mul(t, dot(d2, t)))
        return t, (n if norm(n) > 1e-9 * max(1.0, norm(d2)) else None)


def start_frame(o, tan) -> Frame:
    up = (0.0, 0.0, 1.0) if abs(tan[2]) < 1 - 1e-6 else (0.0, 1.0, 0.0)
    up = unit(sub(up, mul(tan, dot(up, tan))))
    side = cross(up, tan)
    return Frame(o, side, up, tan)


def frames(path: PathSampler, n: int, mode: str) -> list[Frame]:
    """Frames at n+1 stations equally spaced along the path (t = i/n)."""
    sub_steps = 8
    m = n * sub_steps
    pts = [path.at(path.length * i / m) for i in range(m + 1)]
    f0 = start_frame(*pts[0])
    out = [f0]
    if mode == "FIXED":
        out = [Frame(o, f0.side, f0.up, f0.tan) for o, _ in pts]
    elif mode == "FRENET":
        out = []
        prev_up = f0.up
        for i, (o, t) in enumerate(pts):
            _, nrm = path.curvature_normal(path.length * i / m)
            if nrm is None:  # straight piece: carry the previous direction
                up = sub(prev_up, mul(t, dot(prev_up, t)))
                up = unit(up) if norm(up) > 1e-9 else prev_up
            else:
                up = unit(nrm)
            out.append(Frame(o, cross(up, t), up, t))
            prev_up = up
        _align_frenet(out, f0)
    else:  # MINTWIST: double-reflection rotation-minimizing frames
        for i in range(1, m + 1):
            (x0, t0), (x1, t1) = pts[i - 1], pts[i]
            prev = out[-1]
            v1 = sub(x1, x0)
            c1 = dot(v1, v1)
            if c1 < 1e-24:
                out.append(Frame(x1, prev.side, prev.up, t1))
                continue
            rl = sub(prev.up, mul(v1, 2 * dot(v1, prev.up) / c1))
            tl = sub(t0, mul(v1, 2 * dot(v1, t0) / c1))
            v2 = sub(t1, tl)
            c2 = dot(v2, v2)
            up = sub(rl, mul(v2, 2 * dot(v2, rl) / c2)) if c2 > 1e-24 else rl
            up = unit(sub(up, mul(t1, dot(up, t1))))
            out.append(Frame(x1, cross(up, t1), up, t1))
    return out[::sub_steps]


def _align_frenet(fs: list[Frame], f0: Frame) -> None:
    """Rotate every Frenet frame about its tangent by the angle that maps the
    first one onto the start frame, so the profile starts where it was drawn."""
    a = fs[0]
    ang = math.atan2(dot(cross(a.up, f0.up), a.tan), dot(a.up, f0.up))
    c, s = math.cos(ang), math.sin(ang)
    for i, f in enumerate(fs):
        up = add(mul(f.up, c), mul(cross(f.tan, f.up), s))
        fs[i] = Frame(f.o, cross(up, f.tan), up, f.tan)


# ---- placing a profile -------------------------------------------------------
def _to_local(f: Frame, p):
    d = sub(p, f.o)
    return (dot(d, f.side), dot(d, f.up), dot(d, f.tan))


def _station_matrix(f0: Frame, fi: Frame, twist_deg: float, sx: float, sy: float, ox: float, oy: float, sz: float = 1.0):
    """3x3 matrix M and vector b with p' = M p + b, mapping the start section to station i."""
    a = math.radians(twist_deg)
    c, s = math.cos(a), math.sin(a)
    # local (in f0 coords) -> scaled, turned, offset -> world via fi
    # L = R(twist) * diag(sx, sy, 1); world = fi.o + [side up tan]_i * (L * local + (ox, oy, 0))
    L = ((c * sx, -s * sy, 0.0), (s * sx, c * sy, 0.0), (0.0, 0.0, sz))
    Bi = (fi.side, fi.up, fi.tan)  # columns
    B0 = (f0.side, f0.up, f0.tan)  # rows of the inverse (orthonormal)
    # M = Bi * L * B0^T
    M = [[0.0] * 3 for _ in range(3)]
    for r in range(3):
        for col in range(3):
            v = 0.0
            for k in range(3):
                bik = Bi[k][r]
                for j in range(3):
                    v += bik * L[k][j] * B0[j][col]
            M[r][col] = v
    off = add(mul(fi.side, ox), mul(fi.up, oy))
    Mo = [sum(M[r][k] * f0.o[k] for k in range(3)) for r in range(3)]
    b = (fi.o[0] + off[0] - Mo[0], fi.o[1] + off[1] - Mo[1], fi.o[2] + off[2] - Mo[2])
    return M, b


def _det(M) -> float:
    return (M[0][0] * (M[1][1] * M[2][2] - M[1][2] * M[2][1]) - M[0][1] * (M[1][0] * M[2][2] - M[1][2] * M[2][0])
            + M[0][2] * (M[1][0] * M[2][1] - M[1][1] * M[2][0]))


def _apply(shape: TopoDS_Shape, M, b, similar: bool) -> TopoDS_Shape:
    if similar:
        # gp_Trsf.SetValues wants a pure rotation: split off the scale factor
        k = math.copysign(abs(_det(M)) ** (1 / 3), _det(M))
        R = [[v / k for v in row] for row in M]
        rot = gp_Trsf()
        rot.SetValues(R[0][0], R[0][1], R[0][2], b[0], R[1][0], R[1][1], R[1][2], b[1], R[2][0], R[2][1], R[2][2], b[2])
        sc = gp_Trsf()
        if abs(k - 1) > 1e-12:
            sc.SetScale(gp_Pnt(0, 0, 0), k)
        mk = BRepBuilderAPI_Transform(shape, rot.Multiplied(sc), True)
    else:
        g = gp_GTrsf()
        g.SetVectorialPart(gp_Mat(M[0][0], M[0][1], M[0][2], M[1][0], M[1][1], M[1][2], M[2][0], M[2][1], M[2][2]))
        g.SetTranslationPart(gp_XYZ(*b))
        mk = BRepBuilderAPI_GTransform(shape, g, True)
    return mk.Shape()


def _profile_points(wire: TopoDS_Wire, f0: Frame, n: int) -> list[tuple]:
    """n points evenly along a closed profile, in start-frame coords, counter-
    clockwise, starting at the point nearest the +side direction."""
    pc = PathSampler(wire)
    raw = [_to_local(f0, pc.at(pc.length * i / n)[0]) for i in range(n)]
    area = sum(raw[i][0] * raw[(i + 1) % n][1] - raw[(i + 1) % n][0] * raw[i][1] for i in range(n))
    if area < 0:
        raw = list(reversed(raw))
    cx = sum(q[0] for q in raw) / n
    cy = sum(q[1] for q in raw) / n
    # start at the point whose direction from the centroid is closest to angle 0
    k = min(range(n), key=lambda i: abs(math.atan2(raw[i][1] - cy, raw[i][0] - cx)))
    return raw[k:] + raw[:k]


# ---- public operations -------------------------------------------------------
def _heal(shape: TopoDS_Shape) -> TopoDS_Shape:
    """Small repairs OCCT's own sweeps sometimes need (for example the seam of
    a sweep round a closed path): rebuild the solid from its shell and fix."""
    from OCP.ShapeFix import ShapeFix_Shape, ShapeFix_Solid
    from OCP.TopAbs import TopAbs_SHELL

    ex = TopExp_Explorer(shape, TopAbs_SHELL)
    if ex.More() and shape.ShapeType() != TopAbs_SHELL:
        try:
            shape = ShapeFix_Solid().SolidFromShell((getattr(TopoDS, "Shell_s", None) or TopoDS.Shell)(ex.Current()))
        except Exception:  # noqa: BLE001 - keep the original and let the fixer try
            pass
    fx = ShapeFix_Shape(shape)
    fx.Perform()
    return fx.Shape()


def _check(shape: TopoDS_Shape, what: str) -> TopoDS_Shape:
    if shape.IsNull():
        raise CurveError(f"{what}: kernel returned nothing")
    if not BRepCheck_Analyzer(shape).IsValid():
        shape = _heal(shape)
    if not BRepCheck_Analyzer(shape).IsValid():
        raise CurveError(f"{what}: the result is not a valid shape (try fewer sections, or a smoother path)")
    return shape


def loft(wires: list[TopoDS_Wire], solid: bool = True, ruled: bool = False, closed: bool = False) -> TopoDS_Shape:
    if len(wires) < 2:
        raise CurveError("LOFT: give at least 2 sections")
    if solid and not all(w.Closed() for w in wires):
        solid = False
    seq = list(wires) + ([wires[0]] if closed else [])
    mk = BRepOffsetAPI_ThruSections(solid and not closed, ruled, 1e-6)
    mk.CheckCompatibility(True)
    for w in seq:
        mk.AddWire(w)
    mk.Build()
    if not mk.IsDone():
        raise CurveError("LOFT: the kernel could not fit a shape through these sections")
    shape = mk.Shape()
    if closed and solid:
        shape = _solid_from_shell(shape)
    return _check(shape, "LOFT")


def _solid_from_shell(shape: TopoDS_Shape) -> TopoDS_Shape:
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid, BRepBuilderAPI_Sewing
    from OCP.TopAbs import TopAbs_SHELL

    sew = BRepBuilderAPI_Sewing(1e-5)
    sew.Add(shape)
    sew.Perform()
    sewn = sew.SewedShape()
    ex = TopExp_Explorer(sewn, TopAbs_SHELL)
    if not ex.More():
        return shape
    mk = BRepBuilderAPI_MakeSolid((getattr(TopoDS, "Shell_s", None) or TopoDS.Shell)(ex.Current()))
    return mk.Solid() if mk.IsDone() else shape


def _set_mode(mk, ps: PathSampler, mode: str) -> None:
    if mode == "FRENET":
        mk.SetMode(True)
    elif mode == "FIXED":
        f0 = start_frame(*ps.at(0))
        mk.SetMode(gp_Ax2(gp_Pnt(*f0.o), gp_Dir(*f0.tan), gp_Dir(*f0.side)))
    else:
        mk.SetMode(False)  # corrected Frenet = minimal twist


def exact_sweep(profile: TopoDS_Wire, path: TopoDS_Wire, mode: str = "MINTWIST", solid: bool = True) -> TopoDS_Shape:
    mk = BRepOffsetAPI_MakePipeShell(path)
    _set_mode(mk, PathSampler(path), mode)
    mk.Add(profile, False, False)
    mk.Build()
    if not mk.IsDone():
        raise CurveError("SWEEP: the kernel could not sweep this profile along this path")
    if solid and profile.Closed():
        mk.MakeSolid()
    return _check(mk.Shape(), "SWEEP")


def auto_sections(ps: PathSampler, twist: Law, scales: tuple, n_profiles: int) -> int:
    """Enough sections for a smooth fit: one per 6 degrees of twist, one per 10
    degrees the path turns, more where the size changes, and a few per morph."""
    k = 40
    tw = [twist(i / k) for i in range(k + 1)]
    twist_total = sum(abs(b - a) for a, b in zip(tw, tw[1:]))
    tans = [ps.at(ps.length * i / (4 * k))[1] for i in range(4 * k + 1)]
    bend = sum(math.degrees(math.acos(max(-1.0, min(1.0, dot(a, b))))) for a, b in zip(tans, tans[1:]))
    size = 0.0
    for law in scales:
        v = [law(i / k) for i in range(k + 1)]
        size += sum(abs(math.log(max(b, 1e-9) / max(a, 1e-9))) for a, b in zip(v, v[1:]))
    n = 12 + twist_total / 6 + bend / 10 + size * 12 + 6 * (n_profiles - 1)
    return int(min(160, max(12, round(n))))


def law_sweep(profile: TopoDS_Wire, path: TopoDS_Wire, scale: Law, mode: str = "MINTWIST", solid: bool = True) -> TopoDS_Shape:
    """Exact sweep whose profile grows or shrinks by ``scale(t)`` (OCCT's
    evolution law). Robust on long, winding paths such as springs."""
    ps = PathSampler(path)
    k = 48
    arr = _ArrayPnt2d(1, k + 1)
    for i in range(k + 1):
        t = i / k
        v = scale(t)
        if v <= 1e-9:
            raise CurveError(f"SWEEP: the scale must stay above 0 (it is {v:g} at t = {t:g})")
        arr.SetValue(i + 1, gp_Pnt2d(ps.u0 + (ps.u1 - ps.u0) * t, v))
    law = Law_Interpol()
    law.Set(arr, False)
    mk = BRepOffsetAPI_MakePipeShell(path)
    _set_mode(mk, ps, mode)
    mk.SetLaw(profile, law, False, False)
    mk.Build()
    if not mk.IsDone():
        raise CurveError("SWEEP: the kernel could not sweep this profile along this path")
    if solid and profile.Closed():
        mk.MakeSolid()
    return _check(mk.Shape(), "SWEEP")


def section_sweep(
    profiles: list[TopoDS_Wire],
    path: TopoDS_Wire,
    twist: Law,
    scale: Law,
    sx: Law,
    sy: Law,
    ox: Law,
    oy: Law,
    mode: str = "MINTWIST",
    n: int = 0,
    solid: bool = True,
    stations: list[float] | None = None,
) -> tuple[TopoDS_Shape, int]:
    """Sweep with laws (functions of t in [0, 1]); several profiles morph.

    Returns the shape and the number of sections used.
    """
    ps = PathSampler(path)
    if n <= 0:
        n = auto_sections(ps, twist, (scale, sx, sy), len(profiles))
    if n < 2 or n > 400:
        raise CurveError("SWEEP: the number of sections must be from 2 to 400")
    fs = frames(ps, n, mode)
    f0 = fs[0]
    morph = len(profiles) > 1
    if morph:
        if not all(w.Closed() for w in profiles):
            raise CurveError("MORPH: all profiles must be closed")
        k = 64
        pts = [_profile_points(w, f0, k) for w in profiles]
        st = stations or [i / (len(profiles) - 1) for i in range(len(profiles))]
    sections = []
    for i, f in enumerate(fs):
        t = i / n
        s = scale(t)
        a, b = s * sx(t), s * sy(t)
        if a <= 1e-9 or b <= 1e-9:
            raise CurveError(f"SWEEP: the scale must stay above 0 (it is {min(a, b):g} at t = {t:g})")
        M, off = _station_matrix(f0, f, twist(t), a, b, ox(t), oy(t), s)
        if morph:
            j = max(0, min(len(st) - 2, next((q for q in range(len(st) - 1) if t <= st[q + 1] + 1e-12), len(st) - 2)))
            span = st[j + 1] - st[j]
            w = 0.0 if span <= 0 else min(1.0, max(0.0, (t - st[j]) / span))
            w = w * w * (3 - 2 * w)  # ease in and out at each profile
            loc = [add(mul(p, 1 - w), mul(q, w)) for p, q in zip(pts[j], pts[j + 1])]
            world = []
            for (u, v, z) in loc:
                pw = add(f0.o, add(mul(f0.side, u), add(mul(f0.up, v), mul(f0.tan, z))))
                world.append(tuple(sum(M[r][c] * pw[c] for c in range(3)) + off[r] for r in range(3)))
            sections.append(spline(world + [world[0]]))
        else:
            similar = abs(a - b) < 1e-12
            sections.append(_as_wire(_apply(profiles[0], M, off, similar)))
    closed_path = ps.closed and not morph and all(abs(fn(0) - fn(1)) < 1e-9 for fn in (scale, sx, sy, ox, oy)) \
        and abs((twist(1) - twist(0)) % 360) < 1e-9 and mode != "FIXED"
    if closed_path:
        sections = sections[:-1]
    shape = loft(sections, solid=solid, ruled=False, closed=closed_path)
    return shape, n
