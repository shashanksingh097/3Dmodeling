"""Sketch editing commands: STRIM, SEXTEND, SFILLET, SOFFSET, SMIRROR,
SPATTERN and SPROJECT.

Like every sketch step, each is one history entry; the work is done in
``sketch/edit.py`` (plain 2D) except SPROJECT, which reads body edges from
the kernel and lays them flat on the sketch plane.
"""

from __future__ import annotations

import math

from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Line
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopExp import TopExp_Explorer

from ..core.model import ModelError
from ..geometry.sweep import _as_edge
from ..sketch import edit as ed
from ..sketch.sketch import SketchError
from .processor import Arg, CommandError, Processor, Raw, command

from .sketch_handlers import _active, _Reader, _sketch_error, _store, _vals


def _names(r: _Reader) -> list[str]:
    out = []
    while r.more():
        out.append(r.word("the geometry"))
    return out


@command("STRIM", *_vals(3),
         help="Trim a sketch curve back to the curves that cross it: STRIM, 3, u, v removes the piece of curve 3 "
              "nearest (u, v), between the crossings on either side. The new end stays ON the curve that cut it. "
              "A curve nothing crosses is deleted; a circle becomes an arc.")
def strim(p: Processor, **raws):
    sk = _active(p, "STRIM")
    r = _Reader(p, "STRIM", raws.values())
    with _sketch_error("STRIM"):
        n = ed._num(r.word("the curve"))
        at = (r.num("u of the piece to remove"), r.num("v of the piece to remove"))
        r.done()
        said = ed.trim(sk, n, at, p.entry_uid)
    return _store(p, sk, said)


@command("SEXTEND", *_vals(2),
         help="Extend a sketch line or arc to the next curve it meets: SEXTEND, 3.E (on from the end of 3) · "
              "SEXTEND, 3.S, 5 (on from the start, to curve 5, even where 5 would have to go on too). "
              "The end then stays ON that curve.")
def sextend(p: Processor, **raws):
    sk = _active(p, "SEXTEND")
    r = _Reader(p, "SEXTEND", raws.values())
    with _sketch_error("SEXTEND"):
        end = r.word("the end to extend (3.E or 3.S)")
        to = ed._num(r.word("the curve to extend to")) if r.more() else None
        r.done()
        said = ed.extend(sk, end, to, p.entry_uid)
    return _store(p, sk, said)


@command("SFILLET", *_vals(13),
         help="Round sketch corners where two lines meet: SFILLET, 1.E, 4 (the corner at the end of line 1, radius 4) · "
              "SFILLET, 1.E, 2.E, 3.E, 4 (several corners, one radius). The radius is a size like any other: "
              "double-click it to change it. The corner stays as a construction point, so sizes to it still hold.")
def sfillet(p: Processor, **raws):
    sk = _active(p, "SFILLET")
    vals = [v for v in (str(x).strip() for x in raws.values()) if v]
    if len(vals) < 2:
        raise CommandError("SFILLET: give the corner (like 1.E) and then the radius")
    r = _Reader(p, "SFILLET", [vals[-1]])
    rad = r.num("the radius")
    out = []
    with _sketch_error("SFILLET"):
        for corner in vals[:-1]:
            said, _ = ed.fillet(sk, corner.replace(" ", "").upper(), rad, p.entry_uid)
            out.append(said)
    return _store(p, sk, "; ".join(out))


@command("SOFFSET", Arg("d", help="how far (positive: outwards for a closed chain or a circle)"), *_vals(40),
         help="Offset sketch curves: SOFFSET, 3, 1, 2, 3, 4 makes curves 3 away from lines 1..4. Curves joined end "
              "to end are offset as one chain and meet again at the corners. Positive goes outwards for a closed "
              "chain or circle, and to the left of an open chain (walking the lowest-numbered curve from its start). "
              "The offset follows its original when that changes.")
def soffset(p: Processor, d, **raws):
    sk = _active(p, "SOFFSET")
    r = _Reader(p, "SOFFSET", raws.values())
    with _sketch_error("SOFFSET"):
        said, _ = ed.offset(sk, float(d), _names(r), p.entry_uid)
    return _store(p, sk, said)


@command("SMIRROR", Arg("axis", Raw, help="the line to mirror about: a line's number, or H / V"), *_vals(40),
         help="Mirror sketch geometry about a line: SMIRROR, V, 1, 2, 3 · SMIRROR, 7, 1, 2 (about line 7). "
              "The copies stay mirror images when the originals change.")
def smirror(p: Processor, axis, **raws):
    sk = _active(p, "SMIRROR")
    r = _Reader(p, "SMIRROR", raws.values())
    with _sketch_error("SMIRROR"):
        said, _ = ed.mirror(sk, axis.strip().upper(), _names(r), p.entry_uid)
    return _store(p, sk, said)


@command("SPATTERN", Arg("kind", str, help="LINEAR or POLAR"), *_vals(44),
         help="Copies of sketch geometry. SPATTERN, LINEAR, n, du, dv, g1, g2 ... (n in all, the original counts; "
              "each copy du, dv on from the one before) · SPATTERN, POLAR, n, angle, centre, g1 ... (round a point: "
              "a name like O or 3.C, or u, v; angle 360 spreads them round the full turn, less spaces them over that "
              "angle with the last one at its end). The copies follow when the originals change.")
def spattern(p: Processor, kind, **raws):
    sk = _active(p, "SPATTERN")
    r = _Reader(p, "SPATTERN", raws.values())
    if kind not in ("LINEAR", "POLAR"):
        raise CommandError("SPATTERN: the kind is LINEAR or POLAR")
    n = r.num("the count")
    if n != int(n) or n < 2:
        raise CommandError("SPATTERN: the count is a whole number, 2 or more (the original counts)")
    n = int(n)
    with _sketch_error("SPATTERN"):
        if kind == "LINEAR":
            step = (r.num("du"), r.num("dv"))
            if math.hypot(*step) < 1e-12:
                raise CommandError("SPATTERN: the step du, dv must not be 0, 0")
            said, _ = ed.pattern(sk, "LINEAR", n, step, _names(r), uid=p.entry_uid)
        else:
            total = r.num("the angle")
            centre = r.point("the centre")
            if abs(total) < 1e-12:
                raise CommandError("SPATTERN: the angle must not be 0")
            full = abs(abs(total) - 360) < 1e-9
            step = total / n if full else total / (n - 1)
            said, _ = ed.pattern(sk, "POLAR", n, step, _names(r), centre=centre, uid=p.entry_uid)
    return _store(p, sk, said)


# =============================================================================
# SPROJECT
# =============================================================================

_SAMPLES = 24  # lines a curved edge that is not a circle flat on the sketch is drawn with


def _flat(frame, q) -> tuple[float, float]:
    o, x, z = frame.origin, frame.x, frame.z
    y = (z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0])
    d = (q[0] - o[0], q[1] - o[1], q[2] - o[2])
    return (d[0] * x[0] + d[1] * x[1] + d[2] * x[2], d[0] * y[0] + d[1] * y[1] + d[2] * y[2])


def _project_edge(sk, edge, uid: int, construction: bool) -> list:
    """Lay one edge flat on the sketch plane: lines and arcs where they come
    out that way, else a chain of short lines. Each piece is fixed."""
    c = BRepAdaptor_Curve(_as_edge(edge))
    t0, t1 = c.FirstParameter(), c.LastParameter()
    pt = lambda t: tuple(c.Value(t).Coord())  # noqa: E731
    z = sk.frame.z
    tol = 1e-7 * max(1.0, sk.extent())
    kind = c.GetType()
    made = []
    if kind == GeomAbs_Circle:
        circ = c.Circle()
        ax = circ.Axis().Direction().Coord()
        cosn = ax[0] * z[0] + ax[1] * z[1] + ax[2] * z[2]
        if abs(abs(cosn) - 1) < 1e-9:
            cen = _flat(sk.frame, circ.Location().Coord())
            rad = circ.Radius()
            if abs(t1 - t0 - 2 * math.pi) < 1e-9:
                made.append(sk.add_circle(cen, rad, uid, construction))
            else:
                a, b = _flat(sk.frame, pt(t0)), _flat(sk.frame, pt(t1))
                a1 = math.degrees(math.atan2(a[1] - cen[1], a[0] - cen[0]))
                a2 = math.degrees(math.atan2(b[1] - cen[1], b[0] - cen[0]))
                if cosn < 0:  # the circle turns the other way seen from the sketch
                    a1, a2 = a2, a1
                made.append(sk.add_arc(cen, rad, a1, a2, uid, construction))
    if not made:
        if kind == GeomAbs_Line:
            ts = [t0, t1]
        else:
            ts = [t0 + (t1 - t0) * i / _SAMPLES for i in range(_SAMPLES + 1)]
        pts = [_flat(sk.frame, pt(t)) for t in ts]
        keep = [pts[0]]
        for q in pts[1:]:
            if math.dist(q, keep[-1]) > tol:
                keep.append(q)
        for a, b in zip(keep, keep[1:]):
            made.append(sk.add_line(a, b, uid, construction))
    for g in made:
        sk.add_con("FIX", (str(g.n),), uid=uid, auto=True, solve=False)
    return made


@command("SPROJECT", *_vals(40),
         help="Bring body edges into the open sketch, laid flat on its plane and fixed there: SPROJECT, 12, 13 "
              "(edge IDs) · SPROJECT, FACE, 6 (every edge of face 6) · SPROJECT, SEL (the picked edges or faces). "
              "CONSTR at the end makes them construction geometry. They are made again from the bodies whenever "
              "an earlier step changes.")
def sproject(p: Processor, **raws):
    sk = _active(p, "SPROJECT")
    r = _Reader(p, "SPROJECT", raws.values())
    r.allowed = {"CONSTR"}
    m = p.model
    words = []
    while r.more():
        words.append(r.word("an edge ID"))
    r.done()
    if not words:
        raise CommandError("SPROJECT: give edge IDs, FACE and a face ID, or SEL")
    edges = []
    kind = "EDGE"
    for w in words:
        if w.upper() == "FACE":
            kind = "FACE"
            continue
        if w.upper() == "EDGE":
            kind = "EDGE"
            continue
        if w.upper() == "SEL":
            if m.selection_kind not in ("EDGE", "FACE") or not m.selection:
                raise CommandError("SPROJECT: SEL needs picked edges or faces")
            ids = [(m.selection_kind, i) for i in m.selection]
        else:
            v = p.evaluate(w)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not float(v).is_integer():
                raise CommandError(f"SPROJECT: {w} is not an edge ID")
            ids = [(kind, int(v))]
        for k, gid in ids:
            try:
                shape = m.entity_shape(k, gid)
            except ModelError as exc:
                raise CommandError(f"SPROJECT: {exc}") from None
            if k == "EDGE":
                edges.append(shape)
            else:
                ex = TopExp_Explorer(shape, TopAbs_EDGE)
                while ex.More():
                    edges.append(ex.Current())
                    ex.Next()
    made = []
    with _sketch_error("SPROJECT"):
        for e in edges:
            made += _project_edge(sk, e, p.entry_uid, "CONSTR" in r.flags)
        if not made:
            raise SketchError("those edges lie square to the sketch plane, so nothing of them shows on it")
        sk.solve()
    shown = f"{made[0].n}..{made[-1].n}" if len(made) > 3 else ", ".join(str(g.n) for g in made)
    return _store(p, sk, f"projected {len(edges)} edge{'s' if len(edges) != 1 else ''} into sketch {sk.name}: "
                         f"{len(made)} fixed curve{'s' if len(made) != 1 else ''} ({shown})")


