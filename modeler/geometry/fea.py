"""A first strength check (PLAN item 26): linear static stress in a solid.

The solid is filled with equal cubes (a voxel grid, cells whose centre is inside), each a
hexahedral element with incompatible modes, so thin parts in bending are not too stiff. Faces
are fixed or loaded through the grid nodes near them. The system is solved with scipy, and
the result gives von Mises stress per cell, displacement per node, and a field to colour the
surface with.

Units: lengths in mm, forces in N, so stresses and moduli are in MPa (N/mm2).

It is a first check, not a certified analysis: the stair-stepped surface is within one cell of
the true one, stress peaks at sharp inside corners and at the edge of a fixed face are not
converged (the report gives a high percentile beside the peak for that reason), and materials
are linear and isotropic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


class FeaError(Exception):
    pass


@dataclass(frozen=True)
class Elastic:
    E: float  # MPa
    nu: float
    yield_: float  # MPa (for brittle materials: the strength)


ELASTIC = {
    "STEEL": Elastic(200_000, 0.29, 250),
    "STAINLESS": Elastic(193_000, 0.29, 215),
    "CASTIRON": Elastic(110_000, 0.26, 200),
    "ALUMINIUM": Elastic(69_000, 0.33, 276),
    "TITANIUM": Elastic(114_000, 0.34, 880),
    "COPPER": Elastic(117_000, 0.34, 70),
    "BRASS": Elastic(100_000, 0.34, 200),
    "ABS": Elastic(2_300, 0.35, 40),
    "NYLON": Elastic(2_700, 0.39, 50),
    "PLA": Elastic(3_500, 0.36, 50),
    "WOOD": Elastic(11_000, 0.30, 40),
    "GLASS": Elastic(70_000, 0.22, 33),
}


# ---- the element --------------------------------------------------------------------------------
_CORNERS = np.array([(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
                     (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)], float)


def _D(E: float, nu: float) -> np.ndarray:
    lam = E * nu / ((1 + nu) * (1 - 2 * nu))
    mu = E / (2 * (1 + nu))
    D = np.zeros((6, 6))
    D[:3, :3] = lam
    D[np.arange(3), np.arange(3)] = lam + 2 * mu
    D[np.arange(3, 6), np.arange(3, 6)] = mu
    return D


def _B(dN: np.ndarray) -> np.ndarray:
    """Strain-displacement matrix from shape function gradients dN (n, 3), engineering shear."""
    n = len(dN)
    B = np.zeros((6, 3 * n))
    for i in range(n):
        x, y, z = dN[i]
        B[0, 3 * i] = x
        B[1, 3 * i + 1] = y
        B[2, 3 * i + 2] = z
        B[3, 3 * i], B[3, 3 * i + 1] = y, x
        B[4, 3 * i + 1], B[4, 3 * i + 2] = z, y
        B[5, 3 * i], B[5, 3 * i + 2] = z, x
    return B


def _grads(xi: np.ndarray, h) -> tuple[np.ndarray, np.ndarray]:
    """d/dx of the 8 corner functions and the 3 incompatible bubbles at xi, for a box of sides h."""
    h = np.broadcast_to(np.asarray(h, float), (3,))
    c = _CORNERS
    dN = np.empty((8, 3))
    for k in range(3):
        f = 0.125 * c[:, k]
        for j in range(3):
            if j != k:
                f = f * (1 + c[:, j] * xi[j])
        dN[:, k] = f
    dB = np.diag(-2 * xi * (2 / h))  # bubbles 1 - xi_k^2
    return dN * (2 / h)[None, :], dB


def element(E: float, nu: float, h) -> np.ndarray:
    """The 24 x 24 stiffness of a box of sides h (incompatible modes condensed out)."""
    D = _D(E, nu)
    g = 1 / math.sqrt(3)
    Kuu = np.zeros((24, 24))
    Kua = np.zeros((24, 9))
    Kaa = np.zeros((9, 9))
    w = float(np.prod(np.broadcast_to(np.asarray(h, float), (3,)) / 2))  # det J times unit weights
    for a in (-g, g):
        for b in (-g, g):
            for c in (-g, g):
                dN, dB = _grads(np.array([a, b, c]), h)
                Bu, Ba = _B(dN), _B(dB)
                Kuu += Bu.T @ D @ Bu * w
                Kua += Bu.T @ D @ Ba * w
                Kaa += Ba.T @ D @ Ba * w
    return Kuu - Kua @ np.linalg.solve(Kaa, Kua.T)


# ---- the grid -----------------------------------------------------------------------------------
@dataclass
class Grid:
    origin: np.ndarray
    h: np.ndarray  # the cell's sides along x, y, z
    shape: tuple  # cells along x, y, z
    cells: np.ndarray  # (m, 3) i, j, k of the cells inside
    nodes: np.ndarray  # (n, 3) i, j, k of the nodes used
    conn: np.ndarray  # (m, 8) node numbers of each cell (corner order of _CORNERS)

    def node_xyz(self) -> np.ndarray:
        return self.origin + self.nodes * self.h[None, :]

    def cell_xyz(self) -> np.ndarray:
        return self.origin + (self.cells + 0.5) * self.h[None, :]


def inside(pts: np.ndarray, tris: np.ndarray, xs: np.ndarray, ys: np.ndarray, zs: np.ndarray) -> np.ndarray:
    """(nx, ny, nz) booleans: is each point (xs[i], ys[j], zs[k]) inside the closed triangle mesh?
    Rays go up along z from each column; an odd number of crossings below a point means inside."""
    nx, ny = len(xs), len(ys)
    hits: list[list[float]] = [[] for _ in range(nx * ny)]
    tp = pts[tris]  # (t, 3, 3)
    x0, x1 = tp[:, :, 0].min(axis=1), tp[:, :, 0].max(axis=1)
    y0, y1 = tp[:, :, 1].min(axis=1), tp[:, :, 1].max(axis=1)
    i0 = np.searchsorted(xs, x0)
    i1 = np.searchsorted(xs, x1, side="right")
    j0 = np.searchsorted(ys, y0)
    j1 = np.searchsorted(ys, y1, side="right")
    for t in np.nonzero((i1 > i0) & (j1 > j0))[0]:
        a, b, c = tp[t]
        det = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])
        if abs(det) < 1e-300:
            continue  # seen edge-on from below
        X, Y = np.meshgrid(xs[i0[t]:i1[t]], ys[j0[t]:j1[t]], indexing="ij")
        u = ((X - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (Y - a[1])) / det
        v = ((b[0] - a[0]) * (Y - a[1]) - (X - a[0]) * (b[1] - a[1])) / det
        ok = (u >= 0) & (v >= 0) & (u + v <= 1)
        if not ok.any():
            continue
        z = a[2] + u * (b[2] - a[2]) + v * (c[2] - a[2])
        ii, jj = np.nonzero(ok)
        for p, q, zz in zip(ii + i0[t], jj + j0[t], z[ok]):
            hits[p * ny + q].append(float(zz))
    out = np.zeros((nx, ny, len(zs)), bool)
    for col, hz in enumerate(hits):
        if len(hz) < 2:
            continue
        hz = np.sort(hz)
        below = np.searchsorted(hz, zs)
        out[col // ny, col % ny] = (below % 2) == 1
    return out


def voxelize(shape, h: float) -> Grid:
    from . import meshbody as mb

    lo, hi = _box(shape)
    size = np.maximum(hi - lo, 1e-9)
    # the box divides into whole cells (each side as near h as it goes), so flat faces square to
    # the axes fall exactly on the grid
    n = np.maximum(np.round(size / h).astype(int), 1)
    if int(np.prod(n)) > 4_000_000:
        raise FeaError("the cells are too small for this part (more than 4 million in its box)")
    hv = size / n
    origin = lo
    pts, tris = mb.triangles_of(shape, max(h / 8, float(np.linalg.norm(size)) * 2e-4))
    # centres, nudged off the exact grid so rays do not run along edges of the triangles
    jig = hv * np.array([1.234567e-4, 2.345678e-4, 0.0])
    xs = origin[0] + (np.arange(n[0]) + 0.5) * hv[0] + jig[0]
    ys = origin[1] + (np.arange(n[1]) + 0.5) * hv[1] + jig[1]
    zs = origin[2] + (np.arange(n[2]) + 0.5) * hv[2]
    filled = inside(pts, np.asarray(tris), xs, ys, zs)
    cells = np.argwhere(filled)
    if len(cells) == 0:
        raise FeaError("no cell lies inside the part: use a smaller cell size")
    corners = (cells[:, None, :] + ((_CORNERS + 1) / 2).astype(int)[None, :, :]).reshape(-1, 3)
    key = (corners[:, 0] * (n[1] + 1) + corners[:, 1]) * (n[2] + 1) + corners[:, 2]
    uniq, inv = np.unique(key, return_inverse=True)
    nodes = np.stack([uniq // ((n[1] + 1) * (n[2] + 1)), (uniq // (n[2] + 1)) % (n[1] + 1), uniq % (n[2] + 1)],
                     axis=1)
    return Grid(origin, hv, tuple(int(v) for v in n), cells, nodes, inv.reshape(-1, 8))


def _box(shape):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    (getattr(BRepBndLib, "AddOptimal_s", None) or BRepBndLib.AddOptimal)(shape, box, False, False)
    a, b = box.CornerMin(), box.CornerMax()
    return np.array([a.X(), a.Y(), a.Z()]), np.array([b.X(), b.Y(), b.Z()])


# ---- boundary conditions and the solve ------------------------------------------------------------
def surface_nodes(grid: Grid) -> np.ndarray:
    """The nodes on the grid's outside (used by fewer than 8 cells)."""
    count = np.bincount(grid.conn.ravel(), minlength=len(grid.nodes))
    return np.nonzero(count < 8)[0]


def nodes_near(grid: Grid, samples: np.ndarray, reach: float) -> np.ndarray:
    """Surface nodes within ``reach`` of any of the sample points (on a face)."""
    from scipy.spatial import cKDTree

    surf = surface_nodes(grid)
    xyz = grid.node_xyz()[surf]
    d, _ = cKDTree(samples).query(xyz, distance_upper_bound=reach)
    return surf[np.isfinite(d)]


@dataclass
class Result:
    grid: Grid
    u: np.ndarray  # (n, 3) node displacements
    vm: np.ndarray  # (m,) von Mises per cell
    node_vm: np.ndarray  # (n,) averaged to the nodes
    material: str
    elastic: Elastic
    fixed: int  # nodes held
    loaded: int  # nodes loaded
    force: np.ndarray  # total applied force
    reaction: np.ndarray  # total force at the fixed nodes (should balance the load)
    seconds: float = 0.0
    notes: list = field(default_factory=list)

    def at(self, points: np.ndarray) -> np.ndarray:
        """von Mises at any points (nearest node)."""
        from scipy.spatial import cKDTree

        _d, idx = cKDTree(self.grid.node_xyz()).query(np.asarray(points, float))
        return self.node_vm[idx]

    def peak(self) -> tuple[float, np.ndarray]:
        i = int(np.argmax(self.vm))
        return float(self.vm[i]), self.grid.cell_xyz()[i]

    def deflection(self) -> tuple[float, np.ndarray]:
        mag = np.linalg.norm(self.u, axis=1)
        i = int(np.argmax(mag))
        return float(mag[i]), self.grid.node_xyz()[i]


def solve(grid: Grid, elastic: Elastic, material: str, fixed: np.ndarray, loads: list) -> Result:
    """``fixed``: node numbers held in all directions; ``loads``: [(node numbers, total force vector)]."""
    import time

    import scipy.sparse as sp
    import scipy.sparse.linalg as sla

    t0 = time.time()
    n = len(grid.nodes)
    ke = element(elastic.E, elastic.nu, grid.h)
    dofs = (3 * grid.conn[:, :, None] + np.arange(3)[None, None, :]).reshape(len(grid.conn), 24)
    rows = np.repeat(dofs, 24, axis=1).ravel()
    cols = np.tile(dofs, (1, 24)).ravel()
    vals = np.tile(ke.ravel(), len(grid.conn))
    K = sp.coo_matrix((vals, (rows, cols)), shape=(3 * n, 3 * n)).tocsr()
    F = np.zeros(3 * n)
    total = np.zeros(3)
    for nodes, force in loads:
        if len(nodes) == 0:
            continue
        f = np.asarray(force, float) / len(nodes)
        for k in range(3):
            np.add.at(F, 3 * nodes + k, f[k])
        total += np.asarray(force, float)
    held = np.zeros(3 * n, bool)
    held[(3 * fixed[:, None] + np.arange(3)[None, :]).ravel()] = True
    free = np.nonzero(~held)[0]
    Kff = K[free][:, free].tocsr()
    u = np.zeros(3 * n)
    # conjugate gradients with the diagonal as preconditioner: on these grids far faster than a
    # direct solve, which is only the fallback
    diag = Kff.diagonal()
    M = sp.diags(1 / np.where(diag > 0, diag, 1))
    sol, info = sla.cg(Kff, F[free], M=M, rtol=1e-10, maxiter=50_000)
    if info != 0:
        if len(free) > 300_000:
            raise FeaError("the solver did not converge (is the part held so it cannot move freely?)")
        sol = sla.spsolve(Kff.tocsc(), F[free], permc_spec="MMD_AT_PLUS_A")
    u[free] = sol
    if not np.all(np.isfinite(u)):
        raise FeaError("no solution: the part is not held enough to stop it moving (fix more faces)")
    reaction = (K @ u - F).reshape(n, 3)[fixed].sum(axis=0)
    # stress at each cell's centre (the incompatible modes add nothing there)
    dN, _ = _grads(np.zeros(3), grid.h)
    B = _B(dN)
    D = _D(elastic.E, elastic.nu)
    s = (D @ B @ u[dofs].T).T  # (m, 6)
    vm = np.sqrt(0.5 * ((s[:, 0] - s[:, 1]) ** 2 + (s[:, 1] - s[:, 2]) ** 2 + (s[:, 2] - s[:, 0]) ** 2)
                 + 3 * (s[:, 3] ** 2 + s[:, 4] ** 2 + s[:, 5] ** 2))
    acc = np.zeros(n)
    cnt = np.zeros(n)
    np.add.at(acc, grid.conn.ravel(), np.repeat(vm, 8))
    np.add.at(cnt, grid.conn.ravel(), 1)
    return Result(grid, u.reshape(n, 3), vm, acc / np.maximum(cnt, 1), material, elastic, len(fixed),
                  sum(len(nd) for nd, _f in loads), total, reaction, time.time() - t0)


def face_samples(face, h: float) -> tuple[np.ndarray, float, np.ndarray]:
    """Points on a face (to find the grid nodes near it), its area and its mean outward normal."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_REVERSED
    from OCP.TopLoc import TopLoc_Location

    f = BRepBuilderAPI_Copy(face).Shape()
    from OCP.TopoDS import TopoDS

    f = (getattr(TopoDS, "Face_s", None) or TopoDS.Face)(f)
    BRepMesh_IncrementalMesh(f, h / 6, False, 0.3, True)
    loc = TopLoc_Location()
    tri = (getattr(BRep_Tool, "Triangulation_s", None) or BRep_Tool.Triangulation)(f, loc)
    if tri is None:
        raise FeaError("could not mesh a face")
    P = np.array([(q.X(), q.Y(), q.Z()) for q in (tri.Node(i) for i in range(1, tri.NbNodes() + 1))])
    if not loc.IsIdentity():
        from .meshbody import _apply

        P = _apply(loc.Transformation(), P)
    T = np.array([tri.Triangle(i).Get() for i in range(1, tri.NbTriangles() + 1)]) - 1
    if face.Orientation() == TopAbs_REVERSED:
        T = T[:, ::-1]
    a, b, c = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
    cr = np.cross(b - a, c - a) / 2
    area = float(np.linalg.norm(cr, axis=1).sum())
    nrm = cr.sum(axis=0)
    nrm = nrm / (np.linalg.norm(nrm) or 1.0)
    # sample every triangle on a lattice finer than half a cell, so every grid node within reach of
    # the face finds a sample near it
    pts = [P]
    edge = np.max(np.stack([np.linalg.norm(b - a, axis=1), np.linalg.norm(c - b, axis=1),
                            np.linalg.norm(a - c, axis=1)]), axis=0)
    for k in np.unique(np.maximum(np.ceil(edge / (h / 2)).astype(int), 1)):
        sel = np.ceil(edge / (h / 2)).astype(int).clip(min=1) == k
        ij = np.array([(i, j) for i in range(k + 1) for j in range(k + 1 - i)], float) / k
        A, Bv, C = a[sel], b[sel], c[sel]
        pts.append((A[:, None, :] + ij[None, :, 0:1] * (Bv - A)[:, None, :]
                    + ij[None, :, 1:2] * (C - A)[:, None, :]).reshape(-1, 3))
    return np.concatenate(pts), area, nrm
