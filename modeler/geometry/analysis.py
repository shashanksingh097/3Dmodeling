"""Surface analysis: how smooth the joins are, how curved the faces are, and
whether faces have enough draft to come out of a mould.

Each analysis has two outputs:

* numbers in words (``joins``, ``curvature``, ``draft``), so a script or an
  assistant can check a shape without looking at it;
* a coloured mesh (``coloured_mesh``) for the view: zebra stripes, a
  curvature map, or a draft map.

How the joins are judged: along every edge between two faces, at a few
points, the two faces' normals are compared (a crease if they differ) and
so is each face's curvature straight across the edge (tangent only, G1, if
it jumps; curvature continuous, G2, if it does not). This is what zebra
stripes show by eye: stripes that break at a crease, kink at a G1 join and
flow straight on over a G2 join.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
from OCP.GeomLProp import GeomLProp_SLProps
from OCP.gp import gp_Dir, gp_Pnt, gp_Vec
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS

from . import robust

_as_face = getattr(TopoDS, "Face_s", None) or TopoDS.Face
_as_edge = getattr(TopoDS, "Edge_s", None) or TopoDS.Edge

try:  # OCP 7.x
    from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape as _AncestorMap
except ImportError:  # OCP 8.x
    from OCP.collections import (  # type: ignore[no-redef]
        IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as _AncestorMap,
    )

MODES = ("ZEBRA", "CURVATURE", "GAUSS", "DRAFT")

CREASE_DEG = 0.25  # normals further apart than this across an edge: a crease
G2_REL = 0.1  # curvature across an edge may differ by this much (relative) and still count as G2


# =============================================================================
# Curvature at a point of a face
# =============================================================================


@dataclass
class SurfPoint:
    p: np.ndarray
    n: np.ndarray  # unit normal, pointing out of the face (its orientation counted)
    k1: float  # principal curvatures, signed so that a bulge (seen from outside the face) is positive
    k2: float
    d1: np.ndarray | None  # direction of k1
    ok: bool = True

    @property
    def mean(self) -> float:
        return 0.5 * (self.k1 + self.k2)

    @property
    def gauss(self) -> float:
        return self.k1 * self.k2

    def across(self, t: np.ndarray) -> float:
        """Normal curvature in the direction square to t (t: along an edge) in the tangent plane."""
        c = np.cross(self.n, t)
        nc = np.linalg.norm(c)
        if nc < 1e-12 or self.d1 is None:
            return self.mean
        c /= nc
        cos = float(np.dot(c, self.d1))
        return self.k1 * cos * cos + self.k2 * (1 - cos * cos)


def surf_point(srf, u: float, v: float, reversed_: bool) -> SurfPoint:
    pr = GeomLProp_SLProps(srf, u, v, 2, 1e-9)
    p = pr.Value()
    P = np.array([p.X(), p.Y(), p.Z()])
    if not pr.IsNormalDefined():
        return SurfPoint(P, np.array([0.0, 0.0, 1.0]), math.nan, math.nan, None, ok=False)
    n = pr.Normal()
    N = np.array([n.X(), n.Y(), n.Z()])
    sign = -1.0 if reversed_ else 1.0
    if not pr.IsCurvatureDefined():
        return SurfPoint(P, sign * N, math.nan, math.nan, None, ok=False)
    k1, k2 = pr.MaxCurvature(), pr.MinCurvature()
    d1 = None
    if not pr.IsUmbilic():
        a, b = gp_Dir(), gp_Dir()
        pr.CurvatureDirections(a, b)
        d1 = np.array([a.X(), a.Y(), a.Z()])
    # OCCT's curvature is positive where the surface bends towards its normal
    # (a hollow); a bulge is counted positive here. A reversed face's normal
    # points the other way, and so does the sign.
    return SurfPoint(P, sign * N, -sign * k1, -sign * k2, d1)


class _FaceEval:
    def __init__(self, face):
        self.face = face
        self.srf = BRep_Tool.Surface_s(face)
        self.rev = face.Orientation() == TopAbs_REVERSED

    def at_point(self, q) -> SurfPoint | None:
        pj = GeomAPI_ProjectPointOnSurf(gp_Pnt(*map(float, q)), self.srf)
        if not pj.NbPoints():
            return None
        u, v = pj.LowerDistanceParameters()
        return surf_point(self.srf, u, v, self.rev)


# =============================================================================
# Joins between faces (the words behind zebra stripes)
# =============================================================================


@dataclass
class Join:
    edge: int  # edge ID
    angle: float  # worst angle between the two faces' normals, degrees
    k_a: float  # curvature across the edge on each side, where they differ most
    k_b: float

    @property
    def kind(self) -> str:
        if self.angle > CREASE_DEG:
            return "crease"
        if abs(self.k_a - self.k_b) > G2_REL * max(abs(self.k_a), abs(self.k_b)) + 1e-9:
            return "G1"
        return "G2"


def joins(shape, edge_ids: dict, samples: int = 9) -> list[Join]:
    """Each edge between two different faces, judged at ``samples`` points.
    ``edge_ids`` maps an edge shape's hash key to its ID (see ids_of)."""
    m = _AncestorMap()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, m)
    out = []
    for i in range(1, m.Extent() + 1):
        edge = _as_edge(m.FindKey(i))
        faces = list(m.FindFromIndex(i))
        uniq = []
        for f in faces:
            if not any(f.IsSame(g) for g in uniq):
                uniq.append(f)
        if len(uniq) != 2 or BRep_Tool.Degenerated_s(edge):
            continue
        gid = _lookup(edge_ids, edge)
        if gid is None:
            continue
        fa, fb = _FaceEval(_as_face(uniq[0])), _FaceEval(_as_face(uniq[1]))
        c = BRepAdaptor_Curve(edge)
        t0, t1 = c.FirstParameter(), c.LastParameter()
        worst_angle, worst_k = 0.0, (0.0, 0.0)
        for s in range(samples):
            t = t0 + (t1 - t0) * (s + 0.5) / samples
            p, v = gp_Pnt(), gp_Vec()
            c.D1(t, p, v)
            T = np.array([v.X(), v.Y(), v.Z()])
            if np.linalg.norm(T) < 1e-12:
                continue
            T /= np.linalg.norm(T)
            q = (p.X(), p.Y(), p.Z())
            a, b = fa.at_point(q), fb.at_point(q)
            if a is None or b is None or not (a.ok and b.ok):
                continue
            ang = math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(a.n, b.n))))))
            worst_angle = max(worst_angle, ang)
            ka, kb = a.across(T), b.across(T)
            if abs(ka - kb) > abs(worst_k[0] - worst_k[1]):
                worst_k = (ka, kb)
        out.append(Join(gid, worst_angle, *worst_k))
    out.sort(key=lambda j: j.edge)
    return out


def ids_of(model, bid: int, kind: str) -> dict:
    """{hash: [(shape, id), ...]} for the body's entities of one kind."""
    out: dict = {}
    for gid in model.body(bid).entity_ids[kind]:
        sh = model.entity_shape(kind, gid)
        out.setdefault(_hash(sh), []).append((sh, gid))
    return out


def _hash(sh) -> int:
    h = getattr(sh, "HashCode", None)
    if h is not None:
        try:
            return h(1 << 30)
        except TypeError:
            pass
    return hash(sh)


def _lookup(ids: dict, sh):
    for other, gid in ids.get(_hash(sh), []):
        if other.IsSame(sh):
            return gid
    for lst in ids.values():  # (a hash that differs between copies of the same shape)
        for other, gid in lst:
            if other.IsSame(sh):
                return gid
    return None


def _ids_list(ids: list[int], limit: int = 12) -> str:
    s = ", ".join(map(str, ids[:limit]))
    return s + (f" and {len(ids) - limit} more" if len(ids) > limit else "")


def describe_joins(js: list[Join]) -> str:
    if not js:
        return "no joins between faces (one face, or faces that do not touch)"
    g2 = [j for j in js if j.kind == "G2"]
    g1 = [j for j in js if j.kind == "G1"]
    cr = [j for j in js if j.kind == "crease"]
    parts = [f"{len(js)} join{'s' if len(js) != 1 else ''} between faces:"]
    parts.append(f"{len(g2)} smooth in curvature (G2)" + (f": edges {_ids_list([j.edge for j in g2])}" if g2 and
                                                           (g1 or cr) and len(g2) <= 6 else ""))
    if g1:
        w = max(g1, key=lambda j: abs(j.k_a - j.k_b))
        parts.append(f"{len(g1)} tangent only (G1, the curvature jumps): edges {_ids_list([j.edge for j in g1])} "
                     f"(worst on edge {w.edge}: curvature {_g(w.k_a)} meets {_g(w.k_b)})")
    else:
        parts.append("0 tangent only (G1)")
    if cr:
        w = max(cr, key=lambda j: j.angle)
        parts.append(f"{len(cr)} creased (a sharp edge): edges {_ids_list([j.edge for j in cr])} "
                     f"(up to {w.angle:.3g} degrees, edge {w.edge})")
    else:
        parts.append("0 creased")
    return parts[0] + " " + "; ".join(parts[1:])


# =============================================================================
# A mesh with values at its nodes
# =============================================================================


@dataclass
class Mesh:
    nodes: np.ndarray  # (n, 3)
    normals: np.ndarray  # (n, 3), out of the faces
    tris: np.ndarray  # (m, 3) node indices
    face_of_tri: np.ndarray  # (m,) face index (order of TopExp_Explorer)
    k1: np.ndarray  # (n,)
    k2: np.ndarray
    faces: list = field(default_factory=list)

    def tri_areas(self) -> np.ndarray:
        a, b, c = (self.nodes[self.tris[:, i]] for i in range(3))
        return 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)


def mesh(shape, fine: float = 1.0) -> Mesh:
    """A fine mesh of the shape's faces, with normals and curvatures at the nodes."""
    diag = max(robust.diagonal(shape), 1e-6)
    nodes, normals, tris, fot, k1s, k2s, faces = [], [], [], [], [], [], []
    base = 0
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    fi = 0
    while ex.More():
        original = _as_face(ex.Current())
        ex.Next()
        # meshing writes into the shape: mesh a copy of each face, so the model's own stays as it was
        face = _as_face(BRepBuilderAPI_Copy(original).Shape())
        BRepMesh_IncrementalMesh(face, diag / (300.0 * fine), False, 0.05 / fine, True)
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is None or tri.NbNodes() == 0:
            faces.append(original)
            fi += 1
            continue
        trsf = loc.Transformation()
        fe = _FaceEval(face)
        has_uv = tri.HasUVNodes()
        for i in range(1, tri.NbNodes() + 1):
            q = tri.Node(i).Transformed(trsf)
            sp = None
            if has_uv:
                uv = tri.UVNode(i)
                sp = surf_point(fe.srf, uv.X(), uv.Y(), fe.rev)
            if sp is None:
                sp = fe.at_point((q.X(), q.Y(), q.Z())) or SurfPoint(np.zeros(3), np.array([0, 0, 1.0]), math.nan,
                                                                       math.nan, None, ok=False)
            nodes.append((q.X(), q.Y(), q.Z()))
            normals.append(sp.n)
            k1s.append(sp.k1)
            k2s.append(sp.k2)
        rev = fe.rev
        for i in range(1, tri.NbTriangles() + 1):
            a, b, c = tri.Triangle(i).Get()
            if rev:
                b, c = c, b
            tris.append((base + a - 1, base + b - 1, base + c - 1))
            fot.append(fi)
        faces.append(original)
        base += tri.NbNodes()
        fi += 1
    if not tris:
        raise ValueError("the shape has no faces to analyse")
    return Mesh(np.array(nodes, float), np.array(normals, float), np.array(tris, int), np.array(fot, int),
                np.array(k1s, float), np.array(k2s, float), faces)


# =============================================================================
# Curvature and draft in words
# =============================================================================


def _tri_mean(m: Mesh, values: np.ndarray) -> np.ndarray:
    return values[m.tris].mean(axis=1)


def _g(x: float) -> str:
    return f"{x:.4g}" if abs(x) >= 5e-13 else "0"


def curvature(m: Mesh, gauss: bool = False) -> str:
    """In words: the range of mean (or Gaussian) curvature, and the tightest bend.
    Curvature is positive where the surface bulges out, negative where it is hollow."""
    ok = ~(np.isnan(m.k1) | np.isnan(m.k2))
    if not ok.any():
        return "the curvature is not defined anywhere on it"
    areas = m.tri_areas()
    tri_ok = ok[m.tris].all(axis=1)
    areas = np.where(tri_ok, areas, 0.0)
    total = max(float(areas.sum()), 1e-300)
    k1, k2 = np.where(ok, m.k1, 0.0), np.where(ok, m.k2, 0.0)
    kmax = np.maximum(np.abs(k1), np.abs(k2))
    i = int(np.argmax(kmax))
    tight = (f"tightest bend: radius {1 / kmax[i]:.4g} at ({', '.join(f'{x:.4g}' for x in m.nodes[i])})"
             if kmax[i] > 1e-9 else "it is flat everywhere")
    pct = lambda mask: 100.0 * float(areas[mask].sum()) / total  # noqa: E731
    if gauss:
        K = k1 * k2
        Kt = _tri_mean(m, K)
        scale = max(float(np.percentile(np.abs(K[ok]), 99)), 1e-12)
        flat = np.abs(Kt) <= 1e-3 * scale
        pos = (Kt > 0) & ~flat
        neg = (Kt < 0) & ~flat
        return (f"Gaussian curvature from {_g(K[ok].min())} to {_g(K[ok].max())}; {pct(pos):.0f}% of the area is "
                f"curved both ways alike (a dome or a dish), {pct(neg):.0f}% is saddle-shaped, {pct(flat):.0f}% is "
                f"flat or bent one way only (a cylinder or a cone); {tight}")
    H = 0.5 * (k1 + k2)
    Ht = _tri_mean(m, H)
    flat_t = (np.maximum(np.abs(k1), np.abs(k2)) < 1e-6)[m.tris].all(axis=1)
    return (f"mean curvature from {_g(H[ok].min())} to {_g(H[ok].max())} (positive bulges out, negative is hollow; "
            f"area-weighted average {_g(float((Ht * areas).sum()) / total)}); {pct(flat_t & tri_ok):.0f}% of the "
            f"area is flat; {tight}")


def draft_classes(m: Mesh, d, min_deg: float) -> np.ndarray:
    """Per node: +1 can be pulled along +d (draft at least min_deg), -1 along -d, 0 too steep."""
    d = np.asarray(d, float)
    d = d / np.linalg.norm(d)
    s = m.normals @ d
    lim = math.sin(math.radians(min_deg))
    return np.where(s >= lim - 1e-9, 1, np.where(s <= -lim + 1e-9, -1, 0))


def draft(m: Mesh, d, min_deg: float, face_ids: list[int | None]) -> str:
    cls = draft_classes(m, d, min_deg)
    areas = m.tri_areas()
    total = float(areas.sum())
    tcls = cls[m.tris]
    up = (tcls == 1).all(axis=1)
    down = (tcls == -1).all(axis=1)
    steep = ~(up | down)
    bad_faces = sorted({face_ids[f] for f in m.face_of_tri[steep] if face_ids[f] is not None})
    pct = lambda mask: 100.0 * float(areas[mask].sum()) / total  # noqa: E731
    dd = np.asarray(d, float) / np.linalg.norm(d)
    dtxt = ", ".join(f"{x:.4g}" for x in dd)
    msg = (f"pulled along ({dtxt}) with at least {min_deg:g} degree{'' if min_deg == 1 else 's'} of draft: {pct(up):.0f}% of the area comes "
           f"out towards +, {pct(down):.0f}% towards -, {pct(steep):.0f}% is too steep")
    if bad_faces:
        msg += f" (faces {_ids_list(bad_faces)})"
    return msg


# =============================================================================
# Colours for the view
# =============================================================================


def _diverging(x: np.ndarray) -> np.ndarray:
    """x in [-1, 1] -> blue (negative), green (0), red (positive)."""
    x = np.clip(x, -1.0, 1.0)
    r = np.clip(x * 1.6, 0, 1)
    b = np.clip(-x * 1.6, 0, 1)
    g = 1.0 - np.abs(x) * 0.85
    return np.stack([r * 0.95 + 0.05, g * 0.85 + 0.1, b * 0.95 + 0.05], axis=1)


def colours(m: Mesh, mode: str, d=(0.0, 0.0, 1.0), min_deg: float = 1.0, stripes: int = 24) -> np.ndarray:
    """(n, 3) RGB in [0, 1] for each node."""
    if mode == "ZEBRA":
        e = np.asarray(d, float)
        e = e / np.linalg.norm(e)
        ang = np.arccos(np.clip(m.normals @ e, -1.0, 1.0))  # 0..pi
        s = np.sin(ang * stripes)
        w = 0.5 + 0.5 * np.tanh(s * 4.0)  # sharp-edged stripes
        g = 0.08 + 0.88 * w
        return np.stack([g, g, g], axis=1)
    if mode in ("CURVATURE", "GAUSS"):
        v = m.k1 * m.k2 if mode == "GAUSS" else 0.5 * (m.k1 + m.k2)
        v = np.nan_to_num(v)
        scale = float(np.percentile(np.abs(v), 95))
        if scale < 1e-12:
            return _diverging(np.zeros_like(v))
        return _diverging(v / scale)
    if mode == "DRAFT":
        cls = draft_classes(m, d, min_deg)
        out = np.empty((len(cls), 3))
        out[cls == 1] = (0.2, 0.75, 0.3)
        out[cls == -1] = (0.25, 0.45, 0.95)
        out[cls == 0] = (0.95, 0.2, 0.15)
        return out
    raise ValueError(mode)


def face_ids(model, bid: int, m: Mesh) -> list[int | None]:
    ids = ids_of(model, bid, "FACE")
    return [_lookup(ids, f) for f in m.faces]
