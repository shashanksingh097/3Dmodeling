"""Mates: place a copy against another by its faces, edges and axes.

``MATE, kind, <fixed item>, <moving item> [, value] [, FLIP]`` moves the body
that owns the second item so the two items meet:

=============  ==============================================================
COINCIDENT     two flat faces or planes face each other in one plane; two
               axes line up; two round edges share centre and axis; a point
               goes onto a point or a plane
CONCENTRIC     two axes (round faces, round or straight edges, datum axes)
               line up; the copy keeps its place along the axis
DISTANCE, d    flat faces or planes face each other ``d`` apart; a point is
               ``d`` above a plane or from a point; two axes are parallel,
               ``d`` apart
ANGLE, a       the normals or axes of the two items are ``a`` degrees apart
=============  ==============================================================

Items are written as in ``DIST``: ``FACE, 12`` · ``EDGE, 4`` · ``VERTEX, 9``
· ``DATUM, name`` · ``XY``/``YZ``/``ZX`` (the fixed item only). With no items,
the two selected ones are used, the first picked staying where it is.
``FLIP`` turns the copy the other way (faces looking the same way instead of
at each other, an axis reversed).

Mates are placement steps, solved in the order they are written: each one
moves the second copy with the smallest turn and shift that meets it, and
keeps the freedom it does not fix (a COINCIDENT pair of faces can still
slide in their plane). A later mate on the same copy can undo an earlier
one; the result line says what was checked, and ``CONTACT`` or
``CLEARANCE`` check the assembly as a whole. A full solver may come later.
"""

from __future__ import annotations

import math

from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

from ..core import datum as dt
from ..core.model import ModelError, check_kind
from ..geometry import features as ft
from .feature_handlers import _Args, plane_ref
from .handlers import _transform
from .processor import Arg, CommandError, Processor, Raw, command

KINDS = ("COINCIDENT", "CONCENTRIC", "DISTANCE", "ANGLE", "FRAME")
TOL = 1e-7


class Item:
    """One side of a mate: what it is (PLANE, AXIS, POINT, CIRCLE) and where."""

    def __init__(self, label: str, what: str, point: dt.P3, direction: dt.P3 = (0.0, 0.0, 1.0),
                 body: int | None = None, shape=None, ref: tuple = ()) -> None:
        self.label, self.what, self.point, self.dir = label, what, point, direction
        self.body, self.shape = body, shape
        self.ref = ref  # how to find it again: ("FACE", 12) or ("DATUM", "name")

    @property
    def words(self) -> str:
        return {"PLANE": "a flat face", "AXIS": "an axis", "POINT": "a point", "CIRCLE": "a round edge"}[self.what]


def _item_of_entity(p: Processor, kind: str, gid: int) -> Item:
    it = _entity_item(p, kind, gid)
    it.ref = (kind, gid)
    return it


def _entity_item(p: Processor, kind: str, gid: int) -> Item:
    m = p.model
    try:
        shape = m.entity_shape(kind, gid)
        body = m.entity_owner(kind, gid)[0]
    except ModelError as exc:
        raise CommandError(f"MATE: {exc}") from None
    label = f"{kind} {gid}"
    if kind == "FACE":
        got = ft.face_plane(shape)
        if got:
            return Item(label, "PLANE", got[0], got[1], body, shape)
        ax = ft.face_axis(shape)
        if ax:
            return Item(label, "AXIS", ax[0], dt.unit(ax[1]), body, shape)
        raise CommandError(f"MATE: {label} is neither flat nor round (use a flat face, a cylinder or cone face, "
                           "an edge or a vertex)")
    if kind == "EDGE":
        circ = ft.edge_circle(shape)
        if circ:
            return Item(label, "CIRCLE", circ[0], dt.unit(circ[1]), body, shape)
        line = ft.edge_line(shape)
        if line:
            return Item(label, "AXIS", line[0], line[1], body, shape)
        raise CommandError(f"MATE: {label} is neither straight nor round")
    if kind == "VERTEX":
        from .queries import centre

        return Item(label, "POINT", tuple(centre("VERTEX", shape)), body=body, shape=shape)
    raise CommandError(f"MATE: use FACE, EDGE or VERTEX items (or DATUM, XY, YZ, ZX for the fixed one), not {kind}")


def _item_of_datum(d: dt.Datum, label: str, frames: dict | None = None) -> Item:
    it = _datum_item(d, label)
    it.ref = ("DATUM", d.name)
    if frames and d.name.upper() in frames:
        it.body = frames[d.name.upper()]
    return it


def _datum_item(d: dt.Datum, label: str) -> Item:
    if d.kind == "PLANE":
        return Item(label, "PLANE", d.origin, dt.unit(d.z), shape=ft.datum_shape(d))
    if d.kind == "AXIS":
        return Item(label, "AXIS", d.origin, dt.unit(d.z), shape=ft.datum_shape(d))
    return Item(label, "POINT", d.origin, shape=ft.datum_shape(d))


def _read_item(p: Processor, a: _Args, which: str) -> Item:
    word = a.word(f"the {which} item's kind (FACE, EDGE, VERTEX, DATUM)").upper()
    if word == "DATUM":
        name = a.word("the datum name")
        try:
            return _item_of_datum(p.model.datum(name), f"datum {name}", p.model.frames)
        except ModelError as exc:
            raise CommandError(f"MATE: {exc}") from None
    if word in dt.BASE_PLANES:
        if a.i < len(a.raws) and a.raws[a.i] == "":
            a.i += 1  # (the form leaves the ID of XY empty)
        return _item_of_datum(plane_ref(p, word, "MATE"), f"plane {word}")
    try:
        k = check_kind(word)
    except ModelError as exc:
        raise CommandError(f"MATE: {exc}, or DATUM") from None
    return _item_of_entity(p, k, a.entity(k, f"the {which} {k.lower()}"))


def _selected(p: Processor) -> list[Item]:
    m = p.model
    if len(m.selection) != 2 or m.selection_kind not in ("FACE", "EDGE", "VERTEX"):
        raise CommandError("MATE: pick two faces, edges or vertices first (Ctrl+click; the first stays, the "
                           "second moves), or give them: MATE, CONCENTRIC, FACE, 6, FACE, 31")
    return [_item_of_entity(p, m.selection_kind, gid) for gid in m.selection]


# ---- vector help ------------------------------------------------------------------
def _turn(u: dt.P3, v: dt.P3) -> tuple[dt.P3, float]:
    """(axis, radians) of the smallest turn taking unit u onto unit v."""
    c = max(-1.0, min(1.0, dt.dot(u, v)))
    ax = dt.cross(u, v)
    if dt.norm(ax) < 1e-12:
        if c > 0:
            return (0.0, 0.0, 1.0), 0.0
        # opposite: any axis across u
        helper = (1.0, 0.0, 0.0) if abs(u[0]) < 0.9 else (0.0, 1.0, 0.0)
        return dt.unit(dt.cross(u, helper)), math.pi
    return dt.unit(ax), math.acos(c)


def _rot(axis: dt.P3, ang: float, about: dt.P3) -> gp_Trsf:
    t = gp_Trsf()
    if abs(ang) > 1e-14:
        t.SetRotation(gp_Ax1(gp_Pnt(*about), gp_Dir(*axis)), ang)
    return t


def _apply(t: gp_Trsf, pt: dt.P3) -> dt.P3:
    q = gp_Pnt(*pt).Transformed(t)
    return (q.X(), q.Y(), q.Z())


def _apply_dir(t: gp_Trsf, d: dt.P3) -> dt.P3:
    q = gp_Dir(*d).Transformed(t)
    return (q.X(), q.Y(), q.Z())


def _shift(v: dt.P3) -> gp_Trsf:
    t = gp_Trsf()
    t.SetTranslation(gp_Vec(*v))
    return t


def _then(first: gp_Trsf, second: gp_Trsf) -> gp_Trsf:
    """``first``, then ``second``."""
    return second.Multiplied(first)


def _perp(v: dt.P3, d: dt.P3) -> dt.P3:
    """The part of v across direction d."""
    return dt.sub(v, dt.mul(d, dt.dot(v, d)))


def _align(a: Item, b: Item, want: dt.P3) -> gp_Trsf:
    """Turn b (about its own point) so its direction becomes ``want``."""
    ax, ang = _turn(b.dir, want)
    return _rot(ax, ang, b.point)


def _either_way(a: Item, b: Item, flip: bool) -> dt.P3:
    """For axes: a's direction or its reverse, whichever turns b less (FLIP: the other)."""
    same = dt.dot(a.dir, b.dir) >= 0
    if flip:
        same = not same
    return a.dir if same else dt.mul(a.dir, -1.0)


# ---- the mates ----------------------------------------------------------------------
def _planes(a: Item, b: Item, gap: float, flip: bool) -> gp_Trsf:
    want = a.dir if flip else dt.mul(a.dir, -1.0)  # faces look at each other unless FLIP
    t = _align(a, b, want)
    pb = _apply(t, b.point)
    h = dt.dot(dt.sub(pb, a.point), a.dir)
    return _then(t, _shift(dt.mul(a.dir, gap - h)))


def _axes(a: Item, b: Item, flip: bool, gap: float | None = None) -> gp_Trsf:
    t = _align(a, b, _either_way(a, b, flip))
    pb = _apply(t, b.point)
    across = _perp(dt.sub(pb, a.point), a.dir)  # from a's axis out to b's
    if gap is None:
        return _then(t, _shift(dt.mul(across, -1.0)))
    d = dt.norm(across)
    if d < 1e-9:
        raise CommandError(f"MATE: {a.label} and {b.label} are on one line, so there is no side to put "
                           f"them {gap:g} apart on; move one off first")
    return _then(t, _shift(dt.mul(across, gap / d - 1.0)))


def _point_to_plane(plane: Item, pt: dt.P3, gap: float) -> gp_Trsf:
    h = dt.dot(dt.sub(pt, plane.point), plane.dir)
    return _shift(dt.mul(plane.dir, gap - h))


def _solve(kind: str, a: Item, b: Item, value: float | None, flip: bool) -> tuple[gp_Trsf, str]:
    pair = (a.what, b.what)
    axial = ("AXIS", "CIRCLE")
    if kind in ("COINCIDENT", "DISTANCE"):
        gap = value or 0.0
        if pair == ("PLANE", "PLANE"):
            return _planes(a, b, gap, flip), "faces " + ("in one plane" if not gap else f"{gap:g} apart")
        if a.what == "PLANE" and b.what in ("POINT", "CIRCLE"):
            return _point_to_plane(a, b.point, gap), ("on the plane" if not gap else f"{gap:g} above the plane")
        if a.what in ("POINT", "CIRCLE") and b.what == "PLANE":
            # move the plane's body so the plane passes through the point (along its own normal)
            h = dt.dot(dt.sub(a.point, b.point), b.dir)
            return _shift(dt.mul(b.dir, h + gap)), "plane through the point"
        if pair == ("POINT", "POINT") or (a.what in ("POINT", "CIRCLE") and b.what in ("POINT", "CIRCLE")
                                          and "POINT" in pair):
            d = dt.sub(a.point, b.point)
            if not gap:
                return _shift(d), "points together"
            n = dt.norm(d)
            if n < 1e-9:
                raise CommandError(f"MATE: {a.label} and {b.label} are at one place; there is no direction "
                                   f"to put them {gap:g} apart in")
            return _shift(dt.mul(d, 1.0 - gap / n)), f"points {gap:g} apart"
        if pair == ("CIRCLE", "CIRCLE") and kind == "COINCIDENT":
            t = _align(a, b, _either_way(a, b, flip))
            return _then(t, _shift(dt.sub(a.point, _apply(t, b.point)))), "round edges on one centre and axis"
        if a.what in axial and b.what in axial:
            if kind == "DISTANCE":
                return _axes(a, b, flip, gap), f"axes parallel, {gap:g} apart"
            return _axes(a, b, flip), "axes in line"
    elif kind == "CONCENTRIC":
        if a.what in axial and b.what in axial:
            return _axes(a, b, flip), "axes in line"
    elif kind == "ANGLE":
        if a.what != "POINT" and b.what != "POINT":
            want = math.radians(value or 0.0)
            da = a.dir
            db = b.dir
            if flip:
                db = dt.mul(db, -1.0)
            ax = dt.cross(da, db)
            if dt.norm(ax) < 1e-12:
                helper = (1.0, 0.0, 0.0) if abs(da[0]) < 0.9 else (0.0, 1.0, 0.0)
                ax = dt.cross(da, helper)
            ax = dt.unit(ax)
            now = math.atan2(dt.dot(dt.cross(da, db), ax), dt.dot(da, db))
            t = _rot(ax, want - now, b.point)
            return t, f"{value:g} deg between them"
    need = {
        "COINCIDENT": "two flat faces or planes, two axes or round edges, two points, or a point and a plane",
        "DISTANCE": "two flat faces or planes, a point and a plane, two points, or two axes",
        "CONCENTRIC": "two axes: round faces, round or straight edges, or datum axes",
        "ANGLE": "two items with a direction: flat faces, planes, axes or edges",
    }[kind]
    raise CommandError(f"MATE: {kind} needs {need}; {a.label} is {a.words} and {b.label} is {b.words}")


def _check(p: Processor, kind: str, a: Item, b_kind: str, b_gid: int, value: float | None) -> str:
    """What the moved item now does, measured again (and a warning when the
    faces end up in one plane without touching)."""
    nb = _item_of_entity(p, b_kind, b_gid)
    if kind == "ANGLE":
        c = abs(dt.dot(a.dir, nb.dir)) if a.what in ("AXIS", "CIRCLE") or nb.what in ("AXIS", "CIRCLE") else None
        ang = math.degrees(math.acos(max(-1.0, min(1.0, dt.dot(a.dir, nb.dir) if c is None else c))))
        return f"angle {ang:.6g} deg"
    if a.what in ("AXIS", "CIRCLE") and nb.what in ("AXIS", "CIRCLE") and kind != "DISTANCE":
        off = dt.norm(_perp(dt.sub(nb.point, a.point), a.dir))
        ang = math.degrees(math.acos(min(1.0, abs(dt.dot(a.dir, nb.dir)))))
        return f"axes {off:.6g} apart, {ang:.6g} deg"
    try:
        d, _, _ = ft.distance(a.shape, nb.shape)
    except ft.FeatureError:
        return ""
    if kind == "COINCIDENT" and a.what == nb.what == "PLANE" and d > 1e-6:
        p.warn(f"MATE: {a.label} and {nb.label} are in one plane but do not overlap ({d:.6g} apart sideways); "
               "add a CONCENTRIC or DISTANCE mate to slide the copy over")
    return f"distance now {(0.0 if abs(d) < 1e-9 else d):.6g}"


@command(
    "MATE",
    Arg("kind", str, help="COINCIDENT, CONCENTRIC, DISTANCE or ANGLE"),
    *[Arg(f"a{i}", Raw, "") for i in range(1, 9)],
    help="Place a copy against another: MATE, kind, <fixed item>, <moving item> [, value] [, FLIP] moves the "
         "body of the second item. Items: FACE, 12 · EDGE, 4 · VERTEX, 9 · DATUM, name · XY (fixed only). "
         "COINCIDENT: faces against each other, axes or round edges in line, points together. CONCENTRIC: axes "
         "in line. DISTANCE, d: faces d apart. ANGLE, a: a degrees between them. FRAME, a, b: coordinate system "
         "b (CSYS) onto a. FLIP turns the copy the other way. With no items, the two selected (the first stays). "
         "Solved in order; MATES finds mates that repeat or fight and lists what is still free.",
)
def mate(p: Processor, kind, **raws):
    kind = {"COINC": "COINCIDENT", "CONC": "CONCENTRIC", "DIST": "DISTANCE", "ANG": "ANGLE"}.get(kind, kind)
    if kind not in KINDS:
        raise CommandError(f"MATE: the kind is one of {', '.join(KINDS)}, not {kind!r}")
    vals = [raws[f"a{i}"] for i in range(1, 9)]
    words = [v.strip() for v in vals]
    if kind == "FRAME":
        return _mate_frames(p, [w for w in words if w])
    flip = False
    while words and not words[-1]:
        words.pop()
    if words and words[-1].upper() == "FLIP":
        flip = True
        words.pop()
    a = _Args(p, "MATE", words)
    head = words[0].upper() if words else ""
    if not words or head not in ("FACE", "EDGE", "VERTEX", "DATUM", *dt.BASE_PLANES):
        ia, ib = _selected(p)
        sel_kind = p.model.selection_kind
        b_ref = (sel_kind, p.model.selection[1])
    else:
        ia = _read_item(p, a, "fixed")
        start = a.i
        ib = _read_item(p, a, "moving")
        b_word = words[start].upper()
        if b_word not in ("FACE", "EDGE", "VERTEX"):
            raise CommandError(f"MATE: the second item is the one that moves, so it must be a FACE, EDGE or "
                               f"VERTEX of a body, not {ib.label}")
        b_ref = (check_kind(b_word), _gid_from_label(ib.label))
    value = None
    if kind in ("DISTANCE", "ANGLE"):
        value = a.num("the distance" if kind == "DISTANCE" else "the angle (degrees)")
    elif a.more():
        value = a.num("the gap", 0.0)
        if value:
            raise CommandError(f"MATE: {kind} takes no value (use DISTANCE for a gap)")
    a.done()
    if ib.body is None:
        raise CommandError(f"MATE: {ib.label} is not on a body, so nothing can move")
    if ia.body is not None and ia.body == ib.body:
        raise CommandError(f"MATE: {ia.label} and {ib.label} are on the same body ({ib.body}); "
                           "a mate moves the second item's body against another one")
    if kind == "DISTANCE" and value is not None and value < 0:
        raise CommandError("MATE: the distance cannot be negative (FLIP puts the copy on the other side)")
    t, what = _solve(kind, ia, ib, value, flip)
    _transform(p, ib.body, t, "moved", copy=False)
    checked = _check(p, kind, ia, b_ref[0], b_ref[1], value)
    name = p.model.bodies[ib.body].name
    who = f"body {ib.body}" + ("" if not name or name == f"body{ib.body}" else f" '{name}'")
    _record(p, kind, ia, (b_ref[0], b_ref[1]), ib.body, value, flip)
    return f"{kind.lower()}: {ib.label} to {ia.label}, {who} moved ({what}" + (f"; {checked}" if checked else "") + ")"


def _record(p: Processor, kind: str, ia: Item, b_ref: tuple, body: int, value, flip: bool) -> None:
    """Keep the mate (MATES checks them all), and say when it repeats or undoes an earlier one."""
    from .mate_check import after_mate

    rec = {"step": p.entry_index + 1, "kind": kind, "a": tuple(ia.ref), "b": tuple(b_ref), "body": body,
           "fixed": ia.body, "value": value, "flip": flip}
    p.model.mates = [*p.model.mates, rec]
    after_mate(p, rec)


def _mate_frames(p: Processor, words: list[str]) -> str:
    """MATE, FRAME, a, b [, FLIP]: the body of frame b moves so b lies on a (origin and axes)."""
    flip = bool(words) and words[-1].upper() == "FLIP"
    if flip:
        words = words[:-1]
    if len(words) != 2:
        raise CommandError("MATE: FRAME takes two coordinate systems: MATE, FRAME, fixed, moving [, FLIP]")
    m = p.model
    try:
        da = plane_ref(p, words[0], "MATE")
        db = m.datum(words[1], "PLANE")
    except ModelError as exc:
        raise CommandError(f"MATE: {exc}") from None
    body = m.frames.get(db.name.upper())
    if body is None or body not in m.bodies:
        raise CommandError(f"MATE: {db.name} is not on a body (make it with CSYS, name, body ...), so nothing "
                           "can move")
    if m.frames.get(da.name.upper()) == body:
        raise CommandError(f"MATE: {da.name} and {db.name} are on the same body ({body})")
    za, xa = (dt.mul(da.z, -1.0), da.x) if flip else (da.z, da.x)
    t = frame_move(db, da.origin, za, xa)
    _transform(p, body, t, "moved", copy=False)
    a_item = _item_of_datum(da, f"frame {da.name}", m.frames)
    _record(p, "FRAME", a_item, ("DATUM", db.name), body, None, flip)
    nb = m.datum(db.name)
    off = dt.norm(dt.sub(nb.origin, da.origin))
    return (f"frame: {db.name} onto {da.name}" + (" (z turned round)" if flip else "")
            + f", body {body} moved (origins {off:.6g} apart)")


def frame_move(d: dt.Datum, origin, z, x) -> gp_Trsf:
    """The move that takes frame ``d`` onto (origin, z, x)."""
    from OCP.gp import gp_Ax3

    src = gp_Ax3(gp_Pnt(*d.origin), gp_Dir(*d.z), gp_Dir(*d.x))
    dst = gp_Ax3(gp_Pnt(*origin), gp_Dir(*z), gp_Dir(*x))
    t = gp_Trsf()
    t.SetDisplacement(src, dst)
    return t


def _gid_from_label(label: str) -> int:
    return int(label.split()[-1])
