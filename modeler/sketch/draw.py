"""More ways to draw in a sketch: a tangent arc on from an end, a circle
through three points, a centre rectangle, a rectangle at any angle, a
regular polygon and a slot along an arc.

Each one is built from the sketch's own lines, arcs and circles, held
together by ordinary constraints (so the result can be sized and dragged
like anything drawn by hand). Plain Python like ``sketch.py``.
"""

from __future__ import annotations

import math

from .edit import _add, _away, _dot, _parts, _sub, _unit
from .sketch import Geo, Sketch, SketchError


def _con(sk: Sketch, kind: str, *refs: str, uid: int = 0) -> None:
    sk.add_con(kind, tuple(refs), uid=uid, auto=True, solve=False)


def tangent_arc(sk: Sketch, end: str, to, uid: int = 0, construction: bool = False) -> Geo:
    """An arc that carries on smoothly from the end of a line or arc
    (``end``, like 3.E) to the point ``to``."""
    n, role = _parts(end)
    g = sk.geos.get(n) if n is not None else None
    if g is None or g.kind not in ("LINE", "ARC") or role not in ("S", "E"):
        raise SketchError(f"start a tangent arc at the end of a line or arc, like 3.E (got {end})")
    P = sk.pt(g.pts[role])
    back = _away(sk, g, role)
    t = (-back[0], -back[1])  # the way the curve was going as it reached its end
    (Q, rq) = sk.point_value(to)
    w = _sub(Q, P)
    nrm = (-t[1], t[0])
    side = _dot(w, nrm)
    if math.hypot(*w) < 1e-9:
        raise SketchError("the arc's end is where it starts")
    if abs(side) < 1e-9 * max(1.0, math.hypot(*w)):
        raise SketchError(f"that point is straight on from {end}; a line goes there, not an arc")
    s = _dot(w, w) / (2 * side)
    C = _add(P, nrm, s)
    r = abs(s)
    a_p = math.degrees(math.atan2(P[1] - C[1], P[0] - C[0]))
    a_q = math.degrees(math.atan2(Q[1] - C[1], Q[0] - C[0]))
    if s > 0:  # turning left: counter-clockwise from P to Q
        arc = sk.add_arc(C, r, a_p, a_q, uid, construction)
        mine, far = "S", "E"
    else:
        arc = sk.add_arc(C, r, a_q, a_p, uid, construction)
        mine, far = "E", "S"
    _con(sk, "COINCIDENT", end, f"{arc.n}.{mine}", uid=uid)
    _con(sk, "TANGENT", str(g.n), str(arc.n), uid=uid)
    if rq is not None:
        _con(sk, "COINCIDENT", f"{arc.n}.{far}", rq.text, uid=uid)
    return arc


def circle_3p(sk: Sketch, a, b, c, uid: int = 0, construction: bool = False) -> Geo:
    """A circle through three points; named points are kept on it."""
    vals = [sk.point_value(q) for q in (a, b, c)]
    (x1, y1), (x2, y2), (x3, y3) = (v[0] for v in vals)
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-12:
        raise SketchError("the three points are on one line, so no circle passes through them")
    s1, s2, s3 = x1 * x1 + y1 * y1, x2 * x2 + y2 * y2, x3 * x3 + y3 * y3
    ux = (s1 * (y2 - y3) + s2 * (y3 - y1) + s3 * (y1 - y2)) / d
    uy = (s1 * (x3 - x2) + s2 * (x1 - x3) + s3 * (x2 - x1)) / d
    g = sk.add_circle((ux, uy), math.hypot(x1 - ux, y1 - uy), uid, construction)
    for _, ref in vals:
        if ref is not None:
            _con(sk, "ON", ref.text, str(g.n), uid=uid)
    return g


def rect_centre(sk: Sketch, centre, corner, uid: int = 0, construction: bool = False) -> list[Geo]:
    """A level rectangle around a centre point, through a corner. The centre
    is a construction point at the middle of a construction diagonal, so the
    rectangle stays centred when it is sized."""
    (cu, cv), rc = sk.point_value(centre)
    (u, v), rk = sk.point_value(corner)
    du, dv = u - cu, v - cv
    if abs(du) < 1e-9 or abs(dv) < 1e-9:
        raise SketchError("the corner must be off level and off upright from the centre")
    lines = sk.add_rect((cu - du, cv - dv), (cu + du, cv + dv), uid, construction)
    diag = sk.add_line((cu - du, cv - dv), (cu + du, cv + dv), uid, True)
    _con(sk, "COINCIDENT", f"{diag.n}.S", f"{lines[0].n}.S", uid=uid)
    _con(sk, "COINCIDENT", f"{diag.n}.E", f"{lines[2].n}.S", uid=uid)
    mid = sk.add_point((cu, cv), uid)
    mid.construction = True
    _con(sk, "MIDPOINT", str(mid.n), str(diag.n), uid=uid)
    if rc is not None:
        _con(sk, "COINCIDENT", str(mid.n), rc.text, uid=uid)
    if rk is not None:
        _con(sk, "COINCIDENT", f"{diag.n}.E", rk.text, uid=uid)
    return lines + [diag, mid]


def rect_3p(sk: Sketch, a, b, c, uid: int = 0, construction: bool = False) -> list[Geo]:
    """A rectangle at any angle: one side from a to b, and as wide as point c
    is from that side (on c's side)."""
    (A, ra), (B, rb) = sk.point_value(a), sk.point_value(b)
    (Cp, _) = sk.point_value(c)
    d = _sub(B, A)
    if math.hypot(*d) < 1e-9:
        raise SketchError("the first side needs two different points")
    u = _unit(d)
    nrm = (-u[1], u[0])
    w = _dot(_sub(Cp, A), nrm)
    if abs(w) < 1e-9 * max(1.0, math.hypot(*d)):
        raise SketchError("the third point is on the first side's line, so the rectangle would have no width")
    corners = [A, B, _add(B, nrm, w), _add(A, nrm, w)]
    lines = [sk.add_line(corners[i], corners[(i + 1) % 4], uid, construction) for i in range(4)]
    for i in range(4):
        _con(sk, "COINCIDENT", f"{lines[i].n}.E", f"{lines[(i + 1) % 4].n}.S", uid=uid)
    _con(sk, "PERPENDICULAR", str(lines[0].n), str(lines[1].n), uid=uid)
    _con(sk, "PARALLEL", str(lines[0].n), str(lines[2].n), uid=uid)
    _con(sk, "PARALLEL", str(lines[1].n), str(lines[3].n), uid=uid)
    for mine, ref in ((f"{lines[0].n}.S", ra), (f"{lines[0].n}.E", rb)):
        if ref is not None:
            _con(sk, "COINCIDENT", mine, ref.text, uid=uid)
    return lines


def polygon(sk: Sketch, centre, n: int, r: float, angle: float = 90.0, outside: bool = False,
            uid: int = 0, construction: bool = False) -> list[Geo]:
    """A regular polygon with n sides round a construction circle of radius
    r: its corners on the circle, or (``outside``) its sides touching it
    (a second construction circle then goes through the corners).
    ``angle`` is where the first corner is, in degrees from +u."""
    if n != int(n) or n < 3:
        raise SketchError("a polygon has 3 sides or more")
    n = int(n)
    if n > 200:
        raise SketchError("at most 200 sides (a circle is SCIRCLE)")
    if r <= 0:
        raise SketchError("the radius must be positive")
    (cu, cv), rc = sk.point_value(centre)
    circ = sk.add_circle((cu, cv), r, uid, True)
    if rc is not None:
        _con(sk, "COINCIDENT", f"{circ.n}.C", rc.text, uid=uid)
    R = r / math.cos(math.pi / n) if outside else r
    # the corners lie on a circle and the sides are equal: that is what keeps
    # it regular (equal sides that only touch a circle could still lean)
    ring = sk.add_circle((cu, cv), R, uid, True) if outside else circ
    if outside:
        _con(sk, "CONCENTRIC", str(ring.n), str(circ.n), uid=uid)
    corners = [(cu + R * math.cos(math.radians(angle) + 2 * math.pi * i / n),
                cv + R * math.sin(math.radians(angle) + 2 * math.pi * i / n)) for i in range(n)]
    lines = [sk.add_line(corners[i], corners[(i + 1) % n], uid, construction) for i in range(n)]
    for i in range(n):
        _con(sk, "COINCIDENT", f"{lines[i].n}.E", f"{lines[(i + 1) % n].n}.S", uid=uid)
    for ln in lines:
        _con(sk, "ON", f"{ln.n}.S", str(ring.n), uid=uid)
    for ln in lines[1:]:
        _con(sk, "EQUAL", str(lines[0].n), str(ln.n), uid=uid)
    if outside:
        _con(sk, "TANGENT", str(lines[0].n), str(circ.n), uid=uid)
    return lines + ([circ, ring] if outside else [circ])


def arc_slot(sk: Sketch, centre, r: float, a1: float, a2: float, w: float, uid: int = 0,
             construction: bool = False) -> list[Geo]:
    """A slot bent along an arc: its middle runs round ``centre`` at radius r
    from angle a1 to a2 (counter-clockwise), and it is 2w wide with round ends.
    The middle is kept as a construction arc."""
    if r <= 0 or w <= 0:
        raise SketchError("the radius and the half-width must be positive")
    if w >= r:
        raise SketchError(f"the half-width {w:g} must be less than the radius {r:g}")
    span = (a2 - a1) % 360.0
    if span < 1e-6 or span > 360 - 1e-6:
        raise SketchError("the slot needs two different angles")
    a2 = a1 + span
    (cu, cv), rc = sk.point_value(centre)
    mid = sk.add_arc((cu, cv), r, a1, a2, uid, True)
    if rc is not None:
        _con(sk, "COINCIDENT", f"{mid.n}.C", rc.text, uid=uid)
    outer = sk.add_arc((cu, cv), r + w, a1, a2, uid, construction)
    inner = sk.add_arc((cu, cv), r - w, a1, a2, uid, construction)
    t1, t2 = math.radians(a1), math.radians(a2)
    e1 = (cu + r * math.cos(t1), cv + r * math.sin(t1))
    e2 = (cu + r * math.cos(t2), cv + r * math.sin(t2))
    cap2 = sk.add_arc(e2, w, a2, a2 + 180, uid, construction)
    cap1 = sk.add_arc(e1, w, a1 + 180, a1 + 360, uid, construction)
    _con(sk, "COINCIDENT", f"{outer.n}.C", f"{mid.n}.C", uid=uid)
    _con(sk, "COINCIDENT", f"{inner.n}.C", f"{mid.n}.C", uid=uid)
    _con(sk, "COINCIDENT", f"{cap2.n}.C", f"{mid.n}.E", uid=uid)
    _con(sk, "COINCIDENT", f"{cap1.n}.C", f"{mid.n}.S", uid=uid)
    for p, q in ((f"{outer.n}.E", f"{cap2.n}.S"), (f"{cap2.n}.E", f"{inner.n}.E"),
                 (f"{inner.n}.S", f"{cap1.n}.S"), (f"{cap1.n}.E", f"{outer.n}.S")):
        _con(sk, "COINCIDENT", p, q, uid=uid)
    for cap in (cap1, cap2):
        _con(sk, "TANGENT", str(cap.n), str(outer.n), uid=uid)
        _con(sk, "TANGENT", str(cap.n), str(inner.n), uid=uid)
    _con(sk, "EQUAL", str(cap1.n), str(cap2.n), uid=uid)
    return [outer, cap2, inner, cap1, mid]


