"""Mesh bodies: big triangle meshes that stay meshes.

A faceted body (an imported STL turned into a solid) has one B-rep face per
triangle, which gets slow past about 100,000 triangles. A **mesh body** keeps
its triangles as one triangulation instead: the body's shape is a single
OCCT face that carries only a ``Poly_Triangulation`` and no surface. OCCT can
draw it, pick it, measure its volume and write it to STL, and it is one face
with one face ID, so the model, the tree and the views need nothing new.

Booleans between mesh bodies (and between a mesh body and a solid, which is
meshed first) run in ``manifold3d``, which is fast and always gives a closed
mesh. Smoothing, refining and simplifying work on the triangles in numpy or
in manifold3d. The arrays of a mesh are cached, so repeated reads are cheap.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

import numpy as np
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.gp import gp_Pnt, gp_Trsf
from OCP.Poly import Poly_Triangle, Poly_Triangulation
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Face, TopoDS_Shape

_as_face = getattr(TopoDS, "Face_s", None) or TopoDS.Face
_surface = getattr(BRep_Tool, "Surface_s", None) or BRep_Tool.Surface
_triangulation = getattr(BRep_Tool, "Triangulation_s", None) or BRep_Tool.Triangulation

# a mesh body this big is still fine to draw and to combine; past it, say so
MAX_MESH_BODY_TRIANGLES = 5_000_000


class MeshError(Exception):
    """A mesh operation that cannot be done (open mesh in a boolean, nothing left ...)."""


@dataclass(frozen=True)
class MeshInfo:
    triangles: int
    points: int
    closed: bool
    volume: float
    area: float


# ---- the shape that holds a mesh ---------------------------------------------
_CACHE: OrderedDict = OrderedDict()  # shape hash -> (shape, points, tris); the shape keeps the hash valid
_CACHE_SIZE = 48
_SOURCE: OrderedDict = OrderedDict()  # shape hash -> (shape, shown node -> point index, or None if the same)


def _remember(shape: TopoDS_Shape, pts: np.ndarray, tris: np.ndarray) -> None:
    key = hash(shape)
    _CACHE[key] = (shape, pts, tris)
    _CACHE.move_to_end(key)
    while len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)


def make_shape(points: np.ndarray, tris: np.ndarray, remember: bool = True) -> TopoDS_Face:
    """A mesh-body shape: one face carrying these triangles (points N x 3, tris M x 3, 0-based).
    ``remember=False`` for a shape only drawn for a moment (a preview), kept out of the cache."""
    pts = np.ascontiguousarray(points, dtype=float).reshape(-1, 3)
    t = np.ascontiguousarray(tris, dtype=np.int64).reshape(-1, 3)
    if len(t) == 0:
        raise MeshError("the mesh has no triangles")
    # the stored triangles have their points split along sharp edges, so the
    # view shades a sharp edge sharp; arrays() joins them again
    shown_pts, shown_t, src = split_sharp(pts, t, source=True)
    tri = Poly_Triangulation(len(shown_pts), len(shown_t), False)
    for i, (x, y, z) in enumerate(shown_pts.tolist(), 1):
        tri.SetNode(i, gp_Pnt(x, y, z))
    for i, (a, b, c) in enumerate((shown_t + 1).tolist(), 1):
        tri.SetTriangle(i, Poly_Triangle(a, b, c))
    face = TopoDS_Face()
    BRep_Builder().MakeFace(face, tri)
    if remember:
        _remember(face, pts, t)
        _remember_source(face, src)
    return face


def _remember_source(face, src) -> None:
    _SOURCE[hash(face)] = (face, src)
    _SOURCE.move_to_end(hash(face))
    while len(_SOURCE) > _CACHE_SIZE:
        _SOURCE.popitem(last=False)


def moved_shape(old: TopoDS_Shape, points: np.ndarray, moved: np.ndarray | None = None,
                remember: bool = True) -> TopoDS_Face:
    """``old``'s triangles with some points moved to ``points`` (same count and order). Copies the old
    triangulation in C++ and sets only the moved nodes, so a sculpt stroke on a big mesh costs about the
    points it moved, not the whole mesh. Sharp-edge splits stay as they were in ``old``."""
    pts = np.ascontiguousarray(points, dtype=float).reshape(-1, 3)
    old_pts, t = arrays(old)
    hit = _SOURCE.get(hash(old))
    face = _as_face(old)
    loc = TopLoc_Location()
    tri = _triangulation(face, loc)
    if (hit is None or not hit[0].IsEqual(old) or tri is None or not loc.IsIdentity()
            or face.Orientation() == TopAbs_REVERSED or len(pts) != len(old_pts)):
        return make_shape(pts, t, remember)
    src = hit[1]
    if moved is None:
        moved = np.flatnonzero(np.any(pts != old_pts, axis=1))
    flag = np.zeros(len(pts), dtype=bool)
    flag[np.asarray(moved, dtype=np.int64)] = True
    nodes = np.flatnonzero(flag if src is None else flag[src])
    shown = nodes if src is None else src[nodes]
    new_tri = tri.Copy()
    if new_tri.HasNormals():
        new_tri.RemoveNormals()  # the view works them out again from the moved points
    for i, (x, y, z) in zip((nodes + 1).tolist(), pts[shown].tolist()):
        new_tri.SetNode(i, gp_Pnt(x, y, z))
    out = TopoDS_Face()
    BRep_Builder().MakeFace(out, new_tri)
    if remember:
        _remember(out, pts, t)
        _remember_source(out, src)
    return out


def is_mesh(shape: TopoDS_Shape | None) -> bool:
    """True for a mesh-body shape: a lone face with triangles and no surface."""
    if shape is None or shape.IsNull() or shape.ShapeType() != TopAbs_FACE:
        return False
    hit = _CACHE.get(hash(shape))
    if hit is not None and hit[0].IsEqual(shape):
        return True
    face = _as_face(shape)
    loc = TopLoc_Location()
    if _surface(face, loc) is not None:
        return False
    tri = _triangulation(face, loc)
    return tri is not None and tri.NbTriangles() > 0


def arrays(shape: TopoDS_Shape) -> tuple[np.ndarray, np.ndarray]:
    """(points, triangles) of a mesh-body shape, with its placement applied."""
    key = hash(shape)
    hit = _CACHE.get(key)
    if hit is not None and hit[0].IsEqual(shape):
        _CACHE.move_to_end(key)
        return hit[1], hit[2]
    face = _as_face(shape)
    loc = TopLoc_Location()
    tri = _triangulation(face, loc)
    if tri is None:
        raise MeshError("not a mesh body")
    n, m = tri.NbNodes(), tri.NbTriangles()
    pts = np.empty((n, 3))
    for i in range(n):
        p = tri.Node(i + 1)
        pts[i] = (p.X(), p.Y(), p.Z())
    t = np.empty((m, 3), dtype=np.int64)
    for i in range(m):
        t[i] = tri.Triangle(i + 1).Get()
    t -= 1
    if not loc.IsIdentity():
        pts = _apply(loc.Transformation(), pts)
    if face.Orientation() == TopAbs_REVERSED:
        t = t[:, ::-1].copy()
    pts, t = _join_exact(pts, t)  # points split for shading become one again
    _remember(shape, pts, t)
    return pts, t


def _join_exact(pts: np.ndarray, t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Points that are exactly equal become one, kept in the order they first appear, so a mesh
    read back from its triangulation has its points in the order it was made with."""
    _, first, inv = np.unique(pts, axis=0, return_index=True, return_inverse=True)
    order = np.argsort(first, kind="stable")
    rank = np.empty_like(order)
    rank[order] = np.arange(len(order))
    return pts[first[order]], rank[inv.reshape(-1)][t]


def split_sharp(pts: np.ndarray, t: np.ndarray, degrees: float = 50.0, source: bool = False):
    """The same triangles with each point split where faces meet at a sharp edge
    (more than ``degrees`` between their normals), so shading does not smear across it.
    With ``source``, also which point each new point came from (None when nothing was split)."""
    m = len(t)
    nrm = np.cross(pts[t[:, 1]] - pts[t[:, 0]], pts[t[:, 2]] - pts[t[:, 0]])
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1), 1e-300)[:, None]
    # half-edges k of triangle i: corner k to corner k+1
    a = t.reshape(-1)
    b = t[:, [1, 2, 0]].reshape(-1)
    n = int(t.max()) + 1
    key = np.minimum(a, b) * n + np.maximum(a, b)
    order = np.argsort(key, kind="stable")
    ks = key[order]
    pair = np.nonzero(ks[1:] == ks[:-1])[0]
    h1, h2 = order[pair], order[pair + 1]  # two half-edges on one edge
    f1, f2 = h1 // 3, h2 // 3
    smooth = (nrm[f1] * nrm[f2]).sum(axis=1) > np.cos(np.radians(degrees))
    if smooth.all():
        return (pts, t, None) if source else (pts, t)
    h1, h2, f1, f2 = h1[smooth], h2[smooth], f1[smooth], f2[smooth]
    # corners to join: the corner of each triangle at each end of the shared edge
    c_start1, c_end1 = h1, f1 * 3 + (h1 % 3 + 1) % 3
    t2v = a  # vertex of each corner
    # corner of triangle f2 at a vertex: find which of its three corners holds it
    def corner(f, v):
        c = f * 3
        return np.where(t2v[c] == v, c, np.where(t2v[c + 1] == v, c + 1, c + 2))
    links = np.concatenate([
        np.stack([c_start1, corner(f2, t2v[c_start1])], axis=1),
        np.stack([c_end1, corner(f2, t2v[c_end1])], axis=1),
    ])
    lab = np.arange(3 * m)
    while True:  # each fan is small, so this settles in a few rounds
        low = np.minimum(lab[links[:, 0]], lab[links[:, 1]])
        new = lab.copy()
        np.minimum.at(new, links[:, 0], low)
        np.minimum.at(new, links[:, 1], low)
        new = new[new]
        if np.array_equal(new, lab):
            break
        lab = new
    roots, inv = np.unique(lab, return_inverse=True)
    # number the new points in the order of the points they came from, so reading the mesh
    # back (which joins the copies again) gives the points in their first order
    src = t2v[roots]
    order = np.lexsort((roots, src))
    rank = np.empty_like(order)
    rank[order] = np.arange(len(order))
    src = src[order]
    t_new = rank[inv.reshape(-1)].reshape(-1, 3)
    if source:
        return pts[src], t_new, src
    return pts[src], t_new


def _apply(trsf: gp_Trsf, pts: np.ndarray) -> np.ndarray:
    m = np.array([[trsf.Value(r, c) for c in range(1, 5)] for r in range(1, 4)])
    return pts @ m[:, :3].T + m[:, 3]


def transformed(shape: TopoDS_Shape, trsf: gp_Trsf) -> TopoDS_Face:
    """The mesh moved, turned, scaled or mirrored (a mirror flips the triangles so they still face out)."""
    pts, t = arrays(shape)
    out = _apply(trsf, pts)
    if trsf.IsNegative():
        t = t[:, ::-1]
    return make_shape(out, t)


_INFO: OrderedDict = OrderedDict()  # shape hash -> (shape, MeshInfo)


def info(shape: TopoDS_Shape) -> MeshInfo:
    key = hash(shape)
    hit = _INFO.get(key)
    if hit is not None and hit[0].IsEqual(shape):
        return hit[1]
    pts, t = arrays(shape)
    a = pts[t[:, 0]]
    n = np.cross(pts[t[:, 1]] - a, pts[t[:, 2]] - a)  # one cross product for both
    vol = float(np.einsum("ij,ij->", a, n) / 6.0)
    out = MeshInfo(len(t), len(pts), closed(t), vol, float(np.sqrt(np.einsum("ij,ij->i", n, n)).sum() / 2.0))
    _INFO[key] = (shape, out)
    while len(_INFO) > _CACHE_SIZE:
        _INFO.popitem(last=False)
    return out


def volume(pts: np.ndarray, t: np.ndarray) -> float:
    a, b, c = pts[t[:, 0]], pts[t[:, 1]], pts[t[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def area(pts: np.ndarray, t: np.ndarray) -> float:
    a, b, c = pts[t[:, 0]], pts[t[:, 1]], pts[t[:, 2]]
    return float(np.linalg.norm(np.cross(b - a, c - a), axis=1).sum() / 2.0)


def edge_lengths(pts: np.ndarray, t: np.ndarray) -> np.ndarray:
    e = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    return np.linalg.norm(pts[e[:, 0]] - pts[e[:, 1]], axis=1)


_CLOSED: list = []  # [(triangles array, closed)]: a sculpt stroke keeps the same triangles


def closed(t: np.ndarray) -> bool:
    """_closed, remembered for the last few triangle arrays (by identity)."""
    for arr, val in _CLOSED:
        if arr is t:
            return val
    val = _closed(t)
    _CLOSED.insert(0, (t, val))
    del _CLOSED[8:]
    return val


def _closed(t: np.ndarray) -> bool:
    """Every edge is used by exactly two triangles, once each way."""
    e = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]]).astype(np.int64)
    n = int(e.max()) + 1
    fwd = np.sort(e[:, 0] * n + e[:, 1])
    back = np.sort(e[:, 1] * n + e[:, 0])
    return bool((np.diff(fwd) != 0).all() and np.array_equal(fwd, back))


# ---- solids to meshes ---------------------------------------------------------
def weld(pts: np.ndarray, t: np.ndarray, tol: float) -> tuple[np.ndarray, np.ndarray]:
    """Points closer than ``tol`` become one; triangles that collapse are dropped."""
    if len(pts) == 0:
        return pts, t
    key = np.round(pts / max(tol, 1e-12)).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    t = inv[t]
    ok = (t[:, 0] != t[:, 1]) & (t[:, 1] != t[:, 2]) & (t[:, 0] != t[:, 2])
    t = t[ok]
    used, t2 = np.unique(t, return_inverse=True)
    return pts[first][used], t2.reshape(-1, 3)


def triangles_of(shape: TopoDS_Shape, deflection: float, angle: float = 0.3) -> tuple[np.ndarray, np.ndarray]:
    """Triangles of any shape (a B-rep body is meshed first), welded into one mesh."""
    if is_mesh(shape):
        return arrays(shape)
    BRepMesh_IncrementalMesh(shape, deflection, False, angle, True)
    all_pts, all_tris, base = [], [], 0
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        face = _as_face(ex.Current())
        loc = TopLoc_Location()
        tri = _triangulation(face, loc)
        ex.Next()
        if tri is None:
            continue
        n = tri.NbNodes()
        p = np.array([(q.X(), q.Y(), q.Z()) for q in (tri.Node(i) for i in range(1, n + 1))])
        if not loc.IsIdentity():
            p = _apply(loc.Transformation(), p)
        t = np.array([tri.Triangle(i).Get() for i in range(1, tri.NbTriangles() + 1)], dtype=np.int64) - 1
        if face.Orientation() == TopAbs_REVERSED:
            t = t[:, ::-1]
        all_pts.append(p)
        all_tris.append(t + base)
        base += n
    if not all_tris:
        raise MeshError("the body has no faces to mesh")
    pts, t = np.concatenate(all_pts), np.concatenate(all_tris)
    return weld(pts, t, max(deflection * 1e-3, 1e-7))


# ---- manifold3d ---------------------------------------------------------------
def _mf():
    try:
        import manifold3d
    except ImportError as exc:  # pragma: no cover - it is a dependency
        raise MeshError("mesh booleans need the manifold3d package (pip install manifold3d)") from exc
    return manifold3d


def to_manifold(pts: np.ndarray, t: np.ndarray, what: str = "the mesh"):
    mf = _mf()

    def build(merge: bool):
        mesh = mf.Mesh64(vert_properties=np.ascontiguousarray(pts, dtype=np.float64),
                         tri_verts=np.ascontiguousarray(t, dtype=np.uint64))
        if merge:  # points that are the same but were stored twice become one
            mesh.merge()
        return mf.Manifold(mesh)

    man = build(False)  # our own meshes share their points already: no merge needed
    if man.status() != mf.Error.NoError:
        man = build(True)
    if man.status() != mf.Error.NoError:
        raise MeshError(f"{what} is not closed (it has holes or loose edges), so it has no inside; "
                        "close it in a mesh tool first")
    return man


def from_manifold(man) -> tuple[np.ndarray, np.ndarray]:
    mesh = man.to_mesh64()
    pts = np.asarray(mesh.vert_properties, dtype=float)[:, :3].copy()
    t = np.asarray(mesh.tri_verts, dtype=np.int64).copy()
    return pts, t


def boolean(op: str, base: tuple, tools: list[tuple]) -> tuple[np.ndarray, np.ndarray]:
    """UNION / SUBTRACT / INTERSECT of (points, tris) meshes; the result is always closed."""
    mf = _mf()
    a = to_manifold(*base, what="the first body")
    others = [to_manifold(*m, what=f"tool body {i + 1}") for i, m in enumerate(tools)]
    if op == "UNION":
        out = mf.Manifold.batch_boolean([a, *others], mf.OpType.Add)
    elif op == "SUBTRACT":
        tool = others[0] if len(others) == 1 else mf.Manifold.batch_boolean(others, mf.OpType.Add)
        out = a - tool
    else:
        out = a
        for o in others:
            out = out ^ o
    if out.is_empty():
        return np.empty((0, 3)), np.empty((0, 3), dtype=np.int64)
    return from_manifold(out)


def pieces(pts: np.ndarray, t: np.ndarray) -> int:
    """How many separate pieces the mesh is made of."""
    return len(to_manifold(pts, t).decompose())


def drop_specks(pts: np.ndarray, t: np.ndarray, share: float = 1e-4) -> tuple[np.ndarray, np.ndarray]:
    """The mesh without the pieces holding less than ``share`` of its volume (slivers a boolean leaves)."""
    parts = to_manifold(pts, t).decompose()
    if len(parts) < 2:
        return pts, t
    total = sum(abs(q.volume()) for q in parts)
    keep = [q for q in parts if abs(q.volume()) >= share * total]
    if len(keep) == len(parts) or not keep:
        return pts, t
    mf = _mf()
    return from_manifold(mf.Manifold.batch_boolean(keep, mf.OpType.Add) if len(keep) > 1 else keep[0])


def simplify(pts: np.ndarray, t: np.ndarray, tolerance: float) -> tuple[np.ndarray, np.ndarray]:
    """Fewer triangles; no point of the surface moves more than ``tolerance``."""
    return from_manifold(to_manifold(pts, t).simplify(tolerance))


def refine(pts: np.ndarray, t: np.ndarray, length: float) -> tuple[np.ndarray, np.ndarray]:
    """More triangles: every edge longer than ``length`` is split (the shape stays the same)."""
    return from_manifold(to_manifold(pts, t).refine_to_length(length))


def smooth(pts: np.ndarray, t: np.ndarray, steps: int, strength: float = 0.5) -> np.ndarray:
    """Taubin smoothing: each step pulls every point towards the middle of its
    neighbours, then pushes it back a little, so bumps go but the body does not shrink."""
    n = len(pts)
    e = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]]).astype(np.int64)
    e = np.concatenate([e, e[:, ::-1]])
    key = np.sort(e[:, 0] * n + e[:, 1])
    key = key[np.concatenate(([True], key[1:] != key[:-1]))]  # each neighbour once
    src, dst = key // n, key % n
    deg = np.bincount(src, minlength=n).astype(float)
    deg[deg == 0] = 1.0
    lam, mu = strength, -strength / (1.0 - 0.1 * strength)  # the pass band of Taubin's filter
    p = np.array(pts, dtype=float)

    def step(p: np.ndarray, f: float) -> np.ndarray:
        mid = np.stack([np.bincount(src, weights=p[dst, k], minlength=n) for k in range(3)], axis=1)
        return p + f * (mid / deg[:, None] - p)

    for _ in range(max(0, int(steps))):
        p = step(step(p, lam), mu)
    return p


_FACETED: OrderedDict = OrderedDict()  # shape hash -> (shape, faceted B-rep copy)
MAX_FACETED = 100_000


def as_faceted(shape: TopoDS_Shape) -> TopoDS_Shape:
    """A faceted B-rep copy of a mesh body (one flat face per triangle), for the
    kernel tools that need faces: distances, ray tests. Cached."""
    key = hash(shape)
    hit = _FACETED.get(key)
    if hit is not None and hit[0].IsEqual(shape):
        return hit[1]
    from OCP.TopoDS import TopoDS_Compound

    from . import meshfiles

    pts, t = arrays(shape)
    if len(t) > MAX_FACETED:
        raise MeshError(f"the mesh has {len(t):,} triangles; up to {MAX_FACETED:,} can be measured this way. "
                        "SIMPLIFY it first")
    pieces = meshfiles.mesh_to_pieces(pts, t)
    if len(pieces) == 1:
        out = pieces[0].shape
    else:
        out, bld = TopoDS_Compound(), BRep_Builder()
        bld.MakeCompound(out)
        for pc in pieces:
            bld.Add(out, pc.shape)
    _FACETED[key] = (shape, out)
    while len(_FACETED) > 8:
        _FACETED.popitem(last=False)
    return out


def overlap_volume(a: TopoDS_Shape, b: TopoDS_Shape, deflection: float) -> float:
    """Volume two bodies (mesh bodies or solids) have in common, on triangles."""
    ma = to_manifold(*triangles_of(a, deflection))
    mb_ = to_manifold(*triangles_of(b, deflection))
    return float((ma ^ mb_).volume())


# ---- shapes made as meshes (spheres for tests and examples) ---------------------
def sphere(r: float, segments: int = 64, centre=(0.0, 0.0, 0.0)) -> tuple[np.ndarray, np.ndarray]:
    mf = _mf()
    pts, t = from_manifold(mf.Manifold.sphere(r, segments))
    return pts + np.asarray(centre, dtype=float), t
