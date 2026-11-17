"""Editing sketch splines: trim, extend, split, and join curves into one
spline (or turn one curve into a spline).

The pieces of a cut spline keep the points the spline ran through (with
their constraints) and gain the cut point; see spline.pieces.
"""

from __future__ import annotations

import math

from . import edit as ed
from . import spline as sp
from .sketch import kname, Geo, Sketch, SketchError


def _remap(sk: Sketch, n: int, moved: dict[str, str], said: list[str], cut_ends: tuple[str, ...] = ()) -> None:
    """Constraints on spline n's points follow them to where they went
    (``moved``: old role -> "m.role"); constraints on points that went
    are dropped, and so is what held n's extent or a cut end's direction."""
    drop = []
    for k, c in sk.cons.items():
        refs, bad = [], False
        for r in c.refs:
            m, role = ed._parts(r)
            if m == n and role:
                if role in moved:
                    refs.append(moved[role])
                else:
                    bad = True
            else:
                refs.append(r)
        whole = any(ed._parts(r) == (n, "") for r in c.refs)
        if whole and (ed._extent_bound(sk, c, n) or (c.kind == "TANGENT" and c.data.get("end") in cut_ends)):
            bad = True
        if bad:
            drop.append(k)
        else:
            c.refs = tuple(refs)
    ed._drop(sk, drop, said)


def trim(sk: Sketch, g: Geo, lo: float, hi: float, h_lo, h_hi, uid: int = 0) -> str:
    """Remove the piece of spline g from position lo to hi (between the
    curves h_lo and h_hi; None at a free end)."""
    n, said = g.n, []
    if g.closed:
        a, b = hi, lo
        if b <= a:
            b += 360.0
        made, moved, _ = sp.pieces(sk, g, [(a, b)], uid)
        _remap(sk, n, moved, said, ("S", "E"))
        sk.add_con("ON", (f"{n}.S", str(h_hi)), uid=uid, auto=True, solve=False)
        sk.add_con("ON", (f"{n}.E", str(h_lo)), uid=uid, auto=True, solve=False)
        sk.solve()
        return f"trimmed closed spline {n} to an open one between {h_hi} and {h_lo}{ed._dropped(said)}"
    ranges = []
    if h_lo is not None:
        ranges.append((0.0, lo))
    if h_hi is not None:
        ranges.append((hi, 1.0))
    cut = ("E",) if h_hi is None else ("S",) if h_lo is None else ("S", "E")
    made, moved, _ = sp.pieces(sk, g, ranges, uid)
    _remap(sk, n, moved, said, cut)
    first = made[0]
    if h_lo is not None:
        sk.add_con("ON", (f"{first.n}.E", str(h_lo)), uid=uid, auto=True, solve=False)
    if h_hi is not None:
        sk.add_con("ON", (f"{made[-1].n}.S", str(h_hi)), uid=uid, auto=True, solve=False)
    sk.solve()
    if len(made) == 2:
        what = f"cut spline {n} between {h_lo} and {h_hi}: {n} and {made[1].n} are left"
    else:
        what = f"trimmed spline {n} back to {h_lo if h_lo is not None else h_hi}"
    return what + ed._dropped(said)


def extend(sk: Sketch, g: Geo, role: str, to=None, uid: int = 0) -> str:
    """Make spline g longer at its end ``role``, going on the way it leaves
    that end, until it meets the next curve (or curve or axis ``to``). The
    old end stays as a point the spline runs through."""
    from OCP.Geom2d import Geom2d_Line, Geom2d_TrimmedCurve
    from OCP.gp import gp_Dir2d, gp_Pnt2d

    n = g.n
    size = 10.0 * sk.extent()
    P = sk.pt(g.pts[role])
    d = sp.tangent(sk, g, 1.0 if role == "E" else 0.0)
    if role == "S":
        d = (-d[0], -d[1])
    ray = Geom2d_TrimmedCurve(Geom2d_Line(gp_Pnt2d(*P), gp_Dir2d(*d)), 0.0, size)
    tol = 1e-6 * sk.extent()
    best = None
    for h in sk.geos.values():
        if h.n == n or h.kind not in ed.CURVES or (to is not None and h.n != to):
            continue
        for q in sp.crossings(ray, sp.geom2d(sk, h, size), size):
            if to is None and not ed._within(sk, h, q):
                continue
            dist = math.dist(P, q)
            if dist > tol and (best is None or dist < best[0]):
                best = (dist, h.n, q)
    for name in ed.AXES:
        if to == name:
            for q in sp.crossings(ray, sp.axis_curve(name, size), size):
                dist = math.dist(P, q)
                if dist > tol and (best is None or dist < best[0]):
                    best = (dist, name, q)
    if best is None:
        whom = (f"axis {to}" if to in ed.AXES else f"curve {to}") if to is not None else "any curve"
        raise SketchError(f"going on from {n}.{role}, spline {n} never meets {whom}")
    _, h, q = best
    roles = _roles(g)
    idx = [g.pts[r] for r in roles]
    new = sk._new_point(*q)
    idx = idx + [new] if role == "E" else [new] + idx
    new_roles = ["S"] + [f"K{i}" for i in range(1, len(idx) - 1)] + ["E"]
    old = roles if role == "E" else [None] + roles
    moved = {o: f"{n}.{r}" for o, r in zip(old, new_roles) if o is not None}
    g.pts = dict(zip(new_roles, idx))
    said: list[str] = []
    _remap(sk, n, moved, said, (role,))
    sk.add_con("ON", (f"{n}.{role}", str(h)), uid=uid, auto=True, solve=False)
    sk.solve()
    return f"extended spline {n} at {role} to {h}{ed._dropped(said)}"


def _roles(g: Geo) -> list[str]:
    return sorted(g.pts, key=lambda r: (r == "E", 0 if r == "S" else int(r[1:]) if r[0] == "K" else 0))


def split(sk: Sketch, g: Geo, at, uid: int = 0) -> tuple[str, list[Geo]]:
    """Split spline g at points (each put on the spline nearest where it was
    given) or where curve ``at`` (a number, or H / V) crosses it. The pieces
    meet end to end (they are not held smooth where they meet). A closed
    spline split at one place opens there."""
    n = g.n
    eps = ed._eps(sk, g)
    cutter = None
    if isinstance(at, (int, str)):
        cutter = at
        params = [p for p, _, _ in ed._cuts(sk, g, only=cutter)]
    else:
        params = [sp.param(sk, g, q) for q in at]
    if g.closed:
        inside = sorted({round(p % 360.0, 9) for p in params})
    else:
        inside = sorted({round(p, 12) for p in params if eps < p < 1 - eps})
    keep: list[float] = []
    for p in inside:
        if not keep or p - keep[-1] > eps:
            keep.append(p)
    if g.closed and len(keep) > 1 and keep[0] + 360 - keep[-1] <= eps:
        keep.pop()
    if not keep:
        if cutter is not None:
            raise SketchError(f"{cutter} does not cross spline {n}")
        raise SketchError(f"that point is at an end of spline {n} or beyond it; split it between its ends")
    if g.closed:
        ranges = [(keep[i], keep[i + 1]) for i in range(len(keep) - 1)] + [(keep[-1], keep[0] + 360.0)]
    else:
        cuts = [0.0] + keep + [1.0]
        ranges = [(cuts[i], cuts[i + 1]) for i in range(len(cuts) - 1)]
    was_closed = g.closed
    said: list[str] = []
    made, moved, _ = sp.pieces(sk, g, ranges, uid)
    _remap(sk, n, moved, said, ("S", "E") if was_closed else ())
    for a, b in zip(made, made[1:]):
        sk.add_con("COINCIDENT", (f"{a.n}.E", f"{b.n}.S"), uid=uid, auto=True, solve=False)
    if was_closed and len(made) > 1:
        sk.add_con("COINCIDENT", (f"{made[-1].n}.E", f"{made[0].n}.S"), uid=uid, auto=True, solve=False)
    if cutter is not None:
        joints = [f"{x.n}.S" for x in made[1:]] + ([f"{made[0].n}.S", f"{made[0].n}.E"] if was_closed and len(made) == 1
                                                    else [f"{made[0].n}.S"] if was_closed else [])
        for j in joints:
            sk.add_con("ON", (j, str(cutter)), uid=uid, auto=True, solve=False)
    sk.solve()
    if was_closed and len(made) == 1:
        return f"opened closed spline {n} at the cut{ed._dropped(said)}", []
    return (f"split spline {n} into {len(made)}: {', '.join(str(x.n) for x in made)}"
            f"{ed._dropped(said)}"), made[1:]


# =============================================================================
# join curves into one spline
# =============================================================================

def _samples(sk: Sketch, g: Geo, fwd: bool, lone: bool) -> list[tuple[float, float]]:
    """Points a spline through which follows g closely, in walking order."""
    if g.kind == "SPLINE":
        pts = sk.spline_points(g)
        if g.closed:
            pts = pts + [pts[0]]
    elif g.kind == "LINE":
        a, b = sk.pt(g.pts["S"]), sk.pt(g.pts["E"])
        pts = [a, b] if lone else [a, ed._add(a, ed._sub(b, a), 1 / 3), ed._add(a, ed._sub(b, a), 2 / 3), b]
    else:
        span = ed._span(sk, g)
        steps = max(2, math.ceil(span / 30.0))
        pts = [ed._point_at(sk, g, span * i / steps) for i in range(steps + 1)]
        if g.kind in ed.CLOSED:
            pts[-1] = pts[0]
    return pts if fwd else pts[::-1]


def join(sk: Sketch, names: list, uid: int = 0) -> tuple[str, Geo]:
    """Join curves that meet end to end into one smooth spline (corners
    where they meet are rounded off), or turn one line, arc, circle or
    ellipse into a spline. Sizes and constraints on the old curves go,
    except those on the two free ends of the chain, which move to the
    spline's ends."""
    if not names:
        raise SketchError("give the curves to join, e.g. 3, 4, 5")
    geos = []
    for nm in names:
        n = ed._num(nm)
        g = ed._curve(sk, n, "SJOIN", ellipse=True, spline=True)
        if g in geos:
            raise SketchError(f"{n} is given twice")
        geos.append(g)
    if len(geos) == 1:
        g = geos[0]
        if g.kind == "SPLINE":
            raise SketchError(f"{g.n} is a spline already")
        closed = ed.is_closed(g)
        pts = _samples(sk, g, True, True)
        chain_ends = [] if closed else [(g.n, "S"), (g.n, "E")]
    else:
        for g in geos:
            if ed.is_closed(g):
                raise SketchError(f"{kname(g.kind)} {g.n} is closed, so it has no ends to join at")
        chains = ed._chains(sk, geos)
        if len(chains) != 1:
            groups = "; ".join(", ".join(str(p.g.n) for p in ch) for ch, _ in chains)
            raise SketchError(f"these curves do not join end to end into one chain (they make {len(chains)}: "
                              f"{groups}); join one chain at a time")
        chain, closed = chains[0]
        pts = []
        for pc in chain:
            more = _samples(sk, pc.g, pc.fwd, False)
            pts += more if not pts else more[1:]
        first, last = chain[0], chain[-1]
        chain_ends = [] if closed else [(first.g.n, "S" if first.fwd else "E"), (last.g.n, "E" if last.fwd else "S")]
    if closed and math.dist(pts[0], pts[-1]) <= 1e-9 * max(1.0, sk.extent()):
        pts = pts[:-1]
    clean = [pts[0]]
    for q in pts[1:]:
        if math.dist(q, clean[-1]) > 1e-9 * max(1.0, sk.extent()):
            clean.append(q)
    construction = all(g.construction for g in geos)
    new = sk.add_spline(clean, closed, uid, construction)
    old = {g.n for g in geos}
    rename = {}
    if chain_ends:
        rename[chain_ends[0]] = f"{new.n}.S"
        rename[chain_ends[1]] = f"{new.n}.E"
    said: list[str] = []
    drop = []
    for k, c in sk.cons.items():
        refs, bad, inner = [], False, True
        for r in c.refs:
            m, role = ed._parts(r)
            if m in old:
                if (m, role) in rename:
                    refs.append(rename[(m, role)])
                    inner = False
                else:
                    bad = True
            else:
                refs.append(r)
                inner = False
        if bad:
            if inner and c.kind == "COINCIDENT":  # a join inside the chain: the spline runs through it
                drop.append(k)
                c.auto = True
            else:
                drop.append(k)
        elif len(set(refs)) < len(refs):
            drop.append(k)
        else:
            c.refs = tuple(refs)
    ed._drop(sk, drop, said)
    for g in geos:
        sk.geos.pop(g.n, None)
    sk.solve()
    what = ", ".join(f"{kname(g.kind)} {g.n}" for g in geos)
    verb = "made" if len(geos) == 1 else "joined"
    tail = f" ({len(clean)} points{', closed' if closed else ''})"
    return (f"{verb} spline {new.n} from {what}{tail}" if verb == "made"
            else f"joined {what} into spline {new.n}{tail}") + ed._dropped(said), new

