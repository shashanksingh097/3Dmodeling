"""Scan to CAD, part 2: split a mesh into regions at its sharp edges, recognise planes,
cylinders and spheres exactly, and join the fitted surfaces into one solid (SEGMENT,
RECONSTRUCT: commands/mesh_handlers.py).

Regions grow from triangle to neighbouring triangle while the bend between them stays under
an angle, so a region is one smooth piece of the part: a flat face, a round bore, a ball end.
Each region is then tried, simplest first, as a plane, a sphere and a cylinder (least squares,
in that order); the first whose points all lie within the tolerance is taken. A region that
none of them fits is freeform (FITSURF fits those).

To join the pieces, each fitted surface is made big (a plane well past the part, a cylinder
longer than the part, a whole sphere) and OCCT cuts space into the cells those surfaces bound
(BOPAlgo_MakerVolume). A cell belongs to the part when a point inside it is inside the mesh
(winding number); the kept cells are fused into one solid with its faces merged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np


class ScanError(Exception):
    pass


# ---- regions ------------------------------------------------------------------------------
def normals(pts: np.ndarray, t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Unit normals and areas of the triangles."""
    c = np.cross(pts[t[:, 1]] - pts[t[:, 0]], pts[t[:, 2]] - pts[t[:, 0]])
    a = np.linalg.norm(c, axis=1)
    return c / np.maximum(a, 1e-300)[:, None], a / 2


def neighbours(t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Pairs of triangles that share an edge (each pair once)."""
    e = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    owner = np.tile(np.arange(len(t)), 3)
    key = np.sort(e, axis=1)
    order = np.lexsort((key[:, 1], key[:, 0]))
    key, owner = key[order], owner[order]
    same = np.all(key[1:] == key[:-1], axis=1)
    i = np.nonzero(same)[0]
    return owner[i], owner[i + 1]


def segment(pts: np.ndarray, t: np.ndarray, angle: float = 25.0) -> np.ndarray:
    """A region number per triangle (0, 1, ... by size, largest first): neighbours whose normals
    differ by less than ``angle`` degrees are in one region."""
    n, _ = normals(pts, t)
    a, b = neighbours(t)
    smooth = np.einsum("ij,ij->i", n[a], n[b]) > math.cos(math.radians(angle))
    parent = np.arange(len(t))

    def find(x):
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    for x, y in zip(a[smooth], b[smooth]):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[max(rx, ry)] = min(rx, ry)
    roots = np.array([find(i) for i in range(len(t))])
    uniq, inv, counts = np.unique(roots, return_inverse=True, return_counts=True)
    rank = np.empty(len(uniq), int)
    rank[np.argsort(-counts, kind="stable")] = np.arange(len(uniq))
    return rank[inv]


# ---- recognising shapes -----------------------------------------------------------------
@dataclass
class Shape:
    kind: str  # PLANE, CYLINDER, SPHERE or FREEFORM
    rms: float
    worst: float
    centre: tuple = (0.0, 0.0, 0.0)  # a point of the plane / axis, or the sphere's centre
    axis: tuple = (0.0, 0.0, 1.0)  # plane normal (out of the part) or cylinder axis
    radius: float = 0.0
    inside: bool = False  # a cylinder or sphere seen from inside (a bore, a socket)

    def words(self) -> str:
        f = lambda v: ", ".join(f"{x:.4g}" for x in v)
        if self.kind == "PLANE":
            return f"plane through ({f(self.centre)}), normal ({f(self.axis)})"
        if self.kind == "CYLINDER":
            return f"{'bore' if self.inside else 'cylinder'} radius {self.radius:.5g}, axis ({f(self.axis)}) " \
                   f"through ({f(self.centre)})"
        if self.kind == "SPHERE":
            return f"{'socket' if self.inside else 'sphere'} radius {self.radius:.5g} at ({f(self.centre)})"
        return "freeform"


@dataclass
class Region:
    number: int
    tris: np.ndarray
    points: np.ndarray  # the region's own vertex positions
    area: float
    shape: Shape = field(default_factory=lambda: Shape("FREEFORM", math.inf, math.inf))


def fit_plane(p: np.ndarray, nrm: np.ndarray) -> Shape:
    c = p.mean(axis=0)
    _, _, vt = np.linalg.svd(p - c, full_matrices=False)
    n = vt[2]
    if n @ nrm < 0:
        n = -n
    d = (p - c) @ n
    return Shape("PLANE", float(np.sqrt(np.mean(d * d))), float(np.abs(d).max()), tuple(c), tuple(n))


def fit_sphere(p: np.ndarray, nrm: np.ndarray) -> Shape:
    A = np.column_stack([2 * p, np.ones(len(p))])
    b = (p * p).sum(axis=1)
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    c = sol[:3]
    r2 = sol[3] + c @ c
    if r2 <= 0:
        return Shape("SPHERE", math.inf, math.inf)
    r = math.sqrt(r2)
    d = np.linalg.norm(p - c, axis=1) - r
    inside = float(((p - c) * nrm).sum(axis=1).mean()) < 0
    return Shape("SPHERE", float(np.sqrt(np.mean(d * d))), float(np.abs(d).max()), tuple(c), (0.0, 0.0, 1.0),
                 r, inside)


def fit_cylinder(p: np.ndarray, nrm: np.ndarray, tri_n: np.ndarray, w: np.ndarray) -> Shape:
    """The axis is the direction the normals never point along; then a circle in the plane
    square to it."""
    cov = (tri_n * w[:, None]).T @ tri_n
    vals, vecs = np.linalg.eigh(cov)
    a = vecs[:, 0]
    if vals[1] < 1e-6 * vals[2]:  # the normals all point one way: a plane, not a cylinder
        return Shape("CYLINDER", math.inf, math.inf)
    u = np.cross(a, [1.0, 0, 0] if abs(a[0]) < 0.9 else [0, 1.0, 0])
    u /= np.linalg.norm(u)
    v = np.cross(a, u)
    xy = np.column_stack([p @ u, p @ v])
    A = np.column_stack([2 * xy, np.ones(len(xy))])
    sol, *_ = np.linalg.lstsq(A, (xy * xy).sum(axis=1), rcond=None)
    cx, cy = sol[:2]
    r2 = sol[2] + cx * cx + cy * cy
    if r2 <= 0:
        return Shape("CYLINDER", math.inf, math.inf)
    r = math.sqrt(r2)
    d = np.hypot(xy[:, 0] - cx, xy[:, 1] - cy) - r
    z0 = float((p @ a).mean())
    centre = cx * u + cy * v + z0 * a
    radial = p - centre - np.outer((p - centre) @ a, a)
    inside = float((radial * nrm).sum(axis=1).mean()) < 0
    return Shape("CYLINDER", float(np.sqrt(np.mean(d * d))), float(np.abs(d).max()), tuple(centre), tuple(a),
                 r, inside)


def distance(shape: Shape, p: np.ndarray) -> np.ndarray:
    """How far points are from a fitted shape."""
    c, a = np.asarray(shape.centre, float), np.asarray(shape.axis, float)
    if shape.kind == "PLANE":
        return np.abs((p - c) @ a)
    if shape.kind == "SPHERE":
        return np.abs(np.linalg.norm(p - c, axis=1) - shape.radius)
    if shape.kind == "CYLINDER":
        d = p - c
        return np.abs(np.linalg.norm(d - np.outer(d @ a, a), axis=1) - shape.radius)
    return np.full(len(p), np.inf)


def recognise(pts: np.ndarray, t: np.ndarray, labels: np.ndarray, tol: float, min_tris: int = 1) -> list[Region]:
    """Regions with their best simple shape (worst point within ``tol``), largest first."""
    tri_n, tri_a = normals(pts, t)
    vn = np.zeros_like(pts)
    np.add.at(vn, t.ravel(), np.repeat(tri_n * tri_a[:, None], 3, axis=0))
    out = []
    for k in range(labels.max() + 1):
        sel = np.nonzero(labels == k)[0]
        if len(sel) < min_tris:
            continue
        ids = np.unique(t[sel])
        # the corners and the middles of the triangles: a mesh made from CAD has corners only on
        # the ends of a cylinder, which a sphere would fit too
        cen = pts[t[sel]].mean(axis=1)
        p = np.vstack([pts[ids], cen])
        nv = np.vstack([vn[ids], tri_n[sel]])
        nv = nv / np.maximum(np.linalg.norm(nv, axis=1), 1e-300)[:, None]
        reg = Region(k, sel, p, float(tri_a[sel].sum()))
        mean_n = (tri_n[sel] * tri_a[sel, None]).sum(axis=0)
        for shape in (fit_plane(p, mean_n), fit_sphere(p, nv), fit_cylinder(p, nv, tri_n[sel], tri_a[sel])):
            if shape.worst <= tol:
                reg.shape = shape
                break
        out.append(reg)
    # a sliver of a few triangles (noise on a curved face, a thin strip) that a bigger region's
    # shape fits is part of that region, not a face of its own
    total = sum(r.area for r in out)
    big = [r for r in out if r.shape.kind != "FREEFORM" and len(r.tris) > 4]
    keep = []
    for r in out:
        if len(r.tris) <= 4 or r.area < 1e-3 * total:
            host = next((b for b in big if b is not r and len(b.tris) > len(r.tris)
                         and distance(b.shape, r.points).max() <= tol), None)
            if host is not None:
                host.tris = np.concatenate([host.tris, r.tris])
                host.area += r.area
                continue
        keep.append(r)
    return keep


# ---- joining into a solid ---------------------------------------------------------------
def winding(pts: np.ndarray, t: np.ndarray, q: np.ndarray) -> np.ndarray:
    """Generalised winding number of a closed mesh at points ``q`` (about 1 inside, 0 outside)."""
    out = np.zeros(len(q))
    for i, x in enumerate(q):
        a, b, c = pts[t[:, 0]] - x, pts[t[:, 1]] - x, pts[t[:, 2]] - x
        la, lb, lc = (np.linalg.norm(v, axis=1) for v in (a, b, c))
        num = np.einsum("ij,ij->i", a, np.cross(b, c))
        den = la * lb * lc + np.einsum("ij,ij->i", a, b) * lc + np.einsum("ij,ij->i", b, c) * la \
            + np.einsum("ij,ij->i", c, a) * lb
        out[i] = np.arctan2(num, den).sum() / (2 * math.pi)
    return out


def _face(shape: Shape, lo: np.ndarray, hi: np.ndarray):
    """A big face for one fitted shape, reaching well past the box lo..hi."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere
    from OCP.gp import gp_Ax2, gp_Ax3, gp_Dir, gp_Pln, gp_Pnt

    size = float(np.linalg.norm(hi - lo))
    mid = (lo + hi) / 2
    c = np.asarray(shape.centre, float)
    a = np.asarray(shape.axis, float)
    if shape.kind == "PLANE":
        foot = mid - ((mid - c) @ a) * a
        pl = gp_Pln(gp_Ax3(gp_Pnt(*foot), gp_Dir(*a)))
        return BRepBuilderAPI_MakeFace(pl, -2 * size, 2 * size, -2 * size, 2 * size).Face()
    if shape.kind == "CYLINDER":
        from OCP.Geom import Geom_CylindricalSurface

        z = (mid - c) @ a
        base = c + (z - 2 * size) * a
        # the seam goes an odd way round: a seam along a world axis lands exactly on edges of the
        # other faces of a machined part and the kernel then loses the cylinder
        odd = np.array([0.5377, 0.3256, 0.7781])
        x = odd - (odd @ a) * a
        if np.linalg.norm(x) < 1e-6:
            x = np.cross(a, [0.0, 0.6, 0.8])
        surf = Geom_CylindricalSurface(gp_Ax3(gp_Pnt(*base), gp_Dir(*a), gp_Dir(*(x / np.linalg.norm(x)))),
                                       shape.radius)
        return BRepBuilderAPI_MakeFace(surf, 0.0, 2 * math.pi, 0.0, 4 * size, 1e-7).Face()
    if shape.kind == "SPHERE":
        tilt = np.array([0.2673, 0.5345, 0.8018])  # poles and seam off the world axes, as for cylinders
        return BRepPrimAPI_MakeSphere(gp_Ax2(gp_Pnt(*c), gp_Dir(*tilt)), shape.radius).Shape()
    raise ScanError(f"no surface for {shape.kind}")


def _inner_point(cell) -> np.ndarray | None:
    """A point inside a solid: its centre if that is inside, else the middle of a line through it."""
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.BRepGProp import BRepGProp
    from OCP.gp import gp_Pnt
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_State

    g = GProp_GProps()
    (getattr(BRepGProp, "VolumeProperties_s", None) or BRepGProp.VolumeProperties)(cell, g)
    c = g.CentreOfMass()
    cls = BRepClass3d_SolidClassifier(cell)
    cls.Perform(c, 1e-7)
    if cls.State() == TopAbs_State.TopAbs_IN:
        return np.array([c.X(), c.Y(), c.Z()])
    from ..commands.queries import bbox

    lo_hi = bbox(cell)
    lo, hi = np.array(lo_hi[:3]), np.array(lo_hi[3:])
    rng = np.random.default_rng(0)
    for _ in range(200):
        q = lo + rng.random(3) * (hi - lo)
        cls.Perform(gp_Pnt(*q), 1e-7)
        if cls.State() == TopAbs_State.TopAbs_IN:
            return q
    return None


def snap(regions: list[Region], deg: float = 0.3) -> list[Region]:
    """Make nearly parallel directions exactly parallel: plane normals and cylinder axes within ``deg``
    of a world axis, or of the normal of a bigger plane, take that direction. A scan of a machined part
    is a few hundredths of a degree off everywhere, and the kernel cuts space far more reliably when
    a bore is exactly square to the face it goes through."""
    cos = math.cos(math.radians(deg))
    anchors = [np.array(v, float) for v in np.eye(3)]
    out = []
    for r in sorted(regions, key=lambda r: -r.area):
        s = r.shape
        if s.kind in ("PLANE", "CYLINDER"):
            a = np.asarray(s.axis, float)
            for v in anchors:
                d = float(a @ v)
                if abs(d) >= cos:
                    a = v if d > 0 else -v
                    break
            if s.kind == "PLANE":
                anchors.append(a)
            r = replace(r, shape=replace(s, axis=tuple(float(x) for x in a)))
        out.append(r)
    return sorted(out, key=lambda r: r.number)


def reconstruct(pts: np.ndarray, t: np.ndarray, regions: list[Region]):
    """One solid bounded by the regions' fitted surfaces, inside the mesh."""
    from OCP.BOPAlgo import BOPAlgo_MakerVolume
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    try:
        from OCP.TopTools import TopTools_ListOfShape
    except ImportError:  # OCP 8
        from OCP.collections import List_TopoDS_Shape as TopTools_ListOfShape

    free = [r for r in regions if r.shape.kind == "FREEFORM"]
    if free:
        raise ScanError("regions " + ", ".join(str(r.number + 1) for r in free) + " are not a plane, cylinder or "
                        "sphere within the tolerance (raise it, or fit those with FITSURF)")
    regions = snap(regions)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    mv = BOPAlgo_MakerVolume()
    args = TopTools_ListOfShape()
    for r in regions:
        args.Append(_face(r.shape, lo, hi))
    mv.SetArguments(args)
    mv.SetIntersect(True)
    mv.Perform()
    if mv.HasErrors():
        raise ScanError("the kernel could not cut space with the fitted surfaces")
    cells = []
    ex = TopExp_Explorer(mv.Shape(), TopAbs_SOLID)
    while ex.More():
        cells.append(ex.Current())
        ex.Next()
    keep = []
    for cell in cells:
        q = _inner_point(cell)
        if q is None:
            continue
        if not (np.all(q >= lo - 1e-9) and np.all(q <= hi + 1e-9)):
            continue
        if winding(pts, t, q[None, :])[0] > 0.5:
            keep.append(cell)
    if not keep:
        raise ScanError("no piece of space bounded by the fitted surfaces lies inside the mesh")
    solid = keep[0]
    for c in keep[1:]:
        solid = BRepAlgoAPI_Fuse(solid, c).Shape()
    u = ShapeUpgrade_UnifySameDomain(solid, True, True, True)
    u.Build()
    return u.Shape(), len(cells), len(keep)
