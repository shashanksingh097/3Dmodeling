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
* ``FIXED``: the profile only translates, never turns;
* ``NORMAL`` (an :class:`OnSurface`): the profile keeps its angle to a
  surface the path lies on, turning with the surface's normal (a bead on a
  car body, a rib on a hull, a strip that stays flat on a dome).

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


class OnSurface:
    """Frame mode NORMAL: the profile's up direction follows the normal of a
    surface (one face or several) that the path lies on."""

    name = "NORMAL"

    def __init__(self, shape: TopoDS_Shape):
        from OCP.BRep import BRep_Tool
        from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED

        self.shape = shape
        self.faces = []
        ex = TopExp_Explorer(shape, TopAbs_FACE)
        while ex.More():
            f = (getattr(TopoDS, "Face_s", None) or TopoDS.Face)(ex.Current())
            self.faces.append((f, BRep_Tool.Surface_s(f), f.Orientation() == TopAbs_REVERSED))
            ex.Next()
        if not self.faces:
            raise CurveError("the NORMAL surface has no faces")

    def __eq__(self, other):
        return isinstance(other, OnSurface) and other.shape.IsSame(self.shape)

    def __hash__(self):
        return id(self.shape)

    def __str__(self):
        return self.name

    def nearest(self, q):
        """(distance, unit normal) of the surface point nearest q."""
        from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
        from OCP.GeomLProp import GeomLProp_SLProps

        best = None
        for f, srf, rev in self.faces:
            pj = GeomAPI_ProjectPointOnSurf(gp_Pnt(*q), srf)
            if not pj.NbPoints():
                continue
            d = pj.LowerDistance()
            if best is None or d < best[0]:
                best = (d, srf, rev, *pj.LowerDistanceParameters())
        if best is None:
            raise CurveError("the path is nowhere above the NORMAL surface")
        d, srf, rev, u, v = best
        pr = GeomLProp_SLProps(srf, u, v, 1, 1e-9)
        if not pr.IsNormalDefined():
            # a pole or a pinched edge: step inside a little
            pr = GeomLProp_SLProps(srf, u + 1e-6, v + 1e-6, 1, 1e-9)
        n = pr.Normal()
        n = (n.X(), n.Y(), n.Z())
        return d, (mul(n, -1.0) if rev else n)

    def exact_ok(self, path: TopoDS_Wire) -> bool:
        """Whether the kernel's exact sweep can follow this surface along the path: it needs the path
        to sit on the surface as curves on it (a PROJECT result does; a path drawn on its own may not)."""
        mk = BRepOffsetAPI_MakePipeShell(path)
        return bool(mk.SetMode(self.shape))

    def check(self, path: "PathSampler", k: int = 40) -> None:
        tol = 1e-3 * max(1.0, path.length)
        for i in range(k + 1):
            q = path.at(path.length * i / k)[0]
            d, _ = self.nearest(q)
            if d > tol:
                raise CurveError(f"the path must lie on the NORMAL surface, and it is {d:.3g} away from it at "
                                 f"t = {i / k:.3g}; lay it on first (PROJECT, path, surface)")


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


def frames(path: PathSampler, n: int, mode) -> list[Frame]:
    """Frames at n+1 stations equally spaced along the path (t = i/n)."""
    sub_steps = 8 if not isinstance(mode, OnSurface) else 1
    m = n * sub_steps
    pts = [path.at(path.length * i / m) for i in range(m + 1)]
    f0 = start_frame(*pts[0])
    out = [f0]
    if isinstance(mode, OnSurface):
        out = []
        prev = None
        for o, t in pts:
            _, nrm = mode.nearest(o)
            up = sub(nrm, mul(t, dot(nrm, t)))
            if norm(up) < 1e-9:  # the path runs straight into the surface here
                up = prev
            up = unit(up)
            out.append(Frame(o, cross(up, t), up, t))
            prev = up
        _align_frenet(out, f0)
    elif mode == "FIXED":
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


def wire_polygon(wire: TopoDS_Wire, n: int = 48) -> list[tuple]:
    """n points along a curve, evenly in its parameter (enough for the overlap tests)."""
    c = BRepAdaptor_CompCurve(wire)
    u0, u1 = c.FirstParameter(), c.LastParameter()
    out = []
    for i in range(n):
        p = c.Value(u0 + (u1 - u0) * i / n)
        out.append((p.X(), p.Y(), p.Z()))
    return out


def _fmt_t(t: float) -> str:
    return f"{t:.2f}".rstrip("0").rstrip(".") or "0"


def _fmt_p(p) -> str:
    size = max(1.0, max(abs(v) for v in p))
    return "(" + ", ".join(f"{(0.0 if abs(v) < 1e-9 * size else v) + 0.0:.3g}" for v in p) + ")"


def check_slices(polys: list, what: str, ts: list[float] | None = None, path: "PathSampler | None" = None,
                 closed: bool = False) -> None:
    """Raise CurveError when two sections of the shape touch: the shape would
    run into itself (see geometry/overlap.py). ``ts``/``path`` say where each
    section sits on a path, for the message; without them sections are
    numbered from 1 as the user gave them."""
    from . import overlap

    n = len(polys)
    skip = (lambda i, j: i == 0 and j == n - 1) if closed else None
    found = overlap.clashes(polys, skip=skip)
    if not found:
        return
    c = found[0]
    at = _fmt_p(c.where)
    A, B = overlap.Section(polys[c.i]), overlap.Section(polys[c.j])
    if ts is None and A.ok and B.ok and abs(float(A.n @ B.n)) > 1 - 1e-9 and abs(float((B.c - A.c) @ A.n)) < 1e-6 * (A.r + B.r):
        raise CurveError(f"{what}: sections {c.i + 1} and {c.j + 1} lie in the same plane, one over the other, so "
                         "the shape would have no thickness there. Move one of them along the shape.")
    if ts is None or path is None:
        raise CurveError(f"{what}: sections {c.i + 1} and {c.j + 1} cut through each other near {at}, so the "
                         "shape would pass through itself. Move them apart, or turn one so they do not cross.")
    ta, tb = ts[c.i], ts[c.j]
    sa, sb = ta * path.length, tb * path.length
    o, tan = path.at(sa)
    sec = overlap.Section(polys[c.i])
    if sec.ok and abs(float(sec.n @ tan)) < 0.2:
        raise CurveError(f"{what}: the profile lies along the path instead of across it (at t = {_fmt_t(ta)}), so the "
                         "shape would have no thickness. Draw the profile square to the path at its start.")
    reach = max(norm(sub(q, o)) for q in polys[c.i])
    gap = abs(sb - sa)
    if closed:
        gap = min(gap, path.length - gap)
    if gap <= math.pi * reach:  # neighbours: the path bends (or turns a corner) too tightly here
        k = 16
        tans = [path.at(sa + (sb - sa) * i / k)[1] for i in range(k + 1)]
        steps = [math.acos(max(-1.0, min(1.0, dot(a, b)))) for a, b in zip(tans, tans[1:])]
        turn = sum(steps)
        if max(steps, default=0.0) > math.radians(20):
            kk = max(range(len(steps)), key=lambda i: steps[i])
            tc = ta + (tb - ta) * (kk + 0.5) / k
            raise CurveError(f"{what}: the path has a sharp corner at t = {_fmt_t(tc)}, and the shape folds into "
                             "itself there. Round the corner (draw the path as a SPLINE, or put an ARC between the lines).")
        bend = gap / turn if turn > 1e-9 else float("inf")
        tm = (ta + tb) / 2
        raise CurveError(f"{what}: the shape runs into itself near t = {_fmt_t(tm)}: the path bends with a radius of "
                         f"about {bend:.3g} there, but the profile reaches {reach:.3g} from the path. Make the profile "
                         "smaller than the bend, or the bend gentler.")
    raise CurveError(f"{what}: the shape runs into itself: the part at t = {_fmt_t(ta)} meets the part at "
                     f"t = {_fmt_t(tb)} near {at}. The path comes back too close to itself for this profile.")


def check_section_curves(wires: list[TopoDS_Wire], what: str) -> None:
    """Each closed section must be a simple loop: a figure-of-eight cannot be filled."""
    from . import overlap

    for k, w in enumerate(wires):
        if not w.Closed():
            continue
        hit = overlap.self_crossing(wire_polygon(w, 96))
        if hit is not None:
            raise CurveError(f"{what}: section {k + 1} crosses itself near {_fmt_p(hit)}; a section must be a "
                             "simple loop (no figure-of-eight)")


def sweep_slices(profile: TopoDS_Wire, path: TopoDS_Wire, mode: str, scale: Law | None = None,
                 n: int = 0) -> tuple[list, list[float], "PathSampler", bool]:
    """Where an exact sweep's sections are: the profile carried along the path
    (with its scale law) at n+1 stations. For check_slices."""
    ps = PathSampler(path)
    if n <= 0:
        n = min(160, max(24, auto_sections(ps, lambda t: 0.0, (scale or (lambda t: 1.0),), 1)))
    fs = frames(ps, n, mode)
    f0 = fs[0]
    prof = wire_polygon(profile)
    polys, ts = [], []
    closed = ps.closed
    last = n if not closed else n - 1
    for i in range(last + 1):
        t = i / n
        k = scale(t) if scale is not None else 1.0
        M, b = _station_matrix(f0, fs[i], 0.0, k, k, 0.0, 0.0, k)
        polys.append([tuple(sum(M[r][c] * q[c] for c in range(3)) + b[r] for r in range(3)) for q in prof])
        ts.append(t)
    return polys, ts, ps, closed


def loft(wires: list[TopoDS_Wire], solid: bool = True, ruled: bool = False, closed: bool = False,
         what: str = "LOFT", ts: list[float] | None = None, path: "PathSampler | None" = None) -> TopoDS_Shape:
    """Loft through the wires. A solid loft is first checked for sections that
    cut through each other (``ts``/``path`` name them by place on a path)."""
    if len(wires) < 2:
        raise CurveError("LOFT: give at least 2 sections")
    if solid and not all(w.Closed() for w in wires):
        solid = False
    if solid:
        if ts is None:
            check_section_curves(wires, what)
            from . import overlap

            k = overlap.folds_back([wire_polygon(w) for w in wires])
            if k is not None:
                raise CurveError(f"{what}: the shape goes past section {k + 1} and comes back to it, so it would "
                                 "pass through itself. Give the sections in order along the shape.")
        check_slices([wire_polygon(w) for w in wires], what, ts, path, closed=closed or (path is not None and path.closed))
    seq = list(wires) + ([wires[0]] if closed else [])
    # A closed loft (it ends on its first section again) fails in
    # ThruSections now and then for the very same input: about half the runs
    # on a ring of three circles, depending on where things land in memory.
    # A failed run is simply tried again; open lofts have not shown this.
    for _attempt in range(12 if closed else 1):
        mk = BRepOffsetAPI_ThruSections(solid and not closed, ruled, 1e-6)
        mk.CheckCompatibility(True)
        for w in seq:
            mk.AddWire(w)
        mk.Build()
        if mk.IsDone():
            break
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
        # one face closed on itself (a ring lofted round a circle): sewing
        # hands back the bare face, but the loft's own shell is already closed
        ex = TopExp_Explorer(shape, TopAbs_SHELL)
        if not ex.More():
            return shape
    mk = BRepBuilderAPI_MakeSolid((getattr(TopoDS, "Shell_s", None) or TopoDS.Shell)(ex.Current()))
    if not mk.IsDone():
        return shape
    from OCP.BRepLib import BRepLib

    solid = mk.Solid()
    BRepLib.OrientClosedSolid_s(solid)  # outward faces, so the volume comes out positive
    return solid


def _set_mode(mk, ps: PathSampler, mode) -> None:
    if isinstance(mode, OnSurface):
        mode.check(ps)
        if not mk.SetMode(mode.shape):
            raise CurveError("the kernel cannot follow this surface's normal along this path")
    elif mode == "FRENET":
        mk.SetMode(True)
    elif mode == "FIXED":
        f0 = start_frame(*ps.at(0))
        mk.SetMode(gp_Ax2(gp_Pnt(*f0.o), gp_Dir(*f0.tan), gp_Dir(*f0.side)))
    else:
        mk.SetMode(False)  # corrected Frenet = minimal twist


def exact_sweep(profile: TopoDS_Wire, path: TopoDS_Wire, mode: str = "MINTWIST", solid: bool = True,
                what: str = "SWEEP") -> TopoDS_Shape:
    if solid and profile.Closed() and path.Closed():
        return _closed_path_sweep(profile, path, mode, None)
    if solid and profile.Closed():
        check_slices(*_slices_args(profile, path, mode, None, what))
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


def _closed_path_sweep(profile: TopoDS_Wire, path: TopoDS_Wire, mode: str, scale: Law | None) -> TopoDS_Shape:
    """A solid swept round a closed path (a ring, a knot). The exact sweep
    leaves two caps where the ends meet and comes out invalid, so this is a
    closed loft through sections along the path instead (within a percent of
    the exact volume on a trefoil knot)."""
    one, zero = (lambda t: 1.0), (lambda t: 0.0)
    shape, _ = section_sweep([profile], path, zero, scale or one, one, one, zero, zero, mode, 0, True)
    return shape


def _slices_args(profile, path, mode, scale, what):
    polys, ts, ps, closed = sweep_slices(profile, path, mode, scale)
    return polys, what, ts, ps, closed


def law_sweep(profile: TopoDS_Wire, path: TopoDS_Wire, scale: Law, mode: str = "MINTWIST", solid: bool = True,
              what: str = "SWEEP") -> TopoDS_Shape:
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
    if solid and profile.Closed() and path.Closed():
        return _closed_path_sweep(profile, path, mode, scale)
    if solid and profile.Closed():
        check_slices(*_slices_args(profile, path, mode, scale, what))
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
    if isinstance(mode, OnSurface):
        mode.check(ps)
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
    what = "MORPH" if morph else "SWEEP"
    shape = loft(sections, solid=solid, ruled=False, closed=closed_path, what=what,
                 ts=[i / n for i in range(len(sections))], path=ps)
    return shape, n


# ---- rails -------------------------------------------------------------------
# A rail is a curve the swept shape must follow. At each station along the
# path, the section plane (square to the path) cuts each rail in one point,
# and the profile is moved within that plane so the points it had on the rails
# at the start land on the rails again:
#
# * one rail: the profile turns about the path (and, with fit SCALE, grows or
#   shrinks evenly) so its rail point stays on the rail: a twisted handrail, a
#   ribbon round a post;
# * two rails: the profile turns, moves and scales evenly so it spans both
#   rails: a wing between its leading and trailing edges, a hull between keel
#   and deck line. A thickness law in t can thin it on top, square to the
#   line between the rails.
RAIL_FITS = ("SCALE", "TURN")


class _RailCut:
    """Where a rail crosses the section planes, found by walking along it."""

    def __init__(self, wire: TopoDS_Wire, name: str, samples: int = 600):
        self.ps = PathSampler(wire)
        self.name = name
        self.m = samples
        self.s = [self.ps.length * i / samples for i in range(samples + 1)]
        self.pts = [self.ps.at(s)[0] for s in self.s]
        self.last: int | None = None

    def point(self, f: Frame, t: float):
        tol = 1e-7 * max(1.0, self.ps.length)
        d = [dot(sub(q, f.o), f.tan) for q in self.pts]
        roots = []
        for i in range(self.m):
            if abs(d[i]) <= tol:
                roots.append((i, self.s[i], None))
            elif d[i] * d[i + 1] < 0:
                roots.append((i, None, (self.s[i], self.s[i + 1], d[i])))
        if abs(d[self.m]) <= tol:
            roots.append((self.m, self.s[self.m], None))
        if not roots:
            raise CurveError(f"{self.name} does not reach the section at t = {t:.3g} along the path; "
                             "make the rails run the whole length of the path")
        if self.last is None:  # the crossing nearest the path
            pick = min(roots, key=lambda r: norm(sub(self.pts[r[0]], f.o)))
        else:  # the crossing that carries on from the last one
            pick = min(roots, key=lambda r: abs(r[0] - self.last))
        self.last = pick[0]
        if pick[1] is not None:
            return self.ps.at(pick[1])[0]
        a, b, da = pick[2]
        for _ in range(50):
            mid = 0.5 * (a + b)
            dm = dot(sub(self.ps.at(mid)[0], f.o), f.tan)
            if (dm < 0) == (da < 0):
                a, da = mid, dm
            else:
                b = mid
        return self.ps.at(0.5 * (a + b))[0]


def _local2(f: Frame, q) -> tuple[float, float]:
    d = sub(q, f.o)
    return dot(d, f.side), dot(d, f.up)


def _rail_maps(path: PathSampler, fs: list[Frame], rails: list[_RailCut], fit: str, thick: Law):
    """For each frame: (A, c) with section coords p' = A p + c (2x2, 2-vector),
    taking the start section's coords to this station's."""
    pts = [[_local2(f, r.point(f, i / (len(fs) - 1))) for r in rails] for i, f in enumerate(fs)]
    g0 = pts[0][0]
    out = []
    if len(rails) == 1:
        r0 = math.hypot(*g0)
        if r0 < 1e-9:
            raise CurveError("the rail starts on the path itself; it must be off the path to steer the profile")
        a0 = math.atan2(g0[1], g0[0])
        for (g,) in pts:
            r = math.hypot(*g)
            if r < 1e-9:
                raise CurveError("the rail touches the path, so the profile cannot follow it there")
            k = r / r0 if fit == "SCALE" else 1.0
            th = math.atan2(g[1], g[0]) - a0
            c, s = math.cos(th), math.sin(th)
            out.append((((k * c, -k * s), (k * s, k * c)), (0.0, 0.0), k))
        return out, pts
    h0 = pts[0][1]
    e0 = (h0[0] - g0[0], h0[1] - g0[1])
    l0 = math.hypot(*e0)
    if l0 < 1e-9:
        raise CurveError("the two rails start at the same point")
    u0 = (e0[0] / l0, e0[1] / l0)  # along the line between the rails, at the start
    n0 = (-u0[1], u0[0])
    for i, (g, h) in enumerate(pts):
        e = (h[0] - g[0], h[1] - g[1])
        ln = math.hypot(*e)
        if ln < 1e-9:
            raise CurveError(f"the two rails meet at t = {i / (len(fs) - 1):.3g}; they must stay apart")
        k = ln / l0
        th = math.atan2(e[1], e[0]) - math.atan2(e0[1], e0[0])
        c, s = math.cos(th), math.sin(th)
        R = ((k * c, -k * s), (k * s, k * c))
        w = thick(i / (len(fs) - 1))
        if w <= 1e-9:
            raise CurveError(f"the thickness law must stay above 0 (it is {w:g} at t = {i / (len(fs) - 1):g})")
        # S = I + (w - 1) n0 n0^T thins the profile square to the rail line
        S = ((1 + (w - 1) * n0[0] * n0[0], (w - 1) * n0[0] * n0[1]),
             ((w - 1) * n0[1] * n0[0], 1 + (w - 1) * n0[1] * n0[1]))
        A = tuple(tuple(sum(R[r][k2] * S[k2][col] for k2 in range(2)) for col in range(2)) for r in range(2))
        cvec = (g[0] - (A[0][0] * g0[0] + A[0][1] * g0[1]), g[1] - (A[1][0] * g0[0] + A[1][1] * g0[1]))
        out.append((A, cvec, k if abs(w - 1) < 1e-12 else None))
    return out, pts


def _affine_station(f0: Frame, fi: Frame, A, cvec, sz: float):
    """3x3 M and b with world p' = M p + b: section coords at the start, mapped
    by A and shifted by c, placed in station frame fi."""
    L = ((A[0][0], A[0][1], 0.0), (A[1][0], A[1][1], 0.0), (0.0, 0.0, sz))
    Bi = (fi.side, fi.up, fi.tan)
    B0 = (f0.side, f0.up, f0.tan)
    M = [[sum(Bi[k][r] * L[k][j] * B0[j][col] for k in range(3) for j in range(3)) for col in range(3)]
         for r in range(3)]
    off = add(mul(fi.side, cvec[0]), mul(fi.up, cvec[1]))
    Mo = [sum(M[r][k] * f0.o[k] for k in range(3)) for r in range(3)]
    return M, tuple(fi.o[r] + off[r] - Mo[r] for r in range(3))


def rail_sweep(profile: TopoDS_Wire, path: TopoDS_Wire, rails: list[TopoDS_Wire], fit: str = "SCALE",
               thick: Law | None = None, n: int = 0, solid: bool = True) -> tuple[TopoDS_Shape, int]:
    """Sweep a profile along a path, steered by one or two rails (see above).

    Returns the shape and the number of sections used.
    """
    if not 1 <= len(rails) <= 2:
        raise CurveError("give one or two rails")
    if fit not in RAIL_FITS:
        raise CurveError(f"fit must be {' or '.join(RAIL_FITS)}")
    thick = thick or (lambda t: 1.0)
    ps = PathSampler(path)
    names = ["the rail"] if len(rails) == 1 else ["rail 1", "rail 2"]
    if n <= 0:  # a first look at 40 stations decides how many sections a smooth fit needs
        cuts = [_RailCut(w, nm) for w, nm in zip(rails, names)]
        coarse, _ = _rail_maps(ps, frames(ps, 40, "MINTWIST"), cuts, fit, thick)
        turn = [math.degrees(math.atan2(A[1][0], A[0][0])) for A, _, _ in coarse]
        size = [math.hypot(A[0][0], A[1][0]) for A, _, _ in coarse]

        def interp(vals):
            def f(t):
                x = min(max(t, 0.0), 1.0) * 40
                i = min(39, int(x))
                return vals[i] + (vals[i + 1] - vals[i]) * (x - i)
            return f

        n = auto_sections(ps, interp(turn), (interp(size), thick), 1) + 8
    if n < 2 or n > 400:
        raise CurveError("the number of sections must be from 2 to 400")
    cuts = [_RailCut(w, nm) for w, nm in zip(rails, names)]
    fs = frames(ps, n, "MINTWIST")
    maps, _ = _rail_maps(ps, fs, cuts, fit, thick)
    f0 = fs[0]
    sections = []
    for f, (A, cvec, k) in zip(fs, maps):
        similar = k is not None
        M, b = _affine_station(f0, f, A, cvec, k if similar else 1.0)
        sections.append(_as_wire(_apply(profile, M, b, similar)))
    return loft(sections, solid=solid and profile.Closed(), ruled=False, what="RAILSWEEP",
                ts=[i / n for i in range(len(sections))], path=ps), n


# ---- spine lofts ---------------------------------------------------------------
# A loft whose sections follow a curved centre line (the spine). Each section
# is drawn where it belongs along the spine. Its points are read in the spine's
# frame at that place, the points are blended smoothly from section to
# section (a cubic through all of them, so the side stays smooth through the
# middle sections too), and each blend is set back square to the spine at its
# own place. At a section's own station this gives back the section where it
# was drawn (as a smooth curve through 64 points of it).


def _station_of(fs: list[Frame], q) -> int:
    """Index of the fine frame whose plane passes nearest to point q."""
    best, bi = None, 0
    for i, f in enumerate(fs):
        d = sub(q, f.o)
        along = abs(dot(d, f.tan))
        score = along + 1e-3 * norm(d)  # in the plane, and near the spine
        if best is None or score < best:
            best, bi = score, i
    return bi


def _hermite(ts: list[float], vals: list[list[tuple]], t: float) -> list[tuple]:
    """Cubic (Catmull-Rom with uneven spacing) through ``vals`` at ``ts``."""
    n = len(ts)
    if n == 2:
        w = (t - ts[0]) / (ts[1] - ts[0])
        return [add(mul(a, 1 - w), mul(b, w)) for a, b in zip(vals[0], vals[1])]
    k = max(0, min(n - 2, next((q for q in range(n - 1) if t <= ts[q + 1] + 1e-12), n - 2)))

    def slope(i):
        lo, hi = max(0, i - 1), min(n - 1, i + 1)
        return [mul(sub(b, a), 1 / (ts[hi] - ts[lo])) for a, b in zip(vals[lo], vals[hi])]

    h = ts[k + 1] - ts[k]
    s = (t - ts[k]) / h
    h00, h10, h01, h11 = 2 * s**3 - 3 * s**2 + 1, s**3 - 2 * s**2 + s, -2 * s**3 + 3 * s**2, s**3 - s**2
    m0, m1 = slope(k), slope(k + 1)
    return [add(add(mul(p0, h00), mul(d0, h10 * h)), add(mul(p1, h01), mul(d1, h11 * h)))
            for p0, d0, p1, d1 in zip(vals[k], m0, vals[k + 1], m1)]


def spine_loft(sections: list[TopoDS_Wire], spine: TopoDS_Wire, mode: str = "MINTWIST", n: int = 0,
               solid: bool = True) -> tuple[TopoDS_Shape, int, list[float]]:
    """Loft through sections placed along a spine curve.

    Returns the shape, the number of loft sections used, and where each given
    section sits on the spine (t from 0 to 1), in spine order."""
    if len(sections) < 2:
        raise CurveError("SPINELOFT: give at least 2 sections")
    if not all(w.Closed() for w in sections):
        raise CurveError("SPINELOFT: all sections must be closed curves")
    ps = PathSampler(spine)
    fine = 800
    fs = frames(ps, fine, mode)
    placed = []
    for w in sections:
        pc = PathSampler(w)
        ring = [pc.at(pc.length * i / 48)[0] for i in range(48)]
        c = tuple(sum(q[k] for q in ring) / len(ring) for k in range(3))
        placed.append((_station_of(fs, c), w))
    placed.sort(key=lambda kv: kv[0])
    idx = [k for k, _ in placed]
    if len(set(idx)) != len(idx):
        raise CurveError("SPINELOFT: two sections sit at the same place on the spine")
    ts = [k / fine for k in idx]
    k_pts = 64
    local = [_profile_points(w, fs[k], k_pts) for k, w in placed]
    # how many loft sections: enough for the spine's bend between the ends
    turn = 0.0
    for a, b in zip(fs[idx[0]:idx[-1]], fs[idx[0] + 1:idx[-1] + 1]):
        turn += math.degrees(math.acos(max(-1.0, min(1.0, dot(a.tan, b.tan)))))
    if n <= 0:
        n = max(len(sections) - 1, int(math.ceil(turn / 6.0)), 4 * (len(sections) - 1))
        n = min(n, 120)
    if n < len(sections) - 1 or n > 400:
        raise CurveError(f"SPINELOFT: the number of sections must be from {len(sections) - 1} to 400")
    # stations: every given section, plus evenly spread ones in between
    stations = set(idx)
    for i in range(n + 1):
        stations.add(idx[0] + round((idx[-1] - idx[0]) * i / n))
    wires = []
    where = [k / fine for k in sorted(stations)]
    for k in sorted(stations):
        f = fs[k]
        loc = local[idx.index(k)] if k in idx else _hermite(ts, local, k / fine)
        world = [add(f.o, add(mul(f.side, u), add(mul(f.up, v), mul(f.tan, z)))) for (u, v, z) in loc]
        wires.append(spline(world + [world[0]]))
    shape = loft(wires, solid=solid, what="SPINELOFT", ts=where, path=ps)
    return shape, len(wires), ts


# ---- lofts with guide curves -------------------------------------------------
# A loft whose side must pass along guide curves. Every guide crosses every
# section. Each section is cut at the points where the guides cross it, and
# each piece between two guides gets the same number of points on every
# section, so a point's neighbours across the sections sit at the same place
# relative to the guides. Between sections each point column is a smooth
# cubic through the sections; a guide's own column is then replaced by the
# guide, and the columns between two guides are pulled along by a smooth blend
# of how far each guide moved them. Round closed sections the pull of each
# guide is first split into growing or shrinking the section about its
# centre (straight out from it) and a slide (the rest); those two are blended
# between the guides, so a section swells all round rather than shifting
# sideways. At the sections nothing moves (the guides
# cross the sections there), so the loft still passes through every section
# (as a smooth curve through its points) and runs exactly along every guide
# (through the station curves, which the loft fits).


class _Curve:
    """A section or guide as arc length -> point, with nearest-point lookup."""

    def __init__(self, wire: TopoDS_Wire, samples: int = 800):
        self.ps = PathSampler(wire)
        self.L = self.ps.length
        self.closed = wire.Closed()
        self.flip = False
        self.m = samples
        self._pts = [self.ps.at(self.L * i / samples)[0] for i in range(samples + 1)]

    def at(self, s: float):
        s = s % self.L if self.closed else min(max(s, 0.0), self.L)
        return self.ps.at(self.L - s if self.flip else s)[0]

    def locate(self, q) -> float:
        """Arc length (in this curve's own direction) of the point nearest q."""
        d = [norm(sub(p, q)) for p in self._pts]
        i = min(range(len(d)), key=d.__getitem__)
        h = self.L / self.m
        a, b = (i - 1) * h, (i + 1) * h
        if not self.closed:
            a, b = max(a, 0.0), min(b, self.L)
        g = (math.sqrt(5) - 1) / 2
        f = lambda s: norm(sub(self.ps.at(s % self.L if self.closed else s)[0], q))  # noqa: E731
        c, e = b - g * (b - a), a + g * (b - a)
        fc, fe = f(c), f(e)
        for _ in range(40):
            if fc < fe:
                b, e, fe = e, c, fc
                c = b - g * (b - a)
                fc = f(c)
            else:
                a, c, fc = c, e, fe
                e = a + g * (b - a)
                fe = f(e)
        s = 0.5 * (a + b)
        return s % self.L if self.closed else s


def _newell(c: _Curve, k: int = 64):
    pts = [c.ps.at(c.L * i / k)[0] for i in range(k)]
    n = [0.0, 0.0, 0.0]
    for p, q in zip(pts, pts[1:] + pts[:1]):
        n[0] += (p[1] - q[1]) * (p[2] + q[2])
        n[1] += (p[2] - q[2]) * (p[0] + q[0])
        n[2] += (p[0] - q[0]) * (p[1] + q[1])
    return tuple(n)


def _crossing(guide: TopoDS_Wire, section: TopoDS_Wire, gname: str, sname: str, size: float):
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    d = BRepExtrema_DistShapeShape(guide, section)
    d.Perform()
    if not d.IsDone() or d.NbSolution() == 0:
        raise CurveError(f"LOFT: could not find where {gname} meets {sname}")
    tol = max(1e-4, 1e-4 * size)
    if d.Value() > tol:
        raise CurveError(f"LOFT: {gname} misses {sname} by {d.Value():.3g}; every guide must pass through every "
                         "section")
    p = d.PointOnShape1(1)
    return (p.X(), p.Y(), p.Z())


def _smooth(w: float) -> float:
    return w * w * (3 - 2 * w)


def guide_loft(sections: list[TopoDS_Wire], guides: list[TopoDS_Wire], solid: bool = True, points: int = 96,
               per_span: int = 0) -> tuple[TopoDS_Shape, int]:
    """Loft through ``sections`` (in order) whose side runs along ``guides``.

    Returns the shape and the number of station curves the loft was fitted
    through."""
    if len(sections) < 2:
        raise CurveError("LOFT: give at least 2 sections")
    if not guides:
        raise CurveError("LOFT: give at least one guide curve after GUIDE")
    closed = sections[0].Closed()
    if any(w.Closed() != closed for w in sections):
        raise CurveError("LOFT: with guides the sections must be all closed or all open")
    secs = [_Curve(w) for w in sections]
    gds = [_Curve(w, 1200) for w in guides]
    size = max(c.L for c in secs + gds)
    nsec, ng = len(secs), len(gds)
    gnames = [f"guide {j + 1}" for j in range(ng)] if ng > 1 else ["the guide"]
    # orient the sections alike
    if closed:
        n0 = _newell(secs[0])
        for c in secs[1:]:
            c.flip = dot(_newell(c), n0) < 0
    else:
        for a, c in zip(secs, secs[1:]):
            s0, e0 = a.at(0), a.at(a.L)
            st, en = c.ps.at(0)[0], c.ps.at(c.L)[0]
            c.flip = norm(sub(en, s0)) + norm(sub(st, e0)) < norm(sub(st, s0)) + norm(sub(en, e0))
    # where each guide crosses each section: (arc length on the section, arc length on the guide)
    cross_s = [[0.0] * ng for _ in range(nsec)]
    cross_g = [[0.0] * ng for _ in range(nsec)]
    for i, (c, w) in enumerate(zip(secs, sections)):
        for j, (g, gw) in enumerate(zip(gds, guides)):
            q = _crossing(gw, w, gnames[j], f"section {i + 1}", size)
            s = c.locate(q)
            cross_s[i][j] = (c.L - s) % c.L if (c.flip and closed) else (c.L - s if c.flip else s)
            cross_g[i][j] = g.locate(q)
    for j in range(ng):
        col = [cross_g[i][j] for i in range(nsec)]
        steps = [b - a for a, b in zip(col, col[1:])]
        if all(st < 0 for st in steps):
            gds[j].flip = True
            for i in range(nsec):
                cross_g[i][j] = gds[j].L - cross_g[i][j]
        elif not all(st > 0 for st in steps):
            raise CurveError(f"LOFT: {gnames[j]} must cross the sections in the order they are given")
    # the guides' order round (or along) each section must be the same on all of them
    if closed:
        def order(i):
            base = cross_s[i][0]
            return sorted(range(ng), key=lambda j: (cross_s[i][j] - base) % secs[i].L)
    else:
        def order(i):
            return sorted(range(ng), key=lambda j: cross_s[i][j])
    gorder = order(0)
    for i in range(1, nsec):
        if order(i) != gorder:
            raise CurveError(f"LOFT: the guides cross section {i + 1} in a different order than section 1; "
                             "guides cannot cross each other")
    # break points on each section: (arc length, guide or None), as positions that only grow
    breaks = []
    for i, c in enumerate(secs):
        if closed:
            base = cross_s[i][gorder[0]]
            b = [(base + (cross_s[i][j] - base) % c.L, j) for j in gorder] + [(base + c.L, gorder[0])]
        else:
            b = [(cross_s[i][j], j) for j in gorder]
            if b[0][0] > 1e-6 * c.L:
                b.insert(0, (0.0, None))
            if b[-1][0] < c.L * (1 - 1e-6):
                b.append((c.L, None))
        breaks.append(b)
    nseg = len(breaks[0]) - 1
    frac = [sum((breaks[i][k + 1][0] - breaks[i][k][0]) / secs[i].L for i in range(nsec)) / nsec
            for k in range(nseg)]
    counts = [max(4, round(points * f)) for f in frac]
    # points of each section, segment by segment; the guide columns
    cols: list[int | None] = []
    seg_of: list[tuple[int, float]] = []  # per column: (segment, place within it 0..1)
    for k, cnt in enumerate(counts):
        for q in range(cnt):
            cols.append(breaks[0][k][1] if q == 0 else None)
            seg_of.append((k, q / cnt))
    if not closed:
        cols.append(breaks[0][-1][1])
        seg_of.append((nseg - 1, 1.0))
    P = []
    for i, c in enumerate(secs):
        row = []
        for k, cnt in enumerate(counts):
            a, b = breaks[i][k][0], breaks[i][k + 1][0]
            row += [c.at(a + (b - a) * q / cnt) for q in range(cnt)]
        if not closed:
            row.append(c.at(breaks[i][-1][0]))
        P.append(row)
    gcol = {j: cols.index(j) for j in range(ng)}
    # stations between the sections
    if per_span <= 0:
        turn = 0.0
        for g in gds:
            tans = [g.ps.at(g.L * i / 200)[1] for i in range(201)]
            turn = max(turn, sum(math.degrees(math.acos(max(-1.0, min(1.0, dot(a, b)))))
                                 for a, b in zip(tans, tans[1:])))
        per_span = int(min(24, max(6, math.ceil(turn / 8 / (nsec - 1)))))
    ts = list(range(nsec))
    wires, where = [], []
    total = per_span * (nsec - 1)
    for step in range(total + 1):
        v = step / per_span
        i = min(nsec - 2, int(v))
        w = v - i
        base = _hermite(ts, P, v)
        dev = {}
        for j in range(ng):
            g = gds[j]
            s = cross_g[i][j] + (cross_g[i + 1][j] - cross_g[i][j]) * w
            dev[j] = sub(g.at(s), base[gcol[j]])
        if closed:
            # round closed sections each guide sets how much the section grows or shrinks about its centre
            # there (its pull straight out from the centre), and the rest of its pull slides the points;
            # between two guides both blend smoothly, so the section swells all round, not only at the guides
            n = len(base)
            C = tuple(sum(q[c] for q in base) / n for c in range(3))
            grow, slide = {}, {}
            for j in range(ng):
                r = sub(base[gcol[j]], C)
                rr = dot(r, r)
                k = 1.0 + (dot(dev[j], r) / rr if rr > 1e-18 else 0.0)
                if k <= 0.05:
                    raise CurveError(f"LOFT: {gnames[j]} comes so close to the middle of the sections that they "
                                     "would shrink to nothing")
                grow[j], slide[j] = k, sub(dev[j], mul(r, k - 1.0))
            pts = []
            for col, (seg, f) in enumerate(seg_of):
                a, b = breaks[0][seg][1], breaks[0][seg + 1][1]
                w = _smooth(f)
                k = grow[a] * (1 - w) + grow[b] * w
                sl = add(mul(slide[a], 1 - w), mul(slide[b], w))
                pts.append(add(add(C, mul(sub(base[col], C), k)), sl))
            wires.append(spline(pts, closed=True))
            where.append(v / (nsec - 1))
            continue
        pts = []
        for col, (k, f) in enumerate(seg_of):
            a, b = breaks[0][k][1], breaks[0][k + 1][1]
            if a is None and b is None:
                corr = (0.0, 0.0, 0.0)
            elif a is None:
                corr = dev[b]
            elif b is None:
                corr = dev[a]
            else:
                s = _smooth(f)
                corr = add(mul(dev[a], 1 - s), mul(dev[b], s))
            pts.append(add(base[col], corr))
        wires.append(spline(pts, closed=closed))
        where.append(v / (nsec - 1))
    shape = loft(wires, solid=solid and closed, what="LOFT", ts=where)
    return shape, len(wires)
