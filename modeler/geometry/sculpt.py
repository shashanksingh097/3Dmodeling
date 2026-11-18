"""Sculpting mesh bodies: brushes that push, pull, smooth and flatten the
points of a triangle mesh along a stroke (M7).

Everything is numpy on the mesh's arrays (points N x 3, triangles M x 3), so
a stroke on a million-triangle mesh only touches the points near it.

A stroke is a list of points on (or near) the surface. It is resampled into
*dabs* a quarter of the radius apart; each dab moves the points within
``radius`` of its centre, weighted by a smooth falloff (1 at the centre, 0 at
the rim) and by the mask (a value 0..1 per point; 1 = frozen).

Brushes (strength 0..1 is how far one dab moves, as a part of the radius;
a negative strength works the other way, e.g. DRAW digs in):

* DRAW: out along the average normal of the area under the brush.
* CLAY: like DRAW, but only raises points below a plane just above the
  surface, so it builds up flat layers instead of a round bump.
* INFLATE: each point out along its own normal (puffs up).
* SMOOTH: each point towards the middle of its neighbours.
* FLATTEN: points towards the plane of the area under the brush.
* PINCH: points sideways towards the stroke (sharpens a ridge or crease).
* CREASE: PINCH plus a little DRAW inwards: a sharp groove.
* GRAB: the points under the stroke's first point move with the stroke,
  from its first point to its last.

Symmetry mirrors every dab in the planes x = 0, y = 0 and/or z = 0.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

BRUSHES = ("DRAW", "CLAY", "INFLATE", "SMOOTH", "FLATTEN", "PINCH", "CREASE", "GRAB")
SPACING = 0.25  # dabs this far apart, as a part of the radius


JOIN = 0.4  # with a detail size, edges shorter than this times it are joined after the stroke


class SculptError(ValueError):
    pass


@dataclass
class Topology:
    """What the brushes need of the triangles; built once per mesh."""

    tris: np.ndarray
    indptr: np.ndarray  # neighbours of point i: indices[indptr[i]:indptr[i+1]]
    indices: np.ndarray
    degree: np.ndarray
    _tptr: np.ndarray | None = None  # triangles at point i: _tidx[_tptr[i]:_tptr[i+1]] (made when first asked)
    _tidx: np.ndarray | None = None

    def triangles_of(self, points: np.ndarray) -> np.ndarray:
        """The indices of the triangles that use any of these points."""
        if self._tptr is None:
            flat = self.tris.reshape(-1)
            order = np.argsort(flat, kind="stable")
            self._tidx = order // 3
            self._tptr = np.zeros(len(self.degree) + 1, dtype=np.int64)
            np.cumsum(np.bincount(flat, minlength=len(self.degree)), out=self._tptr[1:])
        p = np.asarray(points, dtype=np.int64)
        starts = self._tptr[p]
        counts = self._tptr[p + 1] - starts
        total = int(counts.sum())
        if total == 0:
            return np.zeros(0, dtype=np.int64)
        offs = np.repeat(starts - (np.cumsum(counts) - counts), counts) + np.arange(total)
        hit = np.zeros(len(self.tris), dtype=bool)
        hit[self._tidx[offs]] = True
        return np.flatnonzero(hit)

    @staticmethod
    def of(tris: np.ndarray, n: int) -> "Topology":
        t = np.asarray(tris, dtype=np.int64)
        a = np.concatenate([t[:, 0], t[:, 1], t[:, 2], t[:, 1], t[:, 2], t[:, 0]])
        b = np.concatenate([t[:, 1], t[:, 2], t[:, 0], t[:, 0], t[:, 1], t[:, 2]])
        key = a * n + b
        key.sort()
        keep = np.empty(len(key), dtype=bool)
        if len(key):
            keep[0] = True
            np.not_equal(key[1:], key[:-1], out=keep[1:])  # sort + diff: np.unique is slow on big arrays
        key = key[keep]
        src, dst = key // n, key % n
        degree = np.bincount(src, minlength=n)
        indptr = np.zeros(n + 1, dtype=np.int64)
        np.cumsum(degree, out=indptr[1:])
        return Topology(t, indptr, dst, degree)


def vertex_normals(pts: np.ndarray, tris: np.ndarray) -> np.ndarray:
    """Area-weighted normals at the points (unit length; zero where undefined)."""
    v0, v1, v2 = pts[tris[:, 0]], pts[tris[:, 1]], pts[tris[:, 2]]
    fn = np.cross(v1 - v0, v2 - v0)
    n = np.zeros_like(pts)
    for k in range(3):
        np.add.at(n, tris[:, k], fn)
    length = np.linalg.norm(n, axis=1)
    ok = length > 0
    n[ok] /= length[ok, None]
    return n


def falloff(d: np.ndarray, r: float) -> np.ndarray:
    """1 at the centre, 0 at the rim, smooth at both ends."""
    x = np.clip(1.0 - (d / r) ** 2, 0.0, 1.0)
    return x * x


def resample(stroke: np.ndarray, step: float) -> np.ndarray:
    """Points along the stroke at most ``step`` apart (its first and last point kept)."""
    s = np.asarray(stroke, dtype=float).reshape(-1, 3)
    if len(s) < 2:
        return s
    out = [s[:1]]
    for a, b in zip(s[:-1], s[1:]):
        n = int(np.ceil(np.linalg.norm(b - a) / step))
        if n > 0:
            k = np.arange(1, n + 1)[:, None] / n
            out.append(a + (b - a) * k)
    return np.vstack(out)


def _mirrors(sym: str) -> list[np.ndarray]:
    """The sign patterns of the dab copies (the dab itself first)."""
    signs = [np.ones(3)]
    for axis in "XYZ":
        if axis in sym.upper():
            i = "XYZ".index(axis)
            more = []
            for s in signs:
                m = s.copy()
                m[i] = -1
                more.append(m)
            signs += more
    return signs


@dataclass
class Report:
    dabs: int
    moved: int  # points that moved at least once
    largest: float  # the largest move of one point
    seconds: float
    points: np.ndarray | None = None  # the indices of the points that moved


def stroke(pts: np.ndarray, tris: np.ndarray, brush: str, radius: float, strength: float,
           points, sym: str = "", mask: np.ndarray | None = None,
           topo: Topology | None = None, candidates: np.ndarray | None = None) -> tuple[np.ndarray, Report]:
    """The points after one brush stroke (the input is not changed).
    ``candidates``: indices of every point the stroke (and its mirror copies) could reach, when the
    caller knows them (a drag on a big mesh, see PointGrid); then only those are looked at."""
    t0 = time.perf_counter()
    brush = brush.upper()
    if brush not in BRUSHES:
        raise SculptError(f"unknown brush {brush}: use one of {', '.join(BRUSHES)}")
    if radius <= 0:
        raise SculptError("the radius must be positive")
    if not -1 <= strength <= 1 or strength == 0:
        raise SculptError("the strength is between -1 and 1, and not 0")
    path = np.asarray(points, dtype=float).reshape(-1, 3)
    if len(path) == 0:
        raise SculptError("the stroke has no points")
    if any(c not in "XYZ" for c in sym.upper()):
        raise SculptError(f"symmetry is a mix of X, Y and Z, not {sym!r}")
    start = np.asarray(pts, dtype=float)  # not changed: the brush writes into a copy
    out = start.copy()
    t = np.asarray(tris, dtype=np.int64)
    if mask is not None and len(mask) != len(out):
        mask = None
    free = None if mask is None else np.clip(1.0 - mask, 0.0, 1.0)
    topo = topo or (Topology.of(t, len(out)) if brush == "SMOOTH" else None)
    signs = _mirrors(sym)
    touched = np.zeros(len(out), dtype=bool)
    dabs = 0

    if brush == "GRAB":
        a, b = path[0], path[-1]
        for s in signs:
            centre, move = a * s, (b - a) * s
            near = _near(start, centre, radius)
            if not len(near):
                continue
            w = falloff(np.linalg.norm(start[near] - centre, axis=1), radius) * abs(strength) * (
                1 if strength > 0 else -1)
            if free is not None:
                w = w * free[near]
            out[near] += w[:, None] * move
            touched[near] = True
            dabs += 1
    else:
        centres = resample(path, max(radius * SPACING, 1e-9))
        lo = centres.min(axis=0) - radius
        hi = centres.max(axis=0) + radius
        for s in signs:
            # only the points near this copy of the stroke are looked at again
            slo, shi = np.minimum(lo * s, hi * s), np.maximum(lo * s, hi * s)
            if candidates is None:
                box = np.flatnonzero(np.all((out >= slo) & (out <= shi), axis=1))
            else:
                q = out[candidates]
                box = candidates[np.all((q >= slo) & (q <= shi), axis=1)]
            if not len(box):
                continue
            if topo is not None and len(box) * 8 < len(out):
                tb = t[topo.triangles_of(box)]  # the triangles the brush can reach
            else:
                inbox = np.zeros(len(out), dtype=bool)
                inbox[box] = True
                tb = t[inbox[t].any(axis=1)]
            for c in centres * s:
                d = np.linalg.norm(out[box] - c, axis=1)
                inside = d < radius
                if not inside.any():
                    continue
                near = box[inside]
                w = falloff(d[inside], radius)
                if free is not None:
                    w = w * free[near]
                _dab(out, tb, topo, brush, near, w, c, radius, strength)
                touched[near] = True
                dabs += 1
    idx = np.flatnonzero(touched)
    moved = np.linalg.norm(out[idx] - start[idx], axis=1)
    idx = idx[moved > 0]
    return out, Report(dabs, len(idx), float(moved.max() if len(moved) else 0.0),
                       time.perf_counter() - t0, idx)


class PointGrid:
    """Points sorted into cubes, so the points inside a box are found without looking at all of
    them (a drag on a big mesh asks this at every mouse move)."""

    def __init__(self, pts: np.ndarray, cell: float):
        self.cell = max(float(cell), 1e-9)
        self.lo = pts.min(axis=0)
        key = np.floor((pts - self.lo) / self.cell).astype(np.int64)
        self.dims = key.max(axis=0) + 1
        flat = (key[:, 0] * self.dims[1] + key[:, 1]) * self.dims[2] + key[:, 2]
        self.order = np.argsort(flat, kind="stable")
        self.keys = flat[self.order]

    def inside(self, lo, hi) -> np.ndarray:
        """Indices of the points in cubes that touch the box lo..hi (a few more than inside it)."""
        a = np.clip(np.floor((np.asarray(lo) - self.lo) / self.cell).astype(np.int64), 0, self.dims - 1)
        b = np.clip(np.floor((np.asarray(hi) - self.lo) / self.cell).astype(np.int64), 0, self.dims - 1)
        if np.any(np.asarray(hi) < self.lo) or np.any(b < a):
            return np.zeros(0, dtype=np.int64)
        out = []
        for i in range(a[0], b[0] + 1):
            for j in range(a[1], b[1] + 1):
                k0 = (i * self.dims[1] + j) * self.dims[2]
                s0 = np.searchsorted(self.keys, k0 + a[2], "left")
                s1 = np.searchsorted(self.keys, k0 + b[2], "right")
                if s1 > s0:
                    out.append(self.order[s0:s1])
        return np.concatenate(out) if out else np.zeros(0, dtype=np.int64)


def _near(pts: np.ndarray, c: np.ndarray, r: float) -> np.ndarray:
    return np.flatnonzero(np.einsum("ij,ij->i", pts - c, pts - c) < r * r)


def _area_normal(out: np.ndarray, t: np.ndarray, near: np.ndarray, w: np.ndarray) -> np.ndarray:
    """The weighted average normal of the points under the brush."""
    n = _local_normals(out, t, near)
    avg = (n * w[:, None]).sum(axis=0)
    length = np.linalg.norm(avg)
    return avg / length if length > 0 else np.array([0.0, 0.0, 1.0])


def _local_normals(out: np.ndarray, t: np.ndarray, near: np.ndarray) -> np.ndarray:
    """Normals at only these points (the triangles around them)."""
    mark = np.zeros(len(out), dtype=bool)
    mark[near] = True
    faces = t[mark[t].any(axis=1)]
    v0, v1, v2 = out[faces[:, 0]], out[faces[:, 1]], out[faces[:, 2]]
    fn = np.cross(v1 - v0, v2 - v0)
    pos = np.full(len(out), -1, dtype=np.int64)
    pos[near] = np.arange(len(near))
    n = np.zeros((len(near), 3))
    for k in range(3):
        idx = pos[faces[:, k]]
        ok = idx >= 0
        np.add.at(n, idx[ok], fn[ok])
    length = np.linalg.norm(n, axis=1)
    good = length > 0
    n[good] /= length[good, None]
    return n


def _dab(out, t, topo, brush, near, w, c, radius, strength) -> None:
    step = strength * radius * 0.15  # how far the centre of one dab moves
    if brush == "DRAW":
        out[near] += (w * step)[:, None] * _area_normal(out, t, near, w)
    elif brush == "INFLATE":
        out[near] += (w * step)[:, None] * _local_normals(out, t, near)
    elif brush in ("FLATTEN", "CLAY"):
        nrm = _area_normal(out, t, near, w)
        centre = (out[near] * w[:, None]).sum(axis=0) / max(w.sum(), 1e-12)
        if brush == "CLAY":
            centre = centre + nrm * step * 2
        h = (out[near] - centre) @ nrm  # height above the plane
        if brush == "CLAY":
            h = np.minimum(h, 0.0) if strength > 0 else np.maximum(h, 0.0)  # only raise (or lower)
            out[near] -= (np.abs(w * strength) * h)[:, None] * nrm
        else:
            out[near] -= (np.clip(w * abs(strength), 0, 1) * h)[:, None] * nrm
    elif brush == "SMOOTH":
        mid = _neighbour_mean(out, topo, near)
        out[near] += (np.clip(w * abs(strength), 0, 1))[:, None] * (mid - out[near])
    elif brush in ("PINCH", "CREASE"):
        nrm = _area_normal(out, t, near, w)
        towards = c - out[near]
        towards -= np.outer(towards @ nrm, nrm)  # sideways only
        out[near] += (np.clip(w * strength * 0.5, -1, 1))[:, None] * towards
        if brush == "CREASE":
            out[near] -= (w * step * 0.5)[:, None] * nrm


def _neighbour_mean(out: np.ndarray, topo: Topology, near: np.ndarray) -> np.ndarray:
    """The middle of each point's neighbours (points with none stay put)."""
    deg = topo.degree[near]
    total = int(deg.sum())
    if total == 0:
        return out[near].copy()
    starts = topo.indptr[near]
    ends = np.cumsum(deg)
    offs = np.repeat(starts - (ends - deg), deg) + np.arange(total)
    nb = topo.indices[offs]
    seg = np.repeat(np.arange(len(near)), deg)
    mid = np.empty((len(near), 3))
    for k in range(3):
        mid[:, k] = np.bincount(seg, weights=out[nb, k], minlength=len(near))
    mid /= np.maximum(deg, 1)[:, None]
    lone = deg == 0
    mid[lone] = out[near][lone]
    return mid


def sphere_mask(pts: np.ndarray, centre, r: float, value: float = 1.0,
                old: np.ndarray | None = None, mode: str = "PAINT") -> np.ndarray:
    """A mask (0..1 per point; 1 = frozen) with a soft sphere painted on or erased."""
    m = np.zeros(len(pts)) if old is None or len(old) != len(pts) else np.array(old, dtype=float)
    d = np.linalg.norm(pts - np.asarray(centre, dtype=float), axis=1)
    f = falloff(d, r) * value
    if mode == "PAINT":
        m = np.maximum(m, f)
    else:  # ERASE
        m = np.clip(m - f, 0.0, 1.0)
    return m


# ---- finer triangles where the brush goes (dynamic detail) ---------------------------------------
def _region(pts: np.ndarray, centres: np.ndarray, reach: float) -> np.ndarray:
    """Which points are within ``reach`` of any centre."""
    inside = np.zeros(len(pts), dtype=bool)
    if not len(centres):
        return inside
    lo, hi = centres.min(axis=0) - reach, centres.max(axis=0) + reach
    box = np.flatnonzero(np.all((pts >= lo) & (pts <= hi), axis=1))
    if not len(box):
        return inside
    best = np.full(len(box), np.inf)
    for c in centres:  # a stroke has tens to hundreds of centres
        np.minimum(best, ((pts[box] - c) ** 2).sum(axis=1), out=best)
    inside[box[best <= reach * reach]] = True
    return inside


def refine_near(pts: np.ndarray, tris: np.ndarray, length: float, centres, reach: float,
                mask: np.ndarray | None = None, passes: int = 8, relax: int = 5):
    """Split the edges longer than ``length`` that lie within ``reach`` of the centres (both ends; with
    ``centres`` None, everywhere),
    until none is left there (at most ``passes`` rounds). Existing points keep their indices; new
    points (edge middles) are added at the end and take the mean mask of their edge's ends.
    Returns (points, triangles, mask or None, number of points added)."""
    if length <= 0:
        raise SculptError("the detail size must be positive")
    p = np.asarray(pts, dtype=float)
    t = np.asarray(tris, dtype=np.int64)
    m = None if mask is None else np.asarray(mask, dtype=float)
    c = None if centres is None else np.asarray(centres, dtype=float).reshape(-1, 3)
    n0 = len(p)
    for _ in range(passes):
        inside = np.ones(len(p), dtype=bool) if c is None else _region(p, c, reach)
        if not inside.any():
            break
        # longest-edge splitting (Rivara): a triangle near the stroke whose longest edge is too long has
        # that edge split; any triangle with a split edge has its own longest edge split too, so every
        # triangle is cut across its longest edge and none turns into a sliver
        # work in a window round the stroke; it is big enough when every split edge has an end whose
        # triangles are all in the window (then both triangles on that edge are in it)
        n = len(p)
        grow = reach * 1.5
        while True:
            win = np.ones(len(p), dtype=bool) if c is None else _region(p, c, grow)
            cand = np.flatnonzero(win[t].any(axis=1))
            tc = t[cand]
            a = tc.reshape(-1)  # corner k of each triangle starts edge k
            b = tc[:, [1, 2, 0]].reshape(-1)
            key = np.minimum(a, b) * n + np.maximum(a, b)
            lengths = np.linalg.norm(p[a] - p[b], axis=1).reshape(-1, 3)
            lkey = key.reshape(-1, 3)[np.arange(len(tc)), lengths.argmax(axis=1)]
            seed = (lengths.max(axis=1) > length) & inside[tc].all(axis=1)
            marked_keys = np.unique(lkey[seed])
            for _ in range(64):
                has = np.isin(key, marked_keys).reshape(-1, 3).any(axis=1)
                need = has & ~np.isin(lkey, marked_keys)
                if not need.any():
                    break
                marked_keys = np.union1d(marked_keys, lkey[need])
            if c is None or (win[marked_keys // n] | win[marked_keys % n]).all():
                break
            grow *= 2
        if not len(marked_keys):
            break
        new_idx = n + np.arange(len(marked_keys))
        mlo, mhi = marked_keys // n, marked_keys % n
        p = np.vstack([p, (p[mlo] + p[mhi]) / 2])
        if m is not None:
            m = np.concatenate([m, (m[mlo] + m[mhi]) / 2])
        pos = np.searchsorted(marked_keys, key)
        pos = np.minimum(pos, len(marked_keys) - 1)
        hit = marked_keys[pos] == key
        mid = np.where(hit, new_idx[pos], -1).reshape(-1, 3)  # middle of edge k, or -1
        flag = mid >= 0
        count = flag.sum(axis=1)
        keep = np.ones(len(t), dtype=bool)
        keep[cand[count > 0]] = False
        out = [t[keep]]
        # one split edge: turn the triangle so it is edge 0, then cut it in two
        for k in range(3):
            sel = (count == 1) & flag[:, k]
            if sel.any():
                r = np.roll(tc[sel], -k, axis=1)
                mm = mid[sel, k]
                out += [np.stack([r[:, 0], mm, r[:, 2]], 1), np.stack([mm, r[:, 1], r[:, 2]], 1)]
        # two split edges: turn it so edges 0 and 1 are split, then three triangles
        for k in range(3):
            sel = (count == 2) & ~flag[:, (k + 2) % 3]
            if sel.any():
                r = np.roll(tc[sel], -k, axis=1)
                m0, m1 = mid[sel, k], mid[sel, (k + 1) % 3]
                out.append(np.stack([m0, r[:, 1], m1], 1))
                # the quad a, m0, m1, c: cut from the middle of the longer split edge (as cutting the
                # triangle across its longest edge first, then the half that still has a split edge)
                short = np.linalg.norm(p[r[:, 1]] - p[r[:, 2]], axis=1) >= np.linalg.norm(p[r[:, 0]] - p[r[:, 1]], axis=1)
                out += [np.stack([r[short, 0], m0[short], m1[short]], 1),
                        np.stack([r[short, 0], m1[short], r[short, 2]], 1),
                        np.stack([r[~short, 0], m0[~short], r[~short, 2]], 1),
                        np.stack([m0[~short], m1[~short], r[~short, 2]], 1)]
        sel = count == 3
        if sel.any():
            r, (m0, m1, m2) = tc[sel], mid[sel].T
            out += [np.stack([r[:, 0], m0, m2], 1), np.stack([m0, r[:, 1], m1], 1),
                    np.stack([m2, m1, r[:, 2]], 1), np.stack([m0, m1, m2], 1)]
        t = np.vstack(out)
    if len(p) > n0:  # even out the points there along the surface, so the brush gets no slivers
        region = np.ones(len(p), dtype=bool) if c is None else _region(p, c, reach)
        region[n0:] = True
        new = np.flatnonzero(region)
        sub = t[region[t].any(axis=1)]  # every triangle at those points
        topo = Topology.of(sub, len(p))
        for _ in range(relax):
            d = _neighbour_mean(p, topo, new) - p[new]
            nrm = _local_normals(p, sub, new)
            d -= (d * nrm).sum(axis=1)[:, None] * nrm
            p[new] += 0.5 * d
    return p, t, m, len(p) - n0


def collapse_near(pts: np.ndarray, tris: np.ndarray, length: float, centres, reach: float,
                  mask: np.ndarray | None = None, passes: int = 6):
    """Join the points of edges shorter than ``length`` within ``reach`` of the centres (the other
    half of dynamic topology: where a brush squeezed triangles together, as PINCH and CREASE do,
    they are merged again, so the mesh keeps an even size there and no slivers).

    Each pass takes edges shortest first, at most one per neighbourhood, and joins the two ends at
    the edge's middle, unless that would make the surface non-manifold (the ends must share exactly
    two neighbours), turn a triangle over, or move a frozen (masked) point. Points no triangle uses
    are then dropped and the rest renumbered in order. Returns (points, triangles, mask or None,
    number of points removed)."""
    if length <= 0:
        raise SculptError("the detail size must be positive")
    p = np.asarray(pts, dtype=float).copy()
    t = np.asarray(tris, dtype=np.int64).copy()
    m = None if mask is None else np.asarray(mask, dtype=float).copy()
    c = np.asarray(centres, dtype=float).reshape(-1, 3)
    n0 = len(p)
    joined = 0
    for _ in range(passes):
        inside = _region(p, c, reach)
        if m is not None:
            inside &= m < 0.5  # frozen points stay
        cand = np.flatnonzero(inside[t].all(axis=1))
        if not len(cand):
            break
        tc = t[cand]
        a = tc.reshape(-1)
        b = tc[:, [1, 2, 0]].reshape(-1)
        lens = np.linalg.norm(p[a] - p[b], axis=1)
        short = lens < length
        if not short.any():
            break
        lo, hi = np.minimum(a, b)[short], np.maximum(a, b)[short]
        order = np.argsort(lens[short], kind="stable")
        pairs = np.unique(np.stack([lo[order], hi[order]], 1), axis=0, return_index=True)
        edges = pairs[0][np.argsort(pairs[1])]  # shortest first, each once
        topo = Topology.of(t, len(p))
        nb = lambda i: topo.indices[topo.indptr[i]:topo.indptr[i + 1]]  # noqa: E731
        locked = np.zeros(len(p), dtype=bool)
        remap = np.arange(len(p))
        done = 0
        for ea, eb in edges:
            if locked[ea] or locked[eb]:
                continue
            na, nbb = nb(ea), nb(eb)
            if len(np.intersect1d(na, nbb, assume_unique=True)) != 2:
                continue  # joining would pinch the surface
            mid = (p[ea] + p[eb]) / 2
            # the triangles that stay (not on the edge) at either end must not turn over
            ts = t[topo.triangles_of(np.array([ea, eb]))]
            keep = ~(((ts == ea) | (ts == eb)).sum(axis=1) == 2)
            ts = ts[keep]
            before = np.cross(p[ts[:, 1]] - p[ts[:, 0]], p[ts[:, 2]] - p[ts[:, 0]])
            moved = np.where((ts == ea) | (ts == eb), -1, ts)
            corners = np.where(moved[..., None] < 0, mid, p[np.maximum(moved, 0)])
            after = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
            if (np.einsum("ij,ij->i", before, after) <= 0.05 * np.linalg.norm(before, axis=1)
                    * np.linalg.norm(after, axis=1)).any():
                continue
            p[ea] = mid
            if m is not None:
                m[ea] = (m[ea] + m[eb]) / 2
            remap[eb] = ea
            locked[na] = locked[nbb] = True
            locked[ea] = locked[eb] = True
            done += 1
        if not done:
            break
        joined += done
        t = remap[t]
        t = t[(t[:, 0] != t[:, 1]) & (t[:, 1] != t[:, 2]) & (t[:, 2] != t[:, 0])]
    if joined:
        used = np.zeros(len(p), dtype=bool)
        used[t.reshape(-1)] = True
        new_index = np.cumsum(used) - 1
        p = p[used]
        t = new_index[t]
        if m is not None:
            m = m[used]
    return p, t, m, n0 - len(p)
