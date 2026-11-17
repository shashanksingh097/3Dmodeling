"""More sketch editing: chamfer a corner, split a curve, close a corner,
trim many pieces at once (power trim), and move, rotate, scale or copy
geometry.

Plain Python like ``edit.py``, whose helpers it uses. The same rules hold:
a corner that is cut away stays as a construction point, so sizes to it
still hold; an end that moves loses only what pinned that end; and the
message says which of the user's constraints had to go.
"""

from __future__ import annotations

import copy
import math
import re

from . import edit as ed
from . import ellipse as el
from . import sketch as _sk
from .edit import (
    _add,
    _carrier_hits,
    _corner,
    _curve,
    _cuts,
    _drop,
    _dropped,
    _eps,
    _extent_bound,
    _free_end,
    _geos,
    _n,
    _param,
    _parts,
    _point_at,
    _rename,
    _set,
    _span,
    _sub,
    _unit,
    _dot,
    _ang,
    _copy_geo,
    trim,
)
from .sketch import kname, Geo, Sketch, SketchError, _geo_of

CORNER = re.compile(r"^\s*\d+\s*\.\s*[SE]\s*$", re.I)


# =============================================================================
# keeping a corner that is cut away
# =============================================================================

def _keep_corner(sk: Sketch, g1: Geo, a: str, g2: Geo, b: str, uid: int, said: list[str]) -> Geo:
    """Before the ends g1.a and g2.b (which meet) move apart: put a
    construction point at the corner, ON both curves, and hand it what was
    tied to the corner (a LENGTH to the corner becomes a DIST to it)."""
    P = sk.pt(g1.pts[a])
    pt = sk.add_point(P, uid)
    pt.construction = True
    for k, c in list(sk.cons.items()):
        ends = [_parts(x) for x in c.refs]
        if c.kind == "COINCIDENT" and set(ends) == {(g1.n, a), (g2.n, b)}:
            del sk.cons[k]
            continue
        if c.kind == "TANGENT" and set(ends) == {(g1.n, ""), (g2.n, "")}:
            _drop(sk, [k], said)
            continue
        if (g1.n, a) in ends or (g2.n, b) in ends:
            c.refs = tuple(str(pt.n) if _parts(x) in ((g1.n, a), (g2.n, b)) else x for x in c.refs)
            if len(set(c.refs)) < len(c.refs):
                _drop(sk, [k], said)
    for g, role in ((g1, a), (g2, b)):
        other = "E" if role == "S" else "S"
        for k, c in list(sk.cons.items()):
            if not any(_parts(x) == (g.n, "") for x in c.refs):
                continue
            if g.kind == "LINE" and c.kind == "LENGTH":
                c.kind, c.refs = "DIST", (str(pt.n), f"{g.n}.{other}")
                c.data = {"now": c.data.get("now", c.value)}
            elif g.kind == "LINE" and c.kind in ("HDIST", "VDIST") and len(c.refs) == 1:
                c.refs = (str(pt.n), f"{g.n}.{other}") if other == "E" else (f"{g.n}.{other}", str(pt.n))
            elif _extent_bound(sk, c, g.n):
                _drop(sk, [k], said)
    sk.add_con("ON", (str(pt.n), str(g1.n)), uid=uid, auto=True, solve=False)
    sk.add_con("ON", (str(pt.n), str(g2.n)), uid=uid, auto=True, solve=False)
    return pt


# =============================================================================
# chamfer
# =============================================================================

def chamfer(sk: Sketch, corner: str, d1: float, d2: float | None = None, angle: float | None = None,
            uid: int = 0, args: tuple[int, int] = (-1, -1)) -> tuple[str, Geo]:
    """Cut the corner where two lines meet with a straight line: d1 back
    along the first line and d2 along the second (d2 = d1 when not given),
    or d1 along the first line at ``angle`` degrees to it. The corner stays
    as a construction point; the sizes are dimensions to it.

    ``args`` says where each size is in the command (counted from the end),
    so double-clicking a size edits the right number."""
    if d1 <= 0 or (d2 is not None and d2 <= 0):
        raise SketchError("the chamfer distances must be positive")
    l1, a, l2, b = _corner(sk, corner)
    if l1.kind != "LINE" or l2.kind != "LINE":
        raise SketchError(f"a chamfer goes where two lines meet; {corner} joins a "
                          f"{kname(l1.kind)} and a {kname(l2.kind)} (SFILLET rounds arcs)")
    P = sk.pt(l1.pts[a])
    o1 = sk.pt(l1.pts["E" if a == "S" else "S"])
    o2 = sk.pt(l2.pts["E" if b == "S" else "S"])
    u1, u2 = _unit(_sub(o1, P)), _unit(_sub(o2, P))
    phi = math.acos(max(-1.0, min(1.0, _dot(u1, u2))))
    if phi < 1e-4 or phi > math.pi - 1e-4:
        raise SketchError(f"lines {l1.n} and {l2.n} run on in one line at {corner}; there is no corner to cut")
    if angle is not None:
        th = math.radians(angle)
        rest = math.pi - th - phi
        if not 0 < th < math.pi or rest <= 1e-6:
            raise SketchError(f"angle {_n(angle)} does not make a chamfer here: the corner is "
                              f"{_n(math.degrees(phi))} deg, so the angle must be below {_n(180 - math.degrees(phi))}")
        d2 = d1 * math.sin(th) / math.sin(rest)
    if d2 is None:
        d2 = d1
    len1, len2 = math.dist(P, o1), math.dist(P, o2)
    tol = 1e-9 * sk.extent()
    if d1 >= len1 - tol or d2 >= len2 - tol:
        raise SketchError(f"the chamfer does not fit: lines {l1.n} and {l2.n} are {_n(len1)} and {_n(len2)} long, "
                          f"the chamfer needs {_n(d1)} and {_n(d2)}")
    T1, T2 = _add(P, u1, d1), _add(P, u2, d2)
    said: list[str] = []
    e1, e2 = f"{l1.n}.{a}", f"{l2.n}.{b}"
    pt = _keep_corner(sk, l1, a, l2, b, uid, said)
    _set(sk, l1.pts[a], T1)
    _set(sk, l2.pts[b], T2)
    # the chamfer line runs so that its angle to line 1 reads as the angle asked for
    ch = sk.add_line(T1, T2, uid) if a == "E" else sk.add_line(T2, T1, uid)
    ch.construction = l1.construction and l2.construction
    at1, at2 = ("S", "E") if a == "E" else ("E", "S")
    sk.add_con("COINCIDENT", (e1, f"{ch.n}.{at1}"), uid=uid, auto=True, solve=False)
    sk.add_con("COINCIDENT", (e2, f"{ch.n}.{at2}"), uid=uid, auto=True, solve=False)
    first = sk.add_con("DIST", (str(pt.n), e1), d1, uid=uid, solve=False)
    first.data["arg"] = args[0]
    if angle is not None:
        second = sk.add_con("ANGLE", (str(l1.n), str(ch.n)), angle, uid=uid, solve=False)
    else:
        second = sk.add_con("DIST", (str(pt.n), e2), d2, uid=uid, solve=False)
    second.data["arg"] = args[1]
    sk.solve(blame=first.n)
    size = f"{_n(d1)} at {_n(angle)} deg" if angle is not None else \
        (_n(d1) if abs(d1 - d2) < 1e-12 else f"{_n(d1)} x {_n(d2)}")
    return (f"chamfered the corner of {l1.n} and {l2.n} with line {ch.n}, {size} (C{first.n}, C{second.n}); "
            f"the corner is construction point {pt.n}{_dropped(said)}"), ch


# =============================================================================
# split
# =============================================================================

def _foot(sk: Sketch, g: Geo, q):
    """The point of g's carrier nearest q."""
    if g.kind in ed.ELLIPSES:
        return el.foot(sk, g, q)[0]
    if g.kind == "LINE":
        a, b = sk.pt(g.pts["S"]), sk.pt(g.pts["E"])
        d = _unit(_sub(b, a))
        return _add(a, d, _dot(_sub(q, a), d))
    c, r = sk.pt(g.pts["C"]), sk.radius(g)
    if math.dist(c, q) < 1e-12:
        raise SketchError("that point is at the centre, so it does not say where on the curve")
    return _add(c, _unit(_sub(q, c)), r)


def split(sk: Sketch, n: int, at: list | int | str, uid: int = 0) -> tuple[str, list[Geo]]:
    """Split curve n into pieces: at points (each put on the curve, nearest
    to where it was given) or where curve ``at`` (a number, or H / V) crosses
    it. The pieces stay joined end to end, on one line or circle. A circle
    needs two places or more, and becomes arcs."""
    g = _curve(sk, n, "SSPLIT", ellipse=True)
    was = kname(g.kind)
    span, eps = _span(sk, g), _eps(sk, g)
    cutter = None
    if isinstance(at, (int, str)):
        cutter = at
        if cutter not in ("H", "V"):
            _curve(sk, cutter, "SSPLIT", ellipse=True)
            if cutter == n:
                raise SketchError("a curve cannot be split by itself")
        params = [p for p, _, _ in _cuts(sk, g, only=cutter)]
    else:
        params = [_param(sk, g, _foot(sk, g, q)) for q in at]
    if g.kind in ed.CLOSED:
        inside = sorted({round(p % 360.0, 9) for p in params})
    else:
        inside = sorted({round(p, 12) for p in params if eps < p < span - eps})
    keep = []
    for p in inside:
        if not keep or p - keep[-1] > eps:
            keep.append(p)
    if g.kind in ed.CLOSED and len(keep) > 1 and keep[0] + 360 - keep[-1] <= eps:
        keep.pop()
    if not keep or (g.kind in ed.CLOSED and len(keep) < 2):
        if cutter is not None:
            raise SketchError(f"{cutter} does not cross {kname(g.kind)} {n} "
                              + ("in two places" if g.kind in ed.CLOSED and keep else "on its drawn part"))
        if g.kind in ed.CLOSED:
            raise SketchError(f"a circle is split in two places or more (give two points); circle {n} "
                              "has no ends to split at one")
        raise SketchError(f"that point is at an end of {kname(g.kind)} {n} or beyond it; split it between its ends")
    said: list[str] = []
    pts = [_point_at(sk, g, p) for p in keep]
    made: list[Geo] = []
    if g.kind in ed.CLOSED:
        _drop(sk, [k for k, c in sk.cons.items()
                   if any(_parts(r) == (n, "") for r in c.refs) and c.kind in ("FIX", "OFFSET", "COPY")], said)
        whole = copy.deepcopy(g)  # the full circle or ellipse, to cut the other pieces from
        ed.open_up(sk, g, pts[0], pts[1])
        prev = g
        for i in range(1, len(pts)):
            nxt = ed.piece_of(sk, whole, pts[i], pts[(i + 1) % len(pts)], uid)
            ed.same_carrier(sk, nxt, n, uid)
            sk.add_con("COINCIDENT", (f"{prev.n}.E", f"{nxt.n}.S"), uid=uid, auto=True, solve=False)
            made.append(nxt)
            prev = nxt
        sk.add_con("COINCIDENT", (f"{prev.n}.E", f"{n}.S"), uid=uid, auto=True, solve=False)
        joints = [f"{n}.S"] + [f"{x.n}.S" for x in made]
    else:
        _drop(sk, [k for k, c in sk.cons.items() if _extent_bound(sk, c, n)], said)
        end = sk.pt(g.pts["E"])
        ends = pts[1:] + [end]
        for q0, q1 in zip(pts, ends):
            made.append(ed.piece_of(sk, g, q0, q1, uid))
        _rename(sk, (n, "E"), f"{made[-1].n}.E")
        _set(sk, g.pts["E"], pts[0])
        prev = g
        for piece in made:
            sk.add_con("COINCIDENT", (f"{prev.n}.E", f"{piece.n}.S"), uid=uid, auto=True, solve=False)
            if g.kind == "LINE":  # the pieces stay on one line ...
                sk.add_con("ON", (f"{piece.n}.E", str(n)), uid=uid, auto=True, solve=False)
            else:  # ... or on one circle or ellipse
                ed.same_carrier(sk, piece, n, uid)
            prev = piece
        joints = [f"{x.n}.S" for x in made]
    if cutter is not None:  # the split points stay where the cutting curve crosses
        for j in joints:
            sk.add_con("ON", (j, str(cutter)), uid=uid, auto=True, solve=False)
    sk.solve()
    return (f"split {was} {n} into {len(made) + 1}: {n}, {', '.join(str(x.n) for x in made)}"
            f"{_dropped(said)}"), made


# =============================================================================
# corner: trim or extend two curves so they just meet
# =============================================================================

def _gap(sk: Sketch, g: Geo, q) -> float:
    """How far q is from the drawn curve g."""
    if g.kind == "LINE":
        a, b = sk.pt(g.pts["S"]), sk.pt(g.pts["E"])
        r = _sub(b, a)
        t = max(0.0, min(1.0, _dot(_sub(q, a), r) / (_dot(r, r) or 1e-24)))
        return math.dist(q, _add(a, r, t))
    if g.kind == "POINT":
        return math.dist(q, sk.pt(g.pts["P"]))
    if g.kind == "SPLINE":
        return min(math.dist(q, p) for p in sk.spline_points(g))
    c, r = sk.pt(g.pts["C"]), sk.radius(g)
    if g.kind == "ARC" and _param(sk, g, q) > _span(sk, g):
        return min(math.dist(q, sk.pt(g.pts[e])) for e in ("S", "E"))
    return abs(math.dist(c, q) - r)


def _end_to_move(sk: Sketch, g: Geo, q, pick) -> str:
    """Which end of g goes to q: the side of q away from ``pick`` (the part
    clicked is kept), else the nearer end."""
    if pick is not None:
        if g.kind == "LINE":
            return "S" if _param(sk, g, pick) > _param(sk, g, q) else "E"
        span, tq = _span(sk, g), _param(sk, g, q)
        if tq <= span:
            tp = _param(sk, g, pick)
            if tp > span:  # clicked off the arc: the nearer end's side
                tp = span if tp - span < 360 - tp else 0.0
            return "S" if tp > tq else "E"
        return "E" if tq - span < 360 - tq else "S"
    ends = {r: sk.pt(g.pts[r]) for r in ("S", "E")}
    return min(ends, key=lambda r: math.dist(ends[r], q))


def corner(sk: Sketch, n1: int, n2: int, picks=None, uid: int = 0) -> str:
    """Trim or extend lines or arcs n1 and n2 so that they just meet, with
    an end of each at their crossing. ``picks`` (a point on each) says which
    part of each to keep; without them the end nearer the crossing moves."""
    if n1 == n2:
        raise SketchError("give two different curves")
    g1, g2 = _curve(sk, n1, "SCORNER"), _curve(sk, n2, "SCORNER")
    for g in (g1, g2):
        if g.kind in ed.CLOSED:
            raise SketchError(f"{g.n} is a circle, which has no ends to bring to a corner (STRIM it first)")
    hits = _carrier_hits(sk, g1, g2)
    if not hits:
        what = "they are parallel" if g1.kind == g2.kind == "LINE" else "their lines and circles never cross"
        raise SketchError(f"{kname(g1.kind)} {n1} and {kname(g2.kind)} {n2} never meet: {what}")
    p1, p2 = (picks or (None, None))
    best = None
    for q in hits:
        r1, r2 = _end_to_move(sk, g1, q, p1), _end_to_move(sk, g2, q, p2)
        cost = math.dist(sk.pt(g1.pts[r1]), q) + math.dist(sk.pt(g2.pts[r2]), q)
        if picks is not None:  # a crossing near what was clicked wins
            cost += 0.25 * (math.dist(p1, q) + math.dist(p2, q))
        if best is None or cost < best[0]:
            best = (cost, q, r1, r2)
    _, q, r1, r2 = best
    tol = 1e-7 * sk.extent()
    for g, r in ((g1, r1), (g2, r2)):
        other = sk.pt(g.pts["E" if r == "S" else "S"])
        if math.dist(other, q) <= tol:
            raise SketchError(f"the corner is at the other end of {kname(g.kind)} {g.n}, so nothing of it would be left")
    said: list[str] = []
    moved = []
    for g, r in ((g1, r1), (g2, r2)):
        if math.dist(sk.pt(g.pts[r]), q) > tol:
            _free_end(sk, g.n, r, said)
            _set(sk, g.pts[r], q)
            moved.append(f"{g.n}.{r}")
    joined = any(c.kind == "COINCIDENT" and {_parts(x) for x in c.refs} == {(n1, r1), (n2, r2)}
                 for c in sk.cons.values())
    if not joined:
        sk.add_con("COINCIDENT", (f"{n1}.{r1}", f"{n2}.{r2}"), uid=uid, auto=True, solve=False)
    sk.solve()
    how = f" (moved {', '.join(moved)})" if moved else " (they already met there)"
    return f"brought {kname(g1.kind)} {n1} and {kname(g2.kind)} {n2} to a corner at {n1}.{r1}{how}{_dropped(said)}"


# =============================================================================
# trim many (the power trim)
# =============================================================================

def trim_many(sk: Sketch, picks: list[tuple[int, tuple[float, float]]], uid: int = 0, axes: bool = False) -> str:
    """Trim one piece per pick, in order. A curve cut in the middle by an
    earlier pick lives on as two curves; a later pick on it goes to the one
    under its point."""
    family: dict[int, list[int]] = {}
    out = []
    for n, at in picks:
        cands = [m for m in family.get(n, [n]) if m in sk.geos]
        if not cands:
            out.append(f"{n} was already gone")
            continue
        m = min(cands, key=lambda k: _gap(sk, sk.geos[k], at))
        before = set(sk.geos)
        out.append(trim(sk, m, at, uid, axes))
        family.setdefault(n, [n]).extend(sorted(set(sk.geos) - before))
    return "; ".join(out)


# =============================================================================
# move, rotate, scale, copy
# =============================================================================

_SIZES = ("DIST", "HDIST", "VDIST", "LENGTH", "RADIUS", "DIAMETER", "MAJOR", "MINOR", "ARCLEN")


def _mapping(kind: str, values, sk: Sketch):
    """The point map for MOVE (du, dv), ROTATE (angle, centre) or SCALE
    (factor, centre), and a few words for the message."""
    if kind == "MOVE":
        du, dv = values
        return (lambda q: (q[0] + du, q[1] + dv)), f"moved by {_n(du)}, {_n(dv)}"
    amount, centre = values
    (cu, cv), _ = sk.point_value(centre)
    if kind == "ROTATE":
        a = math.radians(amount)
        ca, sa = math.cos(a), math.sin(a)
        return (lambda q: (cu + (q[0] - cu) * ca - (q[1] - cv) * sa,
                           cv + (q[0] - cu) * sa + (q[1] - cv) * ca)), f"turned {_n(amount)} deg"
    if amount <= 0:
        raise SketchError("the scale factor must be positive")
    return (lambda q: (cu + (q[0] - cu) * amount, cv + (q[1] - cv) * amount)), f"scaled by {_n(amount)}"


def _quarter(angle: float) -> int | None:
    """0, 1, 2, 3 for a turn by a whole number of quarter turns, else None."""
    q = angle / 90.0
    return int(round(q)) % 4 if abs(q - round(q)) < 1e-9 else None


def _kept_kind(c, kind: str, amount) -> str | None:
    """The kind constraint c has after the move (None: it no longer holds)."""
    k = c.kind
    if kind == "ROTATE":
        q = _quarter(amount)
        if k in ("HORIZONTAL", "VERTICAL") and len(c.refs) <= 2:
            if q is None:
                return None
            return k if q % 2 == 0 else ("VERTICAL" if k == "HORIZONTAL" else "HORIZONTAL")
        if k in ("HDIST", "VDIST"):
            if q is None:
                return None
            return k if q % 2 == 0 else ("VDIST" if k == "HDIST" else "HDIST")
        if k == "ANGLE" and len(c.refs) == 1:
            return None if q is None or q % 2 else k
        if k == "COPY":
            return None
    if kind == "SCALE" and k == "COPY":
        return None
    if k == "FIX":
        return k  # its position is taken again where the geometry now is
    return k


def transform(sk: Sketch, kind: str, values, names: list, copy: bool = False, uid: int = 0) -> tuple[str, list[Geo]]:
    """Move, rotate or scale sketch geometry (kind MOVE, ROTATE or SCALE),
    or a copy of it. Constraints among the geometry go with it (a turn by a
    quarter swaps horizontal and vertical; a scale scales the sizes);
    constraints that tie it to the rest of the sketch are dropped when it
    moves, and are not copied."""
    kind = kind.upper()
    if kind not in ("MOVE", "ROTATE", "SCALE"):
        raise SketchError("the kind is MOVE, ROTATE or SCALE")
    f, how = _mapping(kind, values, sk)
    amount = values[0]
    geos = _geos(sk, names, "STRANSFORM")
    inside = {g.n for g in geos}

    def internal(c) -> bool:
        ns = []
        for r in c.refs:
            t = r.strip().upper()
            if t in ("O", "ORIGIN", "H", "V"):
                return False
            ns.append(_geo_of(r))
        return all(x in inside for x in ns)

    said: list[str] = []
    if copy:
        made = []
        to: dict[int, int] = {}
        for g in geos:
            new = _copy_geo(sk, g, f, uid, flip=False)
            if kind == "SCALE" and new.r is not None:
                sk.x[new.r] *= amount
            to[g.n] = new.n
            made.append(new)
        skipped = 0
        for c in list(sk.cons.values()):
            if not internal(c):
                continue
            k = _kept_kind(c, kind, amount)
            if k is None or c.kind in ("OFFSET", "COPY"):
                skipped += not c.auto
                continue

            def moved(r):
                n0, role = _parts(r)
                return f"{to[n0]}.{role}" if role else str(to[n0])
            value = c.value
            if value is not None and kind == "SCALE" and c.kind in _SIZES:
                value *= amount
            sk.add_con(k, tuple(moved(r) for r in c.refs), value, uid=uid, auto=c.auto, solve=False)
        sk.solve()
        note = f" ({skipped} constraint{'s' if skipped != 1 else ''} could not go with the copy)" if skipped else ""
        shown = f"{made[0].n}..{made[-1].n}" if len(made) > 3 else ", ".join(str(g.n) for g in made)
        return f"copied {', '.join(str(g.n) for g in geos)}, {how}: {shown}{note}", made
    # in place: what ties the geometry to the rest lets go first
    touching = [k for k, c in sk.cons.items() if any(_geo_of(r) in inside for r in c.refs) and not internal(c)]
    _drop(sk, touching, said)
    for k, c in list(sk.cons.items()):
        if not internal(c):
            continue
        nk = _kept_kind(c, kind, amount)
        if nk is None:
            _drop(sk, [k], said)
            continue
        c.kind = nk
        if kind == "SCALE" and c.value is not None and c.kind in _SIZES:
            c.value *= amount
        if c.kind == "OFFSET" and kind == "SCALE":
            c.value *= amount
    idx = sorted({i for g in geos for i in g.pts.values()})
    for i in idx:
        _set(sk, i, f(sk.pt(i)))
    if kind == "SCALE":
        for g in geos:
            if g.r is not None:
                sk.x[g.r] *= amount
    for c in sk.cons.values():  # a FIX holds where the geometry is now; sides are read again
        if internal(c) and (c.kind == "FIX" or c.kind in ("HDIST", "VDIST", "ANGLE", "DIST", "TANGENT")):
            keep = dict(c.data)
            c.data = {}
            _sk._choose_sides(sk, c, [sk.ref(r) for r in c.refs])
            for extra in ("arg",):
                if extra in keep:
                    c.data[extra] = keep[extra]
    sk.solve()
    return f"{how}: {', '.join(str(g.n) for g in geos)}{_dropped(said)}", geos


__all__ = ["CORNER", "chamfer", "split", "corner", "trim_many", "transform", "offset_both"]


# =============================================================================
# offset to both sides, with closed ends
# =============================================================================

def offset_both(sk: Sketch, d: float, names: list, flat: bool = False, uid: int = 0) -> tuple[str, list[Geo]]:
    """Offset curves by d to both sides. An open chain gets its two offsets
    joined at each end by a half circle round the chain's end (or a straight
    line with ``flat``), so the result is one closed outline: a slot along a
    path. A closed chain gets an outline inside and one outside. The
    curves offset become construction geometry (the middle of the outline)."""
    if d <= 0:
        raise SketchError("the distance must be positive (it goes to both sides)")
    geos = []
    for t in names:
        g = _curve(sk, ed._num(t), "SOFFSET2")
        if g not in geos:
            geos.append(g)
    if not geos:
        raise SketchError("give the curves to offset")
    made: list[Geo] = []
    for chain, closed in ed._chains(sk, geos):
        left = ed._offset_chain(sk, chain, closed, d, uid)
        right = ed._offset_chain(sk, chain, closed, -d, uid)
        made += left + right
        for pc in chain:  # the path is the middle of the outline now
            pc.g.construction = True
        if closed:
            continue
        first, last = chain[0], chain[-1]
        for pc, role, inward in ((first, "S" if first.fwd else "E", True),
                                 (last, "E" if last.fwd else "S", False)):
            P = sk.pt(pc.g.pts[role])
            t = ed._tangent(sk, pc.g, P, pc.fwd)
            if not inward:
                t = (-t[0], -t[1])  # into the chain from this end
            e1, e2 = _nearest_end(sk, left, P), _nearest_end(sk, right, P)
            if flat:
                cap = sk.add_line(e1, e2, uid)
            else:
                mid = (P[0] - t[0] * d, P[1] - t[1] * d)
                cap = sk.add_arc_3p(e1, mid, e2, uid)
                sk.add_con("COINCIDENT", (f"{cap.n}.C", f"{pc.g.n}.{role}"), uid=uid, auto=True, solve=False)
            made.append(cap)
    sk.solve()
    shown = f"{made[0].n}..{made[-1].n}" if len(made) > 3 else ", ".join(str(g.n) for g in made)
    return f"offset {', '.join(str(g.n) for g in geos)} by {_n(d)} to both sides: {shown}", made


def _nearest_end(sk: Sketch, geos: list[Geo], P) -> str:
    """The name of the end of these curves nearest P."""
    best = min(((math.dist(sk.pt(g.pts[r]), P), f"{g.n}.{r}") for g in geos for r in ("S", "E") if r in g.pts))
    return best[1]
