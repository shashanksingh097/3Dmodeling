"""The built-in commands.

Each handler gets the processor and its parsed arguments, changes the model
through the model's API, and returns a short message.
"""

from __future__ import annotations

import math
import os

from OCP.BRep import BRep_Builder
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex, BRepBuilderAPI_Transform
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer, BRepFilletAPI_MakeFillet
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepPrimAPI import (
    BRepPrimAPI_MakeBox,
    BRepPrimAPI_MakeCone,
    BRepPrimAPI_MakeCylinder,
    BRepPrimAPI_MakeSphere,
    BRepPrimAPI_MakeTorus,
    BRepPrimAPI_MakeWedge,
)
from OCP.BRepTools import BRepTools
from OCP.GeomAbs import GeomAbs_CurveType, GeomAbs_SurfaceType
from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCP.StlAPI import StlAPI_Writer
from OCP.TopAbs import TopAbs_REVERSED
from OCP.TopoDS import TopoDS, TopoDS_Compound

try:  # OCP 7.x
    from OCP.TopTools import TopTools_ListOfShape
except ImportError:  # OCP 8.x
    from OCP.collections import List_TopoDS_Shape as TopTools_ListOfShape  # type: ignore[no-redef]

from ..core.model import ENTITY_KINDS, SELECT_KINDS, UNITS, ModelError, check_kind
from ..lang.expr import ExprError, Vec, fmt_num, format_value
from ..lang.script import COMPARE_WORDS, first_code_line, is_ident
from . import queries
from .processor import REGISTRY, Arg, BodyRef, CommandError, Path, Processor, Raw, Text, command


def _static(cls, name):
    """OCP 7.x names static methods with a "_s" suffix; OCP 8 mostly dropped it."""
    return getattr(cls, name + "_s", None) or getattr(cls, name)


_as_edge = _static(TopoDS, "Edge")
_as_face = _static(TopoDS, "Face")

VIEWS = ("ISO", "TOP", "BOTTOM", "FRONT", "BACK", "LEFT", "RIGHT")


def _added(p: Processor, body, what: str) -> str:
    n = {k: len(body.entity_ids[k]) for k in ENTITY_KINDS}
    name = "" if body.name == f"body{body.id}" else f" '{body.name}'"
    return f"{what} -> body {body.id}{name} ({n['FACE']} faces, {n['EDGE']} edges, {n['VERTEX']} vertices)"


def _new(p: Processor, shape, what: str) -> str:
    return _added(p, p.model.add_body(shape), what)


def _axis(x, y, z, dx, dy, dz, what: str) -> gp_Ax2:
    if dx == dy == dz == 0:
        raise CommandError(f"{what}: the axis direction cannot be (0, 0, 0)")
    return gp_Ax2(gp_Pnt(x, y, z), gp_Dir(dx, dy, dz))


_AXIS_ARGS = (
    Arg("dx", float, 0.0, "axis direction (default +Z)"),
    Arg("dy", float, 0.0),
    Arg("dz", float, 1.0),
)

# =============================================================================
# Primitives
# =============================================================================


@command(
    "BLOCK",
    Arg("x"), Arg("y"), Arg("z"), Arg("dx"), Arg("dy"), Arg("dz"),
    help="Box from corner (x,y,z) with sizes dx,dy,dz.",
)
def block(p: Processor, x, y, z, dx, dy, dz):
    if min(dx, dy, dz) <= 0:
        raise CommandError("BLOCK: sizes must be positive")
    return _new(p, BRepPrimAPI_MakeBox(gp_Pnt(x, y, z), dx, dy, dz).Shape(), "BLOCK")


@command(
    "CYL",
    Arg("x"), Arg("y"), Arg("z"), Arg("r"), Arg("h"), *_AXIS_ARGS,
    Arg("angle", float, 360.0, "sweep angle in degrees, for a sector"),
    help="Cylinder with base center (x,y,z), radius r, height h, along axis (dx,dy,dz).",
)
def cyl(p: Processor, x, y, z, r, h, dx, dy, dz, angle):
    if r <= 0 or h <= 0:
        raise CommandError("CYL: radius and height must be positive")
    if not 0 < angle <= 360:
        raise CommandError("CYL: angle must be in (0, 360]")
    ax = _axis(x, y, z, dx, dy, dz, "CYL")
    mk = BRepPrimAPI_MakeCylinder(ax, r, h) if angle == 360 else BRepPrimAPI_MakeCylinder(ax, r, h, math.radians(angle))
    return _new(p, mk.Shape(), "CYL")


@command(
    "TUBE",
    Arg("x"), Arg("y"), Arg("z"), Arg("ro", help="outer radius"), Arg("ri", help="inner radius"), Arg("h"),
    *_AXIS_ARGS,
    help="Hollow cylinder (pipe) with base center (x,y,z) along axis (dx,dy,dz).",
)
def tube(p: Processor, x, y, z, ro, ri, h, dx, dy, dz):
    if not ro > ri > 0 or h <= 0:
        raise CommandError("TUBE: need outer radius > inner radius > 0 and a positive height")
    ax = _axis(x, y, z, dx, dy, dz, "TUBE")
    outer = BRepPrimAPI_MakeCylinder(ax, ro, h).Shape()
    inner = BRepPrimAPI_MakeCylinder(ax, ri, h).Shape()
    algo = BRepAlgoAPI_Cut(outer, inner)
    if not algo.IsDone():
        raise CommandError("TUBE: kernel failed")
    return _new(p, algo.Shape(), "TUBE")


@command("SPHERE", Arg("x"), Arg("y"), Arg("z"), Arg("r"), help="Sphere with center (x,y,z), radius r.")
def sphere(p: Processor, x, y, z, r):
    if r <= 0:
        raise CommandError("SPHERE: radius must be positive")
    return _new(p, BRepPrimAPI_MakeSphere(gp_Pnt(x, y, z), r).Shape(), "SPHERE")


@command(
    "CONE",
    Arg("x"), Arg("y"), Arg("z"), Arg("r1"), Arg("r2"), Arg("h"), *_AXIS_ARGS,
    help="Cone: base center (x,y,z), base radius r1, top radius r2, height h, along axis (dx,dy,dz).",
)
def cone(p: Processor, x, y, z, r1, r2, h, dx, dy, dz):
    if r1 < 0 or r2 < 0 or r1 == r2 == 0 or h <= 0:
        raise CommandError("CONE: radii must be >= 0 (not both 0) and height positive")
    if r1 == r2:
        raise CommandError("CONE: equal radii make a cylinder; use CYL")
    ax = _axis(x, y, z, dx, dy, dz, "CONE")
    return _new(p, BRepPrimAPI_MakeCone(ax, r1, r2, h).Shape(), "CONE")


@command(
    "TORUS",
    Arg("x"), Arg("y"), Arg("z"), Arg("r1", help="ring radius"), Arg("r2", help="tube radius"), *_AXIS_ARGS,
    help="Torus centered at (x,y,z), ring around axis (dx,dy,dz) (default: in the XY plane).",
)
def torus(p: Processor, x, y, z, r1, r2, dx, dy, dz):
    if r2 <= 0 or r1 <= r2:
        raise CommandError("TORUS: need ring radius > tube radius > 0")
    ax = _axis(x, y, z, dx, dy, dz, "TORUS")
    return _new(p, BRepPrimAPI_MakeTorus(ax, r1, r2).Shape(), "TORUS")


@command(
    "WEDGE",
    Arg("x"), Arg("y"), Arg("z"), Arg("dx"), Arg("dy"), Arg("dz"), Arg("ltx", help="top length along X (0 = sharp ridge)"),
    help="Wedge from corner (x,y,z): base dx by dz, height dy, top face ltx long in X.",
)
def wedge(p: Processor, x, y, z, dx, dy, dz, ltx):
    if min(dx, dy, dz) <= 0 or ltx < 0:
        raise CommandError("WEDGE: sizes must be positive and ltx >= 0")
    ax = gp_Ax2(gp_Pnt(x, y, z), gp_Dir(0, 0, 1), gp_Dir(1, 0, 0))
    return _new(p, BRepPrimAPI_MakeWedge(ax, dx, dy, dz, ltx).Shape(), "WEDGE")


# =============================================================================
# Booleans and blends
# =============================================================================
# The inputs are consumed; the result inherits the first input's name, and
# faces/edges that survive keep their IDs. Keeping inputs (KEEP, ON) is M2.

_TOOLS = [Arg(f"t{i}", BodyRef, 0) for i in range(2, 9)]


def _shape_list(shapes) -> TopTools_ListOfShape:
    lst = TopTools_ListOfShape()
    for s in shapes:
        lst.Append(s)
    return lst


def _boolean(p: Processor, name: str, op, a: int, tools: list[int]) -> str:
    tools = [t for t in tools if t]
    if not tools:
        raise CommandError(f"{name}: give a base body and at least one tool body")
    m = p.model
    if a in tools or len(set(tools)) != len(tools):
        raise CommandError(f"{name}: a body cannot be used twice")
    base = m.body(a).shape
    tool_shapes = [m.body(t).shape for t in tools]
    algo = op()
    algo.SetArguments(_shape_list([base]))
    algo.SetTools(_shape_list(tool_shapes))
    if m.tolerance > 0:
        algo.SetFuzzyValue(m.tolerance)
    algo.Build()
    if not algo.IsDone():
        raise CommandError(f"{name}: the kernel could not combine bodies {', '.join(map(str, [a] + tools))}")
    body = m.replace([a] + tools, algo.Shape(), algo)
    return _added(p, body, f"{name} of {', '.join(map(str, [a] + tools))}")


@command("UNION", Arg("a", BodyRef), Arg("b", BodyRef), *_TOOLS,
         help="Fuse bodies into one new body: UNION, a, b [, c ...] (up to 8; IDs or names).")
def union(p: Processor, a, b, **more):
    return _boolean(p, "UNION", BRepAlgoAPI_Fuse, a, [b, *more.values()])


@command("SUBTRACT", Arg("a", BodyRef), Arg("b", BodyRef), *_TOOLS,
         help="Cut tool bodies b, c ... from body a: SUBTRACT, a, b [, c ...].")
def subtract(p: Processor, a, b, **more):
    return _boolean(p, "SUBTRACT", BRepAlgoAPI_Cut, a, [b, *more.values()])


@command("INTERSECT", Arg("a", BodyRef), Arg("b", BodyRef), *_TOOLS,
         help="Keep only the common volume: INTERSECT, a, b [, c ...].")
def intersect(p: Processor, a, b, **more):
    return _boolean(p, "INTERSECT", BRepAlgoAPI_Common, a, [b, *more.values()])


def _blend(p: Processor, name: str, size: float) -> str:
    """Round or bevel the selected edges (all edges of selected bodies)."""
    m = p.model
    if size <= 0:
        raise CommandError(f"{name}: size must be positive")
    if not m.selection or m.selection_kind not in ("EDGE", "BODY"):
        raise CommandError(f"{name}: select edges (or bodies) first, e.g. PICK, EDGE, 5")
    if m.selection_kind == "BODY":
        groups = {bid: list(m.bodies[bid].entity_ids["EDGE"]) for bid in m.selection}
    else:
        groups: dict[int, list[int]] = {}
        for gid in m.selection:
            groups.setdefault(m.entity_owner("EDGE", gid)[0], []).append(gid)
    msgs = []
    for bid, edges in groups.items():
        maker_cls = BRepFilletAPI_MakeFillet if name == "FILLET" else BRepFilletAPI_MakeChamfer
        mk = maker_cls(m.bodies[bid].shape)
        for gid in edges:
            mk.Add(size, _as_edge(m.entity_shape("EDGE", gid)))
        try:
            mk.Build()
        except Exception:
            mk = None
        if mk is None or not mk.IsDone():
            raise CommandError(f"{name}: the kernel failed on body {bid} (size too large?)")
        body = m.replace([bid], mk.Shape(), mk)
        msgs.append(_added(p, body, f"{name} {size:g} on {len(edges)} edges of body {bid}"))
    return "\n".join(msgs)


@command("FILLET", Arg("r"), help="Round the selected edges (or all edges of selected bodies) with radius r.")
def fillet(p: Processor, r):
    return _blend(p, "FILLET", r)


@command("CHAMFER", Arg("d"), help="Bevel the selected edges (or all edges of selected bodies) by distance d.")
def chamfer(p: Processor, d):
    return _blend(p, "CHAMFER", d)


# =============================================================================
# Transforms and body management
# =============================================================================


def _transform(p: Processor, bid: int, trsf: gp_Trsf, what: str, copy: bool) -> str:
    m = p.model
    shape = m.body(bid).shape
    mk = BRepBuilderAPI_Transform(shape, trsf, True)
    if not mk.IsDone():
        raise CommandError(f"{what}: kernel failed")
    if copy:
        return _new(p, mk.Shape(), f"{what} of body {bid}")
    body = m.replace([bid], mk.Shape(), mk, same_id=True)
    return f"{what} body {bid}" + ("" if body.name == f"body{bid}" else f" '{body.name}'")


@command("MOVE", Arg("b", BodyRef), Arg("dx", float, 0.0), Arg("dy", float, 0.0), Arg("dz", float, 0.0),
         help="Move a body by (dx,dy,dz). It keeps its ID, name and entity IDs.")
def move(p: Processor, b, dx, dy, dz):
    t = gp_Trsf()
    t.SetTranslation(gp_Vec(dx, dy, dz))
    return _transform(p, b, t, "moved", copy=False)


@command(
    "ROTATE",
    Arg("b", BodyRef), Arg("angle", help="degrees"),
    Arg("x", float, 0.0, "a point on the axis"), Arg("y", float, 0.0), Arg("z", float, 0.0),
    *_AXIS_ARGS,
    help="Rotate a body by angle (degrees) about the axis through (x,y,z) along (dx,dy,dz).",
)
def rotate(p: Processor, b, angle, x, y, z, dx, dy, dz):
    if dx == dy == dz == 0:
        raise CommandError("ROTATE: the axis direction cannot be (0, 0, 0)")
    t = gp_Trsf()
    t.SetRotation(gp_Ax1(gp_Pnt(x, y, z), gp_Dir(dx, dy, dz)), math.radians(angle))
    return _transform(p, b, t, f"rotated {angle:g} deg", copy=False)


@command("COPY", Arg("b", BodyRef), Arg("dx", float, 0.0), Arg("dy", float, 0.0), Arg("dz", float, 0.0),
         help="Copy a body, offset by (dx,dy,dz). The copy is a new body (LAST).")
def copy_(p: Processor, b, dx, dy, dz):
    t = gp_Trsf()
    t.SetTranslation(gp_Vec(dx, dy, dz))
    return _transform(p, b, t, "COPY", copy=True)


@command(
    "MIRROR",
    Arg("b", BodyRef), Arg("x", float, 0.0, "a point on the plane"), Arg("y", float, 0.0), Arg("z", float, 0.0),
    Arg("nx", float, 1.0, "plane normal (default: the YZ plane)"), Arg("ny", float, 0.0), Arg("nz", float, 0.0),
    Arg("copy", int, 1, "1 = make a mirrored copy (default), 0 = mirror in place"),
    help="Mirror a body in the plane through (x,y,z) with normal (nx,ny,nz).",
)
def mirror(p: Processor, b, x, y, z, nx, ny, nz, copy):
    if nx == ny == nz == 0:
        raise CommandError("MIRROR: the normal cannot be (0, 0, 0)")
    t = gp_Trsf()
    t.SetMirror(gp_Ax2(gp_Pnt(x, y, z), gp_Dir(nx, ny, nz)))
    return _transform(p, b, t, "MIRROR", copy=bool(copy))


@command("DELETE", Arg("b", BodyRef), help="Delete a body.")
def delete(p: Processor, b):
    body = p.model.remove_body(b)
    return f"deleted body {body.id}"


@command("NAME", Arg("b", BodyRef), Arg("name", Text),
         help="Name a body: NAME, LAST, base. Bodies made from it (booleans, fillets) keep the name.")
def name_(p: Processor, b, name):
    if not is_ident(name):
        raise CommandError(f"NAME: {name!r} is not a valid name (letters, digits, _)")
    if name.upper() in ("LAST", "SEL", "ALL"):
        raise CommandError(f"NAME: {name} is reserved")
    p.model.rename(b, name)
    return f"body {b} is '{name}'"


@command("HIDE", Arg("b", BodyRef), help="Hide a body in the viewport (it stays in the model).")
def hide(p: Processor, b):
    p.model.set_hidden(b, True)
    return f"hid body {b}"


@command("SHOW", Arg("b", Raw, "ALL", "a body, or ALL"), help="Show a hidden body again (default: all of them).")
def show(p: Processor, b):
    if b.strip().upper() == "ALL":
        for bid in sorted(p.model.hidden):
            p.model.set_hidden(bid, False)
        return "showing all bodies"
    bid = p._body_arg(REGISTRY["SHOW"], b)
    p.model.set_hidden(bid, False)
    return f"showing body {bid}"


@command("CLEAR", help="Delete every body and restart IDs. Parameters and macros stay.")
def clear(p: Processor):
    p.model.clear()
    return "model cleared"


# =============================================================================
# Selection
# =============================================================================


@command(
    "PICK",
    Arg("kind", str, help="BODY, FACE, EDGE or VERTEX"),
    Arg("id", int),
    Arg("mode", str, "S", help="S = new selection, A = add, U = remove"),
    help="What a viewport click emits: select one entity by its ID.",
)
def pick(p: Processor, kind, id, mode):
    p.model.select(kind, [id], mode)
    return _describe_selection(p)


CRITERIA = ("ID", "BODY", "NORMAL", "LOC", "BOX", "AT", "TYPE", "SIZE", "RADIUS", "OF", "SET")


@command(
    "SEL",
    Arg("mode", str, help="S new, R reselect, A add, U unselect, ALL, NONE, INVE"),
    Arg("kind", str, "", help="BODY, FACE, EDGE or VERTEX"),
    Arg("crit", str, "", help="ID, BODY, NORMAL, LOC, BOX, AT, TYPE, SIZE, RADIUS, OF, SET"),
    *[Arg(f"v{i}", Raw, "") for i in range(1, 7)],
    help=(
        "Select by criterion. SEL, S, FACE, ID, 3, 6 (IDs 3..6; 'ID' may be left out) · "
        "SEL, S, FACE, NORMAL, 0,0,1 · SEL, R, FACE, LOC, Z, 10 [, 20] · SEL, A, EDGE, SIZE, GT, 10 · "
        "SEL, S, FACE, BOX, x0,y0,z0, x1,y1,z1 · SEL, S, FACE, AT, x,y,z · SEL, S, FACE, TYPE, CYLINDER · "
        "SEL, S, EDGE, RADIUS, EQ, 4 · SEL, S, EDGE, OF, FACE (edges of the selected faces) · "
        "SEL, S, FACE, BODY, 3 · SEL, S, FACE, SET, top · SEL, NONE · SEL, ALL, FACE · SEL, INVE"
    ),
)
def sel(p: Processor, mode, kind, crit, v1, v2, v3, v4, v5, v6):
    m = p.model
    vals = [v for v in (v1, v2, v3, v4, v5, v6)]
    if mode == "NONE":
        m.select_none()
        return "selection cleared"
    if mode == "INVE":
        k = check_kind(kind) if kind else m.selection_kind
        current = set(m.selection) if k == m.selection_kind else set()
        m.select(k, [i for i in m.entity_ids(k) if i not in current], "S")
        return _describe_selection(p)
    if not kind:
        raise CommandError("SEL: kind is required (BODY, FACE, EDGE or VERTEX)")
    k = check_kind(kind)
    if mode == "ALL":
        m.select(k, m.entity_ids(k), "S")
        return _describe_selection(p)
    if mode not in ("S", "R", "A", "U"):
        raise CommandError(f"SEL: unknown mode {mode!r} (S, R, A, U, ALL, NONE, INVE)")
    if crit and crit not in CRITERIA:  # SEL, S, FACE, 3, 6: IDs without the word ID
        vals = [crit] + vals[:-1]
        crit = "ID"
    ids = _match(p, k, crit or "ID", [v for v in vals])
    m.select(k, ids, mode)
    return _describe_selection(p)


def _num(p: Processor, text: str, what: str) -> float:
    if text == "":
        raise CommandError(f"SEL: {what} is required")
    v = p.evaluate(text)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise CommandError(f"SEL: {what} must be a number, got {format_value(v)}")
    return float(v)


def _nums(p: Processor, vals: list[str], n: int, what: str) -> list[float]:
    """Read n numbers; a point value fills several."""
    out: list[float] = []
    for t in vals:
        if len(out) >= n or t == "":
            break
        v = p.evaluate(t)
        if isinstance(v, Vec):
            out.extend(v)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out.append(float(v))
        else:
            raise CommandError(f"SEL: {what} must be numbers")
    if len(out) < n:
        raise CommandError(f"SEL: {what} needs {n} numbers")
    return out[:n]


def _compare(p: Processor, vals: list[str], what: str):
    op = vals[0].upper() if vals and vals[0] else ""
    if op == "BETWEEN":
        lo, hi = _num(p, vals[1], f"{what} low"), _num(p, vals[2], f"{what} high")
        return lambda x: lo - 1e-9 <= x <= hi + 1e-9
    if op not in COMPARE_WORDS:
        raise CommandError(f"SEL: {what} needs an operator: EQ NE LT GT LE GE or BETWEEN")
    ref = _num(p, vals[1] if len(vals) > 1 else "", what)
    tol = 1e-6 * max(1.0, abs(ref))
    return {
        "EQ": lambda x: abs(x - ref) <= tol,
        "NE": lambda x: abs(x - ref) > tol,
        "LT": lambda x: x < ref - tol,
        "GT": lambda x: x > ref + tol,
        "LE": lambda x: x <= ref + tol,
        "GE": lambda x: x >= ref - tol,
    }[op]


_SURF = {
    "PLANE": GeomAbs_SurfaceType.GeomAbs_Plane,
    "CYLINDER": GeomAbs_SurfaceType.GeomAbs_Cylinder,
    "CONE": GeomAbs_SurfaceType.GeomAbs_Cone,
    "SPHERE": GeomAbs_SurfaceType.GeomAbs_Sphere,
    "TORUS": GeomAbs_SurfaceType.GeomAbs_Torus,
    "BSPLINE": GeomAbs_SurfaceType.GeomAbs_BSplineSurface,
}
_CURVE = {
    "LINE": GeomAbs_CurveType.GeomAbs_Line,
    "CIRCLE": GeomAbs_CurveType.GeomAbs_Circle,
    "ELLIPSE": GeomAbs_CurveType.GeomAbs_Ellipse,
    "BSPLINE": GeomAbs_CurveType.GeomAbs_BSplineCurve,
}


def _radius(kind: str, shape) -> float | None:
    if kind == "EDGE":
        c = BRepAdaptor_Curve(_as_edge(shape))
        return c.Circle().Radius() if c.GetType() == _CURVE["CIRCLE"] else None
    if kind == "FACE":
        s = BRepAdaptor_Surface(_as_face(shape))
        t = s.GetType()
        if t == _SURF["CYLINDER"]:
            return s.Cylinder().Radius()
        if t == _SURF["SPHERE"]:
            return s.Sphere().Radius()
    return None


def _normal(shape) -> tuple[float, float, float] | None:
    """Outward normal of a planar face, or None for curved faces."""
    face = _as_face(shape)
    s = BRepAdaptor_Surface(face)
    if s.GetType() != _SURF["PLANE"]:
        return None
    d = s.Plane().Axis().Direction()
    n = (d.X(), d.Y(), d.Z())
    if face.Orientation() == TopAbs_REVERSED:
        n = (-n[0], -n[1], -n[2])
    return n


def _size(kind: str, shape) -> float:
    return queries.props("BODY" if kind == "BODY" else kind, shape).Mass() if kind != "VERTEX" else 0.0


def _match(p: Processor, kind: str, crit: str, vals: list[str]) -> list[int]:
    m = p.model
    all_ids = m.entity_ids(kind)

    def shapes():
        for i in all_ids:
            yield i, m.entity_shape(kind, i)

    if crit == "ID":
        a = int(_num(p, vals[0], "the first ID"))
        b = int(_num(p, vals[1], "the last ID")) if vals[1] else a
        lo, hi = min(a, b), max(a, b)
        ids = [i for i in all_ids if lo <= i <= hi]
        if not ids:
            raise CommandError(f"SEL: no {kind} with ID {lo}" + (f" to {hi}" if hi != lo else ""))
        return ids
    if crit == "BODY":
        if kind == "BODY":
            raise CommandError("SEL: use SEL, S, BODY, ID, n for bodies")
        bid = int(_num(p, vals[0], "the body ID"))
        return list(m.body(bid).entity_ids[kind])
    if crit == "SET":
        if not vals[0]:
            raise CommandError("SEL: give the set name")
        skind, ids = m.named_set(vals[0])
        if skind != kind:
            raise CommandError(f"SEL: set {vals[0]!r} holds {skind}, not {kind}")
        return ids
    if crit == "OF":
        src = check_kind(vals[0] or "BODY")
        if src != m.selection_kind or not m.selection:
            raise CommandError(f"SEL: OF {src} needs {src.lower()}s selected first")
        if kind == "BODY":
            return sorted({m.entity_owner(src, i)[0] for i in m.selection}) if src != "BODY" else list(m.selection)
        from OCP.TopExp import TopExp_Explorer

        from ..core.model import _TOPABS

        out: list[int] = []
        for sid in m.selection:
            bid = sid if src == "BODY" else m.entity_owner(src, sid)[0]
            body = m.bodies[bid]
            exp = TopExp_Explorer(m.entity_shape(src, sid), _TOPABS[kind])
            while exp.More():
                idx = body.maps[kind].FindIndex(exp.Current())
                if idx:
                    gid = body.entity_ids[kind][idx - 1]
                    if gid not in out:
                        out.append(gid)
                exp.Next()
        return sorted(out)
    if crit == "NORMAL":
        if kind != "FACE":
            raise CommandError("SEL: NORMAL works on faces")
        n = _nums(p, vals[:3], 3, "NORMAL")
        tol = _num(p, vals[3], "tolerance") if vals[3] else 1.0
        ln = math.sqrt(sum(c * c for c in n))
        if ln == 0:
            raise CommandError("SEL: NORMAL cannot be (0, 0, 0)")
        n = [c / ln for c in n]
        cos_tol = math.cos(math.radians(tol))
        out = []
        for i, s in shapes():
            fn = _normal(s)
            if fn and sum(a * b for a, b in zip(fn, n)) >= cos_tol - 1e-12:
                out.append(i)
        return out
    if crit == "LOC":
        axis = (vals[0] or "").upper()
        if axis not in ("X", "Y", "Z"):
            raise CommandError("SEL: LOC needs an axis X, Y or Z, then a value or a min and max")
        lo = _num(p, vals[1], "LOC value")
        hi = _num(p, vals[2], "LOC max") if vals[2] else lo
        lo, hi = min(lo, hi), max(lo, hi)
        tol = 1e-6 * max(1.0, abs(lo), abs(hi)) + p.model.tolerance
        k = "XYZ".index(axis)
        return [i for i, s in shapes() if lo - tol <= queries.centre(kind, s)[k] <= hi + tol]
    if crit == "BOX":
        c = _nums(p, vals, 6, "BOX")
        lo = [min(c[j], c[j + 3]) for j in range(3)]
        hi = [max(c[j], c[j + 3]) for j in range(3)]
        out = []
        for i, s in shapes():
            ctr = queries.centre(kind, s)
            if all(lo[j] - 1e-9 <= ctr[j] <= hi[j] + 1e-9 for j in range(3)):
                out.append(i)
        return out
    if crit == "AT":
        pt = _nums(p, vals, 3, "AT")
        vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(*pt)).Vertex()
        best, best_d = None, float("inf")
        for i, s in shapes():
            d = BRepExtrema_DistShapeShape(vertex, s)
            if d.IsDone() and d.Value() < best_d:
                best, best_d = i, d.Value()
        tol = 1e-4 + p.model.tolerance
        if best is None or best_d > tol:
            raise CommandError(f"SEL: no {kind} at ({', '.join(fmt_num(v) for v in pt)})")
        return [best]
    if crit == "TYPE":
        t = (vals[0] or "").upper()
        table = _SURF if kind == "FACE" else _CURVE if kind == "EDGE" else None
        if table is None or t not in table:
            opts = ", ".join(_SURF if kind == "FACE" else _CURVE) if table is not None else ""
            raise CommandError("SEL: TYPE works on faces and edges" + (f" ({opts})" if opts else ""))
        out = []
        for i, s in shapes():
            got = (BRepAdaptor_Surface(_as_face(s)) if kind == "FACE" else BRepAdaptor_Curve(_as_edge(s))).GetType()
            if got == table[t]:
                out.append(i)
        return out
    if crit == "SIZE":
        if kind == "VERTEX":
            raise CommandError("SEL: SIZE is length (edges), area (faces) or volume (bodies)")
        ok = _compare(p, vals, "SIZE")
        return [i for i, s in shapes() if ok(_size(kind, s))]
    if crit == "RADIUS":
        if kind not in ("FACE", "EDGE"):
            raise CommandError("SEL: RADIUS works on circular edges and cylindrical/spherical faces")
        ok = _compare(p, vals, "RADIUS")
        out = []
        for i, s in shapes():
            r = _radius(kind, s)
            if r is not None and ok(r):
                out.append(i)
        return out
    raise CommandError(f"SEL: unknown criterion {crit!r}")


@command("CM", Arg("name", Text), Arg("kind", str, "", help="check the selection is of this kind"),
         help="Save the current selection as a named set: CM, top_faces [, FACE].")
def cm(p: Processor, name, kind):
    m = p.model
    if not is_ident(name):
        raise CommandError(f"CM: {name!r} is not a valid name")
    if kind and check_kind(kind) != m.selection_kind:
        raise CommandError(f"CM: the selection holds {m.selection_kind}, not {check_kind(kind)}")
    if not m.selection:
        raise CommandError("CM: nothing is selected")
    m.save_set(name, m.selection_kind, m.selection)
    return f"set '{name}' = {m.selection_kind} {', '.join(map(str, m.selection))}"


@command("CMSEL", Arg("mode", str, help="S, R, A or U"), Arg("name", Text),
         help="Select a named set: CMSEL, S, top_faces.")
def cmsel(p: Processor, mode, name):
    kind, ids = p.model.named_set(name)
    p.model.select(kind, ids, mode)
    return _describe_selection(p)


@command("CMDEL", Arg("name", Text), help="Delete a named set.")
def cmdel(p: Processor, name):
    p.model.named_set(name)
    del p.model.named_sets[name.upper()]
    return f"set '{name}' deleted"


# =============================================================================
# Session settings
# =============================================================================


@command("/UNITS", Arg("unit", str, help="MM, CM, M or IN"),
         help="Length unit of the model (default MM). Used by EXPORT and the MM/CM/METER/INCH constants.")
def units(p: Processor, unit):
    if unit not in UNITS:
        raise CommandError(f"/UNITS: use one of {', '.join(UNITS)}")
    p.model.units = unit
    return f"units {unit}"


@command("/TOL", Arg("tol", help="0 = exact"), help="Extra tolerance for booleans and geometric selection.")
def tol(p: Processor, tol):
    if tol < 0:
        raise CommandError("/TOL: tolerance cannot be negative")
    p.model.tolerance = tol
    return f"tolerance {tol:g}"


# =============================================================================
# Files
# =============================================================================

_FORMATS = ("STEP", "BREP", "STL")


def _compound(shapes):
    comp = TopoDS_Compound()
    b = BRep_Builder()
    b.MakeCompound(comp)
    for s in shapes:
        b.Add(comp, s)
    return comp


@command(
    "EXPORT",
    Arg("format", str, help="STEP, BREP or STL"),
    Arg("file", Path),
    Arg("b", BodyRef, 0, "body to export (default: all bodies)"),
    logged=False,
    help="Write bodies to a file: EXPORT, STEP, \"part.step\" [, body]. Runs when given; not kept in the history.",
)
def export(p: Processor, format, file, b):
    if format not in _FORMATS:
        raise CommandError(f"EXPORT: format must be one of {', '.join(_FORMATS)}")
    m = p.model
    bodies = [m.body(b)] if b else list(m.bodies.values())
    if not bodies:
        raise CommandError("EXPORT: there are no bodies")
    shape = bodies[0].shape if len(bodies) == 1 else _compound([x.shape for x in bodies])
    path = os.path.abspath(file)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if format == "STEP":
        _static(Interface_Static, "SetCVal")("write.step.unit", m.units)
        w = STEPControl_Writer()
        w.Transfer(shape, STEPControl_AsIs)
        if int(w.Write(path)) != 1:  # IFSelect_RetDone
            raise CommandError(f"EXPORT: could not write {file}")
    elif format == "BREP":
        if not _static(BRepTools, "Write")(shape, path):
            raise CommandError(f"EXPORT: could not write {file}")
    else:
        BRepMesh_IncrementalMesh(shape, 0.05 * UNITS["MM"] / UNITS[m.units] * 2, False, 0.3, True)
        if not StlAPI_Writer().Write(shape, path):
            raise CommandError(f"EXPORT: could not write {file}")
    return f"wrote {len(bodies)} bod{'y' if len(bodies) == 1 else 'ies'} to {file} ({format}, {m.units})"


@command("RUN", Arg("file", Path), session=True,
         help="Run a script file. Each top-level statement becomes a history entry.")
def run_(p: Processor, file):
    try:
        with open(file, encoding="utf-8") as f:
            text = f.read()
    except OSError as exc:
        raise CommandError(f"RUN: {exc.strerror}: {file}") from None
    results = p.run_script(text)
    bad = [r for r in results if not r.ok]
    if bad:
        raise CommandError(f"RUN: stopped at '{first_code_line(bad[0].line)}': {bad[0].message}")
    return f"ran {len(results)} statements from {file}"


# =============================================================================
# History
# =============================================================================


@command("UNDO", Arg("n", int, 1), session=True, help="Undo the last n history entries.")
def undo(p: Processor, n):
    return p.undo(n)


@command("REDO", Arg("n", int, 1), session=True, help="Redo n undone entries.")
def redo(p: Processor, n):
    return p.redo(n)


@command(
    "HIST",
    Arg("action", str, "LIST", help="LIST, EDIT, INSERT, DELETE, SUPPRESS, RESUME, MOVE, REPLAY"),
    Arg("n", int, 0, "entry number (1-based)"),
    Arg("text", Text, "", "new text (quoted; \\n separates lines), or the target position for MOVE"),
    session=True,
    help=(
        "Work with the history: HIST lists it · HIST, EDIT, 3, \"W = 60\" changes entry 3 and re-runs · "
        "HIST, INSERT, 3, \"...\" · HIST, DELETE, 3 · HIST, SUPPRESS, 3 / RESUME, 3 · HIST, MOVE, 5, 2 · HIST, REPLAY"
    ),
)
def hist(p: Processor, action, n, text):
    if action == "LIST":
        return _history_text(p)
    if action == "REPLAY":
        return p.rebuild(0)
    if n <= 0:
        raise CommandError(f"HIST, {action}: give an entry number")
    if action == "EDIT":
        return p.edit_entry(n, text)
    if action in ("INSERT", "INS"):
        return p.insert_entry(n, text)
    if action in ("DELETE", "DEL"):
        return p.delete_entry(n)
    if action in ("SUPPRESS", "SUP"):
        return p.suppress_entry(n, True)
    if action in ("RESUME", "UNSUPPRESS"):
        return p.suppress_entry(n, False)
    if action == "MOVE":
        try:
            to = int(p.evaluate(text))
        except (ExprError, TypeError, ValueError):
            raise CommandError("HIST, MOVE, n, to: give the new position") from None
        return p.move_entry(n, to)
    raise CommandError(f"HIST: unknown action {action!r}")


def _history_text(p: Processor) -> str:
    if not p.history:
        return "history is empty"
    lines = []
    for i, e in enumerate(p.history, 1):
        mark = "x" if not e.ok else "-" if e.suppressed else " "
        undone = "  (undone)" if i > p.cursor else ""
        lines.append(f"{i:>4} {mark} {e.label}{undone}")
    return "\n".join(lines)


# =============================================================================
# View and queries (not part of the history)
# =============================================================================


@command("PICKMODE", Arg("kind", str, help="BODY, FACE, EDGE or VERTEX"), logged=False,
         help="What a viewport click selects.")
def pickmode(p: Processor, kind):
    try:
        kind = check_kind(kind)
    except ModelError:
        raise CommandError(f"PICKMODE: use one of {', '.join(SELECT_KINDS)}") from None
    if p.view:
        p.view.set_pick_mode(kind)
    return f"picking {kind}"


@command("VIEW", Arg("name", str, "ISO", help=", ".join(VIEWS)), logged=False, help="Standard view direction.")
def view(p: Processor, name):
    if name not in VIEWS:
        raise CommandError(f"VIEW: use one of {', '.join(VIEWS)}")
    if p.view:
        p.view.set_view(name)
    return f"view {name}"


@command("FIT", logged=False, help="Zoom to fit all bodies.")
def fit(p: Processor):
    if p.view:
        p.view.fit()


@command("LIST", Arg("what", str, "ALL", help="ALL, BODIES, PARAMS, MACROS, SETS"), logged=False,
         help="List bodies, parameters, macros, named sets and the selection.")
def list_(p: Processor, what):
    m = p.model
    lines = []
    if what in ("ALL", "BODIES"):
        lines.append(f"{len(m.bodies)} bodies ({m.units})")
        for b in m.bodies.values():
            n = {k: len(b.entity_ids[k]) for k in ENTITY_KINDS}
            lines.append(f"  body {b.id} {b.name}: {n['FACE']} faces, {n['EDGE']} edges, {n['VERTEX']} vertices")
    if what in ("ALL", "PARAMS") and p.params:
        lines.append("parameters:")
        lines += [f"  {k} = {format_value(v)}" for k, v in p.params.items()]
    if what in ("ALL", "MACROS") and p.macros:
        lines.append("macros: " + ", ".join(p.macros))
    if what in ("ALL", "SETS") and m.named_sets:
        lines.append("named sets:")
        lines += [f"  {k}: {kind} {', '.join(map(str, ids))}" for k, (kind, ids) in m.named_sets.items()]
    if what == "ALL":
        lines.append(_describe_selection(p))
    if not lines:
        if what not in ("ALL", "BODIES", "PARAMS", "MACROS", "SETS"):
            raise CommandError("LIST: use ALL, BODIES, PARAMS, MACROS or SETS")
        lines.append(f"no {what.lower()}")
    return "\n".join(lines)


@command("ECHO", Arg("expr", Raw), logged=False, help="Print the value of an expression: ECHO, VOL(1)*2.")
def echo(p: Processor, expr):
    try:
        return format_value(p.evaluate(expr))
    except ExprError as exc:
        raise CommandError(str(exc)) from None


@command("HELP", Arg("name", str, "", help="command name"), logged=False, help="List commands, or show one.")
def help_(p: Processor, name):
    if not name:
        lines = [f"{c.name:<10} {c.help.split(' · ')[0]}" for c in REGISTRY.values()]
        lines.append("Blocks: *DO *IF *WHILE *MACRO (see docs/LANGUAGE.md). Parameters: W = 40.")
        return "\n".join(lines)
    if name in p.macros:
        md = p.macros[name]
        return f"macro {md.name}, " + ", ".join(n if d is None else f"[{n}={d}]" for n, d in md.params)
    c = REGISTRY.get(name)
    if c is None:
        raise CommandError(f"HELP: unknown command {name!r}")
    sig = ", ".join([c.name] + [a.name if a.default is None else f"[{a.name}]" for a in c.args])
    lines = [sig, c.help.replace(" · ", "\n  ")] + [f"  {a.name}: {a.help}" for a in c.args if a.help]
    return "\n".join(lines)


def _describe_selection(p: Processor) -> str:
    m = p.model
    if not m.selection:
        return "selection: none"
    ids = m.selection
    shown = ", ".join(str(i) for i in ids[:40]) + (f" ... ({len(ids)} total)" if len(ids) > 40 else "")
    return f"selection: {m.selection_kind} {shown}"
