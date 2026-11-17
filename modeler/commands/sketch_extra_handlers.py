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
from .sketch_handlers import _active, _drawn, _Reader, _sketch_error, _vals


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
