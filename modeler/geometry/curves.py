"""Curves and profiles as OCCT wires.

Paths (curves to sweep along) and profiles (closed sections) are plain
``TopoDS_Wire`` shapes, so they live in the model as ordinary bodies.

Profiles are drawn in a local plane given by an origin and a normal:

* normal +Z: the profile's X is world X and its Y is world Y;
* any other normal: the profile's X is horizontal (world Z x normal) and its
  Y points as far up (+Z) as the plane allows. For normal +X that makes
  profile X = world Y and profile Y = world Z.

An extra angle turns the profile in its plane.
"""

from __future__ import annotations

import math
from typing import Callable, Sequence

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeWire
from OCP.GC import GC_MakeArcOfCircle
from OCP.GeomAPI import GeomAPI_Interpolate
from OCP.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Elips, gp_Pnt, gp_Vec
from OCP.TopoDS import TopoDS_Wire

try:  # OCP 8
    from OCP.collections import HArray1_gp_Pnt as _HArrayPnt
except ImportError:  # OCP 7.x
    from OCP.TColgp import TColgp_HArray1OfPnt as _HArrayPnt  # type: ignore[no-redef]
try:  # OCP 8
    from OCP.collections import Array1_gp_Vec as _ArrayVec
    from OCP.collections import HArray1_bool as _HArrayBool
except ImportError:  # OCP 7.x
    from OCP.TColgp import TColgp_Array1OfVec as _ArrayVec  # type: ignore[no-redef]
    from OCP.TColStd import TColStd_HArray1OfBoolean as _HArrayBool  # type: ignore[no-redef]

Point = Sequence[float]


class CurveError(Exception):
    """Bad input for a curve or profile (the message is shown to the user)."""


# ---- small vector helpers (plain tuples, no numpy needed) ------------------
def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def mul(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(a):
    return math.sqrt(dot(a, a))


def unit(a, what="direction"):
    n = norm(a)
    if n < 1e-12:
        raise CurveError(f"the {what} cannot be (0, 0, 0)")
    return (a[0] / n, a[1] / n, a[2] / n)


def plane_axes(normal: Point, angle_deg: float = 0.0):
    """(x_dir, y_dir, z_dir) of a profile plane, by the rule in the module doc."""
    z = unit(tuple(normal), "normal")
    if abs(z[2]) > 1 - 1e-9:
        x = (1.0, 0.0, 0.0)
    else:
        x = unit(cross((0.0, 0.0, 1.0), z))
    y = cross(z, x)
    if angle_deg:
        a = math.radians(angle_deg)
        c, s = math.cos(a), math.sin(a)
        x, y = add(mul(x, c), mul(y, s)), add(mul(x, -s), mul(y, c))
    return x, y, z


def _pnt(p: Point) -> gp_Pnt:
    return gp_Pnt(float(p[0]), float(p[1]), float(p[2]))


def _wire_of_edges(edges) -> TopoDS_Wire:
    mk = BRepBuilderAPI_MakeWire()
    for e in edges:
        mk.Add(e)
    if not mk.IsDone():
        raise CurveError("the pieces do not join into one curve")
    return mk.Wire()


def _distinct(points: list[Point], what: str) -> None:
    for a, b in zip(points, points[1:]):
        if norm(sub(a, b)) < 1e-9:
            raise CurveError(f"{what}: two points in a row are the same ({a[0]:g}, {a[1]:g}, {a[2]:g})")


# ---- paths -------------------------------------------------------------------
def line(a: Point, b: Point) -> TopoDS_Wire:
    if norm(sub(a, b)) < 1e-9:
        raise CurveError("LINE: the two ends are the same point")
    return _wire_of_edges([BRepBuilderAPI_MakeEdge(_pnt(a), _pnt(b)).Edge()])


def arc3(a: Point, b: Point, c: Point) -> TopoDS_Wire:
    if norm(cross(sub(b, a), sub(c, a))) < 1e-9:
        raise CurveError("ARC: the three points are on one line")
    curve = GC_MakeArcOfCircle(_pnt(a), _pnt(b), _pnt(c)).Value()
    return _wire_of_edges([BRepBuilderAPI_MakeEdge(curve).Edge()])


def polyline(points: list[Point], closed: bool = False) -> TopoDS_Wire:
    if len(points) < 2:
        raise CurveError("POLYLINE: give at least 2 points")
    _distinct(points, "POLYLINE")
    mk = BRepBuilderAPI_MakePolygon()
    for q in points:
        mk.Add(_pnt(q))
    if closed:
        if len(points) < 3:
            raise CurveError("POLYLINE: a closed polyline needs at least 3 points")
        mk.Close()
    if not mk.IsDone():
        raise CurveError("POLYLINE: kernel failed")
    return mk.Wire()


def spline(points: list[Point], closed: bool = False, tol: float = 1e-7) -> TopoDS_Wire:
    """Smooth B-spline through the points (closed = periodic)."""
    if len(points) < 2 or (closed and len(points) < 3):
        raise CurveError("SPLINE: give at least 2 points (3 for a closed one)")
    _distinct(points + ([points[0]] if closed else []), "SPLINE")
    arr = _HArrayPnt(1, len(points))
    for i, q in enumerate(points, 1):
        arr.SetValue(i, _pnt(q))
    interp = GeomAPI_Interpolate(arr, closed, tol)
    interp.Perform()
    if not interp.IsDone():
        raise CurveError("SPLINE: could not fit a curve through these points")
    return _wire_of_edges([BRepBuilderAPI_MakeEdge(interp.Curve()).Edge()])


def sampled(fn: Callable[[float], Point], t0: float, t1: float, n: int, closed: bool = False) -> TopoDS_Wire:
    """B-spline through n+1 samples of fn(t) on [t0, t1]."""
    pts = [tuple(fn(t0 + (t1 - t0) * i / n)) for i in range(n + 1)]
    if closed:
        if norm(sub(pts[0], pts[-1])) > 1e-6 * max(1.0, norm(sub(pts[0], pts[n // 2]))):
            raise CurveError("the curve does not end where it starts, so it cannot be closed")
        pts = pts[:-1]
    return spline(pts, closed)


def helix(origin: Point, axis: Point, r: float, pitch: float, turns: float, taper_deg: float = 0.0,
          left: bool = False, pitch_law: Callable[[float], float] | None = None) -> TopoDS_Wire:
    """Helix around ``axis`` starting on the profile-X side of the axis.

    The radius grows by tan(taper) per unit of height; ``pitch_law(t)``
    (t from 0 to 1) multiplies the pitch locally, for variable-pitch springs.
    """
    if r <= 0 or pitch <= 0 or turns <= 0:
        raise CurveError("HELIX: radius, pitch and turns must be positive")
    x, y, z = plane_axes(axis)
    k = math.tan(math.radians(taper_deg))
    n = max(12, int(math.ceil(turns * 24)))
    # height as the integral of the local pitch over the angle
    heights = [0.0]
    for i in range(1, n + 1):
        tm = (i - 0.5) / n
        lp = pitch * (pitch_law(tm) if pitch_law else 1.0)
        if lp <= 0:
            raise CurveError("HELIX: the pitch law must stay positive")
        heights.append(heights[-1] + lp * turns / n)
    pts = []
    sign = -1.0 if left else 1.0
    for i in range(n + 1):
        a = sign * 2 * math.pi * turns * i / n
        h = heights[i]
        rr = r + k * h
        if rr <= 0:
            raise CurveError("HELIX: the taper makes the radius reach zero")
        p = add(origin, add(mul(x, rr * math.cos(a)), add(mul(y, rr * math.sin(a)), mul(z, h))))
        pts.append(p)
    return spline(pts)


# ---- profiles (closed, on a plane) -------------------------------------------
def _local(origin, axes, u, v):
    x, y, _ = axes
    return add(origin, add(mul(x, u), mul(y, v)))


def circle(origin: Point, r: float, normal: Point = (0, 0, 1), angle: float = 0.0) -> TopoDS_Wire:
    if r <= 0:
        raise CurveError("CIRCLE: radius must be positive")
    x, _, z = plane_axes(normal, angle)
    c = gp_Circ(gp_Ax2(_pnt(origin), gp_Dir(*z), gp_Dir(*x)), r)
    return _wire_of_edges([BRepBuilderAPI_MakeEdge(c).Edge()])


def ellipse(origin: Point, a: float, b: float, normal: Point = (0, 0, 1), angle: float = 0.0) -> TopoDS_Wire:
    """Ellipse with semi-axis a along profile X and b along profile Y."""
    if a <= 0 or b <= 0:
        raise CurveError("ELLIPSE: both semi-axes must be positive")
    if abs(a - b) < 1e-12:
        return circle(origin, a, normal, angle)
    x, y, z = plane_axes(normal, angle)
    if a < b:  # OCCT needs major >= minor; turn the frame instead
        x, y, a, b = y, mul(x, -1.0), b, a
    e = gp_Elips(gp_Ax2(_pnt(origin), gp_Dir(*z), gp_Dir(*x)), a, b)
    return _wire_of_edges([BRepBuilderAPI_MakeEdge(e).Edge()])


def _rounded_polygon(origin, axes, pts2d: list[tuple[float, float]], r: float, what: str) -> TopoDS_Wire:
    """Closed polygon in the plane, corners rounded with radius r (0 = sharp)."""
    pts = [_local(origin, axes, u, v) for u, v in pts2d]
    if r <= 0:
        return polyline(pts, closed=True)
    n = len(pts)
    edges = []
    tangent_pts = []
    for i in range(n):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
        d0, d1 = unit(sub(p0, p1)), unit(sub(p2, p1))
        half = math.acos(max(-1.0, min(1.0, dot(d0, d1)))) / 2
        cut = r / math.tan(half)
        if cut * 2 > min(norm(sub(p0, p1)), norm(sub(p2, p1))) + 1e-9:
            raise CurveError(f"{what}: the corner radius is too big for the sides")
        a, b = add(p1, mul(d0, cut)), add(p1, mul(d1, cut))
        bis = unit(add(d0, d1))
        mid = add(p1, mul(bis, r / math.sin(half) - r))
        tangent_pts.append((a, mid, b))
    for i in range(n):
        a, mid, b = tangent_pts[i]
        edges.append(BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(_pnt(a), _pnt(mid), _pnt(b)).Value()).Edge())
        nxt = tangent_pts[(i + 1) % n][0]
        if norm(sub(nxt, b)) > 1e-9:
            edges.append(BRepBuilderAPI_MakeEdge(_pnt(b), _pnt(nxt)).Edge())
    return _wire_of_edges(edges)


def rect(origin: Point, w: float, h: float, r: float = 0.0, normal: Point = (0, 0, 1), angle: float = 0.0) -> TopoDS_Wire:
    """w by h rectangle centered on origin (w along profile X)."""
    if w <= 0 or h <= 0 or r < 0:
        raise CurveError("RECT: width and height must be positive, radius >= 0")
    if 2 * r > min(w, h) + 1e-12:
        raise CurveError("RECT: the corner radius is more than half the shorter side")
    if abs(2 * r - min(w, h)) < 1e-9:
        r = min(w, h) / 2 - 1e-6
    hw, hh = w / 2, h / 2
    return _rounded_polygon(origin, plane_axes(normal, angle), [(hw, -hh), (hw, hh), (-hw, hh), (-hw, -hh)], r, "RECT")


def polygon(origin: Point, radius: float, sides: int, normal: Point = (0, 0, 1), angle: float = 0.0,
            corner: float = 0.0) -> TopoDS_Wire:
    """Regular polygon with its corners on a circle of ``radius``, first corner on profile X."""
    if radius <= 0 or sides < 3:
        raise CurveError("POLYGON: radius must be positive and sides >= 3")
    pts = [(radius * math.cos(2 * math.pi * i / sides), radius * math.sin(2 * math.pi * i / sides)) for i in range(sides)]
    return _rounded_polygon(origin, plane_axes(normal, angle), pts, corner, "POLYGON")


def star(origin: Point, r_out: float, r_in: float, points: int, normal: Point = (0, 0, 1), angle: float = 0.0) -> TopoDS_Wire:
    if not r_out > r_in > 0 or points < 3:
        raise CurveError("STAR: need outer radius > inner radius > 0 and at least 3 points")
    pts = []
    for i in range(2 * points):
        rr = r_out if i % 2 == 0 else r_in
        a = math.pi * i / points
        pts.append((rr * math.cos(a), rr * math.sin(a)))
    return _rounded_polygon(origin, plane_axes(normal, angle), pts, 0.0, "STAR")


def slot(origin: Point, length: float, width: float, normal: Point = (0, 0, 1), angle: float = 0.0) -> TopoDS_Wire:
    """Stadium shape: overall length along profile X, width along profile Y."""
    if not length > width > 0:
        raise CurveError("SLOT: need length > width > 0")
    axes = plane_axes(normal, angle)
    r, hl = width / 2, length / 2 - width / 2
    p = lambda u, v: _pnt(_local(origin, axes, u, v))  # noqa: E731
    e = [
        BRepBuilderAPI_MakeEdge(p(-hl, -r), p(hl, -r)).Edge(),
        BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(p(hl, -r), p(hl + r, 0), p(hl, r)).Value()).Edge(),
        BRepBuilderAPI_MakeEdge(p(hl, r), p(-hl, r)).Edge(),
        BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(p(-hl, r), p(-hl - r, 0), p(-hl, -r)).Value()).Edge(),
    ]
    return _wire_of_edges(e)


def naca4_points(code: str, chord: float, n: int = 40) -> list[tuple[float, float]]:
    """Closed NACA 4-digit outline (u along the chord from the leading edge, v up).

    Points run from the trailing edge over the upper side to the leading edge
    and back along the lower side; the trailing edge is closed to a point.
    """
    code = code.strip()
    if len(code) != 4 or not code.isdigit():
        raise CurveError(f"AIRFOIL: {code!r} is not a NACA 4-digit code such as 2412 or 0012")
    m, p, t = int(code[0]) / 100, int(code[1]) / 10, int(code[2:]) / 100
    if t <= 0:
        raise CurveError("AIRFOIL: thickness (last two digits) must be above 0")
    if m > 0 and not 0 < p < 1:
        raise CurveError("AIRFOIL: a cambered airfoil needs a camber position digit from 1 to 9")

    def yt(x):  # closed trailing edge variant (-0.1036)
        return 5 * t * (0.2969 * math.sqrt(x) - 0.1260 * x - 0.3516 * x**2 + 0.2843 * x**3 - 0.1036 * x**4)

    def camber(x):
        if m == 0:
            return 0.0, 0.0
        if x < p:
            return m / p**2 * (2 * p * x - x * x), 2 * m / p**2 * (p - x)
        return m / (1 - p) ** 2 * ((1 - 2 * p) + 2 * p * x - x * x), 2 * m / (1 - p) ** 2 * (p - x)

    xs = [(1 - math.cos(math.pi * i / n)) / 2 for i in range(n + 1)]  # cosine spacing, 0..1
    upper, lower = [], []
    for x in xs:
        yc, dyc = camber(x)
        th = math.atan(dyc)
        y = yt(x)
        upper.append((x - y * math.sin(th), yc + y * math.cos(th)))
        lower.append((x + y * math.sin(th), yc - y * math.cos(th)))
    pts = list(reversed(upper)) + lower[1:-1]  # TE -> upper -> LE -> lower (TE not repeated)
    return [(u * chord, v * chord) for u, v in pts]


def airfoil(origin: Point, chord: float, code: str, normal: Point = (0, 0, 1), angle: float = 0.0,
            pivot: float = 0.25) -> TopoDS_Wire:
    """NACA 4-digit airfoil. The chord runs along profile X; ``pivot`` (a fraction
    of the chord, default the quarter chord) sits on ``origin``, so twisting the
    profile turns it about that point."""
    if chord <= 0:
        raise CurveError("AIRFOIL: chord must be positive")
    axes = plane_axes(normal, angle)
    pts2 = naca4_points(code, chord)
    pts = [_local(origin, axes, u - pivot * chord, v) for u, v in pts2]
    # two smooth curves, upper and lower, joined tangent at the nose and
    # sharp at the trailing edge. (One closed curve with a cusp looks the same
    # but breaks OCCT's volume integration.)
    le = min(range(len(pts2)), key=lambda i: pts2[i][0])
    nose = unit(sub(pts[le + 1], pts[le - 1]))
    upper = _interp(pts[: le + 1], end=nose)
    lower = _interp(pts[le:] + [pts[0]], start=nose)
    return _wire_of_edges([upper, lower])


def _interp(points: list[Point], start: Point | None = None, end: Point | None = None):
    """Edge through points; optionally tangent to a direction at one end."""
    arr = _HArrayPnt(1, len(points))
    for i, q in enumerate(points, 1):
        arr.SetValue(i, _pnt(q))
    interp = GeomAPI_Interpolate(arr, False, 1e-7)
    tans = _ArrayVec(1, len(points))
    flags = _HArrayBool(1, len(points))
    for i in range(1, len(points) + 1):
        tans.SetValue(i, gp_Vec(1, 0, 0))
        flags.SetValue(i, False)
    for idx, d in ((1, start), (len(points), end)):
        if d is not None:
            tans.SetValue(idx, gp_Vec(*d))
            flags.SetValue(idx, True)
    interp.Load(tans, flags)
    interp.Perform()
    if not interp.IsDone():
        raise CurveError("could not fit a curve through the airfoil points")
    return BRepBuilderAPI_MakeEdge(interp.Curve()).Edge()
