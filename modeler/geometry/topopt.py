"""A quick topology optimisation (TOPOPT, PLAN item 42) on the STRESS grid (geometry/fea.py).

Each cell of the voxel grid gets a density between a small floor and 1; its stiffness is the
density cubed times the solid cell's (SIMP). Each round solves the part under its load, finds
how much each cell adds to the stiffness (the strain energy), smooths that over its neighbours
(so the result has no checkerboards and no struts thinner than about two cells) and moves the
densities towards the cells that matter, keeping the share of material asked for (optimality
criteria). Cells touching the fixed and loaded faces stay solid.

The result is a suggestion of where material carries the load, to model a real part after: a
mesh of where the density is over a half. It is a first look, not a finished design: the grid
is coarse, the load case is one, and nothing checks stress, buckling or how it would be made.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np

from . import fea


@dataclass
class Result:
    grid: fea.Grid
    density: np.ndarray  # (m,) per cell of grid.cells
    rounds: int
    compliance: list = field(default_factory=list)  # per round (N·mm): lower is stiffer
    share: float = 0.0  # the material kept, of the starting part
    level: float = 0.5  # the density the outline is drawn at
    seconds: float = 0.0
    converged: bool = False


def _neighbours(grid: fea.Grid, radius: float):
    """The smoothing weights between cells (a sparse matrix, rows summing to 1)."""
    import scipy.sparse as sp
    from scipy.spatial import cKDTree

    xyz = grid.cell_xyz()
    tree = cKDTree(xyz)
    pairs = tree.query_pairs(radius, output_type="ndarray")
    i = np.concatenate([pairs[:, 0], pairs[:, 1], np.arange(len(xyz))])
    j = np.concatenate([pairs[:, 1], pairs[:, 0], np.arange(len(xyz))])
    d = np.linalg.norm(xyz[i] - xyz[j], axis=1)
    w = np.maximum(radius - d, 0.0)
    W = sp.coo_matrix((w, (i, j)), shape=(len(xyz), len(xyz))).tocsr()
    return sp.diags(1 / np.asarray(W.sum(axis=1)).ravel()) @ W


def optimise(grid: fea.Grid, elastic: fea.Elastic, fixed: np.ndarray, loads: list, keep: float,
             passive: np.ndarray | None = None, rounds: int = 30, penal: float = 3.0, radius: float = 1.5,
             progress=None) -> Result:
    """``keep``: the share of the cells' volume to keep (0 to 1); ``passive``: cells kept solid."""
    import scipy.sparse as sp
    import scipy.sparse.linalg as sla

    if not 0.02 <= keep < 1:
        raise fea.FeaError("the share to keep is between 0.02 and 1 (like 0.3 for 30%)")
    t0 = time.time()
    n, m = len(grid.nodes), len(grid.cells)
    ke = fea.element(elastic.E, elastic.nu, grid.h)
    dofs = (3 * grid.conn[:, :, None] + np.arange(3)[None, None, :]).reshape(m, 24)
    rows = np.repeat(dofs, 24, axis=1).ravel()
    cols = np.tile(dofs, (1, 24)).ravel()
    F = np.zeros(3 * n)
    for nodes, force in loads:
        if len(nodes):
            f = np.asarray(force, float) / len(nodes)
            for k in range(3):
                np.add.at(F, 3 * nodes + k, f[k])
    held = np.zeros(3 * n, bool)
    held[(3 * fixed[:, None] + np.arange(3)[None, :]).ravel()] = True
    free = np.nonzero(~held)[0]
    H = _neighbours(grid, radius * float(grid.h.max()))
    passive = np.zeros(m, bool) if passive is None else passive
    floor = 1e-3
    x = np.full(m, keep)
    x[passive] = 1.0
    target = keep * m
    if passive.sum() >= target:
        raise fea.FeaError(f"the faces held and loaded already take {passive.sum() / m:.0%} of the part, more "
                           f"than the {keep:.0%} to keep: keep more, or use a smaller cell size")
    u = np.zeros(3 * n)
    out = Result(grid, x, 0)
    move = 0.2
    for it in range(rounds):
        stiff = floor + (1 - floor) * x ** penal
        K = sp.coo_matrix((np.outer(stiff, ke.ravel()).ravel(), (rows, cols)), shape=(3 * n, 3 * n)).tocsr()
        Kff = K[free][:, free]
        diag = Kff.diagonal()
        M = sp.diags(1 / np.where(diag > 0, diag, 1))
        sol, info = sla.cg(Kff, F[free], x0=u[free], M=M, rtol=1e-5, maxiter=5_000)
        if info != 0 or not np.all(np.isfinite(sol)):
            if len(free) > 300_000:
                raise fea.FeaError("the solver did not converge (is the part held so it cannot move freely?)")
            sol = sla.spsolve(Kff.tocsc(), F[free])
        u[free] = sol
        ue = u[dofs]
        energy = np.einsum("ij,jk,ik->i", ue, ke, ue)  # ue · ke · ue per cell
        c = float((stiff * energy).sum())
        out.compliance.append(c)
        dc = -penal * (1 - floor) * x ** (penal - 1) * energy
        dc = (H @ (x * dc)) / np.maximum(x, 1e-3)  # the sensitivity filter of the classic 99-line method
        # optimality criteria: bisect the multiplier that keeps the volume
        lo, hi = 1e-12, 1e12
        while hi / lo > 1 + 1e-6:
            mid = math.sqrt(lo * hi)
            new = np.clip(x * np.sqrt(np.maximum(-dc, 0) / mid), np.maximum(floor, x - move), np.minimum(1, x + move))
            new[passive] = 1.0
            if new.sum() > target:
                lo = mid
            else:
                hi = mid
        change = float(np.abs(new - x).max())
        x = new
        out.rounds = it + 1
        if progress:
            progress(it + 1, rounds, c)
        cs = out.compliance
        if it >= 6 and (change < 0.01 or max(cs[-4:]) - min(cs[-4:]) < 0.005 * cs[-1]):
            out.converged = True
            break
    out.density = x.copy()
    out.density[passive] = 1.0
    # the outline's level: where the densest cells add up to the share asked for (some cells end
    # part way, so a fixed half would keep too little or too much)
    order = np.sort(out.density)[::-1]
    out.level = float(np.clip(order[min(int(round(keep * m)), m - 1)], 0.15, 0.85))
    # bits that float free of the held and loaded cells carry nothing: drop them
    from scipy import ndimage

    solid = np.zeros(grid.shape, bool)
    solid[tuple(grid.cells.T)] = out.density > out.level
    labels, _n = ndimage.label(solid)
    lab = labels[tuple(grid.cells.T)]
    keep_labels = np.unique(lab[passive & (lab > 0)])
    stray = (lab > 0) & ~np.isin(lab, keep_labels)
    out.density[stray] = floor
    out.share = float((out.density > out.level).sum() / m)
    out.seconds = time.time() - t0
    return out


def mesh(res: Result) -> tuple[np.ndarray, np.ndarray]:
    """A closed triangle mesh round the cells denser than the result's level (the cell corners get
    the mean of the densities around them, so the outline runs between cells, not along their
    faces). Cells outside the part take the density of the nearest cell inside, so the outline
    does not shrink half a cell at the part's own surface; trim it to the part afterwards."""
    from scipy import ndimage

    from . import implicit as im

    g = res.grid
    nx, ny, nz = g.shape
    full = np.zeros((nx + 2, ny + 2, nz + 2))
    known = np.zeros(full.shape, bool)
    i, j, k = (g.cells + 1).T
    full[i, j, k] = res.density
    known[i, j, k] = True
    _d, near = ndimage.distance_transform_edt(~known, return_indices=True)
    full = full[tuple(near)]
    # node (corner) values: the mean of the 8 cells round it
    node = sum(full[a:a + nx + 1, b:b + ny + 1, c:c + nz + 1] for a in (0, 1) for b in (0, 1) for c in (0, 1)) / 8
    vals = np.full((nx + 3, ny + 3, nz + 3), 1e3)  # far outside: the outline meets the box at its face
    vals[1:-1, 1:-1, 1:-1] = res.level - node
    vals[vals == 0] = 1e-9
    axes = [g.origin[d] + g.h[d] * (np.arange(s + 3) - 1) for d, s in enumerate((nx, ny, nz))]
    return im.march(vals, axes)
