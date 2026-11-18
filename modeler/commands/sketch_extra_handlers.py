"""The last sketch commands of PLAN.md item 7: ellipses (SELLIPSE, SEARC),
a circle tangent to curves (SCIRCLET), an offset to both sides with closed
ends (SOFFSET2) and the curve where a body cuts the sketch plane
(SINTERSECT).

Like every sketch step each is one history entry; the 2D work is in
``sketch/ellipse.py``, ``sketch/draw.py`` and ``sketch/edit_more.py``.
"""

from __future__ import annotations

import math

from .processor import CommandError, Processor, command
from .sketch_handlers import _active, _drawn, _Reader, _sketch_error, _store, _vals


def _axis_point(c, a: float, angle: float):
    if isinstance(c, str):
        return None
    t = math.radians(angle)
    return (c[0] + a * math.cos(t), c[1] + a * math.sin(t))


def _ellipse(p: Processor, what: str, raws, arc: bool):
    sk = _active(p, what)
    r = _Reader(p, what, raws)
    r.allowed = {"CONSTR", "H", "V"}
    c = r.point("the centre")
    a = r.num("the first radius")
    b = r.num("the second radius")
    angle = r.num("the angle of the first axis", 0.0) if r.more() else 0.0
    t1 = t2 = None
    if arc:
        t1, t2 = r.num("the start angle"), r.num("the end angle")
    r.done()
    if a <= 0:
        raise CommandError(f"{what}: the first radius must be positive")
    uid = p.entry_uid
    with _sketch_error(what):
        if isinstance(c, str):
            (cu, cv), _ = sk.point_value(c)
            at = _axis_point((cu, cv), a, angle)
        else:
            at = _axis_point(c, a, angle)
        g = sk.add_ellipse(c, at, b, uid, "CONSTR" in r.flags, t1, t2)
        for flag, kind in (("H", "HORIZONTAL"), ("V", "VERTICAL")):
            if flag in r.flags:  # the first axis level (or upright)
                sk.add_con(kind, (f"{g.n}.C", f"{g.n}.A"), uid=uid, auto=True, solve=False)
    r.flags -= {"H", "V"}
    return _drawn(p, sk, [g], r, what)


@command("SELLIPSE", *_vals(7),
         help="An ellipse: SELLIPSE, cu, cv, a, b (radius a along u, b across) · SELLIPSE, cu, cv, a, b, 30 (its first "
              "axis turned 30 deg) · H at the end keeps the first axis level. Its points are n.C (centre) and n.A "
              "(the end of the first axis); size it with SDIM, MAJOR, n, a and SDIM, MINOR, n, b.")
def sellipse(p: Processor, **raws):
    return _ellipse(p, "SELLIPSE", raws.values(), arc=False)


@command("SEARC", *_vals(9),
         help="An elliptical arc: SEARC, cu, cv, a, b, angle, t1, t2 (the ellipse as in SELLIPSE, from t1 to t2 "
              "degrees round it, counter-clockwise; 0 is the end of the first axis, 90 the end of the second). "
              "Its ends are n.S and n.E.")
def searc(p: Processor, **raws):
    return _ellipse(p, "SEARC", raws.values(), arc=True)


@command("SCIRCLET", *_vals(9),
         help="A circle touching curves: SCIRCLET, 1, 2, R, 5, AT, u, v (radius 5, touching curves 1 and 2, the one "
              "nearest u, v) · SCIRCLET, 1, 2, 3, AT, u, v (touching three curves; they set its size). Lines, arcs, "
              "circles, H and V, and a line with an ellipse. The touches are TANGENT constraints.")
def scirclet(p: Processor, **raws):
    from ..sketch import draw

    sk = _active(p, "SCIRCLET")
    vals = [str(x).strip() for x in raws.values()]
    while vals and not vals[-1]:
        vals.pop()
    up = [v.upper() for v in vals]
    if "AT" not in up:
        raise CommandError("SCIRCLET: say where the circle goes with AT, u, v (it picks the one nearest there)")
    i = up.index("AT")
    head, tail = vals[:i], vals[i + 1:]
    radius = None
    if "R" in (h.upper() for h in head):
        j = [h.upper() for h in head].index("R")
        if j + 1 >= len(head):
            raise CommandError("SCIRCLET: give the radius after R")
        radius = _Reader(p, "SCIRCLET", [head[j + 1]]).num("the radius")
        head = head[:j] + head[j + 2:]
    r = _Reader(p, "SCIRCLET", tail)
    r.allowed = {"CONSTR"}
    at = r.point("the place")
    r.done()
    with _sketch_error("SCIRCLET"):
        g = draw.circle_tangent(sk, head, at, radius, p.entry_uid, "CONSTR" in r.flags)
    return _drawn(p, sk, [g], r, "SCIRCLET")


@command("SOFFSET2", *_vals(41),
         help="Offset curves to both sides with closed ends, a slot along a path: SOFFSET2, d, 1, 2, 3 (d each "
              "side; round ends) · FLAT at the end: straight ends. A closed chain gets an outline inside and one "
              "outside. The path becomes construction geometry, the middle of the outline.")
def soffset2(p: Processor, **raws):
    from ..sketch import edit_more as em

    sk = _active(p, "SOFFSET2")
    vals = [str(x).strip() for x in raws.values()]
    while vals and not vals[-1]:
        vals.pop()
    flat = bool(vals) and vals[-1].upper() == "FLAT"
    if flat:
        vals.pop()
    if len(vals) < 2:
        raise CommandError("SOFFSET2: give the distance, then the curves")
    d = _Reader(p, "SOFFSET2", vals[:1]).num("the distance")
    with _sketch_error("SOFFSET2"):
        said, _ = em.offset_both(sk, d, vals[1:], flat, p.entry_uid)
    return _store(p, sk, said)


@command("SINTERSECT", *_vals(20),
         help="The curves where bodies cut the sketch plane, brought into the sketch and fixed there: SINTERSECT, 1 "
              "(body 1) · SINTERSECT, 1, 3 · CONSTR at the end makes them construction geometry. Straight cuts come "
              "in as lines, round ones as circles, arcs and ellipses. They are made again whenever an earlier step "
              "changes the bodies.")
def sintersect(p: Processor, **raws):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer

    from ..core.model import ModelError
    from ..sketch import profile as pr
    from ..sketch.sketch import SketchError
    from .sketch_edit_handlers import _project_edge

    sk = _active(p, "SINTERSECT")
    r = _Reader(p, "SINTERSECT", raws.values())
    r.allowed = {"CONSTR"}
    ids = []
    while r.more():
        v = r.num("a body ID")
        if not float(v).is_integer():
            raise CommandError(f"SINTERSECT: {v:g} is not a body ID")
        ids.append(int(v))
    r.done()
    if not ids:
        raise CommandError("SINTERSECT: give the bodies to cut, like SINTERSECT, 1")
    made = []
    with _sketch_error("SINTERSECT"):
        for bid in ids:
            try:
                shape = p.model.body(bid).shape
            except ModelError as exc:
                raise CommandError(f"SINTERSECT: {exc}") from None
            sec = BRepAlgoAPI_Section(shape, pr._plane(sk), True)
            if not sec.IsDone():
                raise SketchError(f"the kernel could not cut body {bid} with the sketch plane")
            ex = TopExp_Explorer(sec.Shape(), TopAbs_EDGE)
            n0 = len(made)
            while ex.More():
                made += _project_edge(sk, ex.Current(), p.entry_uid, "CONSTR" in r.flags)
                ex.Next()
            if len(made) == n0:
                raise SketchError(f"body {bid} does not reach the sketch plane")
        _join_ends(sk, made, p.entry_uid)
        sk.solve()
    shown = f"{made[0].n}..{made[-1].n}" if len(made) > 3 else ", ".join(str(g.n) for g in made)
    return _store(p, sk, f"cut {'body' if len(ids) == 1 else 'bodies'} {', '.join(map(str, ids))} with sketch "
                         f"{sk.name}'s plane: {len(made)} fixed curve{'s' if len(made) != 1 else ''} ({shown})")


def _join_ends(sk, made, uid: int) -> None:
    """Tie the ends of the cut curves that meet (so a closed cut is one loop)."""
    tol = 1e-6 * max(1.0, sk.extent())
    ends = [(g, role) for g in made for role in ("S", "E") if role in g.pts]
    tied = set()
    for i, (g, a) in enumerate(ends):
        for h, b in ends[i + 1:]:
            if g is h or (h.n, b) in tied:
                continue
            if math.dist(sk.pt(g.pts[a]), sk.pt(h.pts[b])) <= tol:
                sk.add_con("COINCIDENT", (f"{g.n}.{a}", f"{h.n}.{b}"), uid=uid, auto=True, solve=False)
                tied.add((h.n, b))
                break


@command("SJOIN", *_vals(40),
         help="Join sketch curves that meet end to end into one smooth spline: SJOIN, 1, 2, 3 (corners where they "
              "meet are rounded off; a closed chain makes a closed spline). One curve: SJOIN, 4 turns a line, arc, "
              "circle or ellipse into a spline you can then reshape by its points. Constraints on the old curves "
              "go, except those on the two free ends of the chain.")
def sjoin(p: Processor, **raws):
    from ..sketch import spline_edit as se

    sk = _active(p, "SJOIN")
    vals = [str(x).strip() for x in raws.values() if str(x).strip()]
    if not vals:
        raise CommandError("SJOIN: give the curves to join, e.g. SJOIN, 1, 2, 3")
    with _sketch_error("SJOIN"):
        said, _ = se.join(sk, vals, p.entry_uid)
    return _store(p, sk, said)
