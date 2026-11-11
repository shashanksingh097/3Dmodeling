"""Datums (PLANE, AXIS, POINT, WORKPLANE) and part features (HOLE, SPLIT,
SHELL, DRAFT, OFFSET).

Datums are named references kept in the model (and in its snapshots, so
undo and history edits treat them like everything else). Features change
bodies through the same checked route as booleans and blends: a result that
is empty or not valid is an error, and the model stays as it was.
"""

from __future__ import annotations

from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.TopAbs import TopAbs_FACE

from ..core import datum as dt
from ..core.model import ModelError, check_kind
from ..geometry import features as ft
from ..geometry import robust
from ..lang.expr import ExprError, Vec, fmt_num, format_value
from ..lang.script import is_ident
from .processor import Arg, BodyRef, CommandError, Processor, Raw, Text, command

_N = 10
_VALS = [Arg(f"v{i}", Raw, "") for i in range(1, _N + 1)]


def _fmt(v) -> str:
    return "(" + ", ".join(fmt_num(round(c, 6) + 0.0) for c in v) + ")"


# ---- reading arguments ---------------------------------------------------------
class _Args:
    """The free arguments of a datum command, read left to right."""

    def __init__(self, p: Processor, what: str, raws: list[str]):
        self.p, self.what = p, what
        self.raws = [r.strip() for r in raws]
        while self.raws and not self.raws[-1]:
            self.raws.pop()
        self.i = 0
        self._pending: list[float] = []  # the rest of a point that filled several numbers

    def more(self) -> bool:
        return bool(self._pending) or self.i < len(self.raws)

    def _next_raw(self, what: str) -> str:
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
        s = self._next_raw(what)
        try:
            v = self.p.evaluate(s)
        except ExprError as exc:
            raise CommandError(f"{self.what}: {what}: {exc}") from None
        if isinstance(v, Vec):
            vals = list(v) + [0.0] * (3 - len(v))
            self._pending = [float(c) for c in vals[1:]]
            return float(vals[0])
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise CommandError(f"{self.what}: {what} must be a number, got {format_value(v)}")
        return float(v)

    def point(self, what: str) -> dt.P3:
        return (self.num(f"{what} x"), self.num(f"{what} y"), self.num(f"{what} z"))

    def word(self, what: str) -> str:
        s = self._next_raw(what)
        if is_ident(s):
            try:
                v = self.p._lookup(s.upper())
                if isinstance(v, str):
                    return v
            except KeyError:
                pass
            return s
        try:
            v = self.p.evaluate(s)
        except ExprError as exc:
            raise CommandError(f"{self.what}: {what}: {exc}") from None
        if isinstance(v, str):
            return v
        if isinstance(v, (int, float)) and not isinstance(v, bool) and float(v).is_integer():
            return str(int(v))
        raise CommandError(f"{self.what}: {what} must be a name, got {format_value(v)}")

    def entity(self, kind: str, what: str) -> int:
        """An entity ID; SEL takes the first selected entity of that kind."""
        s = self.raws[self.i] if self.i < len(self.raws) else ""
        m = self.p.model
        if s.upper() == "SEL":
            self.i += 1
            if m.selection_kind != kind or not m.selection:
                raise CommandError(f"{self.what}: SEL needs a {kind.lower()} selected first")
            return m.selection[0]
        v = self.num(what)
        if not float(v).is_integer():
            raise CommandError(f"{self.what}: {what} must be a whole number")
        gid = int(v)
        try:
            m.entity_owner(kind, gid)
        except ModelError as exc:
            raise CommandError(f"{self.what}: {exc}") from None
        return gid

    def done(self) -> None:
        if self.more():
            extra = self.raws[self.i] if self.i < len(self.raws) else "a number"
            raise CommandError(f"{self.what}: too many arguments (from {extra!r})")


def plane_ref(p: Processor, name: str, what: str) -> dt.Datum:
    """A plane by name: XY, YZ, ZX (also XZ) or a datum plane."""
    key = name.strip().upper()
    if key in dt.BASE_PLANES:
        o, n = dt.BASE_PLANES[key]
        return dt.plane(o, n, name=key)
    try:
        d = p.model.datum(name.strip())
    except ModelError as exc:
        raise CommandError(f"{what}: {exc}; or use XY, YZ, ZX") from None
    if d.kind != "PLANE":
        raise CommandError(f"{what}: {d.name} is a datum {d.kind.lower()}, not a plane")
    return d


def axis_ref(p: Processor, name: str, what: str) -> dt.Datum:
    key = name.strip().upper()
    if key in dt.BASE_AXES:
        return dt.axis((0.0, 0.0, 0.0), dt.BASE_AXES[key], name=key)
    try:
        d = p.model.datum(name.strip())
    except ModelError as exc:
        raise CommandError(f"{what}: {exc}; or use X, Y, Z") from None
    if d.kind != "AXIS":
        raise CommandError(f"{what}: {d.name} is a datum {d.kind.lower()}, not an axis")
    return d


def _check_name(p: Processor, name: str, what: str) -> str:
    if not is_ident(name):
        raise CommandError(f"{what}: {name!r} is not a valid name (letters, digits, _)")
    key = name.upper()
    if key in dt.BASE_PLANES or key in dt.BASE_AXES or key in ("LAST", "SEL", "ALL", "OFF"):
        raise CommandError(f"{what}: {name} is reserved")
    if key in p.params:
        raise CommandError(f"{what}: {name} is already a parameter; pick another name")
    old = p.model.datums.get(key)
    if old is not None:
        raise CommandError(f"{what}: there is already a datum {old.kind.lower()} {old.name}; "
                           f"use another name, or DATUM, DELETE, {old.name} first")
    return name


def _add(p: Processor, d: dt.Datum, how: str) -> str:
    try:
        p.model.add_datum(d)
    except ModelError as exc:
        raise CommandError(f"{d.kind}: {exc}") from None
    if d.kind == "POINT":
        return f"point {d.name} at {_fmt(d.origin)} ({how})"
    if d.kind == "AXIS":
        return f"axis {d.name} through {_fmt(d.origin)} along {_fmt(d.z)} ({how})"
    return f"plane {d.name} through {_fmt(d.origin)}, normal {_fmt(d.z)} ({how})"


def _face_plane(p: Processor, gid: int, what: str):
    got = ft.face_plane(p.model.entity_shape("FACE", gid))
    if got is None:
        raise CommandError(f"{what}: face {gid} is curved; a plane needs a flat face")
    return got


# =============================================================================
# PLANE, AXIS, POINT, DATUM, WORKPLANE
# =============================================================================

PLANE_HOW = ("XY", "YZ", "ZX", "XZ", "PN", "3P", "FACE", "OFFSET", "ANGLE", "MID", "NORMAL")


@command(
    "PLANE",
    Arg("name", Text), Arg("how", str, help="XY YZ ZX · PN · 3P · FACE · OFFSET · ANGLE · MID · NORMAL"), *_VALS,
    help="Datum plane. PLANE, name, XY [, offset] · PN, x,y,z, nx,ny,nz [, angle] (point and normal) · "
         "3P, p1, p2, p3 · FACE, id [, offset] (on a flat face, normal out of the body) · OFFSET, plane, d · "
         "ANGLE, plane, axis, degrees (turned about an axis in it) · MID, face1, face2 (half way between) · "
         "NORMAL, edge [, t] (across an edge at fraction t, default 0)",
)
def plane_(p: Processor, name, how, **raws):
    what = "PLANE"
    _check_name(p, name, what)
    a = _Args(p, what, list(raws.values()))
    if how in dt.BASE_PLANES:
        off = a.num("offset", 0.0)
        a.done()
        base = plane_ref(p, how, what)
        return _add(p, base.moved(off).named(name), f"{how}" + (f" moved {fmt_num(off)}" if off else ""))
    try:
        if how == "PN":
            o, n = a.point("point"), a.point("normal")
            ang = a.num("angle", 0.0)
            a.done()
            return _add(p, dt.plane(o, n, ang, name), "point and normal")
        if how == "3P":
            p1, p2, p3 = a.point("point 1"), a.point("point 2"), a.point("point 3")
            a.done()
            return _add(p, dt.plane_through(p1, p2, p3, name), "through 3 points")
        if how == "FACE":
            gid = a.entity("FACE", "the face")
            off = a.num("offset", 0.0)
            a.done()
            c, n = _face_plane(p, gid, what)
            return _add(p, dt.plane(c, n, name=name).moved(off), f"on face {gid}" + (f", moved {fmt_num(off)}" if off else ""))
        if how == "OFFSET":
            base = plane_ref(p, a.word("the plane"), what)
            d = a.num("the distance")
            a.done()
            return _add(p, base.moved(d).named(name), f"{base.name} moved {fmt_num(d)}")
        if how == "ANGLE":
            base = plane_ref(p, a.word("the plane"), what)
            ax = axis_ref(p, a.word("the axis"), what)
            deg = a.num("the angle")
            a.done()
            if abs(dt.dot(ax.z, base.z)) > 1e-6:
                raise CommandError(f"PLANE: axis {ax.name} does not lie in plane {base.name} (it must be at right angles to the normal)")
            n = _rotate(base.z, ax.z, deg)
            return _add(p, dt.plane(ax.origin, n, name=name), f"{base.name} turned {fmt_num(deg)} deg about {ax.name}")
        if how == "MID":
            f1, f2 = a.entity("FACE", "face 1"), a.entity("FACE", "face 2")
            a.done()
            (c1, n1), (c2, _n2) = _face_plane(p, f1, what), _face_plane(p, f2, what)
            if abs(abs(dt.dot(n1, _n2)) - 1) > 1e-6:
                raise CommandError(f"PLANE: faces {f1} and {f2} are not parallel")
            gap = dt.dot(dt.sub(c2, c1), n1)
            return _add(p, dt.plane(c1, n1, name=name).moved(gap / 2), f"half way between faces {f1} and {f2}")
        if how == "NORMAL":
            eid = a.entity("EDGE", "the edge")
            t = a.num("t", 0.0)
            a.done()
            if not 0 <= t <= 1:
                raise CommandError("PLANE: t must be from 0 (start of the edge) to 1 (end)")
            pt, tan = ft.edge_frame(p.model.entity_shape("EDGE", eid), t)
            return _add(p, dt.plane(pt, tan, name=name), f"across edge {eid} at t = {fmt_num(t)}")
    except dt.DatumError as exc:
        raise CommandError(f"PLANE: {exc}") from None
    raise CommandError(f"PLANE: how must be one of {', '.join(PLANE_HOW)}")


def _rotate(v: dt.P3, k: dt.P3, deg: float) -> dt.P3:
    """v turned by deg about unit axis k (right hand)."""
    import math

    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    kv = dt.cross(k, v)
    kd = dt.dot(k, v)
    return tuple(v[i] * c + kv[i] * s + k[i] * kd * (1 - c) for i in range(3))  # type: ignore[return-value]


AXIS_HOW = ("X", "Y", "Z", "PD", "2P", "EDGE", "FACE", "PLANES")


@command(
    "AXIS",
    Arg("name", Text), Arg("how", str, help="X Y Z · PD · 2P · EDGE · FACE · PLANES"), *_VALS,
    help="Datum axis. AXIS, name, Z · PD, x,y,z, dx,dy,dz (point and direction) · 2P, p1, p2 · "
         "EDGE, id (along a straight edge, or the axis of a round one) · FACE, id (axis of a cylinder or cone, "
         "or the normal through a flat face's centre) · PLANES, plane1, plane2 (where they meet)",
)
def axis_(p: Processor, name, how, **raws):
    what = "AXIS"
    _check_name(p, name, what)
    a = _Args(p, what, list(raws.values()))
    m = p.model
    try:
        if how in dt.BASE_AXES:
            a.done()
            return _add(p, dt.axis((0, 0, 0), dt.BASE_AXES[how], name), f"world {how}")
        if how == "PD":
            o, d = a.point("point"), a.point("direction")
            a.done()
            return _add(p, dt.axis(o, d, name), "point and direction")
        if how == "2P":
            p1, p2 = a.point("point 1"), a.point("point 2")
            a.done()
            return _add(p, dt.axis(p1, dt.sub(p2, p1), name), "through 2 points")
        if how == "EDGE":
            eid = a.entity("EDGE", "the edge")
            a.done()
            e = m.entity_shape("EDGE", eid)
            line = ft.edge_line(e)
            if line:
                return _add(p, dt.axis(line[0], line[1], name), f"along edge {eid}")
            circ = ft.edge_circle(e)
            if circ:
                return _add(p, dt.axis(circ[0], circ[1], name), f"axis of round edge {eid}")
            raise CommandError(f"AXIS: edge {eid} is neither straight nor round")
        if how == "FACE":
            fid = a.entity("FACE", "the face")
            a.done()
            f = m.entity_shape("FACE", fid)
            ax = ft.face_axis(f)
            if ax:
                return _add(p, dt.axis(ax[0], ax[1], name), f"axis of face {fid}")
            c, n = _face_plane(p, fid, what)
            return _add(p, dt.axis(c, n, name), f"normal of face {fid}")
        if how == "PLANES":
            p1 = plane_ref(p, a.word("plane 1"), what)
            p2 = plane_ref(p, a.word("plane 2"), what)
            a.done()
            d = dt.cross(p1.z, p2.z)
            if dt.norm(d) < 1e-9:
                raise CommandError(f"AXIS: planes {p1.name} and {p2.name} are parallel, so they do not meet in a line")
            # the point on both planes nearest the first plane's origin
            n1, n2 = p1.z, p2.z
            h1, h2 = dt.dot(n1, p1.origin), dt.dot(n2, p2.origin)
            dd = dt.dot(d, d)
            pt = dt.mul(dt.add(dt.mul(dt.cross(n2, d), h1), dt.mul(dt.cross(d, n1), h2)), 1 / dd)
            return _add(p, dt.axis(pt, d, name), f"where {p1.name} meets {p2.name}")
    except dt.DatumError as exc:
        raise CommandError(f"AXIS: {exc}") from None
    raise CommandError(f"AXIS: how must be one of {', '.join(AXIS_HOW)}")


POINT_HOW = ("XYZ", "VERTEX", "CENTER", "ON")


@command(
    "POINT",
    Arg("name", Text), Arg("how", str, help="XYZ · VERTEX · CENTER · ON"), *_VALS,
    help="Datum point. POINT, name, XYZ, x,y,z · VERTEX, id · CENTER, kind, id (centre of a round edge, "
         "or the middle of a face, edge or body) · ON, edge, t (at fraction t along an edge)",
)
def point_(p: Processor, name, how, **raws):
    what = "POINT"
    _check_name(p, name, what)
    a = _Args(p, what, list(raws.values()))
    m = p.model
    if how == "XYZ":
        o = a.point("the point")
        a.done()
        return _add(p, dt.point(o, name), "coordinates")
    if how == "VERTEX":
        vid = a.entity("VERTEX", "the vertex")
        a.done()
        return _add(p, dt.point(ft.vertex_point(m.entity_shape("VERTEX", vid)), name), f"at vertex {vid}")
    if how in ("CENTER", "CENTRE"):
        try:
            kind = check_kind(a.word("the kind"))
        except ModelError as exc:
            raise CommandError(f"POINT: {exc}") from None
        if kind == "BODY":
            from .queries import centre

            bid = p._body_arg(_POINT_CMD(), a.word("the body"))
            a.done()
            return _add(p, dt.point(tuple(centre("BODY", m.body(bid).shape)), name), f"centre of body {bid}")
        gid = a.entity(kind, f"the {kind.lower()}")
        a.done()
        shape = m.entity_shape(kind, gid)
        if kind == "EDGE":
            circ = ft.edge_circle(shape)
            if circ:
                return _add(p, dt.point(circ[0], name), f"centre of round edge {gid}")
        from .queries import centre

        return _add(p, dt.point(tuple(centre(kind, shape)), name), f"middle of {kind.lower()} {gid}")
    if how == "ON":
        eid = a.entity("EDGE", "the edge")
        t = a.num("t", 0.5)
        a.done()
        if not 0 <= t <= 1:
            raise CommandError("POINT: t must be from 0 (start of the edge) to 1 (end)")
        pt, _ = ft.edge_frame(m.entity_shape("EDGE", eid), t)
        return _add(p, dt.point(pt, name), f"on edge {eid} at t = {fmt_num(t)}")
    raise CommandError(f"POINT: how must be one of {', '.join(POINT_HOW)}")


def _POINT_CMD():
    from .processor import REGISTRY

    return REGISTRY["POINT"]


@command("DATUM", Arg("action", str, help="DELETE"), Arg("name", Text),
         help="DATUM, DELETE, name removes a datum plane, axis or point. LIST, DATUMS lists them.")
def datum_(p: Processor, action, name):
    if action not in ("DELETE", "DEL"):
        raise CommandError("DATUM: the action is DELETE (LIST, DATUMS lists them)")
    try:
        d = p.model.remove_datum(name)
    except ModelError as exc:
        raise CommandError(f"DATUM: {exc}") from None
    return f"deleted datum {d.kind.lower()} {d.name}"


@command("WORKPLANE", Arg("plane", Raw, "OFF", "a datum plane, XY/YZ/ZX, or OFF"),
         help="Draw new shapes on a plane: WORKPLANE, top. Then the x, y, z of primitives, curves, profiles and HOLE "
              "are measured in that plane (x and y along it, z out of it). WORKPLANE, OFF goes back to world XYZ.")
def workplane(p: Processor, plane):
    word = plane.strip()
    if not word or word.upper() in ("OFF", "XY", "WORLD"):
        p.model.set_workplane(None)
        return "work plane: world XY (coordinates are world X, Y, Z)"
    if is_ident(word):
        try:
            v = p._lookup(word.upper())
            if isinstance(v, str):
                word = v
        except KeyError:
            pass
    d = plane_ref(p, word, "WORKPLANE")
    p.model.set_workplane(d)
    return f"work plane {d.name}: origin {_fmt(d.origin)}, x {_fmt(d.x)}, y {_fmt(d.y)}, z {_fmt(d.z)}"


def place(p: Processor, shape):
    """A new shape built from typed numbers goes onto the work plane."""
    return ft.to_world(shape, p.model.workplane)


def world_point(p: Processor, x, y, z) -> dt.P3:
    wp = p.model.workplane
    return (x, y, z) if wp is None else wp.point(x, y, z)


def world_dir(p: Processor, d) -> dt.P3:
    wp = p.model.workplane
    return tuple(d) if wp is None else wp.direction(d)  # type: ignore[return-value]


# =============================================================================
# HOLE
# =============================================================================


@command(
    "HOLE",
    Arg("b", BodyRef, help="the body to drill"),
    Arg("x"), Arg("y"), Arg("z"),
    Arg("d", help="diameter"),
    Arg("depth", float, 0.0, "depth (0 = through everything)"),
    Arg("kind", str, "SIMPLE", "SIMPLE, CBORE (counterbore) or CSINK (countersink)"),
    Arg("d2", float, 0.0, "counterbore or countersink diameter"),
    Arg("h2", float, 0.0, "counterbore depth, or countersink angle (default 90)"),
    Arg("tip", float, 0.0, "drill point angle, e.g. 118 (0 = flat bottom)"),
    Arg("dx", float, 0.0, "drill direction (default: straight into the face at the point)"),
    Arg("dy", float, 0.0), Arg("dz", float, 0.0),
    help="Drill a hole at (x,y,z) on the surface of a body: HOLE, plate, 20,10,5, 6 (through) · "
         "HOLE, plate, 20,10,5, 6, 8, CBORE, 11, 4 · HOLE, plate, 20,10,5, 6, 0, CSINK, 12 · ... , SIMPLE, , , 118 "
         "for a drill point. One command instead of a cylinder and a subtract.",
)
def hole(p: Processor, b, x, y, z, d, depth, kind, d2, h2, tip, dx, dy, dz):
    from .handlers import _added, combine

    m = p.model
    if d <= 0 or depth < 0:
        raise CommandError("HOLE: the diameter must be positive and the depth 0 (through) or more")
    if kind not in ft.HOLE_KINDS:
        raise CommandError(f"HOLE: kind must be one of {', '.join(ft.HOLE_KINDS)}")
    body = m.body(b)
    at = world_point(p, x, y, z)
    note = ""
    if dx == dy == dz == 0:
        drill, note = _drill_direction(p, body, at)
    else:
        drill = dt.unit(world_dir(p, (dx, dy, dz)))
    through = depth == 0
    if through:
        depth = 2 * robust.diagonal(body.shape) + 1
    try:
        tool = ft.hole_tool(at, drill, d, depth, kind, d2, h2, 0.0 if through else tip)
    except (ft.FeatureError, dt.DatumError) as exc:
        raise CommandError(f"HOLE: {exc}") from None
    before = robust.volume(body.shape)
    shape, maker = combine(p, "SUBTRACT", BRepAlgoAPI_Cut, body.shape, [tool], b)
    if before - robust.volume(shape) < 1e-9 * max(1.0, before):
        raise CommandError(f"HOLE: the hole at {_fmt(at)} misses body {b}; put the point on its surface")
    new = m.replace([b], shape, maker)
    size = f"{'through' if through else 'depth ' + fmt_num(depth)}"
    extra = {"CBORE": f", counterbore {fmt_num(d2)} x {fmt_num(h2)}",
             "CSINK": f", countersink {fmt_num(d2)} at {fmt_num(h2 or 90)} deg"}.get(kind, "")
    return _added(p, new, f"HOLE {fmt_num(d)} {size}{extra} at {_fmt(at)}{note}")


def _drill_direction(p: Processor, body, at: dt.P3):
    """Straight into the flat face the point lies on; else down the work plane's Z."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.gp import gp_Pnt

    v = BRepBuilderAPI_MakeVertex(gp_Pnt(*at)).Vertex()
    tol = 1e-4 * max(1.0, robust.diagonal(body.shape)) + p.model.tolerance
    best = None
    for gid in body.entity_ids["FACE"]:
        f = p.model.entity_shape("FACE", gid)
        dist = BRepExtrema_DistShapeShape(v, f)
        if dist.IsDone() and dist.Value() <= tol:
            plane = ft.face_plane(f)
            if plane is not None:
                return dt.mul(plane[1], -1), f" into face {gid}"
            best = best or gid
    wz = world_dir(p, (0, 0, -1))
    if best is not None:
        return wz, f" (face {best} is curved: drilled along -Z{'' if p.model.workplane is None else ' of the work plane'})"
    return wz, " (not on a face: drilled along -Z)"


# =============================================================================
# SPLIT
# =============================================================================


@command(
    "SPLIT",
    Arg("b", BodyRef, help="the body to split"),
    Arg("by", Raw, help="a plane (datum or XY/YZ/ZX) or a body"),
    Arg("keep", str, "BOTH", "BOTH, ABOVE (normal side) or BELOW (for a plane)"),
    help="Cut a body into pieces: SPLIT, part, mid (by a datum plane) · SPLIT, part, XY · SPLIT, part, cutter "
         "(by the faces of another body, which stays). The piece on the plane's normal side (or the biggest) keeps "
         "the body's ID and name; ABOVE or BELOW keeps only that side.",
)
def split_(p: Processor, b, by, keep):
    from .handlers import _added

    m = p.model
    if keep not in ("BOTH", "ABOVE", "BELOW"):
        raise CommandError("SPLIT: keep must be BOTH, ABOVE or BELOW")
    body = m.body(b)
    word = by.strip()
    plane = None
    tool_body = None
    if is_ident(word) and (word.upper() in dt.BASE_PLANES or word.upper() in m.datums):
        plane = plane_ref(p, word, "SPLIT")
    else:
        from .processor import REGISTRY

        try:
            tool_body = m.body(p._body_arg(REGISTRY["SPLIT"], word))
        except CommandError:
            raise CommandError(f"SPLIT: no plane or body named {word!r} (planes: XY, YZ, ZX"
                               + "".join(f", {d.name}" for d in m.datums.values() if d.kind == "PLANE") + ")") from None
        if tool_body.id == b:
            raise CommandError("SPLIT: a body cannot split itself")
        if keep != "BOTH":
            raise CommandError("SPLIT: ABOVE and BELOW need a plane")
    if plane is not None:
        from .queries import centre

        half = robust.diagonal(body.shape) * 2 + 1
        tools = [ft.plane_face(plane, tuple(centre("BODY", body.shape)), half)]
    else:
        tools = [tool_body.shape]
    if not robust.solids(body.shape):
        raise CommandError(f"SPLIT: body {b} is not a solid")
    try:
        pieces, maker = ft.split(body.shape, tools)
    except ft.FeatureError as exc:
        raise CommandError(f"SPLIT: {exc}") from None
    if len(pieces) < 2:
        what = f"plane {plane.name}" if plane else f"body {tool_body.id}"
        raise CommandError(f"SPLIT: {what} does not cut through body {b}")
    for s in pieces:
        if not robust.is_valid(s):
            raise CommandError("SPLIT: a piece is not a valid shape; the cut probably grazes an edge or face")
    if plane is not None:
        from .queries import centre

        heights = [plane.height(tuple(centre("BODY", s))) for s in pieces]
        order = sorted(range(len(pieces)), key=lambda i: -heights[i])
        if keep == "ABOVE":
            order = [i for i in order if heights[i] > 0]
        elif keep == "BELOW":
            order = [i for i in order if heights[i] < 0][::-1]
        if not order:
            raise CommandError(f"SPLIT: nothing of body {b} is {keep.lower()} plane {plane.name}")
    else:
        vols = [robust.volume(s) for s in pieces]
        order = sorted(range(len(pieces)), key=lambda i: -vols[i])
    kept_copy = body.shape if m.keep else None
    first = m.replace([b], pieces[order[0]], maker, same_id=True)
    others = [m.add_body(pieces[i], "", (maker, [body])) for i in order[1:]]
    if kept_copy is not None:
        k = m.add_body(kept_copy)
        m.set_hidden(k.id, True)
    m.last_body = first.id
    msg = _added(p, first, f"SPLIT body {b} by {plane.name if plane else 'body ' + str(tool_body.id)}")
    if others:
        msg += "; other pieces: bodies " + ", ".join(str(o.id) for o in others)
    dropped = len(pieces) - len(order)
    if dropped:
        msg += f"; dropped {dropped} piece{'s' if dropped > 1 else ''} {'below' if keep == 'ABOVE' else 'above'} the plane"
    return msg


# =============================================================================
# SHELL, DRAFT, OFFSET
# =============================================================================


def _faces_by_body(p: Processor, what: str) -> dict[int, list[int]]:
    m = p.model
    if m.selection_kind != "FACE" or not m.selection:
        raise CommandError(f"{what}: select faces first, e.g. PICK, FACE, 6 or SEL, S, FACE, NORMAL, 0,0,1")
    groups: dict[int, list[int]] = {}
    for gid in m.selection:
        groups.setdefault(m.entity_owner("FACE", gid)[0], []).append(gid)
    return groups


@command(
    "SHELL",
    Arg("t", help="wall thickness"),
    Arg("side", str, "IN", "IN (the wall grows inwards, default) or OUT"),
    help="Hollow out a part with walls of thickness t. Select the faces to open first (PICK, FACE, 6), or select "
         "bodies to make them hollow and closed: SHELL, 2 · SHELL, 1.5, OUT.",
)
def shell(p: Processor, t, side):
    from .handlers import _added, _sig, combine

    m = p.model
    if t <= 0:
        raise CommandError("SHELL: the thickness must be positive")
    if side not in ("IN", "OUT"):
        raise CommandError("SHELL: side must be IN or OUT")
    sign = -1 if side == "IN" else 1
    if m.selection_kind == "BODY" and m.selection:
        groups = {bid: [] for bid in m.selection}
    else:
        groups = _faces_by_body(p, "SHELL")
    msgs = []
    for bid, fids in groups.items():
        body = m.body(bid)
        if not robust.solids(body.shape):
            raise CommandError(f"SHELL: body {bid} is not a solid")
        before = robust.volume(body.shape)
        if not fids:  # closed and hollow: offset the skin, cut it away
            off, _ = ft.offset_shape(body.shape, sign * t)
            if off is None or not robust.is_valid(off):
                raise CommandError(f"SHELL: the wall {t:g} does not fit inside body {bid}; try a thinner wall")
            base, tools = (body.shape, [off]) if side == "IN" else (off, [body.shape])
            shape, maker = combine(p, "SUBTRACT", BRepAlgoAPI_Cut, base, tools, bid)
            if side == "OUT":
                maker = None
            new = m.replace([bid], shape, maker or _NoHist(), same_id=True)
            msgs.append(_added(p, new, f"SHELL {t:g} {side.lower()}, closed, body {bid}"))
            continue
        faces = [m.entity_shape("FACE", f) for f in fids]
        n_faces = len(body.entity_ids["FACE"])

        def good(s) -> bool:
            # a wall too thick for the part can come back as the unchanged
            # solid, still "valid": the wall must really have been made
            if s is None or robust.is_empty(s) or not robust.is_valid(s):
                return False
            if robust.count(s, TopAbs_FACE) <= n_faces - len(faces):
                return False
            v = robust.volume(s)
            return 0 < v < before * (1 - 1e-6) if side == "IN" else v > 0

        def build(v, faces=faces, body=body):
            s, _ = ft.thick_solid(body.shape, faces, sign * v)
            return s if good(s) else None

        shape, maker = ft.thick_solid(body.shape, faces, sign * t)
        if not good(shape):
            limit = robust.largest_working(build, t)
            if limit is None:
                raise CommandError(f"SHELL: body {bid} cannot be shelled with these faces open")
            raise CommandError(f"SHELL: a wall of {t:g} does not fit in body {bid} (small features or tight curves "
                               f"inside). The thickest wall that works here is about {_sig(limit)}.")
        new = m.replace([bid], robust.unwrap(shape), maker, same_id=True)
        msgs.append(_added(p, new, f"SHELL {t:g} {side.lower()}, body {bid} open at face{'s' if len(fids) > 1 else ''} "
                                   + ", ".join(map(str, fids))))
    return "\n".join(msgs)


class _NoHist:
    def IsDeleted(self, _old) -> bool:
        return False

    def Modified(self, _old) -> list:
        return []


@command(
    "DRAFT",
    Arg("angle", help="degrees; positive makes the part narrower along the pull direction"),
    Arg("neutral", Raw, "", "the plane where the faces keep their size (default: the work plane, or XY)"),
    Arg("dx", float, 0.0, "pull direction (default: the neutral plane's normal)"), Arg("dy", float, 0.0),
    Arg("dz", float, 0.0),
    help="Tilt the selected side faces so a moulded or cast part comes out of its mould: "
         "SEL, S, FACE, ... then DRAFT, 3 [, plane [, dx,dy,dz]].",
)
def draft(p: Processor, angle, neutral, dx, dy, dz):
    from .handlers import _added

    m = p.model
    if not 0 < abs(angle) < 89:
        raise CommandError("DRAFT: the angle must be between -89 and 89 degrees, and not 0")
    if neutral.strip():
        word = neutral.strip()
        if is_ident(word):
            try:
                v = p._lookup(word.upper())
                word = v if isinstance(v, str) else word
            except KeyError:
                pass
        plane = plane_ref(p, word, "DRAFT")
    else:
        plane = m.workplane or dt.plane((0, 0, 0), (0, 0, 1), name="XY")
    pull = plane.z if dx == dy == dz == 0 else dt.unit((dx, dy, dz))
    msgs = []
    for bid, fids in _faces_by_body(p, "DRAFT").items():
        body = m.body(bid)
        faces = [m.entity_shape("FACE", f) for f in fids]
        for f, fid in zip(faces, fids):
            got = ft.face_plane(f)
            if got is not None and abs(abs(dt.dot(got[1], pull)) - 1) < 1e-9:
                raise CommandError(f"DRAFT: face {fid} faces the pull direction; draft tilts side faces only")
        shape, maker, bad = ft.draft(body.shape, faces, pull, angle, plane)
        if shape is None:
            which = f"face {fids[bad]}" if bad is not None and bad >= 0 else "these faces"
            raise CommandError(f"DRAFT: {which} of body {bid} cannot be drafted about plane {plane.name} "
                               "(draft works on flat, cylindrical and conical side faces)")
        if robust.is_empty(shape) or not robust.is_valid(shape):
            raise CommandError(f"DRAFT: {angle:g} deg gives an invalid body {bid}; try a smaller angle")
        new = m.replace([bid], robust.unwrap(shape), maker, same_id=True)
        msgs.append(_added(p, new, f"DRAFT {angle:g} deg on {len(fids)} face{'s' if len(fids) > 1 else ''} of body {bid}, "
                                   f"neutral plane {plane.name}"))
    return "\n".join(msgs)


@command(
    "OFFSET",
    Arg("b", BodyRef), Arg("d", help="distance: positive grows the body, negative shrinks it"),
    Arg("corners", str, "ROUND", "ROUND (default) or SHARP corners when growing"),
    help="Grow or shrink a whole body by a distance: OFFSET, part, 2 · OFFSET, part, -1 · OFFSET, part, 2, SHARP.",
)
def offset(p: Processor, b, d, corners):
    from .handlers import _added

    m = p.model
    if d == 0:
        raise CommandError("OFFSET: the distance cannot be 0")
    if corners not in ("ROUND", "SHARP"):
        raise CommandError("OFFSET: corners must be ROUND or SHARP")
    body = m.body(b)
    shape, maker = ft.offset_shape(body.shape, d, corners == "SHARP")
    if shape is None or robust.is_empty(shape) or not robust.is_valid(shape):
        raise CommandError(f"OFFSET: body {b} cannot be offset by {d:g}" +
                           ("; it is thinner than that somewhere" if d < 0 else ""))
    if robust.solids(body.shape) and robust.volume(shape) <= 0:
        raise CommandError(f"OFFSET: shrinking body {b} by {-d:g} leaves nothing")
    new = m.replace([b], robust.unwrap(shape), maker, same_id=True)
    return _added(p, new, f"OFFSET {d:g} of body {b}")
