"""Checks of a triangle mesh after it was changed: cracks, folds and slivers.

A brush, a split or a join can leave a mesh that still draws but no longer works: a crack (an edge
with one triangle where there were two), an edge shared by three triangles, a triangle turned
over against its neighbours (a fold, seen as a dark streak), or a triangle so thin that the next
brush or boolean trips on it. ``check`` counts each kind, over the whole mesh or only near some
points (what a stroke touched), and gives a place for each so a message can say where.

``untangle`` is the repair for folds: it smooths the points of turned-over triangles towards
their neighbours until they lie flat again (masked and sharp points stay where they are).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

THIN_ANGLE = 1.0  # degrees: a triangle whose smallest angle is below this is a sliver
FOLD_COS = -0.5  # neighbours whose normals are more than 120 degrees apart are folded over


@dataclass
class MeshFlaws:
    triangles: int  # how many were looked at
    open_edges: int = 0  # edges with one triangle (a crack, or the rim of an open mesh)
    shared_edges: int = 0  # edges with three or more triangles
    misturned: int = 0  # edges both triangles run the same way (one of them is inside out)
    folded: int = 0  # edges whose two triangles face (nearly) opposite ways
    thin: int = 0  # triangles with an angle under THIN_ANGLE
    flat: int = 0  # triangles with no area
    where: dict[str, list[float]] = field(default_factory=dict)  # a point for each kind found

    @property
    def broken(self) -> int:
        """Problems that change what the mesh is (cracks, three-way edges, inside-out triangles)."""
        return self.open_edges + self.shared_edges + self.misturned

    @property
    def count(self) -> int:
        return self.broken + self.folded + self.thin + self.flat

    def worse_than(self, before: "MeshFlaws") -> dict[str, int]:
        """The kinds there are more of than ``before``, and how many more."""
        out = {}
        for k in ("open_edges", "shared_edges", "misturned", "folded", "thin", "flat"):
            d = getattr(self, k) - getattr(before, k)
            if d > 0:
                out[k] = d
        return out

    def as_dict(self) -> dict:
        return {"triangles": self.triangles, "open_edges": self.open_edges, "shared_edges": self.shared_edges,
                "misturned": self.misturned, "folded": self.folded, "thin": self.thin, "flat": self.flat,
                "where": self.where, "problems": self.count}


WORDS = {"open_edges": ("crack", "cracks"), "shared_edges": ("edge shared by 3+ triangles", "edges shared by 3+ triangles"),
         "misturned": ("triangle turned inside out", "triangles turned inside out"),
         "folded": ("fold", "folds"), "thin": ("sliver triangle", "sliver triangles"),
         "flat": ("triangle with no area", "triangles with no area")}


def words(kind: str, n: int) -> str:
    one, many = WORDS[kind]
    return f"{n} {one if n == 1 else many}"


def _near_triangles(tris: np.ndarray, points: np.ndarray | None, n: int) -> np.ndarray:
    if points is None:
        return np.arange(len(tris))
    mark = np.zeros(n, dtype=bool)
    mark[np.asarray(points, dtype=np.int64)] = True
    return np.flatnonzero(mark[tris].any(axis=1))


def check(pts: np.ndarray, tris: np.ndarray, points: np.ndarray | None = None,
          open_ok: bool = False) -> MeshFlaws:
    """Flaws of the mesh, or of the triangles at ``points`` and their neighbours.

    open_ok: the mesh is meant to be open (a scan), so its rim edges are not counted as cracks.
    With ``points``, edges are judged by every triangle on them, not only the ones near the points."""
    p = np.asarray(pts, dtype=float)
    t = np.asarray(tris, dtype=np.int64)
    n = len(p)
    sel = _near_triangles(t, points, n)
    f = MeshFlaws(len(sel))
    if not len(sel):
        return f
    ts = t[sel]
    v0, v1, v2 = p[ts[:, 0]], p[ts[:, 1]], p[ts[:, 2]]
    cr = np.cross(v1 - v0, v2 - v0)
    area2 = np.linalg.norm(cr, axis=1)
    scale = max(float(np.ptp(p[ts.reshape(-1)], axis=0).max()), 1e-12)
    flat = area2 <= 1e-14 * scale * scale
    f.flat = int(flat.sum())
    if f.flat:
        f.where["flat"] = (v0[flat][0]).round(6).tolist()
    # smallest angle of each triangle
    e = [v1 - v0, v2 - v1, v0 - v2]
    L = [np.linalg.norm(x, axis=1) for x in e]
    with np.errstate(invalid="ignore", divide="ignore"):
        cos = []
        for a, b, la, lb in ((e[2], e[0], L[2], L[0]), (e[0], e[1], L[0], L[1]), (e[1], e[2], L[1], L[2])):
            cos.append(-np.einsum("ij,ij->i", a, b) / (la * lb))
        cmax = np.nan_to_num(np.max(np.stack(cos, 1), axis=1), nan=1.0)
    thin = (cmax > np.cos(np.radians(THIN_ANGLE))) & ~flat
    f.thin = int(thin.sum())
    if f.thin:
        f.where["thin"] = ((v0 + v1 + v2)[thin][0] / 3).round(6).tolist()
    # edges: every triangle on an edge near the points counts, so a crack is not mistaken for a rim
    if points is not None:
        mark = np.zeros(n, dtype=bool)
        mark[ts.reshape(-1)] = True
        around = t[mark[t].any(axis=1)]
    else:
        around = t
    a = around.reshape(-1)
    b = around[:, [1, 2, 0]].reshape(-1)
    tri_of = np.repeat(np.arange(len(around)), 3)
    lo, hi = np.minimum(a, b), np.maximum(a, b)
    key = lo * n + hi
    order = np.argsort(key, kind="stable")
    ks = key[order]
    starts = np.flatnonzero(np.r_[True, ks[1:] != ks[:-1]])
    counts = np.diff(np.r_[starts, len(ks)])
    # only edges with both ends among the checked triangles' points
    inner = np.zeros(n, dtype=bool)
    inner[ts.reshape(-1)] = True
    ends_lo, ends_hi = ks[starts] // n, ks[starts] % n
    judged = inner[ends_lo] & inner[ends_hi]
    if not open_ok:
        once = judged & (counts == 1)
        f.open_edges = int(once.sum())
        if f.open_edges:
            f.where["open_edges"] = p[ends_lo[once][0]].round(6).tolist()
    many = judged & (counts > 2)
    f.shared_edges = int(many.sum())
    if f.shared_edges:
        f.where["shared_edges"] = p[ends_lo[many][0]].round(6).tolist()
    two = np.flatnonzero(judged & (counts == 2))
    if len(two):
        i0, i1 = order[starts[two]], order[starts[two] + 1]
        # both triangles run the edge the same way: one of them is turned inside out
        same = a[i0] == a[i1]
        f.misturned = int(same.sum())
        if f.misturned:
            f.where["misturned"] = p[a[i0][same][0]].round(6).tolist()
        q = around
        c0 = np.cross(p[q[tri_of[i0], 1]] - p[q[tri_of[i0], 0]], p[q[tri_of[i0], 2]] - p[q[tri_of[i0], 0]])
        c1 = np.cross(p[q[tri_of[i1], 1]] - p[q[tri_of[i1], 0]], p[q[tri_of[i1], 2]] - p[q[tri_of[i1], 0]])
        n0, n1 = np.linalg.norm(c0, axis=1), np.linalg.norm(c1, axis=1)
        ok = (n0 > 0) & (n1 > 0) & ~same
        with np.errstate(invalid="ignore", divide="ignore"):
            cosn = np.einsum("ij,ij->i", c0, c1) / (n0 * n1)
        fold = ok & (cosn < FOLD_COS)
        f.folded = int(fold.sum())
        if f.folded:
            f.where["folded"] = p[a[i0][fold][0]].round(6).tolist()
    return f


def folded_points(pts: np.ndarray, tris: np.ndarray, points: np.ndarray | None = None) -> np.ndarray:
    """The points of triangles that are folded over against a neighbour (near ``points``)."""
    p = np.asarray(pts, dtype=float)
    t = np.asarray(tris, dtype=np.int64)
    n = len(p)
    sel = _near_triangles(t, points, n)
    if points is not None:
        mark = np.zeros(n, dtype=bool)
        mark[t[sel].reshape(-1)] = True
        sel = np.flatnonzero(mark[t].any(axis=1))
    q = t[sel]
    a = q.reshape(-1)
    b = q[:, [1, 2, 0]].reshape(-1)
    tri_of = np.repeat(np.arange(len(q)), 3)
    key = np.minimum(a, b) * n + np.maximum(a, b)
    order = np.argsort(key, kind="stable")
    ks = key[order]
    pair = np.flatnonzero(ks[1:] == ks[:-1])
    if not len(pair):
        return np.zeros(0, dtype=np.int64)
    i0, i1 = order[pair], order[pair + 1]
    cr = np.cross(p[q[:, 1]] - p[q[:, 0]], p[q[:, 2]] - p[q[:, 0]])
    c0, c1 = cr[tri_of[i0]], cr[tri_of[i1]]
    with np.errstate(invalid="ignore", divide="ignore"):
        cosn = np.einsum("ij,ij->i", c0, c1) / (np.linalg.norm(c0, axis=1) * np.linalg.norm(c1, axis=1))
    bad = np.nan_to_num(cosn, nan=1.0) < FOLD_COS
    tri = np.unique(np.r_[tri_of[i0][bad], tri_of[i1][bad]])
    return np.unique(q[tri].reshape(-1))


def untangle(pts: np.ndarray, tris: np.ndarray, points: np.ndarray | None = None,
             frozen: np.ndarray | None = None, rounds: int = 12) -> tuple[np.ndarray, int]:
    """Smooth folded triangles flat (near ``points``). Returns (points, folds left).
    ``frozen``: a bool per point that must not move (masked or sharp points)."""
    from .sculpt import Topology, _neighbour_mean

    p = np.asarray(pts, dtype=float).copy()
    t = np.asarray(tris, dtype=np.int64)
    topo = None
    bad = folded_points(p, t, points)
    for _ in range(rounds):
        if frozen is not None and len(bad):
            bad = bad[~frozen[bad]]
        if not len(bad):
            return p, 0
        topo = topo or Topology.of(t, len(p))
        # the fold and the ring round it, so the flattening spreads
        ring = np.unique(np.r_[bad, topo.indices[np.concatenate(
            [np.arange(topo.indptr[i], topo.indptr[i + 1]) for i in bad])]])
        if frozen is not None:
            ring = ring[~frozen[ring]]
        p[ring] += 0.6 * (_neighbour_mean(p, topo, ring) - p[ring])
        bad = folded_points(p, t, ring)
    return p, len(bad) and check(p, t, bad).folded
