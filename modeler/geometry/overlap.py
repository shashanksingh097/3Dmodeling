"""Does a shape built from sections run into itself?

A sweep or a loft that is sound has cross-sections that never touch each
other: two slices of the same solid can only share a point if the solid
passes through itself there. That gives one cheap test that catches the
usual ways these shapes go wrong, before the kernel's own (slow) check:

* a profile that is too big for a bend of the path (a pipe of radius 8 round
  a bend of radius 5): slices close together cross on the inside of the bend;
* a sharp corner in the path: the slices just before and after it cross;
* a path that comes back near itself (a tight helix, a loop): slices from
  different turns cross;
* loft sections that cut through each other, or lie in the same place.

Each section is a closed polygon (points sampled along its curve). Two
polygons are compared by the line where their planes meet: each polygon
covers some stretches of that line, and the polygons touch when stretches
of the two overlap. Polygons in the same plane are compared in that plane.

Separately, :func:`self_crossing` finds a section curve that crosses
itself (a figure-of-eight), which no loft can make a solid from.

Every division below has a denominator that cannot be zero, so no NaN or
infinity (and no numpy warning) can come out of these tests.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class Clash:
    i: int  # first section (index in the list given)
    j: int  # second section
    where: tuple[float, float, float]  # a point where they meet


class Section:
    """A closed planar polygon in 3D, with what the tests need precomputed."""

    def __init__(self, pts) -> None:
        p = np.asarray(pts, dtype=float)
        if len(p) > 1 and np.allclose(p[0], p[-1]):
            p = p[:-1]
        self.p = p
        self.c = p.mean(axis=0) if len(p) else np.zeros(3)
        self.r = float(np.max(np.linalg.norm(p - self.c, axis=1))) if len(p) else 0.0
        # the plane that fits the points best (works for a figure-of-eight too,
        # where the signed area, and so Newell's normal, comes out as zero)
        self.ok = len(p) >= 3 and self.r > 1e-12
        if self.ok:
            sv = np.linalg.svd(p - self.c, full_matrices=False)
            self.n = sv[2][-1]
            self.ok = sv[1][1] > 1e-9 * self.r  # not all on one line
        else:
            self.n = np.array([0.0, 0.0, 1.0])


def _intervals(sec: Section, plane_pt, plane_n, origin, d, tol: float) -> list[tuple[float, float]]:
    """Stretches of the line ``origin + s d`` covered by ``sec`` (the line lies
    in the section's plane and in the other plane)."""
    dist = (sec.p - plane_pt) @ plane_n
    dist = np.where(np.abs(dist) < tol * 1e-3, 0.0, dist)
    d2 = np.roll(dist, -1)
    p2 = np.roll(sec.p, -1, axis=0)
    cross = (dist < 0) != (d2 < 0)  # each edge that changes side crosses the plane once
    if not np.any(cross):
        return []
    a, b = dist[cross], d2[cross]
    w = (a / (a - b))[:, None]  # a and b differ in sign, so a - b is never zero
    hits = sec.p[cross] + w * (p2[cross] - sec.p[cross])
    s = np.sort((hits - origin) @ d)
    return [(float(s[k]), float(s[k + 1])) for k in range(0, len(s) - 1, 2)]


def _point_in_poly2(pt, poly) -> bool:
    x, y = pt
    inside = False
    n = len(poly)
    for k in range(n):
        x1, y1 = poly[k]
        x2, y2 = poly[(k + 1) % n]
        # (y1 > y) != (y2 > y) means y1 != y2, so the division is safe
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _segments_cross2(a, b, tol: float) -> tuple[float, float] | None:
    """First crossing between edges of 2D polygon a and 2D polygon b."""
    a2, b2 = np.roll(a, -1, axis=0), np.roll(b, -1, axis=0)
    for k in range(len(a)):
        p, r = a[k], a2[k] - a[k]
        q, s = b, b2 - b
        den = r[0] * s[:, 1] - r[1] * s[:, 0]
        qp = q - p
        live = np.abs(den) > 1e-15
        safe = np.where(live, den, 1.0)
        t = (qp[:, 0] * s[:, 1] - qp[:, 1] * s[:, 0]) / safe
        u = (qp[:, 0] * r[1] - qp[:, 1] * r[0]) / safe
        ok = live & (t > 1e-9) & (t < 1 - 1e-9) & (u > 1e-9) & (u < 1 - 1e-9)
        if np.any(ok):
            idx = int(np.argmax(ok))
            return tuple(p + t[idx] * r)
    return None


def _coplanar_overlap(A: Section, B: Section, tol: float):
    """Two polygons in the same plane: do their areas overlap?"""
    u = A.p[int(np.argmax(np.linalg.norm(A.p - A.c, axis=1)))] - A.c  # A.ok: A.r > 0, so u is not zero
    u = u - (u @ A.n) * A.n
    u = u / max(np.linalg.norm(u), 1e-300)
    v = np.cross(A.n, u)

    def flat(P):
        return np.stack([(P - A.c) @ u, (P - A.c) @ v], axis=1)

    a, b = flat(A.p), flat(B.p)
    if np.linalg.norm(A.c - B.c) <= tol:  # the same place (a section given twice)
        return A.c
    hit = _segments_cross2(a, b, tol)
    if hit is not None:
        return A.c + hit[0] * u + hit[1] * v
    # one inside the other: test a corner and the centre of each (a corner
    # alone can sit exactly on the other's edge when the two are equal)
    for pt, poly, at in ((b[0], a, B.p[0]), (a[0], b, A.p[0]), (flat(B.c[None])[0], a, B.c), (np.zeros(2), b, A.c)):
        if _point_in_poly2(pt, poly):
            return at
    return None


def touch(A: Section, B: Section, tol: float):
    """A point where the two filled polygons meet, or None."""
    if not (A.ok and B.ok):
        return None
    if np.linalg.norm(A.c - B.c) > A.r + B.r + tol:
        return None
    d = np.cross(A.n, B.n)
    nd = np.linalg.norm(d)
    if nd < 1e-9:  # parallel planes
        if abs((B.c - A.c) @ A.n) > tol:
            return None
        return _coplanar_overlap(A, B, tol)
    d = d / nd
    # a point on both planes: solve n_a.x = n_a.c_a, n_b.x = n_b.c_b, d.x = d.(c_a+c_b)/2
    M = np.stack([A.n, B.n, d])
    rhs = np.array([A.n @ A.c, B.n @ B.c, d @ (A.c + B.c) / 2])
    origin = np.linalg.solve(M, rhs)
    ia = _intervals(A, B.c, B.n, origin, d, tol)
    if not ia:
        return None
    ib = _intervals(B, A.c, A.n, origin, d, tol)
    for a0, a1 in ia:
        for b0, b1 in ib:
            lo, hi = max(a0, b0), min(a1, b1)
            if hi - lo > tol:
                return origin + d * (lo + hi) / 2
    return None


def clashes(polys: list, tol_rel: float = 1e-6, limit: int = 1, skip=None) -> list[Clash]:
    """Pairs of sections that touch. ``skip(i, j)`` may exclude pairs that are
    allowed to meet (the first and last section of a closed loop)."""
    secs = [Section(p) for p in polys]
    if not secs:
        return []
    size = max((s.r for s in secs), default=1.0)
    span = float(np.max([np.linalg.norm(s.c - secs[0].c) for s in secs])) + size
    tol = max(1e-9, tol_rel * span)
    out: list[Clash] = []
    cs = np.array([s.c for s in secs])
    rs = np.array([s.r for s in secs])
    for i in range(len(secs)):
        near = np.nonzero(np.linalg.norm(cs[i + 1:] - cs[i], axis=1) <= rs[i + 1:] + rs[i] + tol)[0] + i + 1
        for j in near:
            j = int(j)
            if skip is not None and skip(i, j):
                continue
            hit = touch(secs[i], secs[j], tol)
            if hit is not None:
                out.append(Clash(i, j, tuple(float(x) for x in hit)))
                if len(out) >= limit:
                    return out
    return out


def folds_back(polys) -> int | None:
    """Index of a section the loft passes and then comes back to (sections
    given out of order along the shape, z = 0, 20, 10), or None.

    The shape travels from section to section; it folds back at section k
    when the steps into and out of k go to opposite sides of k's plane.
    """
    secs = [Section(p) for p in polys]
    for k in range(1, len(secs) - 1):
        s0 = secs[k].c - secs[k - 1].c
        s1 = secs[k + 1].c - secs[k].c
        n = secs[k].n
        a, b = float(s0 @ n), float(s1 @ n)
        if secs[k].ok and a * b < 0 and abs(a) > 0.3 * np.linalg.norm(s0) and abs(b) > 0.3 * np.linalg.norm(s1):
            return k
    return None


def self_crossing(poly) -> tuple[float, float, float] | None:
    """A point where a closed section curve crosses itself, or None."""
    s = Section(poly)
    if not s.ok:
        return None
    p = s.p
    u = p[0] - s.c
    if np.linalg.norm(u) < 1e-12:
        return None
    u = u / np.linalg.norm(u)
    v = np.cross(s.n, u)
    a = np.stack([(p - s.c) @ u, (p - s.c) @ v], axis=1)
    n = len(a)
    a2 = np.roll(a, -1, axis=0)
    for k in range(n):
        p0, r = a[k], a2[k] - a[k]
        # compare with edges that do not share a corner with edge k
        idx = [m for m in range(n) if m not in (k, (k + 1) % n, (k - 1) % n)]
        if not idx:
            continue
        q, sv = a[idx], a2[idx] - a[idx]
        den = r[0] * sv[:, 1] - r[1] * sv[:, 0]
        qp = q - p0
        live = np.abs(den) > 1e-15
        safe = np.where(live, den, 1.0)
        t = (qp[:, 0] * sv[:, 1] - qp[:, 1] * sv[:, 0]) / safe
        w = (qp[:, 0] * r[1] - qp[:, 1] * r[0]) / safe
        ok = live & (t >= 0) & (t <= 1) & (w >= 0) & (w <= 1)
        if np.any(ok):
            m = int(np.argmax(ok))
            hit = p0 + t[m] * r
            return tuple(float(x) for x in s.c + hit[0] * u + hit[1] * v)
    return None


def fmt_t(t: float) -> str:
    return f"{t:.2f}".rstrip("0").rstrip(".") if not math.isclose(t, round(t)) else str(int(round(t)))
