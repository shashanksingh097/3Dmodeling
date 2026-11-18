"""Sketch splines as curves: where they are, where they cross other curves,
and how to cut one into pieces.

A sketch spline is the smooth curve OCCT draws through its points (S, K1,
K2 ... E; a closed one has no E and runs back to S). Positions along it are
given as a fraction of the way from S to E (0..1), or, for a closed spline,
as 0..360 round it, so the trim and split code can treat it like a line or
a circle.

Cutting a spline keeps the points it passes through on each piece (so
sizes and constraints on them carry over) and adds the cut point; a point
half way along each cut span keeps the piece close to the old shape.
"""

from __future__ import annotations

import math
from functools import lru_cache

from .sketch import Geo, Sketch, SketchError


# =============================================================================
# the curve
# =============================================================================

@lru_cache(maxsize=256)
def _curve(pts: tuple, closed: bool):
    from OCP.Geom2dAPI import Geom2dAPI_Interpolate
    from OCP.gp import gp_Pnt2d

    try:  # OCP 8
        from OCP.collections import HArray1_gp_Pnt2d as TColgp_HArray1OfPnt2d
    except ImportError:  # OCP 7
        from OCP.TColgp import TColgp_HArray1OfPnt2d

    arr = TColgp_HArray1OfPnt2d(1, len(pts))
    for i, (u, v) in enumerate(pts, 1):
        arr.SetValue(i, gp_Pnt2d(u, v))
    it = Geom2dAPI_Interpolate(arr, bool(closed), 1e-9)
    it.Perform()
    if not it.IsDone():
        raise SketchError("no smooth curve goes through these spline points (are two of them the same?)")
    return it.Curve()


def curve_through(pts, closed: bool):
    return _curve(tuple((float(u), float(v)) for u, v in pts), bool(closed))


def curve(sk: Sketch, g: Geo):
    """g's OCCT 2D curve (a B-spline in u, v)."""
    return curve_through(sk.spline_points(g), g.closed)


def _range(c):
    return c.FirstParameter(), c.LastParameter()


def period(g: Geo) -> float:
    """The span of positions along g: 1 for an open spline, 360 for a closed one."""
    return 360.0 if g.closed else 1.0


def at(sk: Sketch, g: Geo, p: float):
    """The point at position p along g (see the module notes)."""
    c = curve(sk, g)
    t0, t1 = _range(c)
    f = (p % 360.0) / 360.0 if g.closed else p
    q = c.Value(t0 + (t1 - t0) * f)
    return (q.X(), q.Y())


def tangent(sk: Sketch, g: Geo, p: float):
    """The unit direction of g at position p (the way it runs, S to E)."""
    from OCP.gp import gp_Pnt2d, gp_Vec2d

    c = curve(sk, g)
    t0, t1 = _range(c)
    f = (p % 360.0) / 360.0 if g.closed else p
    q, d = gp_Pnt2d(), gp_Vec2d()
    c.D1(t0 + (t1 - t0) * f, q, d)
    L = math.hypot(d.X(), d.Y()) or 1e-12
    return (d.X() / L, d.Y() / L)


def _foot(c, q):
    """(curve parameter, foot point) of the point of curve c nearest q."""
    from OCP.Geom2dAPI import Geom2dAPI_ProjectPointOnCurve
    from OCP.gp import gp_Pnt2d

    pr = Geom2dAPI_ProjectPointOnCurve(gp_Pnt2d(*q), c)
    t0, t1 = _range(c)
    best = None
    if pr.NbPoints() > 0:
        t = pr.LowerDistanceParameter()
        f = c.Value(t)
        best = (t, (f.X(), f.Y()))
    for t in (t0, t1):  # the projection skips the ends of an open curve
        f = c.Value(t)
        if best is None or math.dist(q, (f.X(), f.Y())) < math.dist(q, best[1]) - 1e-12:
            best = (t, (f.X(), f.Y()))
    return best


def param(sk: Sketch, g: Geo, q) -> float:
    """Where q (on or near g) is along g, as a position (see the module notes)."""
    c = curve(sk, g)
    t0, t1 = _range(c)
    t, _ = _foot(c, q)
    f = (t - t0) / ((t1 - t0) or 1e-12)
    return (f * 360.0) % 360.0 if g.closed else min(max(f, 0.0), 1.0)


def foot(sk: Sketch, g: Geo, q):
    return _foot(curve(sk, g), q)[1]


def distance(sk: Sketch, g: Geo, q) -> float:
    return math.dist(foot(sk, g, q), q)


def length(sk: Sketch, g: Geo) -> float:
    from OCP.Geom2dAdaptor import Geom2dAdaptor_Curve
    from OCP.GCPnts import GCPnts_AbscissaPoint

    return GCPnts_AbscissaPoint.Length_s(Geom2dAdaptor_Curve(curve(sk, g)))


def signed(pts_flat, closed: bool, q) -> float:
    """Distance of q from the spline through pts_flat (u1, v1, u2, v2 ...),
    plus on its left (seen running S to E): the ON-a-spline constraint."""
    from OCP.gp import gp_Pnt2d, gp_Vec2d

    pts = [(pts_flat[i], pts_flat[i + 1]) for i in range(0, len(pts_flat), 2)]
    try:
        c = curve_through(pts, closed)
    except SketchError:
        return math.dist(q, pts[0])
    t, f = _foot(c, q)
    p, d = gp_Pnt2d(), gp_Vec2d()
    c.D1(t, p, d)
    dx, dy = q[0] - f[0], q[1] - f[1]
    dist = math.hypot(dx, dy)
    cr = d.X() * dy - d.Y() * dx
    return dist if cr >= 0 else -dist


def end_direction(pts_flat, closed: bool, end: str):
    """The unit direction a spline leaves its end S (into the curve) or arrives at E."""
    from OCP.gp import gp_Pnt2d, gp_Vec2d

    pts = [(pts_flat[i], pts_flat[i + 1]) for i in range(0, len(pts_flat), 2)]
    try:
        c = curve_through(pts, closed)
    except SketchError:
        return (1.0, 0.0)
    t0, t1 = _range(c)
    p, d = gp_Pnt2d(), gp_Vec2d()
    c.D1(t0 if end == "S" else t1, p, d)
    L = math.hypot(d.X(), d.Y()) or 1e-12
    return (d.X() / L, d.Y() / L)


# =============================================================================
# where a spline crosses another curve
# =============================================================================

def geom2d(sk: Sketch, h: Geo, size: float):
    """h's carrier as an OCCT 2D curve: the line through a line (long enough
    to cross the whole sketch), the circle of an arc, the ellipse of an
    elliptical arc, a spline itself."""
    from OCP.Geom2d import Geom2d_Circle, Geom2d_Ellipse, Geom2d_Line, Geom2d_TrimmedCurve
    from OCP.gp import gp_Ax2d, gp_Circ2d, gp_Dir2d, gp_Elips2d, gp_Pnt2d

    if h.kind == "SPLINE":
        return curve(sk, h)
    if h.kind == "LINE":
        a, b = sk.pt(h.pts["S"]), sk.pt(h.pts["E"])
        if math.dist(a, b) < 1e-12:
            return None
        ln = Geom2d_Line(gp_Pnt2d(*a), gp_Dir2d(b[0] - a[0], b[1] - a[1]))
        return Geom2d_TrimmedCurve(ln, -size, size + math.dist(a, b))
    if h.kind in ("ARC", "CIRCLE"):
        return Geom2d_Circle(gp_Circ2d(gp_Ax2d(gp_Pnt2d(*sk.pt(h.pts["C"])), gp_Dir2d(1, 0)), sk.radius(h)))
    from . import ellipse as el

    c, ax, a, b = el.frame(sk, h)
    if b > a:  # OCCT wants the bigger radius first
        ax, a, b = (-ax[1], ax[0]), b, a
    return Geom2d_Ellipse(gp_Elips2d(gp_Ax2d(gp_Pnt2d(*c), gp_Dir2d(*ax)), a, max(b, 1e-9)))


def axis_curve(name: str, size: float):
    from OCP.Geom2d import Geom2d_Line, Geom2d_TrimmedCurve
    from OCP.gp import gp_Dir2d, gp_Pnt2d

    d = gp_Dir2d(1, 0) if name == "H" else gp_Dir2d(0, 1)
    return Geom2d_TrimmedCurve(Geom2d_Line(gp_Pnt2d(0, 0), d), -size, size)


def crossings(c1, c2, size: float) -> list[tuple[float, float]]:
    from OCP.Geom2dAPI import Geom2dAPI_InterCurveCurve

    if c1 is None or c2 is None:
        return []
    ic = Geom2dAPI_InterCurveCurve(c1, c2, 1e-9 * max(1.0, size))
    out: list[tuple[float, float]] = []
    for i in range(1, ic.NbPoints() + 1):
        q = ic.Point(i)
        q = (q.X(), q.Y())
        if all(math.dist(q, o) > 1e-7 * max(1.0, size) for o in out):
            out.append(q)
    return out


def hits(sk: Sketch, g: Geo, h: Geo) -> list[tuple[float, float]]:
    """Where g and h cross, one of them a spline (a spline's carrier is the
    spline itself)."""
    size = 10.0 * sk.extent()
    return crossings(geom2d(sk, g, size), geom2d(sk, h, size), size)


# =============================================================================
# cutting a spline into pieces
# =============================================================================

def _knots(sk: Sketch, g: Geo) -> list[tuple[float, str]]:
    """(position, role) of each point g passes through, in order."""
    roles = sorted(g.pts, key=lambda r: (r == "E", 0 if r == "S" else int(r[1:]) if r[0] == "K" else 0))
    c = curve(sk, g)
    t0, t1 = _range(c)
    from OCP.Geom2dAPI import Geom2dAPI_ProjectPointOnCurve
    from OCP.gp import gp_Pnt2d

    out = []
    n = len(roles)
    for i, r in enumerate(roles):
        if i == 0:
            f = 0.0
        elif r == "E":
            f = 1.0
        else:  # the interpolation runs through every point: find its parameter
            q = sk.pt(g.pts[r])
            pr = Geom2dAPI_ProjectPointOnCurve(gp_Pnt2d(*q), c)
            if pr.NbPoints() > 0:
                f = (pr.LowerDistanceParameter() - t0) / ((t1 - t0) or 1e-12)
            else:
                f = i / max(1, n - (0 if g.closed else 1))
        out.append((f * 360.0 if g.closed else f, r))
    return out


def pieces(sk: Sketch, g: Geo, ranges: list[tuple[float, float]], uid: int = 0) -> tuple[list[Geo], dict, list[int]]:
    """Cut spline g to the given position ranges (lo < hi; a closed spline's
    may run past 360). The first range stays spline g, the others become new
    splines. Points of g inside a range move to that piece (their constraints
    follow); points in no range are dropped.

    Returns (the pieces, {old role: new "n.role"} for the points that moved,
    the x indices of points no piece kept)."""
    knots = _knots(sk, g)
    old_idx = set(g.pts.values())
    per = period(g)
    span_eps = 1e-7 * per
    c_old = curve(sk, g)
    t0, t1 = _range(c_old)

    def value(p):
        f = (p % 360.0) / 360.0 if g.closed else p
        q = c_old.Value(t0 + (t1 - t0) * f)
        return (q.X(), q.Y())

    # every piece's points as (value, x index or None, old role or None)
    used: set[str] = set()  # a point of g goes to one piece only

    def knot_at(p):
        """The point of g at position p, if there is one there (and still free)."""
        for q, r in knots:
            for wrap in ((0.0, 360.0, 720.0) if g.closed else (0.0,)):
                if abs(q + wrap - p) <= span_eps and r not in used:
                    return r
        return None

    plans = []
    for lo, hi in ranges:
        inside = []
        for wrap in ((0.0, 360.0, 720.0) if g.closed else (0.0,)):
            for p, r in knots:
                if lo + span_eps < p + wrap < hi - span_eps:
                    inside.append((p + wrap, r))
        inside.sort()
        r_lo = knot_at(lo)
        if r_lo:
            used.add(r_lo)
        used.update(r for _, r in inside)
        r_hi = knot_at(hi)
        if r_hi:
            used.add(r_hi)
        seq = [(lo, r_lo)] + inside + [(hi, r_hi)]
        # an extra point half way along a span that a cut shortened keeps the shape
        pts = []
        for i, (p, r) in enumerate(seq):
            if i > 0 and ((i == 1 and seq[0][1] is None) or (i == len(seq) - 1 and r is None)):
                if p - seq[i - 1][0] > 1e-3 * per:
                    pts.append((value(0.5 * (seq[i - 1][0] + p)), None, None))
            pts.append((value(p), g.pts[r] if r is not None else None, r))
        if math.dist(pts[0][0], pts[-1][0]) < 1e-9 * max(1.0, sk.extent()) and len(pts) < 3:
            raise SketchError(f"a piece of spline {g.n} would be too short")
        plans.append(pts)

    moved: dict[str, str] = {}
    out: list[Geo] = []
    kept: set[int] = set()
    for i, pts in enumerate(plans):
        roles = ["S"] + [f"K{k}" for k in range(1, len(pts) - 1)] + ["E"]
        idxs = []
        for (v, idx, r), role in zip(pts, roles):
            if idx is None:
                idx = sk._new_point(*v)
            else:
                sk.x[idx], sk.x[idx + 1] = float(v[0]), float(v[1])
            idxs.append(idx)
            kept.add(idx)
        if i == 0:
            piece = g
            g.pts = dict(zip(roles, idxs))
            g.closed = False
        else:
            piece = sk._geo("SPLINE", dict(zip(roles, idxs)), construction=g.construction)
            piece.closed = False
        for (v, idx, r), role in zip(pts, roles):
            if r is not None:
                moved[r] = f"{piece.n}.{role}"
        out.append(piece)
    gone = sorted(old_idx - kept)
    return out, moved, gone


def from_points(sk: Sketch, pts: list, uid: int = 0, construction: bool = False) -> Geo:
    """A new open spline through pts (u, v pairs)."""
    return sk.add_spline(list(pts), False, uid, construction)


def offset_point(pts_flat, closed: bool, f: float, off: float):
    """The point ``off`` to the left (seen running S to E) of the spline through
    pts_flat at fraction f (0..1 of the way along, or round for a closed one):
    the SOFFSET-of-a-spline constraint."""
    from OCP.gp import gp_Pnt2d, gp_Vec2d

    pts = [(pts_flat[i], pts_flat[i + 1]) for i in range(0, len(pts_flat), 2)]
    c = curve_through(pts, closed)
    t0, t1 = _range(c)
    p, d = gp_Pnt2d(), gp_Vec2d()
    c.D1(t0 + (t1 - t0) * f, p, d)
    L = math.hypot(d.X(), d.Y()) or 1e-12
    return (p.X() - d.Y() / L * off, p.Y() + d.X() / L * off)


def offset_samples(sk: Sketch, g: Geo, f0: float, f1: float, off: float) -> tuple[list[float], list]:
    """Fractions from f0 to f1 and the points ``off`` to the left of g there:
    the points a spline's offset is drawn through (two per span of g, at
    least eight spans), so it follows g closely."""
    n = max(8, 2 * (len(g.pts) - (0 if g.closed else 1)))
    if g.closed and f1 <= f0:
        f1 += 1.0
    fs = [f0 + (f1 - f0) * i / n for i in range(n + 1)]
    flat = [x for q in sk.spline_points(g) for x in q]
    return fs, [offset_point(flat, g.closed, f % 1.0 if g.closed else f, off) for f in fs]


def fraction(sk: Sketch, g: Geo, q) -> float:
    """Where q (on or beside g) is along g, as a fraction 0..1."""
    p = param(sk, g, q)
    return p / 360.0 if g.closed else p
