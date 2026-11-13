"""Freeform surface operations: blends between surfaces, extending and trimming
surfaces, and moving or replacing a face of a solid.

* ``blend``: a surface that bridges two edges of two surfaces and leaves each
  one without a crease (G1) or also without a jump in curvature (G2). Across
  the gap it is a Bezier curve whose end derivatives are taken from the
  surfaces themselves (first derivatives for G1, first and second for G2);
  along the edges it is sampled and fitted, so it is ordinary exact geometry.
* ``extend``: a B-spline surface carries on past an edge the way it was
  going: its last span is evaluated beyond the end and refitted.
* ``trim``: a curve is projected onto a face along the face's normal, splits
  it, and one piece is kept or removed.
* ``replace_face``: a solid's face is replaced by another surface. The solid
  is first grown along the face's outward direction past the new surface,
  then cut by the half-space on the far side of it. ``move_face`` is the same
  with a moved copy of the face's own surface.
"""

from __future__ import annotations

import math

import numpy as np
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_Transform
from OCP.BRepClass import BRepClass_FaceClassifier
from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.BRepTools import BRepTools
from OCP.GCPnts import GCPnts_AbscissaPoint
from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Pnt, gp_Pnt2d, gp_Trsf, gp_Vec
from OCP.TopAbs import TopAbs_FACE, TopAbs_IN, TopAbs_REVERSED

from . import nurbs as nb
from .curves import CurveError

_V = np.array


def _xyz(p) -> np.ndarray:
    return _V([p.X(), p.Y(), p.Z()])


def _vec(v) -> np.ndarray:
    return _V([v.X(), v.Y(), v.Z()])


class SurfaceOpError(CurveError):
    pass


# =============================================================================
# Edges and surfaces sampled
# =============================================================================


def edge_points(edge, n: int) -> np.ndarray:
    """n points spaced evenly by length along an edge, in its own direction."""
    ad = BRepAdaptor_Curve(edge)
    a, b = ad.FirstParameter(), ad.LastParameter()
    length = GCPnts_AbscissaPoint.Length_s(ad, a, b)
    if length < 1e-9:
        raise SurfaceOpError("an edge has no length")
    out = []
    for k in range(n):
        s = length * k / (n - 1)
        if k in (0, n - 1):
            u = a if k == 0 else b
        else:
            ap = GCPnts_AbscissaPoint(ad, s, a)
            u = ap.Parameter() if ap.IsDone() else a + (b - a) * k / (n - 1)
        out.append(_xyz(ad.Value(u)))
    pts = _V(out)
    if edge.Orientation() == TopAbs_REVERSED:
        pts = pts[::-1]
    return pts


class _Side:
    """One side of a blend: an edge on a face, with the face's derivatives across the edge."""

    def __init__(self, edge, face, n: int):
        self.face = face
        self.srf = BRep_Tool.Surface_s(face)
        self.pts = edge_points(edge, n)
        self.n = n

    def reverse(self) -> None:
        self.pts = self.pts[::-1].copy()

    def _raw(self, k: int):
        """(point, S_w, S_ww, leaves the face) at sample k, w across the edge either way."""
        P = self.pts[k]
        pr = GeomAPI_ProjectPointOnSurf(gp_Pnt(*P), self.srf)
        if not pr.NbPoints():
            raise SurfaceOpError("a blend edge does not lie on its surface")
        u, v = pr.LowerDistanceParameters()
        p, su, sv, suu, svv, suv = gp_Pnt(), gp_Vec(), gp_Vec(), gp_Vec(), gp_Vec(), gp_Vec()
        self.srf.D2(u, v, p, su, sv, suu, svv, suv)
        Su, Sv = _vec(su), _vec(sv)
        t = self.pts[min(k + 1, self.n - 1)] - self.pts[max(k - 1, 0)]
        d = np.cross(np.cross(Su, Sv), t)
        if np.linalg.norm(d) < 1e-12:
            raise SurfaceOpError("the surface is degenerate at a blend edge")
        w, *_ = np.linalg.lstsq(np.stack([Su, Sv], axis=1), d, rcond=None)
        size = max(np.linalg.norm(Su), np.linalg.norm(Sv), 1e-12)
        step = 1e-3 * np.linalg.norm(t) / size / max(np.linalg.norm(w), 1e-12)
        inside = BRepClass_FaceClassifier(self.face, gp_Pnt2d(u + step * w[0], v + step * w[1]), 1e-9).State()
        Sw = w[0] * Su + w[1] * Sv
        Sww = w[0] ** 2 * _vec(suu) + 2 * w[0] * w[1] * _vec(suv) + w[1] ** 2 * _vec(svv)
        return P, Sw, Sww, inside != TopAbs_IN

    def crosses(self) -> list:
        """(point, S_w, S_ww) going out of the face at every sample.

        Which way is out is asked of the face at the middle of the edge only (at
        its ends a small step can leave the face either way, past a corner); from
        there each sample keeps the direction of its neighbour."""
        raw = [self._raw(k) for k in range(self.n)]
        out = [None] * self.n
        mid = self.n // 2
        P, Sw, Sww, leaves = raw[mid]
        out[mid] = (P, Sw if leaves else -Sw, Sww)
        for order in (range(mid + 1, self.n), range(mid - 1, -1, -1)):
            for k in order:
                prev = out[k - 1] if k > mid else out[k + 1]
                P, Sw, Sww, _ = raw[k]
                out[k] = (P, Sw if np.dot(Sw, prev[1]) >= 0 else -Sw, Sww)
        return out


# =============================================================================
# BLEND
# =============================================================================


def blend(side1: tuple, side2: tuple, cont: str = "G1", bulge: float = 1.0, samples: int = 61):
    """A surface between (edge1, face1) and (edge2, face2). Returns (face, worst normal angle in degrees
    where it meets the two surfaces)."""
    if cont not in ("G1", "G2"):
        raise SurfaceOpError("the smoothness is G1 or G2")
    if bulge <= 0:
        raise SurfaceOpError("the bulge must be greater than 0")
    A = _Side(*side1, samples)
    B = _Side(*side2, samples)
    straight = np.linalg.norm(A.pts[0] - B.pts[0]) + np.linalg.norm(A.pts[-1] - B.pts[-1])
    crossed = np.linalg.norm(A.pts[0] - B.pts[-1]) + np.linalg.norm(A.pts[-1] - B.pts[0])
    if crossed < straight:
        B.reverse()
    deg = 3 if cont == "G1" else 5
    rows = []
    ca, cb = A.crosses(), B.crosses()
    for k in range(samples):
        Pa, Da, DDa = ca[k]
        Pb, Db, DDb = cb[k]
        chord = float(np.linalg.norm(Pb - Pa))
        if chord < 1e-9:
            raise SurfaceOpError("the two edges touch; a blend needs a gap between them")
        lam = bulge * chord
        aa, ab = lam / np.linalg.norm(Da), lam / np.linalg.norm(Db)
        d1a, d1b = aa * Da, ab * Db
        if deg == 3:
            ctrl = [Pa, Pa + d1a / 3, Pb + d1b / 3, Pb]
        else:
            d2a, d2b = aa * aa * DDa, ab * ab * DDb
            ctrl = [Pa, Pa + d1a / 5, Pa + 2 * d1a / 5 + d2a / 20, Pb + 2 * d1b / 5 + d2b / 20, Pb + d1b / 5, Pb]
        rows.append(ctrl)
    # one surface: across the gap exactly the Bezier rows; along the edges each row of control
    # points is interpolated with the same parameters, so the rows stay compatible
    net = _V(rows)  # [k, j, 3]
    chord = np.linalg.norm(np.diff(net, axis=0), axis=2).mean(axis=1)
    t = np.concatenate([[0.0], np.cumsum(chord)])
    t /= t[-1]
    curves = [_interpolate(net[:, j, :], t) for j in range(deg + 1)]
    ks, ms = nb.knots(curves[0])
    poles = [[nb._xyz(c.Pole(i)) for c in curves] for i in range(1, curves[0].NbPoles() + 1)]
    srf = nb.make_surface(poles, None, curves[0].Degree(), deg, ks, ms, [0.0, 1.0], [deg + 1, deg + 1])
    face = BRepBuilderAPI_MakeFace(srf, 1e-6).Face()
    worst = 0.0
    for side, v_end in ((A, 0.0), (B, 1.0)):
        for k in range(2, samples - 2, 4):
            n_blend = _normal(srf, side.pts[k])
            n_face = _normal(side.srf, side.pts[k])
            ang = math.degrees(math.acos(min(1.0, abs(float(np.dot(n_blend, n_face))))))
            worst = max(worst, ang)
    return face, worst


def _interpolate(points: np.ndarray, params: np.ndarray):
    """A cubic B-spline through the points at the given parameters (the knots follow the parameters only)."""
    from OCP.GeomAPI import GeomAPI_Interpolate

    try:  # OCP 8
        from OCP.collections import HArray1_double as _HReal
        from OCP.collections import HArray1_gp_Pnt as _HPnt
    except ImportError:  # OCP 7.x
        from OCP.TColgp import TColgp_HArray1OfPnt as _HPnt  # type: ignore[no-redef]
        from OCP.TColStd import TColStd_HArray1OfReal as _HReal  # type: ignore[no-redef]

    pts, prm = _HPnt(1, len(points)), _HReal(1, len(points))
    for i, (q, u) in enumerate(zip(points, params), 1):
        pts.SetValue(i, gp_Pnt(*map(float, q)))
        prm.SetValue(i, float(u))
    it = GeomAPI_Interpolate(pts, prm, False, 1e-9)
    it.Perform()
    if not it.IsDone():
        raise SurfaceOpError("the blend could not be fitted along the edges")
    return it.Curve()


def _normal(srf, P) -> np.ndarray:
    pr = GeomAPI_ProjectPointOnSurf(gp_Pnt(*P), srf)
    u, v = pr.LowerDistanceParameters()
    p, su, sv = gp_Pnt(), gp_Vec(), gp_Vec()
    srf.D1(u, v, p, su, sv)
    n = np.cross(_vec(su), _vec(sv))
    return n / max(np.linalg.norm(n), 1e-300)


# =============================================================================
# EXTEND
# =============================================================================

SIDES = ("U0", "U1", "V0", "V1", "ALL")


def extend(g, length: float, side: str):
    """A copy of B-spline surface ``g`` carried on by ``length`` past one side (U0 = start of u ...) or all four."""
    if length <= 0:
        raise SurfaceOpError("the length must be greater than 0")
    if side not in SIDES:
        raise SurfaceOpError(f"the side is one of {', '.join(SIDES)}")
    if g.IsUPeriodic() or g.IsVPeriodic():
        raise SurfaceOpError("a surface that closes on itself has no edge to extend there")
    u0, u1, v0, v1 = g.Bounds()
    sides = ("U0", "U1", "V0", "V1") if side == "ALL" else (side,)

    def speed(along_u: bool, at: float) -> float:
        """Mean |dS/du| (or dv) along the side at parameter ``at``."""
        tot = 0.0
        for k in range(9):
            p, su, sv = gp_Pnt(), gp_Vec(), gp_Vec()
            if along_u:
                g.D1(at, v0 + (v1 - v0) * k / 8, p, su, sv)
                tot += su.Magnitude()
            else:
                g.D1(u0 + (u1 - u0) * k / 8, at, p, su, sv)
                tot += sv.Magnitude()
        return max(tot / 9, 1e-12)

    a, b, c, d = u0, u1, v0, v1
    if "U0" in sides:
        a = u0 - length / speed(True, u0)
    if "U1" in sides:
        b = u1 + length / speed(True, u1)
    if "V0" in sides:
        c = v0 - length / speed(False, v0)
    if "V1" in sides:
        d = v1 + length / speed(False, v1)
    nu = max(30, 3 * g.NbUPoles())
    nv = max(30, 3 * g.NbVPoles())
    # a B-spline evaluated past its ends carries on its end spans' polynomials
    grid = _V([[_xyz(g.Value(a + (b - a) * i / (nu - 1), c + (d - c) * j / (nv - 1))) for j in range(nv)]
               for i in range(nu)])
    from .surfaces import fit

    return fit(grid.tolist())


# =============================================================================
# TRIM
# =============================================================================


def trim(face, curve_shape, point, keep: bool):
    """Split a face by a curve projected onto it along its normal; keep (or remove) the piece nearest ``point``.
    Returns (shape, pieces made)."""
    from OCP.BRepFeat import BRepFeat_SplitShape
    from OCP.BRepOffsetAPI import BRepOffsetAPI_NormalProjection
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_EDGE

    proj = BRepOffsetAPI_NormalProjection(face)
    proj.Add(curve_shape)
    try:
        proj.Build()
    except Exception:  # noqa: BLE001
        raise SurfaceOpError("the curve could not be laid onto the surface") from None
    if not proj.IsDone():
        raise SurfaceOpError("the curve could not be laid onto the surface")
    projected = proj.Shape()
    split = BRepFeat_SplitShape(face)
    ex = TopExp_Explorer(projected, TopAbs_EDGE)
    n = 0
    while ex.More():
        e = nb._as_edge(ex.Current())
        split.Add(e, face)
        n += 1
        ex.Next()
    if not n:
        raise SurfaceOpError("the curve does not lie over the surface (nothing to cut with)")
    try:
        split.Build()
    except Exception:  # noqa: BLE001
        raise SurfaceOpError("the curve does not cut the surface into pieces; it must cross it from edge to edge "
                             "or close into a loop on it") from None
    pieces = [nb._as_face(f) for f in nb._subs(split.Shape(), TopAbs_FACE)]
    if len(pieces) < 2:
        raise SurfaceOpError("the curve does not cut the surface into pieces; it must cross it from edge to edge "
                             "or close into a loop on it")
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex

    vtx = BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex()
    dists = []
    for f in pieces:
        ds = BRepExtrema_DistShapeShape(vtx, f)
        dists.append(ds.Value() if ds.IsDone() else float("inf"))
    near = int(np.argmin(dists))
    chosen = [pieces[near]] if keep else [f for i, f in enumerate(pieces) if i != near]
    if len(chosen) == 1:
        return chosen[0], len(pieces), split
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing

    sew = BRepBuilderAPI_Sewing(1e-6)
    for f in chosen:
        sew.Add(f)
    sew.Perform()
    return sew.SewedShape(), len(pieces), split


# =============================================================================
# Replace or move a face of a solid
# =============================================================================


def _centre(face) -> np.ndarray:
    g = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, g)
    return _xyz(g.CentreOfMass())


def _outward(face, P) -> np.ndarray:
    """Outward normal of a solid's face at (near) point P."""
    srf = BRepAdaptor_Surface(face)
    pr = GeomAPI_ProjectPointOnSurf(gp_Pnt(*P), BRep_Tool.Surface_s(face))
    u, v = pr.LowerDistanceParameters()
    p, su, sv = gp_Pnt(), gp_Vec(), gp_Vec()
    srf.D1(u, v, p, su, sv)
    n = np.cross(_vec(su), _vec(sv))
    n /= max(np.linalg.norm(n), 1e-300)
    return -n if face.Orientation() == TopAbs_REVERSED else n


def replace_face(solid, face, new_face, size: float):
    """The solid with ``face`` replaced by the surface of ``new_face`` (extended as far as needed).

    Returns (shape, list of makers in order) for ID history."""
    c = _centre(face)
    n_out = _outward(face, c)
    tool_srf = BRep_Tool.Surface_s(new_face)
    pr = GeomAPI_ProjectPointOnSurf(gp_Pnt(*c), tool_srf)
    if not pr.NbPoints():
        raise SurfaceOpError("the new surface is not across from the face (nothing to project onto)")
    target = _xyz(pr.NearestPoint())
    reach = float(np.dot(target - c, n_out))
    makers = []
    shape = solid
    if reach > -1e-9:  # the new surface lies outside: grow the solid along the face first
        prism = BRepPrimAPI_MakePrism(face, gp_Vec(*(n_out * (abs(reach) + 0.25 * size)))).Shape()
        fuse = BRepAlgoAPI_Fuse(shape, prism)
        fuse.Build()
        if not fuse.IsDone():
            raise SurfaceOpError("the solid could not be grown towards the new surface")
        shape = fuse.Shape()
        makers.append(fuse)
    # split the (grown) solid by the surface and keep what lies on the solid's side of it; the surface
    # as given first, then carried on past its edges if it does not reach across
    for tool in (new_face, _big_face(tool_srf, new_face, size)):
        out = _cut_back(shape, tool, target, n_out, size)
        if out is not None:
            kept, splitter = out
            makers.append(splitter)
            return kept, makers
    raise SurfaceOpError("the new surface does not cut cleanly across the body there")


def _cut_back(shape, tool, target, n_out, size):
    """(the pieces of ``shape`` on the inner side of ``tool``, as one solid; the splitter) or None."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Splitter
    from OCP.TopAbs import TopAbs_SOLID
    try:  # OCP 7.x
        from OCP.TopTools import TopTools_ListOfShape
    except ImportError:  # OCP 8.x
        from OCP.collections import List_TopoDS_Shape as TopTools_ListOfShape

    from .robust import is_valid, solids

    sp = BRepAlgoAPI_Splitter()
    args, tools = TopTools_ListOfShape(), TopTools_ListOfShape()
    args.Append(shape)
    tools.Append(tool)
    sp.SetArguments(args)
    sp.SetTools(tools)
    sp.Build()
    if not sp.IsDone():
        return None
    pieces = nb._subs(sp.Shape(), TopAbs_SOLID)
    if len(pieces) < 2:
        return None
    srf = BRep_Tool.Surface_s(tool)
    n_tool = _normal(srf, target)
    if np.dot(n_tool, n_out) < 0:
        n_tool = -n_tool
    keep = []
    for so_ in pieces:
        g = GProp_GProps()
        BRepGProp.VolumeProperties_s(so_, g)
        c = _xyz(g.CentreOfMass())
        pr = GeomAPI_ProjectPointOnSurf(gp_Pnt(*c), srf)
        if not pr.NbPoints():
            continue
        q = _xyz(pr.NearestPoint())
        n_here = _normal(srf, q)
        if np.dot(n_here, n_tool) < 0:
            n_here = -n_here
        if np.dot(c - q, n_here) < 0:
            keep.append(so_)
    if len(keep) != 1:
        return None
    if not is_valid(keep[0]) or len(solids(keep[0])) != 1:
        return None
    return keep[0], sp


def _big_face(srf, face, size: float):
    """A face on the surface large enough to cut across the whole solid."""
    from OCP.Geom import Geom_Plane

    if isinstance(srf, Geom_Plane):
        return BRepBuilderAPI_MakeFace(srf.Pln(), -10 * size, 10 * size, -10 * size, 10 * size).Face()
    try:
        g = nb.surface_of(face, need_whole=False)[0]
        g = extend(g, 2 * size, "ALL") if not (g.IsUPeriodic() or g.IsVPeriodic()) else g
        return BRepBuilderAPI_MakeFace(g, 1e-6).Face()
    except CurveError:
        u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
        return BRepBuilderAPI_MakeFace(srf, u0, u1, v0, v1, 1e-6).Face()


def moved(face, d) -> object:
    t = gp_Trsf()
    t.SetTranslation(gp_Vec(*map(float, d)))
    return nb._as_face(BRepBuilderAPI_Transform(face, t, True).Shape())


class SurfaceMatch:
    """Face history for MOVEFACE / REPLACEFACE, found from the geometry of the result.

    Every old face goes to the new faces that lie on its surface (the faces
    around stretch or shrink but stay on their surfaces); the replaced faces
    go to the new faces on the new surfaces. Edges and vertices are left to
    the model's match by place and size."""

    def __init__(self, old_shape, new_shape, replaced: list[tuple]):
        self.new_faces = [nb._as_face(f) for f in nb._subs(new_shape, TopAbs_FACE)]
        self.samples = [_face_samples(f) for f in self.new_faces]
        self.replaced = replaced  # (old face, new surface face)
        self.size = max(1e-9, _diag(new_shape))

    def _on(self, srf, k: int) -> bool:
        tol = 1e-6 * self.size + 1e-7
        for q in self.samples[k]:
            pr = GeomAPI_ProjectPointOnSurf(gp_Pnt(*q), srf)
            if not pr.NbPoints() or pr.LowerDistance() > tol:
                return False
        return True

    def Modified(self, old):  # noqa: N802 - the OCCT maker interface
        if old.ShapeType() != TopAbs_FACE:
            return []
        face = nb._as_face(old)
        srf = None
        for a, tool in self.replaced:
            if a.IsSame(face):
                srf = BRep_Tool.Surface_s(tool)
        if srf is None:
            srf = BRep_Tool.Surface_s(face)
        hits = [self.new_faces[k] for k in range(len(self.new_faces)) if self._on(srf, k)]
        return hits

    def IsDeleted(self, old) -> bool:  # noqa: N802
        return old.ShapeType() == TopAbs_FACE and not self.Modified(old)


def _face_samples(face) -> list:
    """A few points inside a face (its centre and points towards its corners)."""
    u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
    srf = BRep_Tool.Surface_s(face)
    out = []
    for a, b in ((0.5, 0.5), (0.3, 0.3), (0.7, 0.7), (0.3, 0.7), (0.7, 0.3)):
        u, v = u0 + (u1 - u0) * a, v0 + (v1 - v0) * b
        fc = BRepClass_FaceClassifier(face, gp_Pnt2d(u, v), 1e-9)
        if fc.State() == TopAbs_IN:
            out.append(_xyz(srf.Value(u, v)))
    if not out:
        out.append(_centre(face))
    return out


def _diag(shape) -> float:
    from .robust import diagonal

    return diagonal(shape)
