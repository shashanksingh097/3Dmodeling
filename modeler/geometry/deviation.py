"""How far a scan is from a model: DEVIATION, in numbers and as colours.

Every scan point gets a signed distance to the model's surface (positive outside the model,
negative inside), measured against a fine triangulation of the model, so a scan of a hundred
thousand points takes about a second. From those distances come:

* the overall numbers: how many points lie within the tolerance, the largest distance either
  way, the mean and the RMS;
* the same per face of the model, so the faces that are off show by name;
* outliers: points far from everything (stray scan points, dust, the fixture);
* holes in the scan: loops of open edges, with their length and where they are;
* faces the scan hardly covers, where the numbers say little (low confidence).

Points more than ``OUTLIER`` tolerances off that lie in small separate pieces of the scan (dust,
the fixture, stray points) are outliers and left out of the numbers; far points on the scan's main
surface are real and counted.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

OUTLIER = 5.0  # points more than this many tolerances off are outliers, not counted in the numbers
COVERED = 0.8  # a face is measured when this much of its area has scan points near it


@dataclass
class Target:
    """The model as fine triangles, for distances."""

    nodes: np.ndarray
    tris: np.ndarray
    face_of_tri: np.ndarray
    normals: np.ndarray  # per triangle, outward
    centres: np.ndarray
    areas: np.ndarray
    tree: object
    reach: float  # the longest triangle's size: nearest centres within this cover the nearest triangle
    nfaces: int = 0


def target(shape, fine: float) -> Target:
    """``shape`` triangulated finely (deflection ``fine``)."""
    from scipy.spatial import cKDTree

    from . import analysis as an

    from . import robust

    m = an.mesh(shape, fine=1.0) if fine <= 0 else _mesh(shape, fine)
    # big flat triangles next to small curved ones would hide from a nearest-centre search: split
    # them so none is much bigger than the rest
    p, t, fot = _split_big(m.nodes, m.tris, m.face_of_tri, robust.diagonal(shape) / 60)
    a, b, c = p[t[:, 0]], p[t[:, 1]], p[t[:, 2]]
    cr = np.cross(b - a, c - a)
    area2 = np.linalg.norm(cr, axis=1)
    nrm = cr / np.maximum(area2, 1e-300)[:, None]
    cen = (a + b + c) / 3
    size = float(np.max(np.linalg.norm(np.stack([a - cen, b - cen, c - cen], 1), axis=2))) if len(t) else 0.0
    return Target(p, t, fot, nrm, cen, area2 / 2, cKDTree(cen), size, len(m.faces))


def _split_big(p: np.ndarray, t: np.ndarray, fot: np.ndarray, most: float, rounds: int = 12):
    """Cut every triangle with an edge longer than ``most`` into four, until none is left
    (the triangles need not share edges: the pieces lie in the same plane)."""
    p = np.asarray(p, float)
    t = np.asarray(t, np.int64)
    fot = np.asarray(fot)
    for _ in range(rounds):
        e = np.linalg.norm(p[t] - p[t[:, [1, 2, 0]]], axis=2).max(axis=1)
        big = e > most
        if not big.any():
            break
        tb = t[big]
        n = len(p)
        k = len(tb)
        mids = np.vstack([(p[tb[:, 0]] + p[tb[:, 1]]) / 2, (p[tb[:, 1]] + p[tb[:, 2]]) / 2,
                          (p[tb[:, 2]] + p[tb[:, 0]]) / 2])
        p = np.vstack([p, mids])
        m01, m12, m20 = n + np.arange(k), n + k + np.arange(k), n + 2 * k + np.arange(k)
        four = np.vstack([np.stack([tb[:, 0], m01, m20], 1), np.stack([m01, tb[:, 1], m12], 1),
                          np.stack([m20, m12, tb[:, 2]], 1), np.stack([m01, m12, m20], 1)])
        t = np.vstack([t[~big], four])
        fot = np.concatenate([fot[~big], np.tile(fot[big], 4)])
    return p, t, fot


def _mesh(shape, deflection: float):
    """Like analysis.mesh, with a set deflection (no curvatures needed)."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location

    from . import analysis as an

    nodes, tris, fot, faces = [], [], [], []
    base = 0
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    fi = 0
    while ex.More():
        original = an._as_face(ex.Current())
        ex.Next()
        face = an._as_face(BRepBuilderAPI_Copy(original).Shape())
        BRepMesh_IncrementalMesh(face, deflection, False, 0.2, True)
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        faces.append(original)
        if tri is None or tri.NbNodes() == 0:
            fi += 1
            continue
        trsf = loc.Transformation()
        for i in range(1, tri.NbNodes() + 1):
            q = tri.Node(i).Transformed(trsf)
            nodes.append((q.X(), q.Y(), q.Z()))
        rev = face.Orientation() == TopAbs_REVERSED
        for i in range(1, tri.NbTriangles() + 1):
            a, b, c = tri.Triangle(i).Get()
            if rev:
                b, c = c, b
            tris.append((base + a - 1, base + b - 1, base + c - 1))
            fot.append(fi)
        base += tri.NbNodes()
        fi += 1
    if not tris:
        raise ValueError("the model has no faces to measure against")
    n = np.array(nodes, float)
    return an.Mesh(n, np.zeros_like(n), np.array(tris, int), np.array(fot, int), np.zeros(len(n)),
                   np.zeros(len(n)), faces)


def _closest_on_triangles(q: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """The closest point on triangle (a, b, c) to q, row by row (Ericson's method, vectorised)."""
    ab, ac, ap = b - a, c - a, q - a
    d1, d2 = np.einsum("ij,ij->i", ab, ap), np.einsum("ij,ij->i", ac, ap)
    bp = q - b
    d3, d4 = np.einsum("ij,ij->i", ab, bp), np.einsum("ij,ij->i", ac, bp)
    cp = q - c
    d5, d6 = np.einsum("ij,ij->i", ab, cp), np.einsum("ij,ij->i", ac, cp)
    va = d3 * d6 - d5 * d4
    vb = d5 * d2 - d1 * d6
    vc = d1 * d4 - d3 * d2
    with np.errstate(divide="ignore", invalid="ignore"):
        denom = 1.0 / (va + vb + vc)
        v = vb * denom
        w = vc * denom
        out = a + ab * v[:, None] + ac * w[:, None]  # inside the face
        # edges and corners
        cond = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
        t = d1 / (d1 - d3)
        out = np.where(cond[:, None], a + ab * t[:, None], out)
        cond2 = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
        t2 = d2 / (d2 - d6)
        out = np.where(cond2[:, None], a + ac * t2[:, None], out)
        cond3 = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
        t3 = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        out = np.where(cond3[:, None], b + (c - b) * t3[:, None], out)
    out = np.where(((d1 <= 0) & (d2 <= 0))[:, None], a, out)
    out = np.where(((d3 >= 0) & (d4 <= d3))[:, None], b, out)
    out = np.where(((d6 >= 0) & (d5 <= d6))[:, None], c, out)
    return np.nan_to_num(out)


def distances(tg: Target, pts: np.ndarray, k: int = 16) -> tuple[np.ndarray, np.ndarray]:
    """(signed distance, nearest triangle) for each point: positive outside the model."""
    q = np.asarray(pts, float)
    k = min(k, len(tg.tris))
    _d, cand = tg.tree.query(q, k=k)
    cand = cand.reshape(len(q), k)
    best = np.full(len(q), np.inf)
    which = np.zeros(len(q), dtype=np.int64)
    sign_vec = np.zeros((len(q), 3))
    for j in range(k):
        tri = tg.tris[cand[:, j]]
        cp = _closest_on_triangles(q, tg.nodes[tri[:, 0]], tg.nodes[tri[:, 1]], tg.nodes[tri[:, 2]])
        d = np.linalg.norm(q - cp, axis=1)
        better = d < best - 1e-15
        best[better] = d[better]
        which[better] = cand[better, j]
        sign_vec[better] = (q - cp)[better]
    # a triangle further than the k-th centre (less its size) cannot be nearer: check the rest
    kth = np.linalg.norm(q - tg.centres[cand[:, -1]], axis=1)
    unsure = np.flatnonzero(best > kth - tg.reach)
    for i in unsure:
        more = tg.tree.query_ball_point(q[i], best[i] + tg.reach)
        if len(more) <= k:
            continue
        tri = tg.tris[more]
        qq = np.repeat(q[i:i + 1], len(more), axis=0)
        cp = _closest_on_triangles(qq, tg.nodes[tri[:, 0]], tg.nodes[tri[:, 1]], tg.nodes[tri[:, 2]])
        d = np.linalg.norm(qq - cp, axis=1)
        j = int(np.argmin(d))
        if d[j] < best[i]:
            best[i], which[i], sign_vec[i] = d[j], more[j], qq[j] - cp[j]
    # outside when the point lies on the outward side of its nearest triangle
    s = np.einsum("ij,ij->i", sign_vec, tg.normals[which])
    return np.where(s < 0, -best, best), which


@dataclass
class FaceRow:
    face: int  # the model's face ID
    points: int
    within: float  # share of its points within tolerance
    rms: float
    worst: float  # signed: the distance largest in size
    covered: float  # share of its area with scan points near


@dataclass
class Result:
    tol: float
    points: int  # scan points measured (outliers left out)
    within: float
    largest_out: float  # largest positive distance
    largest_in: float  # most negative distance
    mean: float
    rms: float
    faces: list[FaceRow] = field(default_factory=list)
    outliers: int = 0
    outlier_worst: tuple | None = None  # (x, y, z, distance)
    holes: list[dict] = field(default_factory=list)  # {"length", "centre"}
    low: list[FaceRow] = field(default_factory=list)  # faces the scan hardly covers
    signed: np.ndarray | None = None  # per scan point

    def as_dict(self) -> dict:
        r = lambda x: round(float(x), 6)  # noqa: E731
        return {"tolerance": r(self.tol), "points": self.points, "within": r(self.within),
                "largest_out": r(self.largest_out), "largest_in": r(self.largest_in), "mean": r(self.mean),
                "rms": r(self.rms), "met": bool(self.within >= 0.999999 and self.points > 0),
                "faces": [{"face": f.face, "points": f.points, "within": r(f.within), "rms": r(f.rms),
                           "worst": r(f.worst), "covered": r(f.covered)} for f in self.faces],
                "outliers": self.outliers,
                "outlier_worst": None if self.outlier_worst is None else [r(x) for x in self.outlier_worst],
                "holes": [{"length": r(h["length"]), "centre": [r(x) for x in h["centre"]]} for h in self.holes],
                "low_confidence": [f.face for f in self.low]}


def holes(pts: np.ndarray, tris: np.ndarray) -> list[dict]:
    """Loops of open edges in a mesh: each with its length and centre, longest first."""
    t = np.asarray(tris, dtype=np.int64)
    a = t.reshape(-1)
    b = t[:, [1, 2, 0]].reshape(-1)
    n = len(pts)
    key = np.minimum(a, b) * n + np.maximum(a, b)
    uniq, counts = np.unique(key, return_counts=True)
    once = np.isin(key, uniq[counts == 1])
    if not once.any():
        return []
    nxt: dict[int, list[int]] = {}
    for u, v in zip(a[once].tolist(), b[once].tolist()):
        nxt.setdefault(u, []).append(v)
        nxt.setdefault(v, []).append(u)
    seen: set[int] = set()
    out = []
    for start in nxt:
        if start in seen:
            continue
        loop, stack = [], [start]
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            loop.append(x)
            stack += [y for y in nxt[x] if y not in seen]
        idx = np.array(loop)
        q = np.asarray(pts)[idx]
        # length: the open edges among these points
        sel = once & np.isin(a, idx)
        length = float(np.linalg.norm(np.asarray(pts)[a[sel]] - np.asarray(pts)[b[sel]], axis=1).sum())
        out.append({"length": length, "centre": q.mean(axis=0).tolist(), "points": len(idx)})
    out.sort(key=lambda h: -h["length"])
    return out


def deviation(scan_pts: np.ndarray, scan_tris: np.ndarray | None, shape, tol: float, face_ids=None,
              fine: float = 0.0) -> Result:
    """Distances from the scan to ``shape`` against ``tol``. ``face_ids``: the model's face IDs in
    face order (for the per-face rows)."""
    from scipy.spatial import cKDTree

    from . import robust

    if tol <= 0:
        raise ValueError("the tolerance must be positive")
    diag = max(robust.diagonal(shape), 1e-9)
    tg = target(shape, fine or min(tol / 4, diag / 1000))
    q = np.asarray(scan_pts, float)
    if scan_tris is not None and len(scan_tris):
        # points no triangle uses are not part of the scan
        used = np.zeros(len(q), dtype=bool)
        used[np.asarray(scan_tris).reshape(-1)] = True
        if not used.all():
            new = np.cumsum(used) - 1
            q, scan_tris = q[used], new[np.asarray(scan_tris)]
    signed, tri = distances(tg, q)
    far = np.abs(signed) > OUTLIER * tol
    if scan_tris is not None and len(scan_tris):
        # far points on the scan's main surface are real (a bump, a dent): only far points in small
        # separate pieces (dust, the fixture, stray points) are outliers
        far &= _small_piece(len(q), np.asarray(scan_tris))
    keep = ~far
    res = Result(tol, int(keep.sum()), 0.0, 0.0, 0.0, 0.0, 0.0, signed=signed)
    res.outliers = int(far.sum())
    if far.any():
        i = int(np.argmax(np.abs(np.where(far, signed, 0))))
        res.outlier_worst = (*q[i].tolist(), float(signed[i]))
    if keep.any():
        d = signed[keep]
        res.within = float((np.abs(d) <= tol).mean())
        res.largest_out = float(max(d.max(), 0.0))
        res.largest_in = float(min(d.min(), 0.0))
        res.mean = float(d.mean())
        res.rms = float(np.sqrt((d * d).mean()))
    # per face, and how much of each face the scan covers
    spacing = _spacing(q, scan_tris)
    near_scan = cKDTree(q[keep]) if keep.any() else None
    if near_scan is not None:
        gap, _ = near_scan.query(tg.centres)
        covered_tri = gap <= max(3 * spacing, tol)
    else:
        covered_tri = np.zeros(len(tg.centres), dtype=bool)
    face_of_pt = tg.face_of_tri[tri]
    for fi in range(tg.nfaces):
        mine = keep & (face_of_pt == fi)
        on = tg.face_of_tri == fi
        if not on.any():
            continue
        area = tg.areas[on].sum()
        cov = float(tg.areas[on & covered_tri].sum() / area) if area > 0 else 0.0
        fid = face_ids[fi] if face_ids is not None and fi < len(face_ids) else fi + 1
        if mine.any():
            d = signed[mine]
            row = FaceRow(fid, int(mine.sum()), float((np.abs(d) <= tol).mean()), float(np.sqrt((d * d).mean())),
                          float(d[np.argmax(np.abs(d))]), cov)
        else:
            row = FaceRow(fid, 0, 0.0, 0.0, 0.0, cov)
        res.faces.append(row)
        if cov < COVERED:
            res.low.append(row)
    if scan_tris is not None and len(scan_tris):
        res.holes = holes(q, scan_tris)
    return res


def _small_piece(n: int, tris: np.ndarray, share: float = 0.01) -> np.ndarray:
    """A bool per point: in a connected piece of the mesh with under ``share`` of the points."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    a = np.concatenate([tris[:, 0], tris[:, 1], tris[:, 2]])
    b = np.concatenate([tris[:, 1], tris[:, 2], tris[:, 0]])
    g = coo_matrix((np.ones(len(a)), (a, b)), shape=(n, n))
    _k, label = connected_components(g, directed=False)
    size = np.bincount(label)
    return size[label] < share * n


def _spacing(q: np.ndarray, tris) -> float:
    """The scan's typical point spacing (median edge length, or nearest-neighbour distance)."""
    if tris is not None and len(tris):
        t = np.asarray(tris)[:20000]
        return float(np.median(np.linalg.norm(q[t[:, 0]] - q[t[:, 1]], axis=1)))
    from scipy.spatial import cKDTree

    d, _ = cKDTree(q).query(q[:20000], k=2)
    return float(np.median(d[:, 1]))


class Field:
    """Signed distances at any points, for colouring the scan in the view (like a STRESS result)."""

    def __init__(self, tg: Target):
        self.tg = tg

    def at(self, pts) -> np.ndarray:
        return distances(self.tg, np.asarray(pts, float))[0]


def band_colours(signed: np.ndarray, tol: float) -> np.ndarray:
    """Green within the tolerance; yellow to red further out (outside the model), cyan to blue
    further in; past three tolerances magenta (out) or dark blue (in)."""
    x = np.asarray(signed, float) / max(tol, 1e-30)
    out = np.empty((len(x), 3))
    out[:] = (0.25, 0.75, 0.3)  # within
    up = x > 1
    f = np.clip((x[up] - 1) / 2, 0, 1)[:, None]
    out[up] = np.array([0.95, 0.85, 0.15]) * (1 - f) + np.array([0.9, 0.15, 0.1]) * f
    dn = x < -1
    f = np.clip((-x[dn] - 1) / 2, 0, 1)[:, None]
    out[dn] = np.array([0.2, 0.8, 0.95]) * (1 - f) + np.array([0.15, 0.25, 0.9]) * f
    out[x > 3] = (0.85, 0.2, 0.85)
    out[x < -3] = (0.1, 0.1, 0.45)
    return out
