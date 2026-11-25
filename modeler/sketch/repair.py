"""Repairing imported curves (PLAN item 104): what SREPAIR does to a sketch.

Drawings read from DXF, SVG or a traced picture often have ends that almost meet, the same
curve twice, specks a fraction of a millimetre long, and smooth outlines cut into dozens of
short straight pieces. :func:`repair` fixes them in this order:

1. curves drawn twice: one goes;
2. tiny lines and arcs (shorter than ``tiny``): they go, and their neighbours meet instead;
3. gaps: two loose ends closer than ``gap`` meet in the middle and are tied (COINCIDENT);
4. chains of short lines that turn gently (at least ``MIN_CHAIN`` of them, each shorter than
   ``refit`` and turning less than ``TURN`` degrees at each joint) become one spline through their
   points, tied to whatever the chain's ends were tied to.

:func:`survey` says what it would do without changing anything (SCHECK uses it).
"""

from __future__ import annotations

import math
from typing import Any

from .sketch import Sketch, SketchError

MIN_CHAIN = 6  # lines in a chain before it becomes a spline
TURN = 35.0  # degrees: a sharper joint is a corner, kept
MAX_SPLINE_POINTS = 60  # a longer chain is thinned to this many points
ENDED = ("LINE", "ARC", "SPLINE", "EARC")


def defaults(sk: Sketch) -> tuple[float, float, float]:
    """(gap, tiny, refit) for a sketch of this size: 0.2 %, 0.05 % and 10 % of its extent."""
    size = max(sk.extent(), 1e-9)
    return 2e-3 * size, 5e-4 * size, 0.1 * size


class _Groups:
    """Which point indices are tied together (COINCIDENT), as a union-find."""

    def __init__(self, sk: Sketch):
        self.up: dict[int, int] = {}
        for c in sk.cons.values():
            if c.kind != "COINCIDENT":
                continue
            try:
                pts = [sk.ref(r).point for r in c.refs]
            except SketchError:
                continue
            if len(pts) == 2 and None not in pts:
                self.join(pts[0], pts[1])

    def find(self, i: int) -> int:
        while self.up.get(i, i) != i:
            self.up[i] = self.up.get(self.up[i], self.up[i])
            i = self.up[i]
        return i

    def join(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.up[ra] = rb


def _ends(sk: Sketch) -> list[tuple[int, str, int]]:
    """(geometry, S or E, point index) for every end of a drawn (not construction) open curve."""
    out = []
    for g in sk.geos.values():
        if g.construction or g.kind not in ENDED or g.closed:
            continue
        for role in ("S", "E"):
            if role in g.pts:
                out.append((g.n, role, g.pts[role]))
    return out


def _drop(sk: Sketch, n: int) -> None:
    """Take a curve out with the constraints on it (no solve: the caller solves once)."""
    from .sketch import _geo_of

    sk.geos.pop(n, None)
    for k in [k for k, c in sk.cons.items() if any(_geo_of(x) == n for x in c.refs)]:
        del sk.cons[k]


def _duplicates(sk: Sketch) -> list[int]:
    size = max(sk.extent(), 1.0)
    seen: dict[tuple, int] = {}
    out = []
    for g in sk.geos.values():
        pts = sorted((round(sk.pt(i)[0] / size, 7), round(sk.pt(i)[1] / size, 7)) for i in g.pts.values())
        r = round(sk.x[g.r] / size, 7) if g.r is not None else None
        k = (g.kind, tuple(pts), r, g.construction)
        if k in seen:
            out.append(g.n)
        else:
            seen[k] = g.n
    return out


def _length(sk: Sketch, g) -> float:
    if g.kind == "LINE":
        return math.dist(sk.pt(g.pts["S"]), sk.pt(g.pts["E"]))
    if g.kind == "ARC":
        from .sketch import arc_length

        return arc_length(sk, g)
    if g.kind == "CIRCLE":
        return 2 * math.pi * sk.radius(g)
    return math.inf


def _tiny(sk: Sketch, tiny: float) -> list[int]:
    return [g.n for g in sk.geos.values() if g.kind in ("LINE", "ARC", "CIRCLE") and _length(sk, g) < tiny]


def _loose(sk: Sketch, groups: _Groups) -> list[tuple[int, str, int]]:
    """Ends tied to no other end (nor to a point on another curve)."""
    count: dict[int, int] = {}
    ends = _ends(sk)
    for _, _, i in ends:
        r = groups.find(i)
        count[r] = count.get(r, 0) + 1
    tied_elsewhere = set()
    for c in sk.cons.values():  # an end held on a curve or a point is not loose either
        if c.kind in ("ON", "MIDPOINT", "SYMMETRIC") or c.kind == "COINCIDENT":
            for r in c.refs:
                try:
                    p = sk.ref(r).point
                except SketchError:
                    continue
                if p is not None and c.kind != "COINCIDENT":
                    tied_elsewhere.add(p)
    return [e for e in ends if count[groups.find(e[2])] == 1 and e[2] not in tied_elsewhere]


def _gaps(sk: Sketch, gap: float) -> list[tuple[tuple[int, str, int], tuple[int, str, int], float]]:
    """Pairs of loose ends closer than ``gap``, nearest first, each end used once."""
    groups = _Groups(sk)
    loose = _loose(sk, groups)
    pairs = []
    for i, a in enumerate(loose):
        pa = sk.pt(a[2])
        for b in loose[i + 1:]:
            if a[0] == b[0] and sk.geos[a[0]].kind == "LINE":
                continue  # a line's own two ends: that would make it a point
            d = math.dist(pa, sk.pt(b[2]))
            if d <= gap:
                pairs.append((d, a, b))
    pairs.sort(key=lambda t: t[0])
    used: set[int] = set()
    out = []
    for d, a, b in pairs:
        if a[2] in used or b[2] in used:
            continue
        used |= {a[2], b[2]}
        out.append((a, b, d))
    return out


def _turn(d1, d2) -> float:
    c = (d1[0] * d2[0] + d1[1] * d2[1]) / max(1e-30, math.hypot(*d1) * math.hypot(*d2))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def _chains(sk: Sketch, refit: float) -> list[tuple[list[tuple[float, float]], bool, list[int], list, list]]:
    """Chains of short lines meeting two at a time at gentle joints:
    (points, closed, line numbers, what the first end is tied to, what the last end is tied to)."""
    groups = _Groups(sk)
    short = {g.n: g for g in sk.geos.values() if g.kind == "LINE" and not g.construction
             and _length(sk, g) <= refit}
    # every end, by its group
    members: dict[int, list[tuple[int, str]]] = {}
    for n, role, i in _ends(sk):
        members.setdefault(groups.find(i), []).append((n, role))
    # points tied to something that is not a curve end (a POINT, or a curve's middle) count as more
    extra: dict[int, int] = {}
    for c in sk.cons.values():
        if c.kind != "COINCIDENT":
            continue
        for r in c.refs:
            try:
                ref = sk.ref(r)
            except SketchError:
                continue
            if ref.point is not None and not any(ref.point == g.pts.get(x) for g in sk.geos.values()
                                                 if g.kind in ENDED for x in ("S", "E")):
                extra[groups.find(ref.point)] = 1

    def other(n: int, role: str):
        """The line that meets line n at its end ``role``, when exactly one does, smoothly."""
        g = short[n]
        grp = groups.find(g.pts[role])
        ms = members.get(grp, [])
        if len(ms) != 2 or extra.get(grp):
            return None
        m, mrole = ms[0] if ms[1] == (n, role) else ms[1]
        if m not in short or m == n:
            return None
        # the turn at the joint
        a, b = sk.pt(g.pts["S"]), sk.pt(g.pts["E"])
        d1 = (b[0] - a[0], b[1] - a[1]) if role == "E" else (a[0] - b[0], a[1] - b[1])
        h = short[m]
        c, d = sk.pt(h.pts["S"]), sk.pt(h.pts["E"])
        d2 = (d[0] - c[0], d[1] - c[1]) if mrole == "S" else (c[0] - d[0], c[1] - d[1])
        if _turn(d1, d2) > TURN:
            return None
        return m, ("E" if mrole == "S" else "S")

    seen: set[int] = set()
    out = []
    for start in list(short):
        if start in seen:
            continue
        # walk back to one end of the chain
        n, role = start, "S"
        steps = 0
        while True:
            nxt = other(n, role)
            if nxt is None or nxt[0] == start or steps > len(short):
                break
            n, role = nxt[0], ("S" if nxt[1] == "E" else "E")  # the far end of the next line
            steps += 1
        # n's end ``role`` is the chain's start; walk forward from the other end
        first_end = (n, role)
        out_role = "E" if role == "S" else "S"
        lines = [n]
        pts = [sk.pt(short[n].pts[role]), sk.pt(short[n].pts[out_role])]
        closed = False
        cur, cur_out = n, out_role
        while True:
            nxt = other(cur, cur_out)
            if nxt is None:
                break
            m, m_out = nxt
            if m == lines[0]:
                closed = True
                break
            if m in lines:
                break
            lines.append(m)
            pts.append(sk.pt(short[m].pts[m_out]))
            cur, cur_out = m, m_out
        seen.update(lines)
        if len(lines) < MIN_CHAIN:
            continue
        if closed:
            pts = pts[:-1]
        last_end = (cur, cur_out)
        ties = []
        for gn, rl in (first_end, last_end):
            grp = groups.find(short[gn].pts[rl])
            ties.append([f"{a}.{r}" for a, r in members.get(grp, []) if a not in lines])
        out.append((pts, closed, lines, ties[0], ties[1]))
    return out


def _thin(pts: list, keep: int) -> list:
    if len(pts) <= keep:
        return pts
    step = (len(pts) - 1) / (keep - 1)
    return [pts[round(i * step)] for i in range(keep)]


def survey(sk: Sketch, gap: float = 0.0, tiny: float = 0.0, refit: float = 0.0) -> dict[str, Any]:
    """What :func:`repair` would do, on a copy."""
    work = sk.copy()
    return repair(work, gap, tiny, refit, solve=False)


def repair(sk: Sketch, gap: float = 0.0, tiny: float = 0.0, refit: float | None = 0.0, uid: int = 0,
           solve: bool = True) -> dict[str, Any]:
    """Repair the sketch in place; returns what was done. 0 sizes take :func:`defaults`;
    ``refit`` None leaves short lines as they are."""
    g0, t0, r0 = defaults(sk)
    gap = gap or g0
    tiny = tiny or t0
    if refit is not None:
        refit = refit or r0
    rep: dict[str, Any] = {"gap": gap, "tiny": tiny, "refit": refit, "duplicates": [], "tiny_removed": [],
                           "gaps_closed": 0, "largest_gap": 0.0, "splines": [], "lines_refit": 0}
    for n in _duplicates(sk):
        _drop(sk, n)
        rep["duplicates"].append(n)
    for n in _tiny(sk, tiny):
        _drop(sk, n)
        rep["tiny_removed"].append(n)
    # gaps, including the ones the tiny pieces left (they are smaller than a gap)
    for a, b, d in _gaps(sk, max(gap, tiny * 1.01)):
        pa, pb = sk.pt(a[2]), sk.pt(b[2])
        mid = ((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)
        for i in (a[2], b[2]):
            sk.x[i], sk.x[i + 1] = mid
        sk.add_con("COINCIDENT", (f"{a[0]}.{a[1]}", f"{b[0]}.{b[1]}"), uid=uid, solve=False)
        rep["gaps_closed"] += 1
        rep["largest_gap"] = max(rep["largest_gap"], d)
    if refit is not None:
        for pts, closed, lines, tie_s, tie_e in _chains(sk, refit):
            for n in lines:
                _drop(sk, n)
            pts = _thin(pts, MAX_SPLINE_POINTS)
            if (len(pts) < 3 and closed) or len(pts) < 2:
                continue
            g = sk.add_spline(pts, closed, uid)
            if not closed:
                if tie_s:
                    sk.add_con("COINCIDENT", (f"{g.n}.S", tie_s[0]), uid=uid, solve=False)
                if tie_e:
                    sk.add_con("COINCIDENT", (f"{g.n}.E", tie_e[0]), uid=uid, solve=False)
            rep["splines"].append(g.n)
            rep["lines_refit"] += len(lines)
    rep["loose_ends"] = len(_loose(sk, _Groups(sk)))
    if solve:
        sk.solve()
    rep["changes"] = (len(rep["duplicates"]) + len(rep["tiny_removed"]) + rep["gaps_closed"]
                      + len(rep["splines"]))
    return rep


def as_text(rep: dict[str, Any], doing: bool = True) -> str:
    """One line of what was (or would be) done."""
    parts = []
    if rep["duplicates"]:
        parts.append(f"{len(rep['duplicates'])} curve{'s' if len(rep['duplicates']) != 1 else ''} drawn twice "
                     f"{'removed' if doing else 'to remove'}")
    if rep["tiny_removed"]:
        parts.append(f"{len(rep['tiny_removed'])} tiny piece{'s' if len(rep['tiny_removed']) != 1 else ''} "
                     f"{'removed' if doing else 'to remove'}")
    if rep["gaps_closed"]:
        parts.append(f"{rep['gaps_closed']} gap{'s' if rep['gaps_closed'] != 1 else ''} "
                     f"{'closed' if doing else 'to close'} (largest {rep['largest_gap']:.3g})")
    if rep["splines"]:
        parts.append(f"{rep['lines_refit']} short lines {'refit' if doing else 'to refit'} as "
                     f"{len(rep['splines'])} spline{'s' if len(rep['splines']) != 1 else ''}")
    return ", ".join(parts) if parts else "nothing to repair"
