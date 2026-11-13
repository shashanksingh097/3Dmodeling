"""Deforming whole bodies: bend, twist, taper, stretch, and flow along a curve.

A deformation is any smooth map of space, ``fn(points) -> points``. Exact
B-rep geometry cannot simply be pushed through a curved map, so:

1. The body is converted to NURBS (every face a B-spline surface, every
   edge a B-spline curve; the curves of the edges on the faces, in the
   faces' own (u, v) parameters, come along).
2. Every surface and edge curve is refined in place: degree raised to 3 and
   knots inserted until its spans are short. This changes no point of the
   shape, and the (u, v) curves of the edges still fit.
3. The original geometry is evaluated at each spline's Greville points,
   those points are mapped, and new control points are solved for so the
   spline passes exactly through the mapped points (same knots, same
   weights, same parameters). The (u, v) curves of the edges therefore still
   lie where the edges are.
4. Vertices are mapped, tolerances updated, and the shape checked. The
   error between the new surfaces and the true mapped surfaces is measured
   between the Greville points; if it is too large the spans are halved and
   step 2 is repeated.

The faces and edges stay the same objects (geometry is changed in place on a
copy), so their IDs carry over. A faceted body (an imported mesh: hundreds
of flat triangles) has its corner points mapped instead.

The maps themselves (``bend``, ``twist``, ``taper``, ``flow``) work on numpy
arrays of points in a body-aligned frame: ``x`` along the chosen axis, from
the start of the body's box (``s`` from 0 to the length ``L``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import numpy as np
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy, BRepBuilderAPI_NurbsConvert
from OCP.gp import gp_Pnt
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS

from . import nurbs as nb
from . import robust
from .curves import CurveError

_as_face = getattr(TopoDS, "Face_s", None) or TopoDS.Face
_as_edge = getattr(TopoDS, "Edge_s", None) or TopoDS.Edge
_as_vertex = getattr(TopoDS, "Vertex_s", None) or TopoDS.Vertex

Map = Callable[[np.ndarray], np.ndarray]
AXES = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}


class DeformError(CurveError):
    pass


# =============================================================================
# The engine
# =============================================================================


def _subs(shape, kind) -> list:
    seen, out = [], []
    ex = TopExp_Explorer(shape, kind)
    while ex.More():
        s = ex.Current()
        if not any(s.IsSame(t) for t in seen):
            seen.append(s)
            out.append(s)
        ex.Next()
    return out


def _greville(knots_full: np.ndarray, deg: int, n: int) -> np.ndarray:
    return np.array([knots_full[i + 1:i + deg + 1].mean() for i in range(n)])


def _flat(knots, mults) -> np.ndarray:
    return np.repeat(np.asarray(knots, float), np.asarray(mults, int))


def _curve_knots(c):
    return [c.Knot(i) for i in range(1, c.NbKnots() + 1)], [c.Multiplicity(i) for i in range(1, c.NbKnots() + 1)]


def _surf_knots(s, d):
    if d == "U":
        return ([s.UKnot(i) for i in range(1, s.NbUKnots() + 1)],
                [s.UMultiplicity(i) for i in range(1, s.NbUKnots() + 1)])
    return ([s.VKnot(i) for i in range(1, s.NbVKnots() + 1)],
            [s.VMultiplicity(i) for i in range(1, s.NbVKnots() + 1)])


def _targets(knots: list[float], spans: int, a: float, b: float) -> list[float]:
    """Knots to insert so no span of [a, b] (the spline's own range) is longer than (b - a) / spans."""
    h = (b - a) / spans
    out = []
    ks = [k for k in knots if a - 1e-12 <= k <= b + 1e-12]
    for k0, k1 in zip(ks, ks[1:]):
        n = int(math.ceil((k1 - k0) / h - 1e-9))
        out += [k0 + (k1 - k0) * i / n for i in range(1, n)]
    return out


def _refine_curve(c, spans: int) -> None:
    # (degree first: raising it after SetNotPeriodic fails on a rational surface, an OCCT quirk)
    if c.Degree() < 3:
        c.IncreaseDegree(3)
    if c.IsPeriodic():
        c.SetNotPeriodic()
    ks, _ = _curve_knots(c)
    for u in _targets(ks, spans, c.FirstParameter(), c.LastParameter()):
        c.InsertKnot(u, 1, 1e-12, False)


def _refine_surface(s, spans: int) -> None:
    if s.UDegree() < 3 or s.VDegree() < 3:
        s.IncreaseDegree(max(3, s.UDegree()), max(3, s.VDegree()))
    if s.IsUPeriodic():
        s.SetUNotPeriodic()
    if s.IsVPeriodic():
        s.SetVNotPeriodic()
    u0, u1, v0, v1 = s.Bounds()
    ku, _ = _surf_knots(s, "U")
    for u in _targets(ku, spans, u0, u1):
        s.InsertUKnot(u, 1, 1e-12, False)
    kv, _ = _surf_knots(s, "V")
    for v in _targets(kv, spans, v0, v1):
        s.InsertVKnot(v, 1, 1e-12, False)


@dataclass
class _CurveJob:
    c: object
    knots: np.ndarray
    deg: int
    params: np.ndarray
    w: np.ndarray
    pts: np.ndarray  # original points at the parameters
    mid: np.ndarray  # parameters between, for the error check
    mid_pts: np.ndarray


@dataclass
class _SurfJob:
    s: object
    ku: np.ndarray
    kv: np.ndarray
    du: int
    dv: int
    pu: np.ndarray
    pv: np.ndarray
    w: np.ndarray  # (nu, nv)
    pts: np.ndarray  # (nu, nv, 3) original points at (pu x pv)
    mu: np.ndarray
    mv: np.ndarray
    mid_pts: np.ndarray


def _curve_job(c) -> _CurveJob:
    ks, ms = _curve_knots(c)
    kf = _flat(ks, ms)
    n, d = c.NbPoles(), c.Degree()
    g = _greville(kf, d, n)
    w = np.array([c.Weight(i) for i in range(1, n + 1)])
    pts = np.array([_xyz(c.Value(float(u))) for u in g])
    mid = 0.5 * (g[1:] + g[:-1])
    mid_pts = np.array([_xyz(c.Value(float(u))) for u in mid])
    return _CurveJob(c, kf, d, g, w, pts, mid, mid_pts)


def _surf_job(s) -> _SurfJob:
    ku, mu_ = _surf_knots(s, "U")
    kv, mv_ = _surf_knots(s, "V")
    kuf, kvf = _flat(ku, mu_), _flat(kv, mv_)
    nu, nv, du, dv = s.NbUPoles(), s.NbVPoles(), s.UDegree(), s.VDegree()
    pu, pv = _greville(kuf, du, nu), _greville(kvf, dv, nv)
    w = np.array([[s.Weight(i, j) for j in range(1, nv + 1)] for i in range(1, nu + 1)])
    pts = np.array([[_xyz(s.Value(float(u), float(v))) for v in pv] for u in pu])
    mu, mv = 0.5 * (pu[1:] + pu[:-1]), 0.5 * (pv[1:] + pv[:-1])
    mid_pts = np.array([[_xyz(s.Value(float(u), float(v))) for v in mv] for u in mu])
    return _SurfJob(s, kuf, kvf, du, dv, pu, pv, w, pts, mu, mv, mid_pts)


def _xyz(p) -> tuple:
    return (p.X(), p.Y(), p.Z())


def _apply_curve(job: _CurveJob, fn: Map) -> float:
    q = fn(job.pts)
    N = nb.basis(job.knots, job.deg, job.params)  # (k, n)
    W = N @ job.w  # the denominator at each parameter
    R = np.linalg.solve(N, q * W[:, None])  # homogeneous points w * P
    P = R / job.w[:, None]
    for i, p in enumerate(P, 1):
        job.c.SetPole(i, gp_Pnt(*map(float, p)), float(job.w[i - 1]))
    if len(job.mid) == 0:
        return 0.0
    want = fn(job.mid_pts)
    got = np.array([_xyz(job.c.Value(float(u))) for u in job.mid])
    return float(np.max(np.linalg.norm(got - want, axis=1)))


def _apply_surface(job: _SurfJob, fn: Map) -> float:
    nu, nv = len(job.pu), len(job.pv)
    q = fn(job.pts.reshape(-1, 3)).reshape(nu, nv, 3)
    Nu = nb.basis(job.ku, job.du, job.pu)
    Nv = nb.basis(job.kv, job.dv, job.pv)
    W = Nu @ job.w @ Nv.T  # denominators at the grid
    Nu_inv, Nv_inv = np.linalg.inv(Nu), np.linalg.inv(Nv)
    P = np.empty((nu, nv, 3))
    for k in range(3):
        R = Nu_inv @ (q[:, :, k] * W) @ Nv_inv.T
        P[:, :, k] = R / job.w
    s = job.s
    for i in range(nu):
        for j in range(nv):
            s.SetPole(i + 1, j + 1, gp_Pnt(*map(float, P[i, j])), float(job.w[i, j]))
    if len(job.mu) == 0 or len(job.mv) == 0:
        return 0.0
    want = fn(job.mid_pts.reshape(-1, 3)).reshape(len(job.mu), len(job.mv), 3)
    got = np.array([[_xyz(s.Value(float(u), float(v))) for v in job.mv] for u in job.mu])
    return float(np.max(np.linalg.norm(got - want, axis=2)))


def faceted(shape) -> bool:
    """A body of many flat triangles (an imported mesh)."""
    faces = _subs(shape, TopAbs_FACE)
    if len(faces) < 200:
        return False
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.BRepAdaptor import BRepAdaptor_Surface

    return all(BRepAdaptor_Surface(_as_face(f)).GetType() == GeomAbs_Plane for f in faces[:50])


def _deform_faceted(shape, fn: Map):
    from . import meshfiles

    m = meshfiles.triangulate(shape, robust.diagonal(shape) * 1e-4)
    pieces = meshfiles.mesh_to_pieces(fn(np.asarray(m.points, float)), np.asarray(m.tris))
    if not pieces:
        raise DeformError("the mesh has no triangles left")
    if len(pieces) == 1:
        return pieces[0].shape
    from OCP.TopoDS import TopoDS_Compound

    comp, b = TopoDS_Compound(), BRep_Builder()
    b.MakeCompound(comp)
    for pc in pieces:
        b.Add(comp, pc.shape)
    return comp


def _range(edge) -> tuple[float, float]:
    try:
        return tuple(BRep_Tool.Range_s(edge))
    except TypeError:  # older bindings
        got = BRep_Tool.Curve_s(edge, 0.0, 0.0)
        return got[1], got[2]


def _local_map(fn: Map, loc) -> Map:
    """fn seen from inside a placement: geometry stored in local coordinates, placed by ``loc``."""
    if loc.IsIdentity():
        return fn
    t = loc.Transformation()
    M = np.array([[t.Value(r, c) for c in range(1, 5)] for r in range(1, 4)])
    A, b = M[:, :3], M[:, 3]
    Ainv = np.linalg.inv(A)

    def g(P):
        return (fn(P @ A.T + b) - b) @ Ainv.T

    return g


def _unplaced(shape):
    """A copy to change in place (the model's own shape stays as it is)."""
    return BRepBuilderAPI_Copy(shape).Shape()


def deform(shape, fn: Map, tol: float | None = None, max_spans: int = 64):
    """The shape pushed through ``fn``. Returns (new shape, worst error,
    faceted?). Raises DeformError if the result is not a valid shape."""
    if faceted(shape):
        return _deform_faceted(shape, fn), 0.0, True
    size = max(robust.diagonal(shape), 1e-9)
    tol = tol if tol is not None else 1e-4 * size
    spans = 8
    while True:
        work = BRepBuilderAPI_NurbsConvert(_unplaced(shape), True).Shape()
        faces = [_as_face(f) for f in _subs(work, TopAbs_FACE)]
        edges = [_as_edge(e) for e in _subs(work, TopAbs_EDGE)]
        verts = [_as_vertex(v) for v in _subs(work, TopAbs_VERTEX)]
        srfs, s_maps = [], []
        for f in faces:
            loc = TopLoc_Location()
            srfs.append(BRep_Tool.Surface_s(f, loc))  # the stored surface, and where the face places it
            s_maps.append(_local_map(fn, loc))
        crvs, c_maps = [], []
        bld = BRep_Builder()
        for e in edges:
            if BRep_Tool.Degenerated_s(e):
                continue
            loc = TopLoc_Location()
            c = BRep_Tool.Curve_s(e, loc, 0.0, 0.0)
            c = c[0] if isinstance(c, tuple) else c
            if c is None:
                continue
            if not isinstance(c, nb.Geom_BSplineCurve):
                # (a Bezier or other curve: an edge's own 3D curve can simply be replaced by a B-spline copy)
                from OCP.GeomConvert import GeomConvert

                a, z = _range(e)
                c = GeomConvert.CurveToBSplineCurve_s(c)
                bld.UpdateEdge(e, c, loc, BRep_Tool.Tolerance_s(e))
                bld.Range(e, a, z)
            crvs.append(c)
            c_maps.append(_local_map(fn, loc))
        if not all(isinstance(s, nb.Geom_BSplineSurface) for s in srfs) or \
                not all(isinstance(c, nb.Geom_BSplineCurve) for c in crvs):
            raise DeformError("the body could not be turned into NURBS throughout")
        for s in srfs:
            _refine_surface(s, spans)
        for c in crvs:
            _refine_curve(c, spans)
        sjobs = [_surf_job(s) for s in srfs]
        cjobs = [_curve_job(c) for c in crvs]
        vpts = np.array([_xyz(BRep_Tool.Pnt_s(v)) for v in verts]) if verts else np.zeros((0, 3))
        err = 0.0
        for j, g in zip(sjobs, s_maps):
            err = max(err, _apply_surface(j, g))
        for j, g in zip(cjobs, c_maps):
            err = max(err, _apply_curve(j, g))
        if err <= tol or spans >= max_spans:
            break
        spans *= 2
    b = BRep_Builder()
    if len(verts):
        new = fn(vpts)
        for v, p in zip(verts, new):
            b.UpdateVertex(v, gp_Pnt(*map(float, p)), max(BRep_Tool.Tolerance_s(v), tol))
    from OCP.BRepLib import BRepLib
    from OCP.ShapeFix import ShapeFix_Shape

    for e in edges:
        b.SameRange(e, False)
        b.SameParameter(e, False)
    BRepLib.SameParameter_s(work, max(tol, 1e-7), True)
    fix = ShapeFix_Shape(work)
    fix.Perform()
    out = fix.Shape()
    if robust.is_empty(out) or not robust.is_valid(out):
        raise DeformError("the deformed body is not a valid shape (the deformation may fold it onto itself)")
    return out, err, False


# =============================================================================
# The maps
# =============================================================================


@dataclass
class Frame:
    """A body-aligned frame: o is the start of the body's box on the axis,
    a the axis, up and side square to it; L is the box's length along a."""

    o: np.ndarray
    a: np.ndarray
    up: np.ndarray
    side: np.ndarray
    L: float

    def local(self, P: np.ndarray):
        d = P - self.o
        return d @ self.a, d @ self.up, d @ self.side

    def world(self, s, h, w) -> np.ndarray:
        return self.o + np.outer(s, self.a) + np.outer(h, self.up) + np.outer(w, self.side)


def frame_of(shape, axis: str, up: str | None = None) -> Frame:
    """The frame of the body's box along an axis (X, Y or Z), centred on the box."""
    if axis not in AXES:
        raise DeformError(f"the axis is X, Y or Z, got {axis}")
    a = np.array(AXES[axis])
    upname = up or ("Z" if axis != "Z" else "X")
    sign = -1.0 if upname.startswith("-") else 1.0
    upname = upname.lstrip("+-")
    if upname not in AXES or upname == axis:
        raise DeformError(f"the bend direction is another axis than {axis} (X, Y, Z, -X, -Y or -Z)")
    u = sign * np.array(AXES[upname])
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    if box.IsVoid():
        raise DeformError("the body is empty")
    lo, hi = np.array(_xyz(box.CornerMin())), np.array(_xyz(box.CornerMax()))
    c = 0.5 * (lo + hi)
    L = float((hi - lo) @ a)
    if L < 1e-9:
        raise DeformError(f"the body has no length along {axis}")
    o = c - a * (L / 2)
    return Frame(o, a, u, np.cross(a, u), L)


def bend(f: Frame, angle_deg: float, law: Callable[[np.ndarray], np.ndarray] | None = None) -> Map:
    """Bend the body round towards ``up`` so its centre line (along the axis
    through the box centre) becomes an arc of ``angle`` degrees with the same
    length. ``law(t)`` (0..1) shares the bend out along the length (its
    increase is where the bending is); default even."""
    th = math.radians(angle_deg)
    if abs(th) < 1e-12:
        return lambda P: P
    if abs(th) >= 2 * math.pi - 1e-9:
        raise DeformError("BEND: the angle must be less than 360 degrees (the ends would meet)")
    R = f.L / th  # signed: a negative angle bends the other way
    k = 2000
    ts = np.linspace(0, 1, k + 1)
    if law is None:
        phi_of = lambda t: th * t  # noqa: E731
    else:
        g = np.asarray(law(ts), float)
        if np.any(np.diff(g) < -1e-12):
            raise DeformError("BEND: the law must not go down (it says how much of the bend is done by t)")
        g = (g - g[0]) / ((g[-1] - g[0]) or 1.0)
        phi_of = lambda t: th * np.interp(t, ts, g)  # noqa: E731

    if law is None:
        def centre(t):
            phi = th * t
            return R * np.sin(phi), R * (1 - np.cos(phi)), phi
    else:
        # integrate the centre line: unit speed, direction turning by phi(t)
        phis = phi_of(ts)
        dx = np.cos(phis) * f.L / k
        dy = np.sin(phis) * f.L / k
        xs = np.concatenate([[0.0], np.cumsum(0.5 * (dx[1:] + dx[:-1]))])
        ys = np.concatenate([[0.0], np.cumsum(0.5 * (dy[1:] + dy[:-1]))])

        def centre(t):
            return np.interp(t, ts, xs), np.interp(t, ts, ys), phi_of(t)

    def fn(P):
        s, h, w = f.local(P)
        t = s / f.L
        inside = np.clip(t, 0.0, 1.0)
        cx, cy, phi = centre(inside)
        # past the ends the body carries straight on along the end direction
        extra = (t - inside) * f.L
        cx = cx + extra * np.cos(phi)
        cy = cy + extra * np.sin(phi)
        # a point h above the centre line sits h along the line's normal
        nx, ny = -np.sin(phi), np.cos(phi)
        return f.world(cx + h * nx, cy + h * ny, w)

    return fn


def twist(f: Frame, angle_deg: float, law: Callable[[np.ndarray], np.ndarray] | None = None) -> Map:
    """Turn each cross-section about the axis by angle * law(t)."""
    th = math.radians(angle_deg)
    law = law or (lambda t: t)

    def fn(P):
        s, h, w = f.local(P)
        t = np.clip(s / f.L, 0.0, 1.0)
        a = th * np.asarray(law(t), float)
        c, sn = np.cos(a), np.sin(a)
        return f.world(s, h * c - w * sn, h * sn + w * c)

    return fn


def taper(f: Frame, end_scale: float, law: Callable[[np.ndarray], np.ndarray] | None = None) -> Map:
    """Scale each cross-section about the axis by 1 + (end_scale - 1) * law(t)."""
    law = law or (lambda t: t)

    def fn(P):
        s, h, w = f.local(P)
        t = np.clip(s / f.L, 0.0, 1.0)
        k = 1.0 + (end_scale - 1.0) * np.asarray(law(t), float)
        if np.any(k <= 1e-9):
            raise DeformError("TAPER: the scale must stay above 0 along the body")
        return f.world(s, h * k, w * k)

    return fn


def stretch(f: Frame, factor: float, keep_volume: bool = True) -> Map:
    """Stretch along the axis from the start of the box; the sides shrink by
    1/sqrt(factor) so the volume stays the same (unless keep_volume is off)."""
    if factor <= 0:
        raise DeformError("STRETCH: the factor must be greater than 0")
    k = 1.0 / math.sqrt(factor) if keep_volume else 1.0

    def fn(P):
        s, h, w = f.local(P)
        return f.world(s * factor, h * k, w * k)

    return fn


def flow(f: Frame, path, fit: bool = False, mode: str = "MINTWIST", start: float = 0.0) -> Map:
    """Lay the body along a curve: its length along the axis follows the curve
    (from ``start``, an arc length), its cross-section turns with the curve's
    frame (``up`` of the body to the frame's up, as a SWEEP profile drawn at
    the start would). ``fit`` stretches the body to the curve's length."""
    from . import sweep as sw

    ps = sw.PathSampler(path)
    n = 400
    fs = sw.frames(ps, n, mode)
    scale = ps.length / f.L if fit else 1.0
    if not fit and start + f.L > ps.length * (1 + 1e-9) and not ps.closed:
        raise DeformError(f"FLOW: the body is {f.L:.4g} long and the curve only {ps.length:.4g} from where it "
                          "starts; add FIT to stretch the body to the curve, or use a longer curve")
    ts = np.array([i / n for i in range(n + 1)]) * ps.length
    O = np.array([fr.o for fr in fs])
    U = np.array([fr.up for fr in fs])
    S = np.array([fr.side for fr in fs])
    T = np.array([fr.tan for fr in fs])

    def interp(arr, x):
        return np.stack([np.interp(x, ts, arr[:, k]) for k in range(3)], axis=1)

    def fn(P):
        s, h, w = f.local(P)
        arc = start + s * scale
        if ps.closed:
            arc = np.mod(arc, ps.length)
        inside = np.clip(arc, 0.0, ps.length)
        o = interp(O, inside)
        up = interp(U, inside)
        side = interp(S, inside)
        tan = interp(T, inside)
        o = o + tan * (arc - inside)[:, None]  # past an end: straight on
        # the curve frame's side is up x tan; the body's side is a x up = tan x up there: the opposite
        return o + up * h[:, None] - side * w[:, None]

    return fn
