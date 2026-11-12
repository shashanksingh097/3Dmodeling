"""Editing sketch geometry: trim, extend, fillet a corner, offset, mirror
and pattern.

Plain Python like the rest of the sketch. Each operation changes the
geometry and its constraints so that the sketch keeps meaning what it
meant: a trimmed end sits ON the curve that cut it, a fillet keeps the
corner as a construction point (so sizes to the corner survive), and
offsets and copies are held to their originals by constraints of their
own (OFFSET, COPY), so they follow when the original changes later.

What happens to the constraints of an end that moves is listed in the
message each operation returns.
"""

from __future__ import annotations

import math

from .sketch import Con, Geo, Sketch, SketchError, _geo_of, _REF

CURVES = ("LINE", "ARC", "CIRCLE")


# =============================================================================
# small 2D helpers
# =============================================================================

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _add(a, b, s=1.0):
    return (a[0] + s * b[0], a[1] + s * b[1])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _unit(a):
    L = math.hypot(*a)
    if L < 1e-15:
        raise SketchError("two points of that geometry are at the same place")
    return (a[0] / L, a[1] / L)


def _ang(c, q) -> float:
    return math.degrees(math.atan2(q[1] - c[1], q[0] - c[0]))


def _parts(ref: str) -> tuple[int | None, str]:
    m = _REF.match(ref)
    if not m:
        return None, ""
    return int(m.group(1)), (m.group(2) or "").upper()


def _curve(sk: Sketch, n: int, what: str) -> Geo:
    g = sk.geos.get(n)
    if g is None:
        have = ", ".join(map(str, sorted(sk.geos))) or "none yet"
        raise SketchError(f"sketch {sk.name} has no geometry {n} (it has: {have})")
    if g.kind not in CURVES:
        raise SketchError(f"{n} is a point; give a line, arc or circle")
    return g


def _num(text) -> int:
    t = str(text).strip()
    if not t.isdigit():
        raise SketchError(f"{t!r} is not a geometry number")
    return int(t)


# =============================================================================
# where curves cross
# =============================================================================

def _carrier_hits(sk: Sketch, g: Geo, h: Geo) -> list[tuple[float, float]]:
    """Where the full carriers (the line through a line, the circle of an arc)
    of g and h cross."""
    def line(x):
        return sk.pt(x.pts["S"]), sk.pt(x.pts["E"])

    def circ(x):
        return sk.pt(x.pts["C"]), sk.radius(x)

    if g.kind == "LINE" and h.kind == "LINE":
        (a, b), (c, d) = line(g), line(h)
        r, s = _sub(b, a), _sub(d, c)
        den = _cross(r, s)
        if abs(den) < 1e-12 * max(1.0, math.hypot(*r) * math.hypot(*s)):
            return []
        t = _cross(_sub(c, a), s) / den
        return [_add(a, r, t)]
    if g.kind == "LINE" or h.kind == "LINE":
        ln, rd = (g, h) if g.kind == "LINE" else (h, g)
        (a, b), (c, rad) = line(ln), circ(rd)
        dvec = _unit(_sub(b, a))
        f = _sub(a, c)
        B = _dot(f, dvec)
        Cq = _dot(f, f) - rad * rad
        disc = B * B - Cq
        if disc < -1e-9 * rad * rad:
            return []
        if disc < 0:
            disc = 0.0
        sq = math.sqrt(disc)
        return [_add(a, dvec, -B - sq)] if sq < 1e-12 else [_add(a, dvec, -B - sq), _add(a, dvec, -B + sq)]
    (c1, r1), (c2, r2) = circ(g), circ(h)
    dd = math.dist(c1, c2)
    if dd < 1e-12 or dd > r1 + r2 + 1e-9 or dd < abs(r1 - r2) - 1e-9:
        return []
    a = (r1 * r1 - r2 * r2 + dd * dd) / (2 * dd)
    hh = math.sqrt(max(r1 * r1 - a * a, 0.0))
    u = _unit(_sub(c2, c1))
    m = _add(c1, u, a)
    if hh < 1e-12:
        return [m]
    nrm = (-u[1], u[0])
    return [_add(m, nrm, hh), _add(m, nrm, -hh)]


def _param(sk: Sketch, g: Geo, q) -> float:
    """Where q is along g: 0..1 along a line, degrees from the start along an
    arc (0..360), degrees from +u around a circle (0..360)."""
    if g.kind == "LINE":
        a, b = sk.pt(g.pts["S"]), sk.pt(g.pts["E"])
        r = _sub(b, a)
        return _dot(_sub(q, a), r) / (_dot(r, r) or 1e-24)
    c = sk.pt(g.pts["C"])
    ang = _ang(c, q)
    if g.kind == "CIRCLE":
        return ang % 360.0
    a1, _ = sk.arc_angles(g)
    return (ang - a1) % 360.0


def _span(sk: Sketch, g: Geo) -> float:
    if g.kind == "LINE":
        return 1.0
    if g.kind == "CIRCLE":
        return 360.0
    a1, a2 = sk.arc_angles(g)
    return a2 - a1


def _eps(sk: Sketch, g: Geo) -> float:
    """A param tolerance worth about a millionth of the sketch size."""
    size = 1e-6 * sk.extent()
    if g.kind == "LINE":
        return size / (math.dist(sk.pt(g.pts["S"]), sk.pt(g.pts["E"])) or 1.0)
    return math.degrees(size / (sk.radius(g) or 1.0))


def _within(sk: Sketch, h: Geo, q) -> bool:
    """Is q (on h's carrier) on the drawn part of h?"""
    if h.kind == "CIRCLE":
        return True
    p, e = _param(sk, h, q), _eps(sk, h)
    if h.kind == "LINE":
        return -e <= p <= 1 + e
    span = _span(sk, h)
    return p <= span + e or p >= 360 - e


def _cuts(sk: Sketch, g: Geo, only: int | None = None, whole: bool = False) -> list[tuple[float, int, tuple]]:
    """(param on g, the curve that crosses there, point) for every curve
    crossing g's carrier (on the drawn part of the other curve, unless whole)."""
    out = []
    for h in sk.geos.values():
        if h.n == g.n or h.kind not in CURVES or (only is not None and h.n != only):
            continue
        for q in _carrier_hits(sk, g, h):
            if whole or _within(sk, h, q):
                out.append((_param(sk, g, q), h.n, q))
    return out


# =============================================================================
# constraints of geometry that changes
# =============================================================================

# kinds whose meaning depends on where a curve's ends are
_EXTENT = ("LENGTH", "MIDPOINT", "FIX")


def _refs_end(c: Con, n: int, role: str) -> bool:
    return any(_parts(r) == (n, role) for r in c.refs)


def _extent_bound(sk: Sketch, c: Con, n: int) -> bool:
    """Does constraint c hold curve n's extent (so it breaks when an end moves)?"""
    if not any(_parts(r) == (n, "") for r in c.refs):
        return False
    g = sk.geos.get(n)
    if c.kind in _EXTENT:
        return True
    if c.kind == "EQUAL" and g is not None and g.kind == "LINE":
        return True
    if c.kind in ("HDIST", "VDIST") and len(c.refs) == 1:
        return True
    return c.kind in ("OFFSET", "COPY")


def _drop(sk: Sketch, keys, said: list[str]) -> None:
    for k in sorted(set(keys)):
        c = sk.cons.pop(k, None)
        if c is not None and not c.auto:
            said.append(f"C{k} ({c.kind.lower()})")


def _free_end(sk: Sketch, n: int, role: str, said: list[str]) -> None:
    """Before an end of curve n moves: drop what pinned that end or its extent."""
    _drop(sk, [k for k, c in sk.cons.items() if _refs_end(c, n, role) or _extent_bound(sk, c, n)], said)


def _rename(sk: Sketch, old: tuple[int, str], new: str) -> None:
    for c in sk.cons.values():
        if any(_parts(r) == old for r in c.refs):
            c.refs = tuple(new if _parts(r) == old else r for r in c.refs)


def _dropped(said: list[str]) -> str:
    return f"; dropped {', '.join(said)}" if said else ""


def _set(sk: Sketch, i: int, q) -> None:
    sk.x[i], sk.x[i + 1] = float(q[0]), float(q[1])


# =============================================================================
# trim and extend
# =============================================================================

def trim_piece(sk: Sketch, n: int, pick) -> tuple[float, float, int | None, int | None]:
    """The piece of curve n that a click at ``pick`` removes: (from, to) in
    n's params and the curves cutting there (None at a free end)."""
    g = _curve(sk, n, "STRIM")
    span, eps = _span(sk, g), _eps(sk, g)
    tp = _param(sk, g, pick)
    cuts = _cuts(sk, g)
    if g.kind == "LINE":
        tp = min(max(tp, 0.0), 1.0)
    elif g.kind == "ARC" and tp > span:  # off the arc: the nearer end
        tp = span if tp - span < 360 - tp else 0.0
    if g.kind == "CIRCLE":
        ps = sorted({(round(p, 9) % 360, h) for p, h, _ in cuts})
        if len(ps) < 2:
            return 0.0, 360.0, None, None
        before = [x for x in ps if x[0] <= tp]
        after = [x for x in ps if x[0] > tp]
        lo = before[-1] if before else ps[-1]
        hi = after[0] if after else ps[0]
        return lo[0], hi[0], lo[1], hi[1]
    inside = sorted((p, h) for p, h, _ in cuts if eps < p < span - eps)
    lo = max((x for x in inside if x[0] < tp), default=None)
    hi = min((x for x in inside if x[0] >= tp), default=None)
    return (lo[0] if lo else 0.0), (hi[0] if hi else span), (lo[1] if lo else None), (hi[1] if hi else None)


def _point_at(sk: Sketch, g: Geo, p: float):
    if g.kind == "LINE":
        a, b = sk.pt(g.pts["S"]), sk.pt(g.pts["E"])
        return _add(a, _sub(b, a), p)
    c, r = sk.pt(g.pts["C"]), sk.radius(g)
    base = 0.0 if g.kind == "CIRCLE" else sk.arc_angles(g)[0]
    t = math.radians(base + p)
    return (c[0] + r * math.cos(t), c[1] + r * math.sin(t))


def trim(sk: Sketch, n: int, pick, uid: int = 0) -> str:
    """Remove the piece of curve n between the curves that cross it, on the
    side of ``pick``. A curve nothing crosses is deleted."""
    g = _curve(sk, n, "STRIM")
    lo, hi, h_lo, h_hi = trim_piece(sk, n, pick)
    said: list[str] = []
    if h_lo is None and h_hi is None:
        return sk.delete(str(n)) + " (nothing crosses it, so all of it went)"
    if g.kind == "CIRCLE":
        q_lo, q_hi = _point_at(sk, g, lo), _point_at(sk, g, hi)
        # what is left runs counter-clockwise from hi round to lo
        _drop(sk, [k for k, c in sk.cons.items() if c.kind == "FIX" and _parts(c.refs[0]) == (n, "")], said)
        c = sk.pt(g.pts["C"])
        s, e = sk._new_point(*q_hi), sk._new_point(*q_lo)
        g.kind, g.pts, g.r = "ARC", {"C": g.pts["C"], "S": s, "E": e}, None
        sk.add_con("ON", (f"{n}.S", str(h_hi)), uid=uid, auto=True, solve=False)
        sk.add_con("ON", (f"{n}.E", str(h_lo)), uid=uid, auto=True, solve=False)
        sk.solve()
        del c
        return f"trimmed circle {n} to an arc between {h_hi} and {h_lo}{_dropped(said)}"
    span = _span(sk, g)
    if h_lo is None:  # the piece at the start goes: the start moves to hi
        _free_end(sk, n, "S", said)
        _set(sk, g.pts["S"], _point_at(sk, g, hi))
        sk.add_con("ON", (f"{n}.S", str(h_hi)), uid=uid, auto=True, solve=False)
        what = f"trimmed {g.kind.lower()} {n} back to {h_hi}"
    elif h_hi is None:  # the piece at the end goes
        _free_end(sk, n, "E", said)
        _set(sk, g.pts["E"], _point_at(sk, g, lo))
        sk.add_con("ON", (f"{n}.E", str(h_lo)), uid=uid, auto=True, solve=False)
        what = f"trimmed {g.kind.lower()} {n} back to {h_lo}"
    else:  # a piece in the middle: n keeps the start, a new curve takes the end
        q_lo, q_hi = _point_at(sk, g, lo), _point_at(sk, g, hi)
        end = sk.pt(g.pts["E"])
        if g.kind == "LINE":
            new = sk.add_line(q_hi, end, uid, g.construction)
        else:
            c = sk.pt(g.pts["C"])
            new = sk.add_arc(c, sk.radius(g), _ang(c, q_hi), _ang(c, end), uid, g.construction)
        _drop(sk, [k for k, c in sk.cons.items() if _extent_bound(sk, c, n)], said)
        _rename(sk, (n, "E"), f"{new.n}.E")
        _set(sk, g.pts["E"], q_lo)
        if g.kind == "LINE":  # the two pieces stay on one line
            sk.add_con("ON", (f"{new.n}.S", str(n)), uid=uid, auto=True, solve=False)
            sk.add_con("ON", (f"{new.n}.E", str(n)), uid=uid, auto=True, solve=False)
        else:  # ... or on one circle
            sk.add_con("COINCIDENT", (f"{new.n}.C", f"{n}.C"), uid=uid, auto=True, solve=False)
            sk.add_con("ON", (f"{new.n}.S", str(n)), uid=uid, auto=True, solve=False)
        sk.add_con("ON", (f"{n}.E", str(h_lo)), uid=uid, auto=True, solve=False)
        sk.add_con("ON", (f"{new.n}.S", str(h_hi)), uid=uid, auto=True, solve=False)
        what = f"cut {g.kind.lower()} {n} between {h_lo} and {h_hi}: {n} and {new.n} are left"
    del span
    sk.solve()
    return what + _dropped(said)


def extend(sk: Sketch, end: str, to: int | None = None, uid: int = 0) -> str:
    """Make a line or arc longer at one end until it meets the next curve
    (or curve ``to``, which may also be extended in thought: its full line
    or circle counts)."""
    n, role = _parts(end)
    if n is None or role not in ("S", "E"):
        raise SketchError(f"give the end to extend, like 3.E or 3.S (got {end})")
    g = _curve(sk, n, "SEXTEND")
    if g.kind == "CIRCLE":
        raise SketchError(f"{n} is a circle, which has no ends")
    if to is not None:
        _curve(sk, to, "SEXTEND")
        if to == n:
            raise SketchError("a curve cannot be extended to itself")
    span, eps = _span(sk, g), _eps(sk, g)
    best = None
    for p, h, q in _cuts(sk, g, only=to, whole=to is not None):
        if g.kind == "LINE":
            far = p - 1 if role == "E" else -p
        else:
            if span + eps < p < 360 - eps:
                far = p - span if role == "E" else 360 - p
            else:
                continue
        if far > eps and (best is None or far < best[0]):
            best = (far, h, q)
    if best is None:
        whom = f"curve {to}" if to is not None else "any curve"
        raise SketchError(f"going on from {n}.{role}, {g.kind.lower()} {n} never meets {whom}")
    _, h, q = best
    said: list[str] = []
    _free_end(sk, n, role, said)
    _set(sk, g.pts[role], q)
    sk.add_con("ON", (f"{n}.{role}", str(h)), uid=uid, auto=True, solve=False)
    sk.solve()
    return f"extended {g.kind.lower()} {n} at {role} to {h}{_dropped(said)}"


# =============================================================================
# fillet a corner
# =============================================================================

def _corner(sk: Sketch, corner: str):
    """The two line ends that meet at ``corner``: (line, role, line, role)."""
    n, role = _parts(corner)
    g = sk.geos.get(n) if n is not None else None
    if g is None or g.kind != "LINE" or role not in ("S", "E"):
        raise SketchError(f"give the corner as the end of a line, like 3.E (got {corner})")
    at = sk.pt(g.pts[role])
    tol = 1e-6 * sk.extent()
    others = []
    for h in sk.geos.values():
        if h.n == n:
            continue
        for r2 in ("S", "E"):
            if r2 in h.pts and h.kind != "POINT" and math.dist(sk.pt(h.pts[r2]), at) <= tol:
                others.append((h, r2))
    lines = [(h, r2) for h, r2 in others if h.kind == "LINE"]
    if len(others) != 1 or len(lines) != 1:
        if not others:
            raise SketchError(f"nothing else ends at {n}.{role}, so there is no corner to round")
        if len(lines) != len(others):
            raise SketchError(f"an arc ends at {n}.{role}; a fillet goes between two lines")
        raise SketchError(f"{len(others) + 1} curves meet at {n}.{role}; a fillet goes where two lines meet")
    return g, role, lines[0][0], lines[0][1]


def fillet(sk: Sketch, corner: str, r: float, uid: int = 0) -> tuple[str, Geo]:
    """Round the corner where two lines meet with an arc of radius r,
    tangent to both. The corner stays as a construction point, so sizes
    given to it still hold."""
    if r <= 0:
        raise SketchError("the radius must be positive")
    l1, a, l2, b = _corner(sk, corner)
    P = sk.pt(l1.pts[a])
    o1 = sk.pt(l1.pts["E" if a == "S" else "S"])
    o2 = sk.pt(l2.pts["E" if b == "S" else "S"])
    d1, d2 = _unit(_sub(o1, P)), _unit(_sub(o2, P))
    theta = math.acos(max(-1.0, min(1.0, _dot(d1, d2))))
    if theta < 1e-4 or theta > math.pi - 1e-4:
        raise SketchError(f"lines {l1.n} and {l2.n} run on in one line at {corner}; there is no corner to round")
    t = r / math.tan(theta / 2)
    len1, len2 = math.dist(P, o1), math.dist(P, o2)
    if t >= min(len1, len2) - 1e-9 * sk.extent():
        most = min(len1, len2) * math.tan(theta / 2)
        raise SketchError(f"radius {r:g} does not fit: the lines are too short (the most is about {most:.4g})")
    T1, T2 = _add(P, d1, t), _add(P, d2, t)
    bis = _unit(_add(d1, d2))
    C = _add(P, bis, r / math.sin(theta / 2))
    A1, A2 = _ang(C, T1), _ang(C, T2)
    first_is_1 = (A2 - A1) % 360 < 180  # counter-clockwise the short way
    said: list[str] = []
    e1, e2 = f"{l1.n}.{a}", f"{l2.n}.{b}"
    # the corner itself stays, as a construction point on both lines
    pt = sk.add_point(P, uid)
    pt.construction = True
    for k, c in list(sk.cons.items()):
        ends = [_parts(x) for x in c.refs]
        if c.kind == "COINCIDENT" and set(ends) == {(l1.n, a), (l2.n, b)}:
            del sk.cons[k]  # the corner join is the arc now
            continue
        if (l1.n, a) in ends or (l2.n, b) in ends:
            c.refs = tuple(str(pt.n) if _parts(x) in ((l1.n, a), (l2.n, b)) else x for x in c.refs)
            if len(set(c.refs)) < len(c.refs):
                _drop(sk, [k], said)
    for ln, other in ((l1, "E" if a == "S" else "S"), (l2, "E" if b == "S" else "S")):
        for k, c in list(sk.cons.items()):
            if not any(_parts(x) == (ln.n, "") for x in c.refs):
                continue
            if c.kind == "LENGTH":  # the length was to the corner: keep it so
                c.kind, c.refs = "DIST", (str(pt.n), f"{ln.n}.{other}")
                c.data = {"now": c.data.get("now", c.value)}
            elif c.kind in ("HDIST", "VDIST") and len(c.refs) == 1:
                s_or_e = (str(pt.n), f"{ln.n}.{other}") if other == "E" else (f"{ln.n}.{other}", str(pt.n))
                c.refs = s_or_e
            elif _extent_bound(sk, c, ln.n):
                _drop(sk, [k], said)
    sk.add_con("ON", (str(pt.n), str(l1.n)), uid=uid, auto=True, solve=False)
    sk.add_con("ON", (str(pt.n), str(l2.n)), uid=uid, auto=True, solve=False)
    _set(sk, l1.pts[a], T1)
    _set(sk, l2.pts[b], T2)
    arc = sk.add_arc(C, r, A1, A2, uid) if first_is_1 else sk.add_arc(C, r, A2, A1, uid)
    arc.construction = l1.construction and l2.construction
    end1, end2 = ("S", "E") if first_is_1 else ("E", "S")
    sk.add_con("COINCIDENT", (e1, f"{arc.n}.{end1}"), uid=uid, auto=True, solve=False)
    sk.add_con("COINCIDENT", (e2, f"{arc.n}.{end2}"), uid=uid, auto=True, solve=False)
    sk.add_con("TANGENT", (str(l1.n), str(arc.n)), uid=uid, auto=True, solve=False)
    sk.add_con("TANGENT", (str(l2.n), str(arc.n)), uid=uid, auto=True, solve=False)
    rad = sk.add_con("RADIUS", (str(arc.n),), r, uid=uid, solve=False)
    sk.solve(blame=rad.n)
    return (f"rounded the corner of {l1.n} and {l2.n} with arc {arc.n}, R{_n(r)} (C{rad.n}); "
            f"the corner is construction point {pt.n}{_dropped(said)}"), arc


def _n(v: float) -> str:
    v = round(v, 6) + 0.0
    return str(int(v)) if float(v).is_integer() else f"{v:g}"


# =============================================================================
# offset
# =============================================================================

class _Piece:
    def __init__(self, g: Geo, fwd: bool):
        self.g, self.fwd = g, fwd


def _ends(sk: Sketch, g: Geo, fwd: bool):
    a, b = sk.pt(g.pts["S"]), sk.pt(g.pts["E"])
    return (a, b) if fwd else (b, a)


def _tangent(sk: Sketch, g: Geo, q, fwd: bool):
    """The walking direction of piece g at point q."""
    if g.kind == "LINE":
        d = _unit(_sub(sk.pt(g.pts["E"]), sk.pt(g.pts["S"])))
    else:
        c = sk.pt(g.pts["C"])
        rr = _unit(_sub(q, c))
        d = (-rr[1], rr[0])  # counter-clockwise
    return d if fwd else (-d[0], -d[1])


def _chains(sk: Sketch, geos: list[Geo]) -> list[tuple[list[_Piece], bool]]:
    """Group curves into chains joined end to end: (pieces in walking order, closed)."""
    tol = 1e-6 * sk.extent()
    left = {g.n: g for g in geos}
    out = []
    while left:
        start = left.pop(min(left))
        chain = [_Piece(start, True)]
        if start.kind == "CIRCLE":
            out.append((chain, True))
            continue

        def grow(at_end: bool):
            while True:
                tip_piece = chain[-1] if at_end else chain[0]
                a, b = _ends(sk, tip_piece.g, tip_piece.fwd)
                tip = b if at_end else a
                found = []
                for n, h in left.items():
                    if h.kind == "CIRCLE":
                        continue
                    for role in ("S", "E"):
                        if math.dist(sk.pt(h.pts[role]), tip) <= tol:
                            found.append((h, role))
                if not found:
                    return
                if len(found) > 1:
                    raise SketchError(f"{len(found) + 1} curves meet at ({tip[0]:g}, {tip[1]:g}); "
                                      "offset one chain of curves at a time")
                h, role = found[0]
                del left[h.n]
                if at_end:
                    chain.append(_Piece(h, role == "S"))
                else:
                    chain.insert(0, _Piece(h, role == "E"))

        grow(True)
        grow(False)
        first = chain[0]
        last = chain[-1]
        closed = len(chain) > 1 and math.dist(_ends(sk, first.g, first.fwd)[0], _ends(sk, last.g, last.fwd)[1]) <= tol
        if len(chain) == 1 and first.g.kind == "CIRCLE":
            closed = True
        out.append((chain, closed))
    return out


def _area(sk: Sketch, chain: list[_Piece]) -> float:
    poly = []
    for pc in chain:
        g = pc.g
        if g.kind == "LINE":
            poly.append(_ends(sk, g, pc.fwd)[0])
            continue
        c, r = sk.pt(g.pts["C"]), sk.radius(g)
        a1, a2 = (0.0, 360.0) if g.kind == "CIRCLE" else sk.arc_angles(g)
        pts = [(c[0] + r * math.cos(math.radians(a1 + (a2 - a1) * i / 16)),
                c[1] + r * math.sin(math.radians(a1 + (a2 - a1) * i / 16))) for i in range(16)]
        poly += pts if pc.fwd else pts[::-1]
    return 0.5 * sum(_cross(poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly)))


def _offset_hits(lines_or_circles, near):
    """Crossing nearest ``near`` of two offset carriers, each ('L', point, dir) or ('C', centre, r)."""
    A, B = lines_or_circles
    pts = []
    if A[0] == "L" and B[0] == "L":
        den = _cross(A[2], B[2])
        if abs(den) > 1e-12:
            t = _cross(_sub(B[1], A[1]), B[2]) / den
            pts = [_add(A[1], A[2], t)]
    elif A[0] == "L" or B[0] == "L":
        L, Cc = (A, B) if A[0] == "L" else (B, A)
        f = _sub(L[1], Cc[1])
        bq = _dot(f, L[2])
        disc = bq * bq - (_dot(f, f) - Cc[2] ** 2)
        if disc >= -1e-9:
            sq = math.sqrt(max(disc, 0.0))
            pts = [_add(L[1], L[2], -bq - sq), _add(L[1], L[2], -bq + sq)]
    else:
        c1, r1, c2, r2 = A[1], A[2], B[1], B[2]
        dd = math.dist(c1, c2)
        if dd > 1e-12:
            a = (r1 * r1 - r2 * r2 + dd * dd) / (2 * dd)
            h2 = r1 * r1 - a * a
            if h2 >= -1e-9:
                u = _unit(_sub(c2, c1))
                m = _add(c1, u, a)
                hh = math.sqrt(max(h2, 0.0))
                pts = [_add(m, (-u[1], u[0]), hh), _add(m, (-u[1], u[0]), -hh)]
    if not pts:
        return None
    return min(pts, key=lambda q: math.dist(q, near))


def offset(sk: Sketch, d: float, names: list, uid: int = 0) -> tuple[str, list[Geo]]:
    """Offset curves by d. Curves joined end to end are offset as one chain,
    with corners met again (sharp corners stay sharp). For a closed chain or
    a circle a positive d goes outwards; for an open chain, to the left
    walking along the lowest-numbered curve from its start to its end."""
    if abs(d) < 1e-12:
        raise SketchError("the distance must not be 0")
    geos = []
    for t in names:
        g = _curve(sk, _num(t), "SOFFSET")
        if g not in geos:
            geos.append(g)
    if not geos:
        raise SketchError("give the curves to offset")
    made: list[Geo] = []
    for chain, closed in _chains(sk, geos):
        made += _offset_chain(sk, chain, closed, d, uid)
    sk.solve()
    return f"offset {', '.join(str(g.n) for g in geos)} by {_n(d)}: {', '.join(str(g.n) for g in made)}", made


def _offset_chain(sk: Sketch, chain: list[_Piece], closed: bool, d: float, uid: int) -> list[Geo]:
    lowest = min(chain, key=lambda pc: pc.g.n)
    if closed:
        sigma = -1.0 if _area(sk, chain) > 0 else 1.0  # outwards is to the right of a counter-clockwise walk
    else:
        sigma = 1.0 if lowest.fwd else -1.0
    s = sigma * d  # how far to the left of the walk
    if len(chain) == 1 and chain[0].g.kind == "CIRCLE":
        g = chain[0].g
        r = sk.radius(g) + d
        if r <= 0:
            raise SketchError(f"{_n(d)} inwards is more than the radius of circle {g.n}")
        new = sk.add_circle(sk.pt(g.pts["C"]), r, uid, g.construction)
        sk.cons[sk._next_con] = Con(sk._next_con, "OFFSET", (str(new.n), str(g.n)), d,
                                    data={"k": -1.0}, uid=uid, auto=True)
        sk._next_con += 1
        return [new]
    for pc in chain:
        if pc.g.kind == "CIRCLE":
            raise SketchError(f"circle {pc.g.n} has no ends to join to other curves; offset it on its own")

    def carrier(pc):
        g = pc.g
        if g.kind == "LINE":
            a, b = _ends(sk, g, pc.fwd)
            dirn = _unit(_sub(b, a))
            return ("L", _add(a, (-dirn[1], dirn[0]), s), dirn)
        c = sk.pt(g.pts["C"])
        # left of a counter-clockwise walk is towards the centre
        r = sk.radius(g) - (s if pc.fwd else -s)
        if r <= 1e-9 * sk.extent():
            raise SketchError(f"{_n(abs(d))} that way is more than the radius of arc {g.n}")
        return ("C", c, r)

    n = len(chain)
    joints = []  # per joint between piece i and i+1: (point, tangent?)
    for i in range(n if closed else n - 1):
        pa, pb = chain[i], chain[(i + 1) % n]
        J = _ends(sk, pa.g, pa.fwd)[1]
        ta, tb = _tangent(sk, pa.g, J, pa.fwd), _tangent(sk, pb.g, J, pb.fwd)
        smooth = abs(_cross(ta, tb)) < 1e-7 and _dot(ta, tb) > 0
        if smooth:
            joints.append((_add(J, (-ta[1], ta[0]), s), True))
        else:
            near = _add(J, _unit(_add((-ta[1], ta[0]), (-tb[1], tb[0]))) if abs(_dot(ta, tb) + 1) > 1e-9 else (-ta[1], ta[0]), s)
            q = _offset_hits((carrier(pa), carrier(pb)), near)
            if q is None:
                raise SketchError(f"the offsets of {pa.g.n} and {pb.g.n} do not meet again; try a smaller distance")
            joints.append((q, False))
    # the point where each piece starts and ends (walking order), and how it is held
    starts, ends = [], []
    for i, pc in enumerate(chain):
        a, b = _ends(sk, pc.g, pc.fwd)
        if i == 0 and not closed:
            t = _tangent(sk, pc.g, a, pc.fwd)
            starts.append((_add(a, (-t[1], t[0]), s), True))
        else:
            starts.append(joints[i - 1])
        if i == n - 1 and not closed:
            t = _tangent(sk, pc.g, b, pc.fwd)
            ends.append((_add(b, (-t[1], t[0]), s), True))
        else:
            ends.append(joints[i])
    made = []
    for i, pc in enumerate(chain):
        g = pc.g
        (qa, na), (qb, nb) = starts[i], ends[i]
        own_s, own_e = (qa, qb) if pc.fwd else (qb, qa)
        normal = [r for r, flag in (("S", na if pc.fwd else nb), ("E", nb if pc.fwd else na)) if flag]
        if g.kind == "LINE":
            a0, b0 = sk.pt(g.pts["S"]), sk.pt(g.pts["E"])
            if _dot(_sub(own_e, own_s), _sub(b0, a0)) <= 1e-9 * sk.extent() ** 2:
                raise SketchError(f"{_n(abs(d))} is too far: line {g.n} would turn round; try a smaller distance")
            new = sk.add_line(own_s, own_e, uid, g.construction)
            k = 1.0 if pc.fwd else -1.0  # signed distance of the new line from g's own start->end
            k *= 1.0 if s > 0 else -1.0
        else:
            c = sk.pt(g.pts["C"])
            r = math.dist(c, own_s)
            new = sk.add_arc(c, r, _ang(c, own_s), _ang(c, own_e), uid, g.construction)
            k = (1.0 if pc.fwd else -1.0) * (1.0 if s > 0 else -1.0)
        sk.cons[sk._next_con] = Con(sk._next_con, "OFFSET", (str(new.n), str(g.n)), abs(d),
                                    data={"k": k, "normal": normal}, uid=uid, auto=True)
        sk._next_con += 1
        made.append(new)
    # sharp corners: the offset pieces meet there
    for i in range(n if closed else n - 1):
        if joints[i][1]:
            continue
        pa, pb = chain[i], chain[(i + 1) % n]
        ra = "E" if pa.fwd else "S"
        rb = "S" if pb.fwd else "E"
        sk.add_con("COINCIDENT", (f"{made[i].n}.{ra}", f"{made[(i + 1) % n].n}.{rb}"), uid=uid, auto=True, solve=False)
    return made


# =============================================================================
# mirror and pattern
# =============================================================================

def _copy_geo(sk: Sketch, g: Geo, f, uid: int, flip: bool) -> Geo:
    """A copy of g with every point moved by f; flip reverses an arc (a mirror)."""
    if g.kind == "POINT":
        new = sk._geo("POINT", {"P": sk._new_point(*f(sk.pt(g.pts["P"])))}, construction=g.construction)
    elif g.kind == "LINE":
        new = sk._geo("LINE", {"S": sk._new_point(*f(sk.pt(g.pts["S"]))),
                               "E": sk._new_point(*f(sk.pt(g.pts["E"])))}, construction=g.construction)
    elif g.kind == "CIRCLE":
        cp = sk._new_point(*f(sk.pt(g.pts["C"])))
        sk.x.append(abs(sk.x[g.r]))
        new = sk._geo("CIRCLE", {"C": cp}, r=len(sk.x) - 1, construction=g.construction)
    else:
        s, e = f(sk.pt(g.pts["S"])), f(sk.pt(g.pts["E"]))
        if flip:
            s, e = e, s
        new = sk._geo("ARC", {"C": sk._new_point(*f(sk.pt(g.pts["C"]))), "S": sk._new_point(*s),
                              "E": sk._new_point(*e)}, construction=g.construction)
    del uid
    return new


def _held(sk: Sketch, new: Geo, g: Geo, data: dict, uid: int, extra: tuple = ()) -> None:
    sk.cons[sk._next_con] = Con(sk._next_con, "COPY", (str(new.n), str(g.n)) + extra, None, data=data,
                                uid=uid, auto=True)
    sk._next_con += 1


def _geos(sk: Sketch, names: list, what: str) -> list[Geo]:
    out = []
    for t in names:
        n = _num(t)
        g = sk.geos.get(n)
        if g is None:
            raise SketchError(f"sketch {sk.name} has no geometry {n}")
        if g not in out:
            out.append(g)
    if not out:
        raise SketchError("give the geometry to copy")
    return out


def mirror(sk: Sketch, axis: str, names: list, uid: int = 0) -> tuple[str, list[Geo]]:
    """Mirror copies of geometry about a line (a sketch line, or H / V).
    Each copy is held as the mirror image of its original."""
    ax = sk.ref(axis)
    if ax.geo is None or ax.is_point or ax.geo.kind != "LINE":
        raise SketchError(f"mirror about a line (a line's number, or H / V), not {axis}")
    a, b = sk.pt(ax.geo.pts["S"]), sk.pt(ax.geo.pts["E"])
    dirn = _unit(_sub(b, a))

    def f(q):
        rel = _sub(q, a)
        along = _dot(rel, dirn)
        foot = _add(a, dirn, along)
        return (2 * foot[0] - q[0], 2 * foot[1] - q[1])

    made, skipped = [], []
    tol = 1e-6 * sk.extent()
    for g in _geos(sk, names, "SMIRROR"):
        if not ax.fixed and g.n == ax.geo.n:
            skipped.append(g.n)
            continue
        if all(math.dist(f(sk.pt(i)), sk.pt(i)) <= tol for i in g.pts.values()) and g.kind != "ARC":
            skipped.append(g.n)  # on the axis: its mirror is itself
            continue
        new = _copy_geo(sk, g, f, uid, flip=True)
        _held(sk, new, g, {"T": "MIRROR"}, uid, (ax.text,))
        made.append(new)
    if not made:
        raise SketchError("everything given lies on the mirror line, so there is nothing to copy")
    sk.solve()
    note = f" ({', '.join(map(str, skipped))} on the mirror line, left as is)" if skipped else ""
    return f"mirrored about {ax.text}: {', '.join(str(g.n) for g in made)}{note}", made


def pattern(sk: Sketch, kind: str, n: int, step, names: list, centre=None, uid: int = 0) -> tuple[str, list[Geo]]:
    """Copies of geometry in a row (LINEAR, step = (du, dv)) or round a
    point (POLAR, step = the angle between copies). n counts the original."""
    if n < 2 or n != int(n):
        raise SketchError("the count is a whole number, 2 or more (the original counts)")
    geos = _geos(sk, names, "SPATTERN")
    made = []
    extra: tuple = ()
    if kind == "POLAR":
        (cu, cv), cref = sk.point_value(centre)
        if cref is None:  # a centre given as numbers: a fixed construction point there
            cp = sk.add_point((cu, cv), uid)
            cp.construction = True
            sk.add_con("FIX", (str(cp.n),), uid=uid, auto=True, solve=False)
            cref_text = str(cp.n)
        else:
            cref_text = cref.text
        extra = (cref_text,)
    for i in range(1, int(n)):
        if kind == "LINEAR":
            du, dv = step[0] * i, step[1] * i
            data = {"T": "MOVE", "du": du, "dv": dv}

            def f(q, du=du, dv=dv):
                return (q[0] + du, q[1] + dv)
        else:
            a = math.radians(step * i)
            data = {"T": "TURN", "a": step * i}

            def f(q, a=a):
                x, y = q[0] - cu, q[1] - cv
                return (cu + x * math.cos(a) - y * math.sin(a), cv + x * math.sin(a) + y * math.cos(a))
        for g in geos:
            new = _copy_geo(sk, g, f, uid, flip=False)
            _held(sk, new, g, data, uid, extra)
            made.append(new)
    sk.solve()
    shown = f"{made[0].n}..{made[-1].n}" if len(made) > 3 else ", ".join(str(g.n) for g in made)
    return f"{kind.lower()} pattern of {', '.join(str(g.n) for g in geos)}, {int(n)} in all: {shown}", made


def geo_in(c: Con) -> list[int]:
    return [g for g in (_geo_of(r) for r in c.refs) if g is not None]
