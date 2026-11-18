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
           topo: Topology | None = None) -> tuple[np.ndarray, Report]:
    """The points after one brush stroke (the input is not changed)."""
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
            box = np.flatnonzero(np.all((out >= slo) & (out <= shi), axis=1))
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
