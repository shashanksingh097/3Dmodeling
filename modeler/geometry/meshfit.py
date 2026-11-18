"""Fitting smooth NURBS surfaces to meshes (scan to CAD).

``fit_patch`` turns a patch of triangles (a whole open scan, or the part of a
mesh you painted with MASK) into one smooth B-spline face:

1. The patch's best-fit plane (principal axes of its points) gives each point
   a position (x, y) on the plane and a height h above it. The patch must be
   a "height field" over that plane: no triangle may turn over when laid flat
   on it, or the patch folds back and needs splitting into smaller pieces.
2. The surface is a B-spline whose control points sit on an even grid over
   the plane (so x and y are reproduced exactly) and whose heights are fitted
   by least squares, with a small bending penalty so that control points with
   no data under them stay smooth. The grid is made finer until every mesh
   point is within the tolerance, or the grid limit is reached.
3. The patch's outline (and any holes in it) become trimming curves on the
   surface, fitted as smooth closed curves, so the face has the patch's
   shape and not the grid's rectangle (``trim=False`` keeps the rectangle).

The deviation reported is measured along the plane's normal at every mesh
point, which for a height field is the distance a person would measure.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import nurbs

MAX_POLES = 40  # per direction
MIN_POLES = 4
FIT_POINTS = 60_000  # fit on at most this many points; deviation is checked on all
BEND = 1e-4  # bending penalty, relative to the data term


class FitError(Exception):
    """A patch that cannot be fitted as asked (it folds, it is empty ...)."""


@dataclass
class Fit:
    shape: object  # the face
    surface: object  # Geom_BSplineSurface
    poles: tuple[int, int]
    max_dev: float
    mean_dev: float
    points: int
    reached: bool  # max_dev <= tol


# ---- the patch --------------------------------------------------------------------------
def patch(pts: np.ndarray, tris: np.ndarray, keep: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, int]:
    """The triangles to fit: those with every corner kept (``keep`` per point, None = all),
    largest connected piece only. Returns (points, triangles, pieces found)."""
    t = tris if keep is None else tris[np.all(keep[tris], axis=1)]
    if not len(t):
        raise FitError("no triangles to fit (paint the region with MASK first, or fit ALL)")
    labels = _components(len(pts), t)
    lab = labels[t[:, 0]]
    ids, counts = np.unique(lab, return_counts=True)
    t = t[lab == ids[np.argmax(counts)]]
    used = np.unique(t)
    remap = -np.ones(len(pts), dtype=np.int64)
    remap[used] = np.arange(len(used))
    return pts[used], remap[t], len(ids)


def _components(n: int, t: np.ndarray) -> np.ndarray:
    parent = np.arange(n)

    def find(a):
        root = a
        while parent[root] != root:
            root = parent[root]
        while parent[a] != root:
            parent[a], a = root, parent[a]
        return root

    for a, b in np.concatenate([t[:, [0, 1]], t[:, [1, 2]]]):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    return np.array([find(i) for i in range(n)])


def boundary_loops(t: np.ndarray) -> list[list[int]]:
    """Closed loops of edges used by one triangle only, each in walking order."""
    e = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    key = np.sort(e, axis=1)
    _, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    inv = inv.reshape(-1)
    border = e[cnt[inv] == 1]
    nxt: dict[int, list[int]] = {}
    for a, b in border:
        nxt.setdefault(int(a), []).append(int(b))
    loops, seen = [], set()
    for start in list(nxt):
        if start in seen:
            continue
        loop, a = [], start
        while a not in seen and a in nxt:
            seen.add(a)
            loop.append(a)
            a = nxt[a].pop() if len(nxt[a]) > 1 else nxt[a][0]
        if len(loop) >= 3:
            loops.append(loop)
    return loops


# ---- the plane and the height field ------------------------------------------------------
def frame(pts: np.ndarray, tris: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(origin, 3x3 axes as rows: x, y, normal), the normal on the side the triangles face."""
    c = pts.mean(axis=0)
    _, _, vt = np.linalg.svd(pts - c, full_matrices=False)
    ax = vt.copy()
    n = np.cross(pts[tris[:, 1]] - pts[tris[:, 0]], pts[tris[:, 2]] - pts[tris[:, 0]]).sum(axis=0)
    if np.dot(n, ax[2]) < 0:
        ax[2] = -ax[2]
    ax[1] = np.cross(ax[2], ax[0])
    return c, ax


def folds(xy: np.ndarray, tris: np.ndarray) -> float:
    """Share of the patch's area whose triangles turn over when laid on the plane."""
    a = xy[tris[:, 1]] - xy[tris[:, 0]]
    b = xy[tris[:, 2]] - xy[tris[:, 0]]
    s = a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]
    total = np.abs(s).sum()
    return float(np.abs(s[s <= 0]).sum() / total) if total > 0 else 1.0


# ---- least squares ------------------------------------------------------------------------
def _knots(n: int, deg: int) -> tuple[list[float], list[int], np.ndarray]:
    ks, ms = nurbs._uniform_clamped(n, deg)
    return ks, ms, np.repeat(np.asarray(ks), ms)


def _greville(full: np.ndarray, n: int, deg: int) -> np.ndarray:
    return np.array([full[i + 1: i + deg + 1].mean() for i in range(n)])


def _second_diff(n: int) -> np.ndarray:
    d = np.zeros((max(n - 2, 0), n))
    for i in range(n - 2):
        d[i, i: i + 3] = (1.0, -2.0, 1.0)
    return d


def _solve(u: np.ndarray, v: np.ndarray, h: np.ndarray, nu: int, nv: int, deg: int) -> tuple[np.ndarray, tuple]:
    """Heights of an nu x nv control grid fitted to h(u, v)."""
    ku, mu, fu = _knots(nu, deg)
    kv, mv, fv = _knots(nv, deg)
    bu, bv = nurbs.basis(fu, deg, u), nurbs.basis(fv, deg, v)
    m = nu * nv
    ata, atb = np.zeros((m, m)), np.zeros(m)
    for s in range(0, len(u), 4000):
        a = (bu[s: s + 4000, :, None] * bv[s: s + 4000, None, :]).reshape(-1, m)
        ata += a.T @ a
        atb += a.T @ h[s: s + 4000]
    du, dv = _second_diff(nu), _second_diff(nv)
    pen = np.kron(du.T @ du, np.eye(nv)) + np.kron(np.eye(nu), dv.T @ dv)
    lam = BEND * np.trace(ata) / max(np.trace(pen), 1e-30)
    z = np.linalg.solve(ata + lam * pen + 1e-12 * np.eye(m), atb)
    return z.reshape(nu, nv), (ku, mu, fu, kv, mv, fv)


def _heights(z: np.ndarray, knots: tuple, deg: int, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    _, _, fu, _, _, fv = knots
    out = np.empty(len(u))
    for s in range(0, len(u), 20000):
        bu, bv = nurbs.basis(fu, deg, u[s: s + 20000]), nurbs.basis(fv, deg, v[s: s + 20000])
        out[s: s + 20000] = np.einsum("pi,ij,pj->p", bu, z, bv)
    return out


def _too_many(nu: int, nv: int, points: int, grow: float) -> bool:
    """A finer grid would have more unknowns than a quarter of the points: it would only
    follow the mesh's own facets and noise, not the shape."""
    return nu * nv * grow * grow > max(points / 4, 16)


# ---- the fit ---------------------------------------------------------------------------------
def fit_patch(pts: np.ndarray, tris: np.ndarray, tol: float, deg: int = 3, trim: bool = True,
              max_poles: int = MAX_POLES) -> Fit:
    if len(tris) < 2:
        raise FitError("the patch needs at least 2 triangles")
    c, ax = frame(pts, tris)
    loc = (pts - c) @ ax.T
    xy, h = loc[:, :2], loc[:, 2]
    if folds(xy, tris) > 0.002:
        raise FitError("the patch folds back over itself when seen from its average direction; "
                       "fit it in smaller pieces (MASK a smaller region)")
    lo, hi = xy.min(axis=0), xy.max(axis=0)
    span = np.maximum(hi - lo, 1e-9)
    pad = 0.01 * span
    lo, hi = lo - pad, hi + pad
    span = hi - lo
    uv = (xy - lo) / span
    pick = np.arange(len(uv))
    if len(pick) > FIT_POINTS:
        pick = np.random.default_rng(0).choice(len(uv), FIT_POINTS, replace=False)
    ratio = span[0] / span[1]
    k = MIN_POLES
    while True:
        nu = int(np.clip(round(k * max(ratio, 1) ** 0.5), deg + 1, max_poles))
        nv = int(np.clip(round(k / min(ratio, 1) ** 0.5), deg + 1, max_poles))
        z, knots = _solve(uv[pick, 0], uv[pick, 1], h[pick], nu, nv, deg)
        dev = np.abs(_heights(z, knots, deg, uv[:, 0], uv[:, 1]) - h)
        if dev.max() <= tol or (nu >= max_poles and nv >= max_poles) or _too_many(nu, nv, len(pts), 1.5):
            break
        k = int(k * 1.5) + 1
    ku, mu, fu, kv, mv, fv = knots
    gu, gv = _greville(fu, nu, deg), _greville(fv, nv, deg)
    net = []
    for i in range(nu):
        row = []
        for j in range(nv):
            q = np.array([lo[0] + gu[i] * span[0], lo[1] + gv[j] * span[1], z[i, j]])
            row.append(tuple(c + q @ ax))
        net.append(row)
    surf = nurbs.make_surface(net, deg_u=deg, deg_v=deg, knots_u=ku, mults_u=mu, knots_v=kv, mults_v=mv)
    face = _trimmed_face(surf, uv, tris) if trim else nurbs.surface_shape(surf)
    return Fit(face, surf, (nu, nv), float(dev.max()), float(dev.mean()), len(pts), bool(dev.max() <= tol))


# ---- trimming ----------------------------------------------------------------------------
def _loop_area(p: np.ndarray) -> float:
    return 0.5 * float(np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1]))


def _trim_curve(p2: np.ndarray):
    """A smooth closed 2D curve through a loop of (u, v) points."""
    from OCP.GeomAPI import GeomAPI
    from OCP.gp import gp_Ax3, gp_Dir, gp_Pln, gp_Pnt

    d = np.linalg.norm(np.diff(np.vstack([p2, p2[:1]]), axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(d)])
    count = int(np.clip(len(p2), 24, 400))
    at = np.linspace(0, s[-1], count + 1)
    q = np.column_stack([np.interp(at, s, np.append(p2[:, 0], p2[0, 0])),
                         np.interp(at, s, np.append(p2[:, 1], p2[0, 1]))])
    n = int(np.clip(len(p2) // 3, 8, 120))
    c3 = nurbs.fit_curve(np.column_stack([q, np.zeros(len(q))]), n, 3, closed=True)
    pln = gp_Pln(gp_Ax3(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1), gp_Dir(1, 0, 0)))
    to2d = getattr(GeomAPI, "To2d_s", None) or GeomAPI.To2d
    return to2d(c3, pln)


def _trimmed_face(surf, uv: np.ndarray, tris: np.ndarray):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
    from OCP.BRepLib import BRepLib
    from OCP.ShapeFix import ShapeFix_Face

    loops = [uv[np.array(lp)] for lp in boundary_loops(tris)]
    if not loops:
        return nurbs.surface_shape(surf)  # closed patch: nothing to trim by
    u0, u1, v0, v1 = surf.Bounds()
    loops = [np.column_stack([u0 + p[:, 0] * (u1 - u0), v0 + p[:, 1] * (v1 - v0)]) for p in loops]
    loops.sort(key=lambda p: -abs(_loop_area(p)))
    wires = []
    for i, p in enumerate(loops):
        if abs(_loop_area(p)) < 1e-6 * abs(_loop_area(loops[0])):
            continue  # a sliver from a stray triangle
        outer = i == 0
        if (_loop_area(p) > 0) != outer:  # outer loop anticlockwise, holes clockwise
            p = p[::-1]
        c2 = _trim_curve(p)
        e = BRepBuilderAPI_MakeEdge(c2, surf).Edge()
        wires.append(BRepBuilderAPI_MakeWire(e).Wire())
    mk = BRepBuilderAPI_MakeFace(surf, wires[0], True)
    for w in wires[1:]:
        mk.Add(w)
    if not mk.IsDone():
        raise FitError("the kernel could not trim the surface to the patch outline; try trim NO")
    face = mk.Face()
    build = getattr(BRepLib, "BuildCurves3d_s", None) or BRepLib.BuildCurves3d
    build(face)
    fix = ShapeFix_Face(face)
    fix.Perform()
    return fix.Face()


# ---- closed meshes: one surface round the whole body --------------------------------------
def star_centre(pts: np.ndarray, tris: np.ndarray) -> np.ndarray:
    """A point from which every triangle is seen from outside, or a FitError."""
    a, b, c3 = pts[tris[:, 0]], pts[tris[:, 1]], pts[tris[:, 2]]
    n = np.cross(b - a, c3 - a)
    vol6 = np.einsum("ij,ij->i", a, n)
    tot = vol6.sum()
    if abs(tot) < 1e-12:
        raise FitError("the mesh encloses no volume")
    centre = ((a + b + c3) * vol6[:, None]).sum(axis=0) / (4 * tot)  # the volume's centre
    mid = (a + b + c3) / 3
    side = np.einsum("ij,ij->i", n, mid - centre) * np.sign(tot)
    area = np.linalg.norm(n, axis=1)
    if area[side <= 0].sum() > 0.002 * area.sum():
        raise FitError("the body is not round enough to wrap one surface round it (from its centre some of "
                       "it hides other parts); fit it in pieces with MASK and FITSURF, b, MASK")
    return centre


def pole_axes(rel: np.ndarray) -> np.ndarray:
    """Axes (rows x, y, z) for wrapping a surface round a body: the z ends gather to points,
    which look pinched where the shape has detail, so z goes where the surface is plainest
    (the radius varies least near both ends)."""
    r = np.linalg.norm(rel, axis=1)
    d = rel / np.maximum(r, 1e-12)[:, None]
    _, _, vt = np.linalg.svd(rel - rel.mean(axis=0), full_matrices=False)
    cands = list(vt) + list(np.eye(3))
    g = (1 + 5 ** 0.5) / 2  # and the 12 directions of an icosahedron's corners (6 axes)
    cands += [np.array(v) / np.linalg.norm(v) for v in ((0, 1, g), (0, 1, -g), (1, g, 0), (1, -g, 0),
                                                         (g, 0, 1), (-g, 0, 1))]
    best, score = cands[0], np.inf
    for z in cands:
        c = d @ z
        sc = 0.0
        for near in (c > 0.9, c < -0.9):  # within about 25 degrees of either end
            if near.sum() >= 3:
                sc += float(np.std(r[near]))
        if sc < score - 1e-12:
            best, score = z, sc
    z = best / np.linalg.norm(best)
    x = np.cross(z, [1.0, 0, 0] if abs(z[0]) < 0.9 else [0, 1.0, 0])
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    # the seam (where the surface's u starts and ends) goes down the plainest side too
    lon = np.arctan2(d @ y, d @ x)
    side = np.abs(d @ z) < 0.9
    best_a, score = 0.0, np.inf
    for a in np.linspace(-np.pi, np.pi, 36, endpoint=False):
        near = side & (np.abs(np.angle(np.exp(1j * (lon - a)))) < np.radians(8))
        sc = float(np.std(r[near])) if near.sum() >= 3 else np.inf
        if sc < score:
            best_a, score = a, sc
    x2 = np.cos(best_a) * x + np.sin(best_a) * y
    return np.array([x2, np.cross(z, x2), z])


def _periodic_basis(n: int, deg: int, u: np.ndarray) -> np.ndarray:
    h = 1.0 / n
    kn = np.array([(i - deg) * h for i in range(n + 2 * deg + 1)])
    b = nurbs.basis(kn, deg, np.mod(u, 1.0))
    out = np.zeros((len(u), n))
    for col in range(b.shape[1]):
        out[:, col % n] += b[:, col]
    return out


def fit_closed(pts: np.ndarray, tris: np.ndarray, tol: float, deg: int = 3, max_poles: int = MAX_POLES) -> Fit:
    """One smooth surface wrapped round a closed mesh that is seen whole from its centre,
    closed into a solid. Round in u (longitude), its two ends gather to single points (poles)."""
    centre = star_centre(pts, tris)
    ax = pole_axes(pts - centre)
    d = (pts - centre) @ ax.T
    r = np.linalg.norm(d, axis=1)
    u = np.mod(np.arctan2(d[:, 1], d[:, 0]) / (2 * np.pi), 1.0)
    v = np.arccos(np.clip(d[:, 2] / np.maximum(r, 1e-12), -1, 1)) / np.pi
    pick = np.arange(len(u))
    if len(pick) > FIT_POINTS:
        pick = np.random.default_rng(0).choice(len(u), FIT_POINTS, replace=False)
    k = 6
    while True:
        nu = int(np.clip(2 * k, deg + 2, max_poles))
        nv = int(np.clip(k, deg + 2, max_poles))
        net, knots_v = _solve_closed(u[pick], v[pick], pts[pick], nu, nv, deg)
        surf = _closed_surface(net, knots_v, deg)
        dev = _distances(surf, pts)
        if dev.max() <= tol or (nu >= max_poles and nv >= max_poles) or _too_many(nu, nv, len(pts), 1.5):
            break
        k = int(k * 1.5) + 1
    return Fit(_solid(surf), surf, (nu, nv), float(dev.max()), float(dev.mean()), len(pts), bool(dev.max() <= tol))


def _solve_closed(u, v, x, nu, nv, deg):
    ks, ms, fv = _knots(nv, deg)
    bu = _periodic_basis(nu, deg, u)
    bv = nurbs.basis(fv, deg, v)
    # unknowns: the south pole, rows 1..nv-2 (nu points each), the north pole
    m = 2 + nu * (nv - 2)
    a = np.zeros((len(u), m))
    a[:, 0] = bv[:, 0]
    a[:, 1] = bv[:, -1]
    a[:, 2:] = (bu[:, :, None] * bv[:, None, 1:-1]).reshape(len(u), -1)
    du = np.zeros((nu, nu))
    for i in range(nu):
        du[i, (i - 1) % nu], du[i, i], du[i, (i + 1) % nu] = 1, -2, 1
    pen = np.zeros((m, m))
    pen[2:, 2:] = np.kron(du.T @ du, np.eye(nv - 2))
    ata = a.T @ a
    lam = BEND * np.trace(ata) / max(np.trace(pen), 1e-30)
    sol = np.linalg.solve(ata + lam * pen + 1e-12 * np.eye(m), a.T @ x)
    net = np.empty((nu, nv, 3))
    net[:, 0], net[:, -1] = sol[0], sol[1]
    net[:, 1:-1] = sol[2:].reshape(nu, nv - 2, 3)
    return net, (ks, ms)


def _closed_surface(net, knots_v, deg):
    """The kernel's surface, round in u; OCCT counts periodic poles from its own start,
    so try the shifts and keep the one that matches the fit."""
    from OCP.Geom import Geom_BSplineSurface

    nu, nv = net.shape[:2]
    ku, mu = [i / nu for i in range(nu + 1)], [1] * (nu + 1)
    ks, ms = knots_v
    probe_u = np.array([0.13, 0.41, 0.77])
    want = np.einsum("pi,ijk->pjk", _periodic_basis(nu, deg, probe_u), net)[:, nv // 2]
    best, err = None, np.inf
    for s in range(nu):
        sh = np.roll(net, -s, axis=0)
        poles = nurbs._Arr2Pnt(1, nu, 1, nv)
        for i in range(nu):
            for j in range(nv):
                poles.SetValue(i + 1, j + 1, nurbs.gp_Pnt(*map(float, sh[i, j])))
        srf = Geom_BSplineSurface(poles, nurbs._real1(ku), nurbs._real1(ks), nurbs._int1(mu), nurbs._int1(ms),
                                  deg, deg, True, False)
        u0, u1, v0, v1 = srf.Bounds()
        vmid = v0 + (v1 - v0) * _greville_mid(ks, ms, nv, deg)
        e = 0.0
        for pu, w in zip(probe_u, want):
            q = srf.Value(u0 + pu * (u1 - u0), vmid)
            e = max(e, float(np.linalg.norm(np.array([q.X(), q.Y(), q.Z()]) - w)))
        if e < err:
            best, err = srf, e
    return best


def _greville_mid(ks, ms, nv, deg):
    # the v at which row nv // 2 alone is not what we compare: compare the full surface at that v
    full = np.repeat(np.asarray(ks), ms)
    return float(full[nv // 2 + 1: nv // 2 + deg + 1].mean())


def _distances(surf, pts: np.ndarray, sample: int = 4000) -> np.ndarray:
    """Distance from (a sample of) the points to the surface."""
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.gp import gp_Pnt

    idx = np.arange(len(pts))
    if len(idx) > sample:
        idx = np.random.default_rng(1).choice(len(idx), sample, replace=False)
    proj = GeomAPI_ProjectPointOnSurf()
    u0, u1, v0, v1 = surf.Bounds()
    proj.Init(surf, u0, u1, v0, v1)
    out = np.empty(len(idx))
    for k, i in enumerate(idx):
        proj.Perform(gp_Pnt(*map(float, pts[i])))
        out[k] = proj.LowerDistance() if proj.NbPoints() else np.inf
    return out


def _solid(surf):
    """The closed face as a solid, its outside out."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepLib import BRepLib
    from OCP.TopoDS import TopoDS_Shell, TopoDS_Solid

    face = BRepBuilderAPI_MakeFace(surf, 1e-6).Face()
    bld = BRep_Builder()
    shell, solid = TopoDS_Shell(), TopoDS_Solid()
    bld.MakeShell(shell)
    bld.Add(shell, face)
    shell.Closed(True)
    bld.MakeSolid(solid)
    bld.Add(solid, shell)
    orient = getattr(BRepLib, "OrientClosedSolid_s", None) or BRepLib.OrientClosedSolid
    orient(solid)
    return solid
