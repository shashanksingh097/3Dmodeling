"""More sketch commands: SCHAMFER, SSPLIT, SCORNER, STRANSFORM, and the
drawing commands SARCT, SCIRCLE3, SRECTC, SRECT3, SNGON and SSLOTARC.

Like every sketch step each is one history entry. The work is done in
``sketch/edit_more.py`` and ``sketch/draw.py`` (plain 2D). Power trim is
STRIM with several pieces (``sketch_edit_handlers.py``).
"""

from __future__ import annotations

from ..sketch import draw
from ..sketch import edit as ed
from ..sketch import edit_more as em
from .processor import CommandError, Processor, command
from .sketch_handlers import _active, _drawn, _Reader, _sketch_error, _store, _vals


def _words(raws) -> list[str]:
    vals = [str(x).strip() for x in raws]
    while vals and not vals[-1]:
        vals.pop()
    return vals


@command("SCHAMFER", *_vals(14),
         help="Cut sketch corners where two lines meet with a straight line: SCHAMFER, 1.E, 3 (3 back along both "
              "lines) · SCHAMFER, 1.E, 3, 5 (3 along line 1, 5 along the other) · SCHAMFER, 1.E, 3, ANGLE, 30 "
              "(3 along line 1, at 30 deg to it) · SCHAMFER, 1.E, 2.E, 3 (several corners). The sizes are dimensions: "
              "double-click one to change it. The corner stays as a construction point, so sizes to it still hold.")
def schamfer(p: Processor, **raws):
    sk = _active(p, "SCHAMFER")
    vals = _words(raws.values())
    corners = []
    while vals and em.CORNER.match(vals[0]):
        corners.append(vals.pop(0).replace(" ", "").upper())
    if not corners:
        raise CommandError("SCHAMFER: give the corner first, like 1.E (the end of line 1 where another line meets it)")
    angle_form = len(vals) == 3 and vals[1].upper() == "ANGLE"
    if not (len(vals) in (1, 2) or angle_form):
        raise CommandError("SCHAMFER: after the corners give d, or d, d2, or d, ANGLE, degrees")
    r = _Reader(p, "SCHAMFER", [v for v in vals if v.upper() != "ANGLE"])
    d1 = r.num("the distance")
    d2 = angle = None
    args = (-1, -1)
    if angle_form:
        angle, args = r.num("the angle"), (-3, -1)
    elif len(vals) == 2:
        d2, args = r.num("the second distance"), (-2, -1)
    out = []
    with _sketch_error("SCHAMFER"):
        for c in corners:
            said, _ = em.chamfer(sk, c, d1, d2, angle, p.entry_uid, args)
            out.append(said)
    return _store(p, sk, "; ".join(out))


@command("SSPLIT", *_vals(20),
         help="Split a sketch curve so its parts can be sized or held apart: SSPLIT, 3, u, v (at the point of curve 3 "
              "nearest u, v) · SSPLIT, 3, u1, v1, u2, v2 (at several points; a circle needs two) · SSPLIT, 3, 5 "
              "(where curve 5 crosses it; H or V for an axis). The parts stay joined, on one line or circle.")
def ssplit(p: Processor, **raws):
    sk = _active(p, "SSPLIT")
    vals = _words(raws.values())
    if len(vals) < 2:
        raise CommandError("SSPLIT: give the curve, then a point u, v (or the curve that crosses it)")
    with _sketch_error("SSPLIT"):
        n = ed._num(vals[0])
        if len(vals) == 2:
            at = ed._cutter(vals[1])
        else:
            r = _Reader(p, "SSPLIT", vals[1:])
            r.allowed = set()
            at = []
            while r.more():
                at.append((r.num("u of the split point"), r.num("v of the split point")))
            r.done()
        said, _ = em.split(sk, n, at, p.entry_uid)
    return _store(p, sk, said)


@command("SCORNER", *_vals(6),
         help="Trim or extend two sketch lines or arcs so they just meet in a corner: SCORNER, 1, 2 (the end of each "
              "nearer the crossing moves to it) · SCORNER, 1, 2, u1, v1, u2, v2 (keep the part of 1 at u1, v1 and of 2 "
              "at u2, v2, as the Corner tool clicks them).")
def scorner(p: Processor, **raws):
    sk = _active(p, "SCORNER")
    vals = _words(raws.values())
    if len(vals) not in (2, 6):
        raise CommandError("SCORNER: give two curves, and optionally a point on the part of each to keep")
    with _sketch_error("SCORNER"):
        n1, n2 = ed._num(vals[0]), ed._num(vals[1])
        picks = None
        if len(vals) == 6:
            r = _Reader(p, "SCORNER", vals[2:])
            picks = ((r.num("u1"), r.num("v1")), (r.num("u2"), r.num("v2")))
        said = em.corner(sk, n1, n2, picks, p.entry_uid)
    return _store(p, sk, said)


@command("STRANSFORM", *_vals(60),
         help="Move, turn or scale sketch geometry, or copies of it: STRANSFORM, MOVE, du, dv, 1, 2, 3 · "
              "STRANSFORM, ROTATE, 45, O, 1, 2 (45 deg about the origin; the centre is a point name or u, v) · "
              "STRANSFORM, SCALE, 2, 0, 0, 5 (twice the size about 0, 0) · COPY at the end leaves the originals where "
              "they are. Constraints among the geometry go with it; ties to the rest of the sketch are let go.")
def stransform(p: Processor, **raws):
    sk = _active(p, "STRANSFORM")
    vals = _words(raws.values())
    copy = bool(vals) and vals[-1].upper() == "COPY"
    if copy:
        vals.pop()
    if not vals:
        raise CommandError("STRANSFORM: start with MOVE, ROTATE or SCALE")
    kind = vals.pop(0).upper()
    kind = {"ROT": "ROTATE", "TURN": "ROTATE", "MV": "MOVE"}.get(kind, kind)
    if kind not in ("MOVE", "ROTATE", "SCALE"):
        raise CommandError("STRANSFORM: the kind is MOVE, ROTATE or SCALE")
    r = _Reader(p, "STRANSFORM", vals)
    r.allowed = set()
    if kind == "MOVE":
        values = (r.num("du"), r.num("dv"))
    else:
        amount = r.num("the angle" if kind == "ROTATE" else "the factor")
        values = (amount, r.point("the centre"))
    names = []
    while r.more():
        names.append(r.word("the geometry"))
    r.done()
    if not names:
        raise CommandError("STRANSFORM: give the geometry to move (its numbers)")
    with _sketch_error("STRANSFORM"):
        said, _ = em.transform(sk, kind, values, names, copy, p.entry_uid)
    return _store(p, sk, said)


# =============================================================================
# more ways to draw
# =============================================================================


@command("SARCT", *_vals(4),
         help="An arc that carries on smoothly from the end of a line or arc: SARCT, 3.E, u, v (to u, v; or to a point "
              "name like 5.S). It is tied to that end and tangent to the curve.")
def sarct(p: Processor, **raws):
    sk = _active(p, "SARCT")
    r = _Reader(p, "SARCT", raws.values())
    end = r.word("the end to go on from (like 3.E)").replace(" ", "").upper()
    to = r.point("the end of the arc")
    r.done()
    with _sketch_error("SARCT"):
        g = draw.tangent_arc(sk, end, to, p.entry_uid, "CONSTR" in r.flags)
    return _drawn(p, sk, [g], r, "SARCT")


@command("SCIRCLE3", *_vals(7),
         help="A circle through three points: SCIRCLE3, u1, v1, u2, v2, u3, v3 (named points like 3.E stay on it).")
def scircle3(p: Processor, **raws):
    sk = _active(p, "SCIRCLE3")
    r = _Reader(p, "SCIRCLE3", raws.values())
    a, b, c = r.point("the first point"), r.point("the second point"), r.point("the third point")
    r.done()
    with _sketch_error("SCIRCLE3"):
        g = draw.circle_3p(sk, a, b, c, p.entry_uid, "CONSTR" in r.flags)
    return _drawn(p, sk, [g], r, "SCIRCLE3")


@command("SRECTC", *_vals(5),
         help="A level rectangle from its centre and a corner: SRECTC, cu, cv, u, v. It keeps the centre on a "
              "construction diagonal, so it stays centred when sized.")
def srectc(p: Processor, **raws):
    sk = _active(p, "SRECTC")
    r = _Reader(p, "SRECTC", raws.values())
    c, k = r.point("the centre"), r.point("a corner")
    r.done()
    with _sketch_error("SRECTC"):
        geos = draw.rect_centre(sk, c, k, p.entry_uid, "CONSTR" in r.flags)
    return _drawn(p, sk, geos, r, "SRECTC")


@command("SRECT3", *_vals(7),
         help="A rectangle at any angle: SRECT3, u1, v1, u2, v2, u3, v3 (one side from the first point to the second; "
              "the third says how wide, and on which side).")
def srect3(p: Processor, **raws):
    sk = _active(p, "SRECT3")
    r = _Reader(p, "SRECT3", raws.values())
    a, b, c = r.point("the first corner"), r.point("the second corner"), r.point("a point on the far side")
    r.done()
    with _sketch_error("SRECT3"):
        geos = draw.rect_3p(sk, a, b, c, p.entry_uid, "CONSTR" in r.flags)
    return _drawn(p, sk, geos, r, "SRECT3")


@command("SNGON", *_vals(7),
         help="A regular polygon: SNGON, cu, cv, n, r (n sides, corners on a construction circle of radius r, the "
              "first corner straight up) · SNGON, cu, cv, 6, 10, 0 (first corner at 0 deg) · OUT at the end: the sides "
              "touch the circle instead (r is then across the flats, halved).")
def sngon(p: Processor, **raws):
    sk = _active(p, "SNGON")
    vals = _words(raws.values())
    outside = bool(vals) and vals[-1].upper() in ("OUT", "IN") and vals[-1].upper() == "OUT"
    if vals and vals[-1].upper() in ("OUT", "IN"):
        vals.pop()
    r = _Reader(p, "SNGON", vals)
    c = r.point("the centre")
    n, rad = r.num("the number of sides"), r.num("the radius")
    angle = r.num("the angle of the first corner") if r.more() else 90.0
    r.done()
    with _sketch_error("SNGON"):
        geos = draw.polygon(sk, c, n, rad, angle, outside, p.entry_uid, "CONSTR" in r.flags)
    return _drawn(p, sk, geos, r, "SNGON")


@command("SSLOTARC", *_vals(7),
         help="A slot bent along an arc: SSLOTARC, cu, cv, r, a1, a2, w (its middle round the centre at radius r from "
              "a1 to a2 degrees, counter-clockwise; w is half its width, the radius of its round ends).")
def sslotarc(p: Processor, **raws):
    sk = _active(p, "SSLOTARC")
    r = _Reader(p, "SSLOTARC", raws.values())
    c = r.point("the centre")
    rad, a1, a2, w = r.num("the radius"), r.num("the start angle"), r.num("the end angle"), r.num("the half-width")
    r.done()
    with _sketch_error("SSLOTARC"):
        geos = draw.arc_slot(sk, c, rad, a1, a2, w, p.entry_uid, "CONSTR" in r.flags)
    return _drawn(p, sk, geos, r, "SSLOTARC")
