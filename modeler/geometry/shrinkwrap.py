"""Shrinkwrap (PLAN item 78): one clean closed skin around messy meshes or a whole assembly.

The bodies are sampled as points on their surfaces. On a grid, every cell nearer than ``gap`` to a
surface is *blocked*; the cells reached from the grid's border without crossing a blocked cell are
*outside*, and everything else is the inside of the skin, so holes and slits narrower than about
twice the gap, inner voids and overlaps are closed over and loose bits within the gap are joined.
The skin is then pulled back in by the gap (a distance field from the outside), so it lies on the
outer surface again, and meshed (implicit.march). It is a mesh body: for printing, for a quick
outside shape, for a cover or a simplified look.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import implicit

MAX_CELLS = 6_000_000


class WrapError(Exception):
    pass


@dataclass
class Skin:
    points: np.ndarray
    tris: np.ndarray
    cell: float


def surface_points(shapes, spacing: float) -> np.ndarray:
    """Points on the surfaces of ``shapes`` no farther apart than ``spacing``."""
    from . import analysis as an
    from . import meshbody as mb
    from . import pointcloud as pc

    out = []
    for s in shapes:
        if pc.is_points(s):
            out.append(pc.arrays(s))
            continue
        if mb.is_mesh(s):
            p, t = mb.arrays(s)
        else:
            m = an.mesh(s)
            p, t = m.nodes, m.tris
        p, t = np.asarray(p, float), np.asarray(t)
        out.append(p)
        if not len(t):
            continue
        a, b, c = p[t[:, 0]], p[t[:, 1]], p[t[:, 2]]
        longest = np.max(np.stack([np.linalg.norm(b - a, axis=1), np.linalg.norm(c - b, axis=1),
                                   np.linalg.norm(a - c, axis=1)]), axis=0)
        k = np.ceil(longest / spacing).astype(int)  # k x k points across each triangle
        for kk in np.unique(k):
            if kk <= 1:
                out.append((a[k == kk] + b[k == kk] + c[k == kk]) / 3)
                continue
            i, j = np.meshgrid(np.arange(kk + 1), np.arange(kk + 1), indexing="ij")
            keep = i + j <= kk
            u, v = (i[keep] / kk)[None, :, None], (j[keep] / kk)[None, :, None]
            sel = k == kk
            aa, bb, cc = a[sel][:, None, :], b[sel][:, None, :], c[sel][:, None, :]
            out.append((aa + u * (bb - aa) + v * (cc - aa)).reshape(-1, 3))
    if not out:
        raise WrapError("nothing to wrap")
    return np.vstack(out)


def wrap(shapes, gap: float, cell: float = 0.0) -> Skin:
    from scipy import ndimage
    from scipy.spatial import cKDTree

    if gap <= 0:
        raise WrapError("the gap must be positive")
    probe = surface_points(shapes, max(gap, 1e-6) * 4)
    lo, hi = probe.min(axis=0), probe.max(axis=0)
    size = hi - lo
    if cell <= 0:
        cell = min(gap / 2, float(np.linalg.norm(size)) / 60)
        cell = max(cell, float((np.prod(size + 4 * gap) / MAX_CELLS) ** (1 / 3)))
    pad = gap + 3 * cell
    box = (*(lo - pad), *(hi + pad))
    xs, ys, zs = (lo[i] - pad - cell + cell * np.arange(int(np.ceil((hi[i] - lo[i] + 2 * pad) / cell)) + 3)
                  for i in range(3))
    n = len(xs) * len(ys) * len(zs)
    if n > MAX_CELLS:
        small = float((np.prod(np.array(box[3:]) - np.array(box[:3])) / MAX_CELLS) ** (1 / 3)) * 1.05
        raise WrapError(f"a cell of {cell:.3g} needs {n:,} grid points; use a cell of at least {small:.3g}")
    pts = surface_points(shapes, cell / 2)
    tree = cKDTree(pts)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    grid = np.c_[X.ravel(), Y.ravel(), Z.ravel()]
    d, _ = tree.query(grid, distance_upper_bound=gap + 2 * cell)
    d = d.reshape(X.shape)
    blocked = d <= gap
    free = ~blocked
    labels, _count = ndimage.label(free)
    border = np.unique(np.r_[labels[0].ravel(), labels[-1].ravel(), labels[:, 0].ravel(), labels[:, -1].ravel(),
                             labels[:, :, 0].ravel(), labels[:, :, -1].ravel()])
    border = border[border > 0]
    outside = np.isin(labels, border)
    if outside.all():
        raise WrapError("nothing to wrap: no surfaces in the box")
    # The skin is where a point is exactly ``gap`` inside the outside region's edge. That edge is
    # sampled where it really is: for each outside cell next to the inside, the point at the gap
    # from its nearest surface point, towards the cell. Distances to those points (not to whole
    # cells) give a smooth skin that sits on flat faces and comes back to a sharp edge at corners.
    edge = outside & ndimage.binary_dilation(~outside)
    cells = np.c_[X[edge], Y[edge], Z[edge]]
    _dd, idx = tree.query(cells)
    near = pts[idx]
    away = cells - near
    away /= np.maximum(np.linalg.norm(away, axis=1), 1e-12)[:, None]
    rim = cKDTree(near + gap * away)
    din = ndimage.distance_transform_edt(~outside) * cell  # rough, for cells deep inside
    band = ~outside & (din <= gap + 3 * cell)
    exact, _ = rim.query(np.c_[X[band], Y[band], Z[band]])
    dout = ndimage.distance_transform_edt(outside) * cell
    vals = np.where(outside, dout + gap, gap - din - 3 * cell)
    vals[band] = gap - exact
    vals[0, :, :] = vals[-1, :, :] = vals[:, 0, :] = vals[:, -1, :] = vals[:, :, 0] = vals[:, :, -1] = cell
    vals[vals == 0] = 1e-12 * cell
    p, t = implicit.march(vals, (xs, ys, zs))
    if not len(t):
        raise WrapError("the skin came out empty (try a smaller cell)")
    from . import meshbody as mb

    p, t = mb.drop_specks(p, t)  # grid-sized crumbs along sharp edges
    return Skin(np.asarray(p, float), np.asarray(t), cell)
