"""Sketch commands (SKETCH ... ENDSKETCH, drawing, constraints, dimensions)
and the features made from sketches (EXTRUDE, REVOLVE).

Every step is one command and one history entry, so a sketch is built,
undone and edited like everything else: changing the size in an ``SDIM``
entry re-runs the history from there, and the extrude after it follows.
The GUI's sketch mode only builds these lines.

Sketch positions are 2D: ``u`` along the sketch plane's X, ``v`` along its
Y. Wherever a command takes a point, a sketch point name works too
(``3.E`` = the end of line 3, ``ORIGIN``), and the new curve is then
tied to that point with a coincident constraint.
"""

from __future__ import annotations

import math
import re

from ..core import datum as dt
from ..core.model import ModelError
from ..geometry import robust
from ..lang.expr import ExprError, Vec, fmt_num, format_value
from ..lang.script import is_ident
from ..sketch import profile as prof
from ..sketch.sketch import CON_KINDS, DIM_KINDS, Sketch, SketchError
from .feature_handlers import _check_name, _face_plane, axis_ref, plane_ref
from .processor import Arg, BodyRef, CommandError, Processor, Raw, Text, command

_POINT_NAME = re.compile(r"^\s*(\d+\s*\.\s*[SECP]|O|ORIGIN)\s*$", re.I)
_FLAGS = ("H", "V", "CONSTR", "CLOSE")


def _vals(n: int) -> list[Arg]:
    return [Arg(f"v{i}", Raw, "") for i in range(1, n + 1)]


class _Reader:
    """Free sketch arguments, left to right: points (u, v or a point name),
    numbers, names, and trailing flag words."""

    def __init__(self, p: Processor, what: str, raws):
        self.p, self.what = p, what
        self.raws = [str(r).strip() for r in raws]
        while self.raws and not self.raws[-1]:
            self.raws.pop()
        self.i = 0
        self._pending: list[float] = []
        self.flags: set[str] = set()
        # flag words at the end (CONSTR, H, V, CLOSE); one is given back as a
        # value when the command runs short, so a parameter named H still works
        self._taken: list[str] = []
        while self.raws and self.raws[-1].upper() in _FLAGS:
            self._taken.append(self.raws.pop())
            self.flags.add(self._taken[-1].upper())

    def more(self) -> bool:
        return bool(self._pending) or self.i < len(self.raws)

    def _raw(self, what: str) -> str:
        if self.i >= len(self.raws) and self._taken:
            back = self._taken.pop()
            self.raws.append(back)
            if back.upper() not in (w.upper() for w in self._taken):
                self.flags.discard(back.upper())
        if self.i >= len(self.raws) or not self.raws[self.i]:
            raise CommandError(f"{self.what}: {what} is required")
        s = self.raws[self.i]
        self.i += 1
        return s

    def num(self, what: str, default: float | None = None) -> float:
        if self._pending:
            return self._pending.pop(0)
        if default is not None and (self.i >= len(self.raws) or not self.raws[self.i]):
            self.i += 1
            return default
        s = self._raw(what)
        try:
            v = self.p.evaluate(s)
        except ExprError as exc:
            raise CommandError(f"{self.what}: {what}: {exc}") from None
        if isinstance(v, Vec):
            vals = [float(c) for c in v]
            self._pending = vals[1:2] if len(vals) >= 2 else []
            return vals[0]
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise CommandError(f"{self.what}: {what} must be a number, got {format_value(v)}")
        return float(v)

    def point(self, what: str):
        """(u, v), or a point name such as 3.E or O."""
        if not self._pending and self.i < len(self.raws) and _POINT_NAME.match(self.raws[self.i]):
            self.i += 1
            name = self.raws[self.i - 1].replace(" ", "").upper()
            return "ORIGIN" if name == "O" else name
        return (self.num(f"{what} u"), self.num(f"{what} v"))

    def word(self, what: str) -> str:
        return self._raw(what).strip()

    def done(self) -> None:
        if self.more():
            extra = self.raws[self.i] if self.i < len(self.raws) else "a number"
            raise CommandError(f"{self.what}: too many arguments (from {extra!r})")
        bad = self.flags - self.allowed
        if bad:
            raise CommandError(f"{self.what}: {', '.join(sorted(bad))} does not apply here")

    allowed: set[str] = {"CONSTR"}


def _active(p: Processor, what: str) -> Sketch:
    m = p.model
    if not m.active_sketch:
        raise CommandError(f"{what}: no sketch is open; start one with SKETCH, name, plane")
    return m.edit_sketch(m.active_sketch)


def _store(p: Processor, sk: Sketch, said: str) -> str:
    p.model.put_sketch(sk)
    if sk.redundant:
        p.warn(f"sketch {sk.name}: {', '.join('C' + str(n) for n in sk.redundant)} only repeat other constraints; "
               "delete them (SDEL) to keep the sketch clean")
    return f"{said}; {sk.status()}"


def _sketch_error(what: str):
    class _Wrap:
        def __enter__(self):
            return self

        def __exit__(self, et, ev, tb):
            if et is not None and issubclass(et, SketchError):
                raise CommandError(f"{what}: {ev}") from None
            return False

    return _Wrap()


# =============================================================================
# SKETCH, ENDSKETCH
# =============================================================================


@command(
    "SKETCH",
    Arg("name", Text, help="a new name (or an open, unused sketch to carry on with)"),
    Arg("on", Raw, "", "a datum plane, XY/YZ/ZX, FACE (then its ID), or DELETE (default: the work plane, or XY)"),
    Arg("id", Raw, "", "the face ID after FACE (SEL = the picked face)"),
    help="Start a 2D sketch on a plane: SKETCH, s1, XY · SKETCH, s1, top (a datum plane) · SKETCH, s1, FACE, 6 "
         "(on a flat face; its body is where EXTRUDE adds or cuts by default). Then draw with SLINE, SRECT, SCIRCLE, "
         "SARC ..., hold it with SCON and SDIM, and finish with ENDSKETCH. SKETCH, s1, DELETE removes a sketch.",
)
def sketch_(p: Processor, name, on, id):
    m = p.model
    word = on.strip()
    if word.upper() == "DELETE":
        try:
            sk = m.remove_sketch(name)
        except ModelError as exc:
            raise CommandError(f"SKETCH: {exc}") from None
        return f"deleted sketch {sk.name}"
    if m.active_sketch:
        raise CommandError(f"SKETCH: sketch {m.sketches[m.active_sketch].name} is still open; ENDSKETCH first")
    old = m.sketches.get(name.strip().upper())
    if old is not None:
        if word:
            raise CommandError(f"SKETCH: there is already a sketch {old.name}; use another name, "
                               f"or SKETCH, {old.name} (no plane) to carry on drawing in it")
        if old.used_by:
            raise CommandError(f"SKETCH: {old.name} is already used by {', '.join(old.used_by)}. To change it, "
                               "edit its steps in the history (the features after them follow)")
        sk = old.copy()
        sk.closed = False
        m.put_sketch(sk)
        m.set_active_sketch(sk.name)
        return f"reopened sketch {sk.name}; {sk.status()}"
    if not is_ident(name):
        raise CommandError(f"SKETCH: {name!r} is not a valid name (letters, digits, _)")
    _check_name(p, name, "SKETCH")
    if m.body_by_name(name) is not None:
        raise CommandError(f"SKETCH: {name} is already the name of body {m.body_by_name(name).id}")
    base = 0
    if not word:
        frame = m.workplane or dt.plane((0, 0, 0), (0, 0, 1), name="XY")
        where = f"work plane {frame.name}" if m.workplane else "XY"
    elif word.upper() == "FACE":
        r = _Reader(p, "SKETCH", [id])
        raw = id.strip()
        if raw.upper() == "SEL":
            if m.selection_kind != "FACE" or not m.selection:
                raise CommandError("SKETCH: SEL needs a face picked first")
            gid = m.selection[0]
        else:
            v = r.num("the face ID")
            if not float(v).is_integer():
                raise CommandError("SKETCH: the face ID must be a whole number")
            gid = int(v)
        try:
            base = m.entity_owner("FACE", gid)[0]
        except ModelError as exc:
            raise CommandError(f"SKETCH: {exc}") from None
        c, n = _face_plane(p, gid, "SKETCH")
        frame = dt.plane(c, n)
        where = f"face {gid} of body {base}"
    else:
        if is_ident(word):
            try:
                v = p._lookup(word.upper())
                if isinstance(v, str):
                    word = v
            except KeyError:
                pass
        frame = plane_ref(p, word, "SKETCH")
        where = frame.name
    sk = Sketch(name.strip(), dt.Datum("PLANE", name.strip(), frame.origin, frame.z, frame.x), base)
    sk.solve()
    m.put_sketch(sk)
    m.set_active_sketch(sk.name)
    return f"sketch {sk.name} on {where}: u along {_v(frame.x)}, v along {_v(frame.y)}"


def _v(v) -> str:
    return "(" + ", ".join(fmt_num(round(c, 6) + 0.0) for c in v) + ")"


@command("ENDSKETCH", help="Finish the open sketch. It stays in the model for EXTRUDE and REVOLVE.")
def endsketch(p: Processor):
    m = p.model
    if not m.active_sketch:
        raise CommandError("ENDSKETCH: no sketch is open")
    sk = m.edit_sketch(m.active_sketch)
    sk.closed = True
    m.put_sketch(sk)
    m.set_active_sketch(None)
    try:
        n = len(prof.regions(sk))
        shape = f"{n} profile{'s' if n != 1 else ''} ready to extrude"
    except SketchError as exc:
        shape = f"no closed profile yet ({exc})"
    return f"closed {sk.status()}; {shape}"


# =============================================================================
# drawing
# =============================================================================


def _drawn(p: Processor, sk: Sketch, geos, r: _Reader, what: str) -> str:
    uid = p.entry_uid
    for flag, kind in (("H", "HORIZONTAL"), ("V", "VERTICAL")):
        if flag in r.flags:
            sk.add_con(kind, (str(geos[0].n),), uid=uid, auto=True, solve=False)
    with _sketch_error(what):
        sk.solve()
    said = "; ".join(sk.describe(g.n) for g in geos[:6])
    if len(geos) > 6:
        said += f" ... ({len(geos)} curves)"
    return _store(p, sk, said)


@command("SPOINT", *_vals(3), help="A sketch point: SPOINT, u, v (CONSTR at the end makes it construction).")
def spoint(p: Processor, **raws):
    sk = _active(p, "SPOINT")
    r = _Reader(p, "SPOINT", raws.values())
    at = r.point("the point")
    r.done()
    with _sketch_error("SPOINT"):
        g = sk.add_point(at, p.entry_uid)
    return _drawn(p, sk, [g], r, "SPOINT")


@command("SLINE", *_vals(7),
         help="A sketch line: SLINE, u1, v1, u2, v2 · SLINE, 3.E, 40, 0 (from the end of line 3, tied to it). "
              "Add H or V at the end to make it horizontal or vertical, CONSTR for construction.")
def sline(p: Processor, **raws):
    sk = _active(p, "SLINE")
    r = _Reader(p, "SLINE", raws.values())
    r.allowed = {"CONSTR", "H", "V"}
    a, b = r.point("the start"), r.point("the end")
    r.done()
    with _sketch_error("SLINE"):
        g = sk.add_line(a, b, p.entry_uid, "CONSTR" in r.flags)
    return _drawn(p, sk, [g], r, "SLINE")


@command("SPOLY", *_vals(60),
         help="Lines joined end to end: SPOLY, 0,0, 40,0, 40,20, CLOSE (CLOSE joins the last point to the first).")
def spoly(p: Processor, **raws):
    sk = _active(p, "SPOLY")
    r = _Reader(p, "SPOLY", raws.values())
    r.allowed = {"CONSTR", "CLOSE"}
    pts = []
    while r.more():
        pts.append(r.point(f"point {len(pts) + 1}"))
    r.done()
    with _sketch_error("SPOLY"):
        geos = sk.add_poly(pts, "CLOSE" in r.flags, p.entry_uid, "CONSTR" in r.flags)
    return _drawn(p, sk, geos, r, "SPOLY")


@command("SRECT", *_vals(5),
         help="A rectangle from two opposite corners: SRECT, u1, v1, u2, v2 (its sides are kept horizontal and vertical).")
def srect(p: Processor, **raws):
    sk = _active(p, "SRECT")
    r = _Reader(p, "SRECT", raws.values())
    a, b = r.point("the first corner"), r.point("the opposite corner")
    r.done()
    with _sketch_error("SRECT"):
        geos = sk.add_rect(a, b, p.entry_uid, "CONSTR" in r.flags)
    return _drawn(p, sk, geos, r, "SRECT")


@command("SCIRCLE", *_vals(4), help="A sketch circle: SCIRCLE, u, v, r (or SCIRCLE, 3.C, r around the centre of 3).")
def scircle(p: Processor, **raws):
    sk = _active(p, "SCIRCLE")
    r = _Reader(p, "SCIRCLE", raws.values())
    c = r.point("the centre")
    rad = r.num("the radius")
    r.done()
    with _sketch_error("SCIRCLE"):
        g = sk.add_circle(c, rad, p.entry_uid, "CONSTR" in r.flags)
    return _drawn(p, sk, [g], r, "SCIRCLE")


@command("SARC", *_vals(6),
         help="A sketch arc: SARC, u, v, r, a1, a2 (centre, radius, start and end angle in degrees, counter-clockwise).")
def sarc(p: Processor, **raws):
    sk = _active(p, "SARC")
    r = _Reader(p, "SARC", raws.values())
    c = r.point("the centre")
    rad, a1, a2 = r.num("the radius"), r.num("the start angle"), r.num("the end angle")
    r.done()
    with _sketch_error("SARC"):
        g = sk.add_arc(c, rad, a1, a2, p.entry_uid, "CONSTR" in r.flags)
    return _drawn(p, sk, [g], r, "SARC")


@command("SARC3", *_vals(7),
         help="An arc through three points: SARC3, start, middle, end (each u, v or a point name like 3.E).")
def sarc3(p: Processor, **raws):
    sk = _active(p, "SARC3")
    r = _Reader(p, "SARC3", raws.values())
    a, b, c = r.point("the start"), r.point("a point on the arc"), r.point("the end")
    r.done()
    with _sketch_error("SARC3"):
        g = sk.add_arc_3p(a, b, c, p.entry_uid, "CONSTR" in r.flags)
    return _drawn(p, sk, [g], r, "SARC3")


@command("SSLOT", *_vals(6),
         help="A slot: SSLOT, u1, v1, u2, v2, r (two half circles of radius r around the two centres, joined by lines).")
def sslot(p: Processor, **raws):
    sk = _active(p, "SSLOT")
    r = _Reader(p, "SSLOT", raws.values())
    a, b = r.point("the first centre"), r.point("the second centre")
    rad = r.num("the radius")
    r.done()
    with _sketch_error("SSLOT"):
        geos = sk.add_slot(a, b, rad, p.entry_uid, "CONSTR" in r.flags)
    return _drawn(p, sk, geos, r, "SSLOT")


# =============================================================================
# constraints and dimensions
# =============================================================================


@command(
    "SCON", Arg("kind", str, help=" ".join(CON_KINDS)), *_vals(3),
    help="Constrain sketch geometry: SCON, COINCIDENT, 1.E, 2.S · ON, 3.S, 1 (point on a curve) · HORIZONTAL, 1 · "
         "VERTICAL, 2 · PARALLEL, 1, 3 · PERPENDICULAR, 1, 2 · TANGENT, 4, 5 · EQUAL, 1, 3 · MIDPOINT, 5.C, 1 · "
         "SYMMETRIC, 2.S, 3.S, V · CONCENTRIC, 5, 6 · FIX, 2.E. Names: 3 (geometry), 3.S/3.E/3.C, ORIGIN, H, V.",
)
def scon(p: Processor, kind, **raws):
    sk = _active(p, "SCON")
    kind = {"COINCIDENT": "COINCIDENT", "COIN": "COINCIDENT", "HORIZ": "HORIZONTAL", "VERT": "VERTICAL",
            "PERP": "PERPENDICULAR", "TAN": "TANGENT", "MID": "MIDPOINT", "SYM": "SYMMETRIC"}.get(kind, kind)
    if kind in DIM_KINDS:
        raise CommandError(f"SCON: {kind} has a size, so it is a dimension: SDIM, {kind}, ..., size")
    if kind not in CON_KINDS:
        raise CommandError(f"SCON: the kind is one of {', '.join(CON_KINDS)}")
    refs = tuple(v for v in (str(x).strip() for x in raws.values()) if v)
    if not refs:
        raise CommandError(f"SCON, {kind}: say what to constrain (e.g. 1, 2.E)")
    with _sketch_error(f"SCON, {kind}"):
        c = sk.add_con(kind, refs, uid=p.entry_uid)
    return _store(p, sk, f"C{c.n} {c.kind.lower()} {', '.join(c.refs)}")


@command(
    "SDIM", Arg("kind", str, help=" ".join(DIM_KINDS)), *_vals(3),
    help="Give sketch geometry a size (the last argument, any expression): SDIM, LENGTH, 1, 40 · DIST, 1.S, 3.E, W · "
         "DIST, 5.C, 1, 12 (point to line) · HDIST, ORIGIN, 5.C, 15 · VDIST, ORIGIN, 5.C, 10 · RADIUS, 5, 4 · DIAMETER, 5, 8 · "
         "ANGLE, 1, 2, 30 (degrees; with one line, from H). Change it later by editing this history entry.",
)
def sdim(p: Processor, kind, **raws):
    sk = _active(p, "SDIM")
    kind = {"DIAM": "DIAMETER", "RAD": "RADIUS", "LEN": "LENGTH", "DISTANCE": "DIST"}.get(kind, kind)
    if kind in CON_KINDS:
        raise CommandError(f"SDIM: {kind} has no size, so it is a constraint: SCON, {kind}, ...")
    if kind not in DIM_KINDS:
        raise CommandError(f"SDIM: the kind is one of {', '.join(DIM_KINDS)}")
    vals = [v for v in (str(x).strip() for x in raws.values()) if v]
    if len(vals) < 2:
        raise CommandError(f"SDIM, {kind}: give what to measure and then the size, e.g. SDIM, {kind}, 1, 40")
    r = _Reader(p, "SDIM", [vals[-1]])
    value = r.num("the size")
    with _sketch_error(f"SDIM, {kind}"):
        c = sk.add_con(kind, tuple(vals[:-1]), value, uid=p.entry_uid)
    unit = " deg" if kind == "ANGLE" else ""
    return _store(p, sk, f"C{c.n} {kind.lower()} {', '.join(c.refs)} = {fmt_num(value)}{unit}")


@command("SDEL", *_vals(4), help="Delete sketch geometry (SDEL, 3: with its constraints) or a constraint (SDEL, C4).")
def sdel(p: Processor, **raws):
    sk = _active(p, "SDEL")
    names = [v for v in (str(x).strip() for x in raws.values()) if v]
    if not names:
        raise CommandError("SDEL: say what to delete (3, or C4)")
    out = []
    # constraints first, then geometry from the highest number, so names stay valid
    order = sorted(names, key=lambda t: (not t.upper().startswith("C"), -int(re.sub(r"\D", "", t) or 0)))
    with _sketch_error("SDEL"):
        for t in order:
            if t.upper().startswith("C") and int(t[1:] or 0) not in sk.cons:
                continue  # already gone with its geometry
            out.append(sk.delete(t))
    return _store(p, sk, "; ".join(out))


@command("SMOVE", Arg("what", Raw, help="a point (3.E) or geometry (3)"), Arg("u"), Arg("v"),
         help="Drag sketch geometry: SMOVE, 3.E, 25, 10 puts the end of line 3 at (25, 10) as far as the constraints "
              "allow (the rest follows). SMOVE, 3, u, v moves line 3 by its start point.")
def smove(p: Processor, what, u, v):
    sk = _active(p, "SMOVE")
    with _sketch_error("SMOVE"):
        sk.move(what, u, v)
        r = sk.ref(what)
    n = r.geo.n if r.geo is not None else None
    return _store(p, sk, sk.describe(n) if n else f"{what} at ({fmt_num(u)}, {fmt_num(v)})")


@command("SCONSTRUCT", Arg("what", Raw, help="geometry number"), Arg("mode", str, "ON", "ON or OFF"),
         help="Construction geometry helps place things but is not part of the profile: SCONSTRUCT, 3 · SCONSTRUCT, 3, OFF.")
def sconstruct(p: Processor, what, mode):
    sk = _active(p, "SCONSTRUCT")
    with _sketch_error("SCONSTRUCT"):
        r = sk.ref(what)
    if r.geo is None or r.fixed or "." in what:
        raise CommandError("SCONSTRUCT: give a geometry number")
    if mode not in ("ON", "OFF"):
        raise CommandError("SCONSTRUCT: ON or OFF")
    sk.geos[r.geo.n].construction = mode == "ON"
    return _store(p, sk, f"{sk.geos[r.geo.n].kind.lower()} {r.geo.n} is {'construction' if mode == 'ON' else 'profile'} geometry")


@command("SSEL", *_vals(12), logged=False,
         help="Select sketch geometry for the GUI's constraint buttons: SSEL, 1, 3.E · SSEL, A, 4 (add) · SSEL, NONE. "
              "Not part of the history: the constraints it leads to name their geometry.")
def ssel(p: Processor, **raws):
    m = p.model
    names = [v.upper() for v in (str(x).strip() for x in raws.values()) if v]
    if not m.active_sketch:
        raise CommandError("SSEL: no sketch is open")
    sk = m.sketches[m.active_sketch]
    mode = "S"
    if names and names[0] in ("A", "U", "S"):
        mode, names = names[0], names[1:]
    if not names or names == ["NONE"]:
        m.sketch_selection = []
    else:
        with _sketch_error("SSEL"):
            for t in names:
                if not (t.startswith("C") and t[1:].isdigit()):
                    sk.ref(t)
        cur = list(getattr(m, "sketch_selection", [])) if mode != "S" else []
        for t in names:
            if mode == "U":
                cur = [c for c in cur if c != t]
            elif t not in cur:
                cur.append(t)
        m.sketch_selection = cur
    from ..core.model import Event

    m._emit(Event("sketch_selection"))
    return "sketch selection: " + (", ".join(m.sketch_selection) or "none")


# =============================================================================
# EXTRUDE, REVOLVE
# =============================================================================

_MODES = ("NEW", "ADD", "CUT")


def _profile(p: Processor, name: str, what: str):
    m = p.model
    try:
        sk = m.sketch(name)
    except ModelError as exc:
        raise CommandError(f"{what}: {exc}") from None
    note = ""
    if m.active_sketch == sk.name.upper():
        sk = sk.copy()
        sk.closed = True
        m.put_sketch(sk)
        m.set_active_sketch(None)
        note = f" (closed sketch {sk.name})"
    try:
        faces = prof.faces(sk)
    except SketchError as exc:
        raise CommandError(f"{what}: sketch {sk.name}: {exc}") from None
    return sk, faces, note


def _target(p: Processor, sk: Sketch, mode: str, target: int, what: str) -> int:
    m = p.model
    if mode == "NEW":
        if target:
            raise CommandError(f"{what}: a body to add to or cut from only goes with ADD or CUT")
        return 0
    if not target:
        target = sk.base_body
        if not target or target not in m.bodies:
            raise CommandError(f"{what}: say which body to {mode.lower()}: {what}, {sk.name}, ..., {mode}, part")
    m.body(target)
    return target


def _mark_used(p: Processor, sk: Sketch, by: str) -> None:
    s = p.model.edit_sketch(sk.name)
    s.used_by.append(by)
    p.model.put_sketch(s)


def _finish(p: Processor, sk: Sketch, solids: list, mode: str, target: int, what: str, said: str) -> str:
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse

    from .handlers import _added, _compound, combine

    m = p.model
    tool = solids[0] if len(solids) == 1 else _compound(solids)
    if not robust.checked_ok(tool, True):
        raise CommandError(f"{what}: the shape made from sketch {sk.name} is not a valid solid "
                           "(for REVOLVE: does the profile cross the axis?)")
    if mode == "NEW":
        body = m.add_body(tool)
        _mark_used(p, sk, f"{what} body {body.id}")
        return _added(p, body, said)
    base = m.body(target)
    before = robust.volume(base.shape)
    name = "UNION" if mode == "ADD" else "SUBTRACT"
    op = BRepAlgoAPI_Fuse if mode == "ADD" else BRepAlgoAPI_Cut
    shape, maker = combine(p, name, op, base.shape, [tool], target, merge=mode == "ADD")
    after = robust.volume(shape)
    if mode == "CUT" and before - after < 1e-9 * max(1.0, before):
        raise CommandError(f"{what}: the cut misses body {target}; check the sketch plane, the distance and its sign")
    if mode == "ADD" and after - before < 1e-9 * max(1.0, before):
        p.warn(f"{what}: the new material is all inside body {target} already, so nothing changed")
    new = m.replace([target], shape, maker)
    _mark_used(p, sk, f"{what} into body {target}" if mode == "ADD" else f"{what} cut in body {target}")
    return _added(p, new, said)


@command(
    "EXTRUDE",
    Arg("sketch", Text, help="the sketch to extrude"),
    Arg("d", help="distance along the sketch normal (negative: the other way; 0 with CUT: through everything)"),
    Arg("mode", str, "NEW", "NEW (a new body), ADD (to a body) or CUT (from a body)"),
    Arg("b", BodyRef, 0, "the body to add to or cut from (default: the body the sketch was drawn on)"),
    Arg("back", float, 0.0, "also extrude this far the other way (d = back: symmetric)"),
    help="Push a sketch's closed profiles into a solid: EXTRUDE, s1, 20 (new body) · EXTRUDE, s1, 5, ADD (a boss "
         "on the body the sketch is on) · EXTRUDE, s1, -8, CUT (a pocket) · EXTRUDE, s1, 0, CUT, part (through all) "
         "· EXTRUDE, s1, 10, NEW, , 10 (10 each way). Loops inside loops become holes.",
)
def extrude(p: Processor, sketch, d, mode, b, back):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.gp import gp_Vec

    if mode not in _MODES:
        raise CommandError(f"EXTRUDE: the mode is one of {', '.join(_MODES)}")
    if back < 0:
        raise CommandError("EXTRUDE: the distance the other way (back) must be 0 or more")
    sk, faces, note = _profile(p, sketch, "EXTRUDE")
    target = _target(p, sk, mode, b, "EXTRUDE")
    z = sk.frame.z
    if d == 0:
        if mode != "CUT":
            raise CommandError("EXTRUDE: the distance cannot be 0 (0 means through everything, and only with CUT)")
        shape = p.model.body(target).shape
        size = robust.diagonal(shape) + dt.norm(dt.sub(sk.frame.origin, _centre(shape))) + 1
        d, back = size, size
        through = True
    else:
        through = False
    start, length = -back, d + (back if d > 0 else -back)
    solids = []
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Trsf

    for f in faces:
        if start:
            t = gp_Trsf()
            t.SetTranslation(gp_Vec(*dt.mul(z, start if d > 0 else -start)))
            f = BRepBuilderAPI_Transform(f, t, True).Shape()
        prism = BRepPrimAPI_MakePrism(f, gp_Vec(*dt.mul(z, length)))
        prism.Build()
        if not prism.IsDone():
            raise CommandError(f"EXTRUDE: the kernel could not extrude sketch {sk.name}")
        solids.append(prism.Shape())
    how = {"NEW": "", "ADD": f" added to body {target}", "CUT": f" cut from body {target}"}[mode]
    dist = "through everything" if through else f"{fmt_num(d)}" + (f" (and {fmt_num(back)} back)" if back else "")
    return _finish(p, sk, solids, mode, target, "EXTRUDE",
                   f"EXTRUDE {sk.name} {dist}{how}: {len(faces)} profile{'s' if len(faces) != 1 else ''}{note}")


def _centre(shape):
    from ..commands.queries import centre

    return tuple(centre("BODY", shape))


@command(
    "REVOLVE",
    Arg("sketch", Text, help="the sketch to turn"),
    Arg("axis", Raw, help="a line of the sketch (its number), H or V (the sketch axes), or a datum axis / X, Y, Z"),
    Arg("angle", float, 360.0, "degrees (default a full turn; negative turns the other way)"),
    Arg("mode", str, "NEW", "NEW, ADD or CUT"),
    Arg("b", BodyRef, 0, "the body to add to or cut from"),
    help="Turn a sketch's profiles about an axis into a solid: REVOLVE, s1, V (a full turn about the sketch's "
         "vertical axis) · REVOLVE, s1, 5, 90 (a quarter turn about line 5, usually a construction line) · "
         "REVOLVE, s1, H, 360, CUT, part. The profile must stay on one side of the axis.",
)
def revolve(p: Processor, sketch, axis, angle, mode, b):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeRevol
    from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt

    if mode not in _MODES:
        raise CommandError(f"REVOLVE: the mode is one of {', '.join(_MODES)}")
    if angle == 0 or abs(angle) > 360:
        raise CommandError("REVOLVE: the angle must be between -360 and 360, and not 0")
    sk, faces, note = _profile(p, sketch, "REVOLVE")
    target = _target(p, sk, mode, b, "REVOLVE")
    word = axis.strip().upper()
    f = sk.frame
    if word in ("H", "V") or re.fullmatch(r"\d+", word):
        try:
            r = sk.ref(word)
        except SketchError as exc:
            raise CommandError(f"REVOLVE: {exc}") from None
        if r.geo is None or r.geo.kind != "LINE":
            raise CommandError(f"REVOLVE: {word} is not a line of sketch {sk.name}")
        if r.fixed:
            a, e = (0.0, 0.0), ((1.0, 0.0) if word == "H" else (0.0, 1.0))
        else:
            a, e = sk.pt(r.geo.pts["S"]), sk.pt(r.geo.pts["E"])
            if not r.geo.construction:
                p.warn(f"REVOLVE: line {word} is also part of the profile; a construction line "
                       f"(SCONSTRUCT, {word}) is the usual axis")
        origin = f.point(*a)
        direction = dt.unit(dt.sub(f.point(*e), origin))
        what_axis = f"line {word}" if not r.fixed else f"the sketch's {word} axis"
    else:
        ax = axis_ref(p, axis, "REVOLVE")
        origin, direction = ax.origin, ax.z
        what_axis = f"axis {ax.name}"
    solids = []
    for face in faces:
        rev = BRepPrimAPI_MakeRevol(face, gp_Ax1(gp_Pnt(*origin), gp_Dir(*direction)), math.radians(angle), True)
        rev.Build()
        if not rev.IsDone():
            raise CommandError(f"REVOLVE: the kernel could not turn sketch {sk.name}; the profile must not cross the axis")
        solids.append(rev.Shape())
    how = {"NEW": "", "ADD": f" added to body {target}", "CUT": f" cut from body {target}"}[mode]
    return _finish(p, sk, solids, mode, target, "REVOLVE",
                   f"REVOLVE {sk.name} {fmt_num(angle)} deg about {what_axis}{how}{note}")


def sketch_listing(p: Processor, name: str = "") -> list[str]:
    m = p.model
    if not m.active_sketch and not m.sketches:
        raise CommandError("LIST, SKETCH: there are no sketches")
    sk = m.sketches[m.active_sketch] if m.active_sketch else list(m.sketches.values())[-1]
    lines = [sk.status()]
    for n in sorted(sk.geos):
        g = sk.geos[n]
        tags = []
        if g.construction:
            tags.append("construction")
        tags.append("fixed" if sk.fully_defined(g) else "free")
        lines.append(f"  {sk.describe(n)}  [{', '.join(tags)}]")
    for c in sk.cons.values():
        size = ""
        if c.is_dim:
            size = f" = {fmt_num(c.value)}{' deg' if c.kind == 'ANGLE' else ''}"
        lines.append(f"  C{c.n} {c.kind.lower()} {', '.join(c.refs)}{size}")
    return lines
