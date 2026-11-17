"""Ellipses and elliptical arcs in a sketch: the plain 2D math.

An ellipse is stored as its centre C, the end A of one axis (so the first
radius is the distance C to A, and the axis can be turned or sized like any
point), and the second radius across it (one number, like a circle's
radius). An elliptical arc adds its start S and end E, which stay on the
ellipse; it runs counter-clockwise from S to E.

Positions round an ellipse are its parametric angle t in degrees: the point
at t is C + a cos t along the first axis + b sin t across it. t = 0 is A.

Plain Python like the rest of the sketch: no kernel, no Qt.
"""

from __future__ import annotations

import math

ROUND_KINDS = ("ELLIPSE", "EARC")


def frame(sk, g):
    """(centre, unit first axis, a (first radius), b (second radius))."""
    c, p = sk.pt(g.pts["C"]), sk.pt(g.pts["A"])
    dx, dy = p[0] - c[0], p[1] - c[1]
    a = math.hypot(dx, dy) or 1e-12
    return c, (dx / a, dy / a), a, abs(sk.x[g.r])


def point(sk, g, t: float):
    c, ax, a, b = frame(sk, g)
    ct, st = math.cos(math.radians(t)), math.sin(math.radians(t))
    return (c[0] + a * ct * ax[0] - b * st * ax[1], c[1] + a * ct * ax[1] + b * st * ax[0])


def local(sk, g, q):
    """q in the ellipse's own axes: (along the first axis, across it)."""
    c, ax, _, _ = frame(sk, g)
    d = (q[0] - c[0], q[1] - c[1])
    return d[0] * ax[0] + d[1] * ax[1], -d[0] * ax[1] + d[1] * ax[0]


def param(sk, g, q) -> float:
    """The parametric angle (degrees, -180..180) of the point of g nearest
    in angle to q (exact for points on the ellipse)."""
    _, _, a, b = frame(sk, g)
    x, y = local(sk, g, q)
    return math.degrees(math.atan2(y / (b or 1e-12), x / a))


def arc_params(sk, g) -> tuple[float, float]:
    """Start and end parameter of an elliptical arc, end > start."""
    t1, t2 = param(sk, g, sk.pt(g.pts["S"])), param(sk, g, sk.pt(g.pts["E"]))
    while t2 <= t1 + 1e-9:
        t2 += 360.0
    return t1, t2


def params(sk, g) -> tuple[float, float]:
    return (0.0, 360.0) if g.kind == "ELLIPSE" else arc_params(sk, g)


def polyline(sk, g, n: int = 64):
    t1, t2 = params(sk, g)
    steps = max(8, int(n * (t2 - t1) / 360) + 1)
    return [point(sk, g, t1 + (t2 - t1) * i / steps) for i in range(steps + 1)]


def level(a: float, b: float, x: float, y: float) -> float:
    """About the distance of (x, y) (in the ellipse's axes) outside the
    ellipse (negative inside): exact on the ellipse and close near it."""
    k = math.hypot(x / a, y / b)
    if k < 1e-12:
        return -min(a, b)
    # distance along the ray from the centre, scaled by how steep the curve is there
    r_at = math.hypot(x, y) / k  # where the ray meets the ellipse
    return (k - 1.0) * r_at


def side(sk, g, q) -> float:
    _, _, a, b = frame(sk, g)
    x, y = local(sk, g, q)
    return level(a, b, x, y)


def foot(sk, g, q):
    """The point of g's ellipse nearest to q (and its parameter)."""
    best_t, best_d = 0.0, float("inf")
    for i in range(72):
        t = i * 5.0
        d = math.dist(point(sk, g, t), q)
        if d < best_d:
            best_t, best_d = t, d
    step = 2.5
    for _ in range(40):  # golden-free bisection on the angle: plenty for drawing and picking
        for t in (best_t - step, best_t + step):
            d = math.dist(point(sk, g, t), q)
            if d < best_d:
                best_t, best_d = t, d
        step *= 0.6
    return point(sk, g, best_t), best_t


def distance(sk, g, q) -> float:
    """Distance from q to the drawn ellipse or arc."""
    p, t = foot(sk, g, q)
    if g.kind == "EARC":
        t1, t2 = arc_params(sk, g)
        if not within(t, t1, t2):
            return min(math.dist(q, sk.pt(g.pts["S"])), math.dist(q, sk.pt(g.pts["E"])))
    return math.dist(p, q)


def within(t: float, t1: float, t2: float, eps: float = 1e-9) -> bool:
    return (t - t1) % 360.0 <= (t2 - t1) + eps or (t - t1) % 360.0 >= 360 - eps


# ---- where an ellipse crosses another curve ------------------------------------------------

def _level_of(sk, h):
    """A function of a point: zero on h's carrier (the full line, circle or ellipse)."""
    if h.kind == "LINE":
        a, b = sk.pt(h.pts["S"]), sk.pt(h.pts["E"])
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1e-12
        return lambda q: (dx * (q[1] - a[1]) - dy * (q[0] - a[0])) / L
    if h.kind in ("CIRCLE", "ARC"):
        c, r = sk.pt(h.pts["C"]), sk.radius(h)
        return lambda q: math.dist(q, c) - r
    return lambda q: side(sk, h, q)


def hits(sk, g, h) -> list[tuple[float, float]]:
    """Where the carriers of g (an ellipse or elliptical arc) and h cross:
    the full ellipse of g against h's full line, circle or ellipse."""
    f = _level_of(sk, h)
    n = 720
    ts = [i * 360.0 / n for i in range(n + 1)]
    vals = [f(point(sk, g, t)) for t in ts]
    size = max(frame(sk, g)[2], frame(sk, g)[3])
    out: list[tuple[float, float]] = []

    def add(t):
        q = point(sk, g, t)
        if abs(f(q)) < 1e-7 * max(1.0, size) and all(math.dist(q, o) > 1e-7 * max(1.0, size) for o in out):
            out.append(q)

    for i in range(n):
        v0, v1 = vals[i], vals[i + 1]
        if v0 == 0.0:
            add(ts[i])
        elif v0 * v1 < 0:
            lo, hi, flo = ts[i], ts[i + 1], v0
            for _ in range(80):
                mid = 0.5 * (lo + hi)
                fm = f(point(sk, g, mid))
                if (fm < 0) == (flo < 0):
                    lo, flo = mid, fm
                else:
                    hi = mid
            add(0.5 * (lo + hi))
        elif i > 0 and abs(v0) < abs(vals[i - 1]) and abs(v0) <= abs(v1) and abs(v0) < 1e-3 * size:
            # a touch without a crossing: polish the smallest |f| nearby
            lo, hi = ts[i - 1], ts[i + 1]
            for _ in range(80):
                m1, m2 = lo + (hi - lo) / 3, hi - (hi - lo) / 3
                if abs(f(point(sk, g, m1))) < abs(f(point(sk, g, m2))):
                    hi = m2
                else:
                    lo = m1
            add(0.5 * (lo + hi))
    return out
