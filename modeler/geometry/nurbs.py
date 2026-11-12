"""NURBS curves and surfaces: control points, weights, knots, and editing them.

A NURBS curve body is a wire of one edge whose curve is a B-spline; a NURBS
surface body is one face on a B-spline surface, bounded by the surface's own
edges (not trimmed). Any other curve or face can still be edited: a line, an
arc or a cylinder face is first turned into its exact B-spline, and a curve
made of several pieces is rebuilt into one with ``rebuild_curve``.

Editing never changes a body in place. Each edit copies the geometry, changes
the copy and makes a new shape with the same topology, so the model can hand
the old body's IDs to the new one through ``SameTopology``.

Pole and knot numbers given by users start at 1. Knot positions are given on
0..1 along the curve (or along u or v of a surface), whatever the kernel's own
parameter range is.

Shapes made from a network of curves (``network``) are sampled and fitted
(the Gordon construction: two lofts added, minus the surface through the
crossing points), so they pass through every curve.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_CompCurve
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire, BRepBuilderAPI_Sewing
from OCP.BRepTools import BRepTools
from OCP.Geom import Geom_BSplineCurve, Geom_BSplineSurface
from OCP.GeomAbs import GeomAbs_C0, GeomAbs_C1, GeomAbs_G1
from OCP.GeomConvert import GeomConvert
from OCP.gp import gp_Pnt
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SHELL, TopAbs_VERTEX, TopAbs_WIRE
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Shape

from .curves import CurveError, norm, sub

try:  # OCP 8
    from OCP.collections import Array1_double as _ArrReal
    from OCP.collections import Array1_gp_Pnt as _ArrPnt
    from OCP.collections import Array1_int as _ArrInt
    from OCP.collections import Array2_double as _Arr2Real
    from OCP.collections import Array2_gp_Pnt as _Arr2Pnt
except ImportError:  # OCP 7.x
    from OCP.TColgp import TColgp_Array1OfPnt as _ArrPnt  # type: ignore[no-redef]
    from OCP.TColgp import TColgp_Array2OfPnt as _Arr2Pnt  # type: ignore[no-redef]
    from OCP.TColStd import TColStd_Array1OfInteger as _ArrInt  # type: ignore[no-redef]
    from OCP.TColStd import TColStd_Array1OfReal as _ArrReal  # type: ignore[no-redef]
    from OCP.TColStd import TColStd_Array2OfReal as _Arr2Real  # type: ignore[no-redef]

from ..core.model import TopTools_IndexedMapOfShape  # noqa: E402 (OCP 7 and 8 names)

_as_edge = getattr(TopoDS, "Edge_s", None) or TopoDS.Edge
_as_face = getattr(TopoDS, "Face_s", None) or TopoDS.Face
_as_wire = getattr(TopoDS, "Wire_s", None) or TopoDS.Wire
_as_shell = getattr(TopoDS, "Shell_s", None) or TopoDS.Shell

MAX_DEGREE = Geom_BSplineCurve.MaxDegree_s() if hasattr(Geom_BSplineCurve, "MaxDegree_s") else 25
# G2 is passed as C1: the plate solver reads the number as an order (0, 1, 2), and GeomAbs_G2 is 3
CONTINUITY = {"G0": GeomAbs_C0, "G1": GeomAbs_G1, "G2": GeomAbs_C1}


class NurbsError(CurveError):
    pass


# =============================================================================
# Reading a body's B-spline
# =============================================================================


def _subs(shape: TopoDS_Shape, kind) -> list:
    out, ex = [], TopExp_Explorer(shape, kind)
    while ex.More():
        out.append(ex.Current())
        ex.Next()
    return out


def _unique(shape, kind) -> int:
    m = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, kind, m)
    return m.Extent()


def curve_of(shape: TopoDS_Shape) -> Geom_BSplineCurve:
    """A copy of the B-spline of a one-piece curve body (lines and arcs are converted exactly)."""
    if _subs(shape, TopAbs_FACE):
        raise NurbsError("this is not a curve")
    n = _unique(shape, TopAbs_EDGE)
    if n == 0:
        raise NurbsError("this body has no curve")
    if n > 1:
        raise NurbsError(f"this curve is made of {n} pieces; REBUILD it into one smooth curve first")
    edge = _as_edge(_subs(shape, TopAbs_EDGE)[0])
    got = BRep_Tool.Curve_s(edge, 0.0, 0.0)
    crv = got[0] if isinstance(got, tuple) else got
    try:
        a, b = BRep_Tool.Range_s(edge)
    except TypeError:  # older bindings return the range through the call above
        a, b = got[1], got[2]
    if crv is None:
        raise NurbsError("this edge has no 3D curve")
    if not isinstance(crv, Geom_BSplineCurve):
        from OCP.Geom import Geom_TrimmedCurve

        crv = Geom_TrimmedCurve(crv, a, b)  # lines are endless: convert the piece the edge uses
    bs = GeomConvert.CurveToBSplineCurve_s(crv)  # always a new curve (a B-spline is copied)
    lo, hi = bs.FirstParameter(), bs.LastParameter()
    if (a > lo + 1e-9 or b < hi - 1e-9) and not bs.IsPeriodic():
        bs.Segment(a, b)
    if edge.Orientation() == 1:  # TopAbs_REVERSED: keep the order the curve is walked in
        bs.Reverse()
    return bs


def _natural(face, surf) -> bool:
    """Whether a face is the whole of its surface (not trimmed by other curves)."""
    u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
    s0, s1, t0, t1 = surf.Bounds()
    tol = 1e-6 * max(1.0, abs(s1 - s0), abs(t1 - t0))
    whole = abs(u0 - s0) < tol and abs(u1 - s1) < tol and abs(v0 - t0) < tol and abs(v1 - t1) < tol
    return whole and len(_subs(face, TopAbs_WIRE)) == 1


def surface_of(shape: TopoDS_Shape, need_whole: bool = True) -> tuple[Geom_BSplineSurface, object]:
    """(copy of the B-spline surface, face) of a one-face surface body."""
    faces = _subs(shape, TopAbs_FACE)
    if len(faces) != 1:
        what = "has no faces" if not faces else f"has {len(faces)} faces"
        raise NurbsError(f"this body {what}; control points belong to a curve or to a single surface")
    face = _as_face(faces[0])
    srf = BRep_Tool.Surface_s(face)
    u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
    try:
        bs = GeomConvert.SurfaceToBSplineSurface_s(srf)
    except Exception:  # noqa: BLE001 - infinite surfaces (planes) cannot convert whole
        from OCP.Geom import Geom_RectangularTrimmedSurface

        bs = GeomConvert.SurfaceToBSplineSurface_s(Geom_RectangularTrimmedSurface(srf, u0, u1, v0, v1))
    s0, s1, t0, t1 = bs.Bounds()
    if (u0 > s0 + 1e-9 or u1 < s1 - 1e-9 or v0 > t0 + 1e-9 or v1 < t1 - 1e-9) and _natural_box(face):
        bs.Segment(max(u0, s0), min(u1, s1), max(v0, t0), min(v1, t1))  # a plane or cylinder face: its box
    if need_whole and not _natural(face, bs):
        raise NurbsError("this face is trimmed by other curves, so moving its control points would tear it "
                         "from its edges; REBUILD it, or edit the curves it was made from")
    return bs, face


def _natural_box(face) -> bool:
    """A face bounded by four straight-in-uv edges (a planar rectangle, a cylinder strip)."""
    return len(_subs(face, TopAbs_WIRE)) == 1 and _unique(face, TopAbs_EDGE) <= 4


def copy(g):
    """An independent copy of a B-spline curve or surface (the converters copy one given to them)."""
    if isinstance(g, Geom_BSplineCurve):
        return GeomConvert.CurveToBSplineCurve_s(g)
    return GeomConvert.SurfaceToBSplineSurface_s(g)


def kind_of(shape: TopoDS_Shape) -> str:
    """"curve", "surface" or "" for a body."""
    if _subs(shape, TopAbs_FACE):
        return "surface" if len(_subs(shape, TopAbs_FACE)) == 1 else ""
    return "curve" if _subs(shape, TopAbs_EDGE) else ""


def geometry_of(shape: TopoDS_Shape, need_whole: bool = True):
    k = kind_of(shape)
    if k == "curve":
        return curve_of(shape)
    if k == "surface":
        return surface_of(shape, need_whole)[0]
    if _subs(shape, TopAbs_FACE):
        raise NurbsError("this is a body of many faces; control points belong to a curve or to a single surface")
    raise NurbsError("this body has no curve or surface")


# =============================================================================
# Shapes from geometry
# =============================================================================


def curve_shape(c: Geom_BSplineCurve):
    edge = BRepBuilderAPI_MakeEdge(c).Edge()
    mk = BRepBuilderAPI_MakeWire(edge)
    return mk.Wire()


def surface_shape(s: Geom_BSplineSurface):
    mk = BRepBuilderAPI_MakeFace(s, 1e-6)
    if not mk.IsDone():
        raise NurbsError("the kernel could not make a face on this surface")
    return mk.Face()


def shape_of(g):
    return curve_shape(g) if isinstance(g, Geom_BSplineCurve) else surface_shape(g)


class SameTopology:
    """A 'maker' for Model.replace: entities of the old and new shape match by position.

    Used when an edit keeps the topology (one edge stays one edge, a face keeps
    its four sides), so every face, edge and vertex keeps its ID."""

    def __init__(self, old: TopoDS_Shape, new: TopoDS_Shape):
        self._map: dict = {}
        for kind in (TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX):
            a, b = TopTools_IndexedMapOfShape(), TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(old, kind, a)
            TopExp.MapShapes_s(new, kind, b)
            if a.Extent() == b.Extent():
                for i in range(1, a.Extent() + 1):
                    self._map[a.FindKey(i)] = b.FindKey(i)

    def IsDeleted(self, s) -> bool:  # noqa: N802 - the OCCT maker interface
        return False

    def Modified(self, s):  # noqa: N802
        for k, v in self._map.items():
            if k.IsSame(s):
                return [v]
        return []


class SewMaker:
    """Entity history of a sewing, for Model.replace."""

    def __init__(self, sew: BRepBuilderAPI_Sewing, result: TopoDS_Shape):
        self.sew, self.result = sew, result

    def IsDeleted(self, s) -> bool:  # noqa: N802
        return False

    def Modified(self, s):  # noqa: N802
        try:
            if self.sew.IsModified(s):
                return [self.sew.Modified(s)]
        except Exception:  # noqa: BLE001
            pass
        return []


# =============================================================================
# Making NURBS
# =============================================================================


def _uniform_clamped(n: int, deg: int) -> tuple[list[float], list[int]]:
    inner = n - deg - 1
    knots = [i / (inner + 1) for i in range(inner + 2)]
    mults = [deg + 1] + [1] * inner + [deg + 1]
    return knots, mults


def _real1(vals: Sequence[float]):
    a = _ArrReal(1, len(vals))
    for i, v in enumerate(vals, 1):
        a.SetValue(i, float(v))
    return a


def _int1(vals: Sequence[int]):
    a = _ArrInt(1, len(vals))
    for i, v in enumerate(vals, 1):
        a.SetValue(i, int(v))
    return a


def _pnt1(pts: Sequence[Sequence[float]]):
    a = _ArrPnt(1, len(pts))
    for i, q in enumerate(pts, 1):
        a.SetValue(i, gp_Pnt(*map(float, q[:3])))
    return a


def make_curve(points: Sequence[Sequence[float]], degree: int = 3, weights: Sequence[float] | None = None,
               closed: bool = False, knots: Sequence[float] | None = None,
               mults: Sequence[int] | None = None) -> Geom_BSplineCurve:
    """A NURBS curve from its control points (clamped: it starts and ends on the end points).
    ``closed``: a smooth closed loop (periodic), the points go round once."""
    n = len(points)
    w = list(weights) if weights is not None else [1.0] * n
    if any(x <= 0 for x in w):
        raise NurbsError("every weight must be greater than 0")
    if not 1 <= degree <= MAX_DEGREE:
        raise NurbsError(f"the degree must be from 1 to {MAX_DEGREE}")
    if closed:
        if n < 3:
            raise NurbsError("a closed curve needs at least 3 control points")
        if degree >= n:
            raise NurbsError(f"a closed curve of degree {degree} needs at least {degree + 1} control points")
        ks, ms = [i / n for i in range(n + 1)], [1] * (n + 1)
    else:
        if n < 2:
            raise NurbsError("give at least 2 control points")
        if degree >= n:
            raise NurbsError(f"degree {degree} needs at least {degree + 1} control points (or a lower degree)")
        ks, ms = _uniform_clamped(n, degree)
    if knots is not None:
        ks, ms = list(knots), list(mults or [1] * len(knots))
    for a, b in zip(points, points[1:] + ([points[0]] if closed else [])):
        if norm(sub(a[:3], b[:3])) < 1e-9 and n == 2:
            raise NurbsError("the control points are all in one place")
    try:
        return Geom_BSplineCurve(_pnt1(points), _real1(w), _real1(ks), _int1(ms), degree, closed)
    except Exception as exc:  # noqa: BLE001 - Standard_ConstructionError
        raise NurbsError(f"the kernel refused these control points ({exc})") from None


def make_surface(net: Sequence[Sequence[Sequence[float]]], weights=None, deg_u: int = 3, deg_v: int = 3,
                 knots_u=None, mults_u=None, knots_v=None, mults_v=None) -> Geom_BSplineSurface:
    """A NURBS surface from a net of control points: ``net[i][j]``, i along u, j along v."""
    nu, nv = len(net), len(net[0])
    if any(len(r) != nv for r in net):
        raise NurbsError("every row of the control net must have the same number of points")
    deg_u, deg_v = min(deg_u, nu - 1), min(deg_v, nv - 1)
    if deg_u < 1 or deg_v < 1:
        raise NurbsError("the control net needs at least 2 x 2 points")
    ku, mu = (knots_u, mults_u) if knots_u is not None else _uniform_clamped(nu, deg_u)
    kv, mv = (knots_v, mults_v) if knots_v is not None else _uniform_clamped(nv, deg_v)
    poles, ws = _Arr2Pnt(1, nu, 1, nv), _Arr2Real(1, nu, 1, nv)
    for i in range(nu):
        for j in range(nv):
            poles.SetValue(i + 1, j + 1, gp_Pnt(*map(float, net[i][j][:3])))
            w = 1.0 if weights is None else float(weights[i][j])
            if w <= 0:
                raise NurbsError("every weight must be greater than 0")
            ws.SetValue(i + 1, j + 1, w)
    try:
        return Geom_BSplineSurface(poles, ws, _real1(ku), _real1(kv), _int1(mu), _int1(mv), deg_u, deg_v)
    except Exception as exc:  # noqa: BLE001
        raise NurbsError(f"the kernel refused this control net ({exc})") from None


# =============================================================================
# Reading and editing control points
# =============================================================================


def _xyz(p: gp_Pnt) -> tuple[float, float, float]:
    return (p.X(), p.Y(), p.Z())


def poles(g) -> list:
    """Curve: [(x,y,z)...]; surface: rows along u of points along v."""
    if isinstance(g, Geom_BSplineCurve):
        return [_xyz(g.Pole(i)) for i in range(1, g.NbPoles() + 1)]
    return [[_xyz(g.Pole(i, j)) for j in range(1, g.NbVPoles() + 1)] for i in range(1, g.NbUPoles() + 1)]


def weights(g) -> list:
    if isinstance(g, Geom_BSplineCurve):
        return [g.Weight(i) for i in range(1, g.NbPoles() + 1)]
    return [[g.Weight(i, j) for j in range(1, g.NbVPoles() + 1)] for i in range(1, g.NbUPoles() + 1)]


def knots(g, direction: str = "U") -> tuple[list[float], list[int]]:
    if isinstance(g, Geom_BSplineCurve):
        return ([g.Knot(i) for i in range(1, g.NbKnots() + 1)],
                [g.Multiplicity(i) for i in range(1, g.NbKnots() + 1)])
    if direction == "U":
        return ([g.UKnot(i) for i in range(1, g.NbUKnots() + 1)],
                [g.UMultiplicity(i) for i in range(1, g.NbUKnots() + 1)])
    return ([g.VKnot(i) for i in range(1, g.NbVKnots() + 1)],
            [g.VMultiplicity(i) for i in range(1, g.NbVKnots() + 1)])


def _check_index(g, idx: tuple[int, ...]) -> tuple[int, ...]:
    if isinstance(g, Geom_BSplineCurve):
        if len(idx) != 1:
            raise NurbsError("a curve's control point is one number, e.g. 3")
        n = g.NbPoles()
        if not 1 <= idx[0] <= n:
            raise NurbsError(f"the curve has control points 1 to {n}, not {idx[0]}")
        return idx
    if len(idx) != 2:
        raise NurbsError("a surface's control point is two numbers: (row along u, point along v), e.g. (2, 3)")
    nu, nv = g.NbUPoles(), g.NbVPoles()
    if not (1 <= idx[0] <= nu and 1 <= idx[1] <= nv):
        raise NurbsError(f"the surface has control points (1..{nu}, 1..{nv}), not ({idx[0]}, {idx[1]})")
    return idx


def pole(g, idx: tuple[int, ...]) -> tuple[float, float, float]:
    idx = _check_index(g, idx)
    return _xyz(g.Pole(*idx))


def move_pole(g, idx: tuple[int, ...], to: Sequence[float]) -> None:
    idx = _check_index(g, idx)
    g.SetPole(*idx, gp_Pnt(*map(float, to)))


def set_weight(g, idx: tuple[int, ...], w: float) -> None:
    idx = _check_index(g, idx)
    if w <= 0:
        raise NurbsError("a weight must be greater than 0")
    g.SetWeight(*idx, float(w))


def _param(g, t: float, direction: str) -> float:
    if not 0 < t < 1:
        raise NurbsError("a knot goes strictly between the ends: give a number between 0 and 1")
    if isinstance(g, Geom_BSplineCurve):
        a, b = g.FirstParameter(), g.LastParameter()
    else:
        u0, u1, v0, v1 = g.Bounds()
        a, b = (u0, u1) if direction == "U" else (v0, v1)
    return a + (b - a) * t


def insert_knot(g, t: float, mult: int = 1, direction: str = "U") -> int:
    """Add a knot at t (0..1) without changing the shape. Returns how many control points were added."""
    before = len(_flat(poles(g)))
    u = _param(g, t, direction)
    deg = g.Degree() if isinstance(g, Geom_BSplineCurve) else (g.UDegree() if direction == "U" else g.VDegree())
    if not 1 <= mult <= deg:
        raise NurbsError(f"the multiplicity must be from 1 to the degree ({deg})")
    if isinstance(g, Geom_BSplineCurve):
        g.InsertKnot(u, mult, 1e-9)
    elif direction == "U":
        g.InsertUKnot(u, mult, 1e-9)
    else:
        g.InsertVKnot(u, mult, 1e-9)
    return len(_flat(poles(g))) - before


def elevate(g, degree: int, direction: str = "U") -> None:
    if not 1 <= degree <= MAX_DEGREE:
        raise NurbsError(f"the degree must be from 1 to {MAX_DEGREE}")
    if isinstance(g, Geom_BSplineCurve):
        if degree < g.Degree():
            raise NurbsError(f"the curve is degree {g.Degree()}; a degree can only go up without changing the shape "
                             "(REBUILD makes a lower one)")
        g.IncreaseDegree(degree)
        return
    du, dv = g.UDegree(), g.VDegree()
    nu = degree if direction in ("U", "BOTH") else du
    nv = degree if direction in ("V", "BOTH") else dv
    if nu < du or nv < dv:
        raise NurbsError(f"the surface is degree {du} x {dv}; a degree can only go up without changing the shape "
                         "(REBUILD makes a lower one)")
    g.IncreaseDegree(nu, nv)


def _flat(x) -> list:
    return [q for row in x for q in row] if x and isinstance(x[0], list) else list(x)


def describe(g) -> str:
    """Lines listing the control points (and weights when not all 1)."""
    ps, ws = poles(g), weights(g)
    rational = any(abs(w - 1) > 1e-12 for w in _flat(ws))

    def pt(q, w) -> str:
        s = f"({q[0]:.6g}, {q[1]:.6g}, {q[2]:.6g})"
        return s + (f"  w {w:.6g}" if rational else "")

    if isinstance(g, Geom_BSplineCurve):
        ks, _ = knots(g)
        head = (f"curve: degree {g.Degree()}, {g.NbPoles()} control points, {len(ks)} knots"
                f"{', closed' if g.IsPeriodic() else ''}{', rational' if rational else ''}")
        return "\n".join([head] + [f"  {i}: {pt(q, w)}" for i, (q, w) in enumerate(zip(ps, ws), 1)])
    head = (f"surface: degree {g.UDegree()} x {g.VDegree()}, {g.NbUPoles()} x {g.NbVPoles()} control points"
            f"{', rational' if rational else ''}")
    lines = [head]
    for i, (row, wrow) in enumerate(zip(ps, ws), 1):
        for j, (q, w) in enumerate(zip(row, wrow), 1):
            lines.append(f"  ({i}, {j}): {pt(q, w)}")
    return "\n".join(lines)


# =============================================================================
# B-spline basis in numpy (for fitting)
# =============================================================================


def basis(knots_full: np.ndarray, deg: int, u: np.ndarray) -> np.ndarray:
    """Matrix N[k, i] = N_i,deg(u_k) for a full (flat) knot vector, Cox-de Boor."""
    kn = np.asarray(knots_full, float)
    u = np.asarray(u, float)
    n = len(kn) - deg - 1
    hi = kn[n]
    uu = np.minimum(u, hi - 1e-12 * max(1.0, abs(hi)))
    N = np.zeros((len(u), len(kn) - 1))
    for i in range(len(kn) - 1):
        N[:, i] = (kn[i] <= uu) & (uu < kn[i + 1])
    for d in range(1, deg + 1):
        M = np.zeros((len(u), len(kn) - 1 - d))
        for i in range(len(kn) - 1 - d):
            a = kn[i + d] - kn[i]
            b = kn[i + d + 1] - kn[i + 1]
            left = (uu - kn[i]) / a * N[:, i] if a > 0 else 0.0
            right = (kn[i + d + 1] - uu) / b * N[:, i + 1] if b > 0 else 0.0
            M[:, i] = left + right
        N = M
    return N[:, :n]


def _flat_knots(ks, ms) -> np.ndarray:
    return np.repeat(np.asarray(ks, float), np.asarray(ms, int))


def fit_curve(points: np.ndarray, n: int, deg: int, closed: bool = False) -> Geom_BSplineCurve:
    """Least-squares NURBS (weights 1) with ``n`` control points through sampled points."""
    pts = np.asarray(points, float)
    d = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    t = np.concatenate([[0.0], np.cumsum(d)])
    if t[-1] < 1e-12:
        raise NurbsError("the curve has no length")
    t /= t[-1]
    if closed:
        if n < deg + 1 or n < 3:
            raise NurbsError(f"a closed curve of degree {deg} needs at least {max(3, deg + 1)} control points")
        # uniform periodic basis: extend the knots and wrap the extra columns round
        h = 1.0 / n
        kn = np.array([(i - deg) * h for i in range(n + 2 * deg + 1)])
        tt = t[:-1]  # the last sample repeats the first
        B = basis(kn, deg, tt + 0.0)
        A = np.zeros((len(tt), n))
        for c in range(B.shape[1]):
            A[:, c % n] += B[:, c]
        P, *_ = np.linalg.lstsq(A, pts[:-1], rcond=None)
        # OCCT counts periodic poles from its own start; find the shift that matches
        best, best_err = None, float("inf")
        for s in range(n):
            cand = make_curve([tuple(q) for q in np.roll(P, -s, axis=0)], deg, closed=True)
            err = max(norm(sub(_xyz(cand.Value(cand.FirstParameter() + (cand.LastParameter() - cand.FirstParameter())
                                               * x)), tuple(q))) for x, q in zip(tt[::7], pts[:-1][::7]))
            if err < best_err:
                best, best_err = cand, err
        return best
    if n < deg + 1:
        raise NurbsError(f"degree {deg} needs at least {deg + 1} control points")
    ks, ms = _uniform_clamped(n, deg)
    A = basis(_flat_knots(ks, ms), deg, t)
    # ends exactly on the curve's ends; the rest by least squares
    P = np.zeros((n, 3))
    P[0], P[-1] = pts[0], pts[-1]
    if n > 2:
        rhs = pts - np.outer(A[:, 0], P[0]) - np.outer(A[:, -1], P[-1])
        inner, *_ = np.linalg.lstsq(A[:, 1:-1], rhs, rcond=None)
        P[1:-1] = inner
    return make_curve([tuple(q) for q in P], deg, knots=ks, mults=ms)


def sample_wire(shape: TopoDS_Shape, count: int = 400) -> tuple[np.ndarray, bool]:
    """Points evenly spaced along a curve body (all its pieces in order) and whether it closes."""
    from .sweep import PathSampler, as_wire

    w = as_wire(shape, "the curve")
    ps = PathSampler(w)
    pts = np.array([ps.at(ps.length * k / (count - 1))[0] for k in range(count)])
    closed = bool(w.Closed()) or float(np.linalg.norm(pts[0] - pts[-1])) < 1e-7 * max(1.0, ps.length)
    return pts, closed


def rebuild_curve(shape: TopoDS_Shape, n: int, deg: int) -> tuple[Geom_BSplineCurve, float]:
    """(one smooth curve with n control points, largest distance from the old curve)."""
    pts, closed = sample_wire(shape, max(400, 12 * n))
    c = fit_curve(pts, n, deg, closed)
    return c, _deviation_curve(c, pts)


def _deviation_curve(c: Geom_BSplineCurve, pts: np.ndarray) -> float:
    from OCP.GeomAPI import GeomAPI_ProjectPointOnCurve

    worst = 0.0
    for q in pts[:: max(1, len(pts) // 60)]:
        pr = GeomAPI_ProjectPointOnCurve(gp_Pnt(*q), c)
        if pr.NbPoints():
            worst = max(worst, pr.LowerDistance())
    return worst


def fit_surface_grid(grid: np.ndarray, nu: int, nv: int, du: int, dv: int) -> Geom_BSplineSurface:
    """Least-squares surface (weights 1) through a grid of sampled points grid[i, j] (i along u)."""
    G = np.asarray(grid, float)
    du, dv = min(du, nu - 1), min(dv, nv - 1)
    ku, mu = _uniform_clamped(nu, du)
    kv, mv = _uniform_clamped(nv, dv)
    # parameters from mean chord lengths, so a surface squeezed on one side still fits evenly
    lu = np.linalg.norm(np.diff(G, axis=0), axis=2).mean(axis=1)
    lv = np.linalg.norm(np.diff(G, axis=1), axis=2).mean(axis=0)
    tu = np.concatenate([[0], np.cumsum(lu)]) / max(lu.sum(), 1e-12)
    tv = np.concatenate([[0], np.cumsum(lv)]) / max(lv.sum(), 1e-12)
    A = basis(_flat_knots(ku, mu), du, tu)
    B = basis(_flat_knots(kv, mv), dv, tv)
    Ap, Bp = np.linalg.pinv(A), np.linalg.pinv(B)
    P = np.einsum("ia,abk,jb->ijk", Ap, G, Bp)
    return make_surface(P.tolist(), None, du, dv, ku, mu, kv, mv)


def sample_surface(g, nu: int, nv: int) -> np.ndarray:
    u0, u1, v0, v1 = g.Bounds()
    return np.array([[_xyz(g.Value(u0 + (u1 - u0) * i / (nu - 1), v0 + (v1 - v0) * j / (nv - 1)))
                      for j in range(nv)] for i in range(nu)])


def rebuild_surface(shape: TopoDS_Shape, nu: int, nv: int, du: int, dv: int) -> tuple[Geom_BSplineSurface, float]:
    """(a surface with nu x nv control points, largest distance from the old one) for a one-face body.
    A trimmed face is rebuilt over its whole box of parameters."""
    g, face = surface_of(shape, need_whole=False)
    u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
    srf = BRep_Tool.Surface_s(face)
    su, sv = max(40, 4 * nu), max(40, 4 * nv)
    G = np.array([[_xyz(srf.Value(u0 + (u1 - u0) * i / (su - 1), v0 + (v1 - v0) * j / (sv - 1)))
                   for j in range(sv)] for i in range(su)])
    s = fit_surface_grid(G, nu, nv, du, dv)
    back = sample_surface(s, su, sv)
    return s, float(np.linalg.norm(back - G, axis=2).max())


# =============================================================================
# Surfaces from curves
# =============================================================================


def compatible(curves: list[Geom_BSplineCurve]) -> list[Geom_BSplineCurve]:
    """Copies of the curves with one degree and one knot vector (on 0..1), shapes unchanged."""
    out = []
    for c in curves:
        c = copy(c)
        if c.IsPeriodic():
            c.SetNotPeriodic()
        out.append(c)
    deg = max(c.Degree() for c in out)
    for c in out:
        if c.Degree() < deg:
            c.IncreaseDegree(deg)
    norm_curves = []
    for c in out:
        ks, ms = knots(c)
        a, b = ks[0], ks[-1]
        ks01 = [(k - a) / (b - a) for k in ks]
        norm_curves.append(Geom_BSplineCurve(_pnt1([_xyz(c.Pole(i)) for i in range(1, c.NbPoles() + 1)]),
                                             _real1([c.Weight(i) for i in range(1, c.NbPoles() + 1)]),
                                             _real1(ks01), _int1(ms), deg, False))
    # every knot of every curve, at its highest multiplicity
    want: dict[float, int] = {}
    for c in norm_curves:
        for k, m in zip(*knots(c)):
            key = round(k, 10)
            want[key] = max(want.get(key, 0), m)
    for c in norm_curves:
        have = {round(k, 10): m for k, m in zip(*knots(c))}
        for k, m in sorted(want.items()):
            if have.get(k, 0) < m:
                c.InsertKnot(k, m, 1e-9)
    if len({c.NbPoles() for c in norm_curves}) != 1:
        raise NurbsError("the curves could not be matched to one another (their knots differ too much)")
    return norm_curves


def net_surface(curves: list[Geom_BSplineCurve], deg: int = 3) -> Geom_BSplineSurface:
    """A surface whose rows of control points are the control points of the curves (in order).

    Control point (i, j) is point j of row (curve) i: u runs across the rows, v along them."""
    if len(curves) < 2:
        raise NurbsError("give at least 2 curves")
    cs = compatible(curves)
    ks, ms = knots(cs[0])
    net = [[_xyz(c.Pole(j)) for j in range(1, c.NbPoles() + 1)] for c in cs]
    ws = [[c.Weight(j) for j in range(1, c.NbPoles() + 1)] for c in cs]
    deg = max(1, min(deg, len(cs) - 1))
    ku, mu = _uniform_clamped(len(cs), deg)
    return make_surface(net, ws, deg, cs[0].Degree(), ku, mu, ks, ms)


# ---- network of curves (Gordon surface) -------------------------------------------

class _Curve:
    """A curve body sampled for the network construction (any pieces, walked in order)."""

    def __init__(self, shape: TopoDS_Shape, label: str):
        from .sweep import as_wire

        self.label = label
        self.w = as_wire(shape, label)
        self.ad = BRepAdaptor_CompCurve(self.w)
        self.a, self.b = self.ad.FirstParameter(), self.ad.LastParameter()
        self.flip = False
        self.samples = np.array([self.at(k / 400) for k in range(401)])

    def at(self, s: float) -> np.ndarray:
        s = min(max(s, 0.0), 1.0)
        if self.flip:
            s = 1.0 - s
        return np.array(_xyz(self.ad.Value(self.a + (self.b - self.a) * s)))


def _meet(c: _Curve, d: _Curve) -> tuple[float, float, float]:
    """(s on c, t on d, gap) where two curves come closest."""
    D = np.linalg.norm(c.samples[:, None, :] - d.samples[None, :, :], axis=2)
    i, j = np.unravel_index(np.argmin(D), D.shape)
    s, t = i / 400, j / 400
    h = 1 / 400
    for _ in range(40):  # refine: alternate closest-point steps with a shrinking bracket
        best = (float(np.linalg.norm(c.at(s) - d.at(t))), s, t)
        for ds in (-h, 0, h):
            for dt in (-h, 0, h):
                q = float(np.linalg.norm(c.at(s + ds) - d.at(t + dt)))
                if q < best[0]:
                    best = (q, min(max(s + ds, 0), 1), min(max(t + dt, 0), 1))
        if best[1] == s and best[2] == t:
            h /= 2
            if h < 1e-7:
                break
        s, t = best[1], best[2]
    return s, t, float(np.linalg.norm(c.at(s) - d.at(t)))


def _monotone(x: np.ndarray, y: np.ndarray):
    """Shape-keeping cubic through (x, y) (Fritsch-Carlson), as a function of arrays."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) == 2:
        return lambda q: np.interp(q, x, y)
    h, delta = np.diff(x), np.diff(y) / np.diff(x)
    m = np.zeros_like(y)
    m[0], m[-1] = delta[0], delta[-1]
    for k in range(1, len(x) - 1):
        if delta[k - 1] * delta[k] <= 0:
            m[k] = 0
        else:
            w1, w2 = 2 * h[k] + h[k - 1], h[k] + 2 * h[k - 1]
            m[k] = (w1 + w2) / (w1 / delta[k - 1] + w2 / delta[k])

    def f(q):
        q = np.clip(np.asarray(q, float), x[0], x[-1])
        k = np.clip(np.searchsorted(x, q) - 1, 0, len(x) - 2)
        t = (q - x[k]) / h[k]
        h00, h10 = 2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t
        h01, h11 = -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2
        return h00 * y[k] + h10 * h[k] * m[k] + h01 * y[k + 1] + h11 * h[k] * m[k + 1]

    return f


def _cardinal(nodes: np.ndarray):
    """Natural cubic spline cardinal functions: L(q)[:, i] is 1 at node i and 0 at the others."""
    n = len(nodes)
    if n == 2:
        def lin(q):
            t = (np.asarray(q, float) - nodes[0]) / (nodes[1] - nodes[0])
            return np.stack([1 - t, t], axis=-1)
        return lin
    h = np.diff(nodes)
    A = np.zeros((n, n))
    A[0, 0] = A[-1, -1] = 1
    for k in range(1, n - 1):
        A[k, k - 1], A[k, k], A[k, k + 1] = h[k - 1], 2 * (h[k - 1] + h[k]), h[k]
    R = np.zeros((n, n))  # second derivatives M = Ainv @ R @ y
    for k in range(1, n - 1):
        R[k, k - 1] += 6 / h[k - 1]
        R[k, k] += -6 / h[k - 1] - 6 / h[k]
        R[k, k + 1] += 6 / h[k]
    Mm = np.linalg.solve(A, R)  # rows: M_k as combination of y

    def L(q):
        q = np.clip(np.asarray(q, float), nodes[0], nodes[-1])
        k = np.clip(np.searchsorted(nodes, q) - 1, 0, n - 2)
        hk = h[k]
        a = (nodes[k + 1] - q) / hk
        b = (q - nodes[k]) / hk
        out = np.zeros((len(q), n))
        rows = np.arange(len(q))
        out[rows, k] += a
        out[rows, k + 1] += b
        c1 = (a ** 3 - a) * hk ** 2 / 6
        c2 = (b ** 3 - b) * hk ** 2 / 6
        out += c1[:, None] * Mm[k] + c2[:, None] * Mm[k + 1]
        return out

    return L


def network(u_shapes: list[TopoDS_Shape], v_shapes: list[TopoDS_Shape], samples: int = 41,
            tol: float | None = None) -> tuple[Geom_BSplineSurface, float]:
    """A surface through a network of curves: the u curves run one way, the v curves cross them.

    Every u curve must meet every v curve. Returns (surface, largest gap where curves meet)."""
    if len(u_shapes) < 2 or len(v_shapes) < 2:
        raise NurbsError("give at least 2 curves each way")
    U = [_Curve(s, f"u curve {i + 1}") for i, s in enumerate(u_shapes)]
    V = [_Curve(s, f"v curve {j + 1}") for j, s in enumerate(v_shapes)]
    size = float(np.ptp(np.vstack([c.samples for c in U + V]), axis=0).max())
    tol = tol if tol is not None else 2e-3 * max(size, 1.0)
    S = np.zeros((len(U), len(V)))  # where v curve j crosses u curve i, along u curve i
    T = np.zeros((len(U), len(V)))  # ... along v curve j
    worst = 0.0
    for i, c in enumerate(U):
        for j, d in enumerate(V):
            s, t, gap = _meet(c, d)
            if gap > tol:
                raise NurbsError(f"{c.label} and {d.label} do not meet (they come within {gap:.3g} of each other)")
            S[i, j], T[i, j], worst = s, t, max(worst, gap)
    # walk every curve so the crossings come in increasing order
    for i, c in enumerate(U):
        if S[i, -1] < S[i, 0]:
            c.flip, S[i] = True, 1 - S[i]
        if np.any(np.diff(S[i]) <= 0):
            raise NurbsError(f"the v curves must cross {c.label} in the order they are given")
    for j, d in enumerate(V):
        if T[-1, j] < T[0, j]:
            d.flip, T[:, j] = True, 1 - T[:, j]
        if np.any(np.diff(T[:, j]) <= 0):
            raise NurbsError(f"the u curves must cross {d.label} in the order they are given")
    # global parameters of the crossings: u along the u curves, v along the v curves
    uj = S.mean(axis=0)
    vi = T.mean(axis=1)
    uj = (uj - uj[0]) / (uj[-1] - uj[0])
    vi = (vi - vi[0]) / (vi[-1] - vi[0])
    P = np.array([[(U[i].at(S[i, j]) + V[j].at(T[i, j])) / 2 for j in range(len(V))] for i in range(len(U))])
    hu = [_monotone(uj, S[i]) for i in range(len(U))]  # u curve i: global u -> its own s
    gv = [_monotone(vi, T[:, j]) for j in range(len(V))]  # v curve j: global v -> its own t
    Lv, Mu = _cardinal(vi), _cardinal(uj)
    us = np.linspace(0, 1, samples)
    vs = np.linspace(0, 1, samples)
    Cu = np.array([[U[i].at(float(s)) for s in hu[i](us)] for i in range(len(U))])  # [i, a, 3]
    Dv = np.array([[V[j].at(float(t)) for t in gv[j](vs)] for j in range(len(V))])  # [j, b, 3]
    Lb, Ma = Lv(vs), Mu(us)  # [b, i], [a, j]
    G = (np.einsum("bi,iak->abk", Lb, Cu) + np.einsum("aj,jbk->abk", Ma, Dv)
         - np.einsum("bi,aj,ijk->abk", Lb, Ma, P))
    from .surfaces import fit

    srf = fit(G.tolist())
    return srf, worst


# ---- patch (fill a loop of curves) ---------------------------------------------------

def fill(boundary: list[tuple], interior_curves: list = (), interior_points: list = (), degree: int = 3):
    """A smooth face inside a closed loop of edges.

    boundary: (edge, face or None, continuity "G0"/"G1"/"G2"); with a face, the
    patch meets that face smoothly along the edge. Interior curves and points
    are passed through too."""
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeFilling

    if len(boundary) < 1:
        raise NurbsError("give the curves around the hole")
    mk = BRepOffsetAPI_MakeFilling(degree, 24, 4, False, 1e-5, 1e-4, 1e-2, 0.1, 8, 9)
    for edge, face, cont in boundary:
        if face is not None and cont != "G0":
            mk.Add(edge, face, CONTINUITY[cont], True)
        else:
            mk.Add(edge, GeomAbs_C0, True)
    for e in interior_curves:
        mk.Add(e, GeomAbs_C0, False)
    for q in interior_points:
        mk.Add(gp_Pnt(*map(float, q)))
    try:
        mk.Build()
    except Exception as exc:  # noqa: BLE001
        raise NurbsError(f"the kernel could not fill this loop ({exc}); check that the curves join end to end") from None
    if not mk.IsDone():
        raise NurbsError("the kernel could not fill this loop; check that the curves join end to end")
    errs = {"G0": mk.G0Error(), "G1": mk.G1Error(), "G2": mk.G2Error()}
    return mk.Shape(), errs


def boundary_loop_gap(edges: list) -> float:
    """Largest gap between the ends of the edges when chained into a loop (0: closed)."""
    from OCP.BRep import BRep_Tool as BT

    ends = []
    for e in edges:
        vs = _subs(e, TopAbs_VERTEX)
        pts = [np.array(_xyz(BT.Pnt_s(TopoDS.Vertex_s(v) if hasattr(TopoDS, "Vertex_s") else TopoDS.Vertex(v))))
               for v in vs]
        if len(pts) < 2:
            pts = pts * 2
        ends.append((pts[0], pts[-1]))
    if len(ends) == 1:
        return float(np.linalg.norm(ends[0][0] - ends[0][1]))
    worst = 0.0
    for k, (a, b) in enumerate(ends):  # every end must touch some end of another edge
        for q in (a, b):
            others = [p for m, (c, d) in enumerate(ends) if m != k for p in (c, d)]
            worst = max(worst, min(float(np.linalg.norm(q - p)) for p in others))
    return worst


# ---- sewing ----------------------------------------------------------------------------

def sew(shapes: list[TopoDS_Shape], tol: float):
    """(shell or solid, sewing, free edge count). A closed shell becomes a solid."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
    from OCP.ShapeFix import ShapeFix_Solid

    from .robust import is_valid, volume

    mk = BRepBuilderAPI_Sewing(tol)
    for s in shapes:
        mk.Add(s)
    mk.Perform()
    out = mk.SewedShape()
    if out.IsNull():
        raise NurbsError("sewing gave nothing")
    free = mk.NbFreeEdges()
    if out.ShapeType() == TopAbs_SHELL and free == 0:
        so = BRepBuilderAPI_MakeSolid(_as_shell(out)).Solid()
        fx = ShapeFix_Solid(so)
        fx.Perform()
        solid = fx.Solid()
        if is_valid(solid) and abs(volume(solid)) > 0:
            if volume(solid) < 0:
                solid.Reverse()
            return solid, mk, 0
    return out, mk, free


def angle_deg(a, b) -> float:
    c = sum(x * y for x, y in zip(a, b)) / max(1e-300, norm(a) * norm(b))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))
