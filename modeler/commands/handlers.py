"""The M0 command set: a few primitives, picking/selection and view commands."""

from __future__ import annotations

from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer, BRepFilletAPI_MakeFillet
from OCP.BRepPrimAPI import (
    BRepPrimAPI_MakeBox,
    BRepPrimAPI_MakeCone,
    BRepPrimAPI_MakeCylinder,
    BRepPrimAPI_MakeSphere,
    BRepPrimAPI_MakeTorus,
)
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
from OCP.TopoDS import TopoDS

# OCP 7.x names static methods with a "_s" suffix; OCP 8 dropped it.
_as_edge = getattr(TopoDS, "Edge_s", None) or TopoDS.Edge

from ..core.model import ENTITY_KINDS, SELECT_KINDS
from .processor import REGISTRY, Arg, CommandError, Processor, command

VIEWS = ("ISO", "TOP", "BOTTOM", "FRONT", "BACK", "LEFT", "RIGHT")


def _added(p: Processor, shape, what: str) -> str:
    body = p.model.add_body(shape)
    n = {k: len(body.entity_ids[k]) for k in ENTITY_KINDS}
    return f"{what} -> body {body.id} ({n['FACE']} faces, {n['EDGE']} edges, {n['VERTEX']} vertices)"


@command(
    "BLOCK",
    Arg("x"), Arg("y"), Arg("z"), Arg("dx"), Arg("dy"), Arg("dz"),
    help="Box from corner (x,y,z) with sizes dx,dy,dz.",
)
def block(p: Processor, x, y, z, dx, dy, dz):
    if min(dx, dy, dz) <= 0:
        raise CommandError("BLOCK: sizes must be positive")
    return _added(p, BRepPrimAPI_MakeBox(gp_Pnt(x, y, z), dx, dy, dz).Shape(), "BLOCK")


@command(
    "CYL",
    Arg("x"), Arg("y"), Arg("z"), Arg("r"), Arg("h"),
    help="Cylinder along +Z with base center (x,y,z), radius r, height h.",
)
def cyl(p: Processor, x, y, z, r, h):
    if r <= 0 or h <= 0:
        raise CommandError("CYL: radius and height must be positive")
    ax = gp_Ax2(gp_Pnt(x, y, z), gp_Dir(0, 0, 1))
    return _added(p, BRepPrimAPI_MakeCylinder(ax, r, h).Shape(), "CYL")


@command("SPHERE", Arg("x"), Arg("y"), Arg("z"), Arg("r"), help="Sphere with center (x,y,z), radius r.")
def sphere(p: Processor, x, y, z, r):
    if r <= 0:
        raise CommandError("SPHERE: radius must be positive")
    return _added(p, BRepPrimAPI_MakeSphere(gp_Pnt(x, y, z), r).Shape(), "SPHERE")


@command(
    "CONE",
    Arg("x"), Arg("y"), Arg("z"), Arg("r1"), Arg("r2"), Arg("h"),
    help="Cone along +Z: base center (x,y,z), base radius r1, top radius r2, height h.",
)
def cone(p: Processor, x, y, z, r1, r2, h):
    if r1 < 0 or r2 < 0 or r1 == r2 == 0 or h <= 0:
        raise CommandError("CONE: radii must be >= 0 (not both 0) and height positive")
    ax = gp_Ax2(gp_Pnt(x, y, z), gp_Dir(0, 0, 1))
    return _added(p, BRepPrimAPI_MakeCone(ax, r1, r2, h).Shape(), "CONE")


@command(
    "TORUS",
    Arg("x"), Arg("y"), Arg("z"), Arg("r1", help="ring radius"), Arg("r2", help="tube radius"),
    help="Torus in the XY plane, centered at (x,y,z).",
)
def torus(p: Processor, x, y, z, r1, r2):
    if r2 <= 0 or r1 <= r2:
        raise CommandError("TORUS: need ring radius > tube radius > 0")
    ax = gp_Ax2(gp_Pnt(x, y, z), gp_Dir(0, 0, 1))
    return _added(p, BRepPrimAPI_MakeTorus(ax, r1, r2).Shape(), "TORUS")


# ---- booleans ---------------------------------------------------------------
# For now the input bodies are consumed. Keeping them (KEEP, ON) comes in M2.

_TOOLS = [Arg(f"t{i}", int, 0) for i in range(2, 9)]


def _boolean(p: Processor, name: str, op, a: int, tools: list[int]) -> str:
    tools = [t for t in tools if t]
    if not tools:
        raise CommandError(f"{name}: give a base body and at least one tool body")
    m = p.model
    shape = m.body(a).shape
    for t in tools:
        if t == a:
            raise CommandError(f"{name}: body {a} cannot be its own tool")
        tool = m.body(t).shape
        algo = op(shape, tool)
        if not algo.IsDone():
            raise CommandError(f"{name}: kernel failed with body {t}")
        shape = algo.Shape()
    for bid in [a] + tools:
        m.remove_body(bid)
    return _added(p, shape, f"{name} of {', '.join(map(str, [a] + tools))}")


@command("UNION", Arg("a", int), Arg("b", int), *_TOOLS,
         help="Fuse bodies into one new body: UNION, a, b [, c ...] (up to 8).")
def union(p: Processor, a, b, **more):
    return _boolean(p, "UNION", BRepAlgoAPI_Fuse, a, [b, *more.values()])


@command("SUBTRACT", Arg("a", int), Arg("b", int), *_TOOLS,
         help="Cut tool bodies b, c ... from body a: SUBTRACT, a, b [, c ...].")
def subtract(p: Processor, a, b, **more):
    return _boolean(p, "SUBTRACT", BRepAlgoAPI_Cut, a, [b, *more.values()])


@command("INTERSECT", Arg("a", int), Arg("b", int), *_TOOLS,
         help="Keep only the common volume: INTERSECT, a, b [, c ...].")
def intersect(p: Processor, a, b, **more):
    return _boolean(p, "INTERSECT", BRepAlgoAPI_Common, a, [b, *more.values()])


# ---- edge blends ------------------------------------------------------------
def _blend(p: Processor, name: str, size: float) -> str:
    """Round or bevel the selected edges (all on one body), or every edge of
    the selected bodies."""
    m = p.model
    if size <= 0:
        raise CommandError(f"{name}: size must be positive")
    if not m.selection or m.selection_kind not in ("EDGE", "BODY"):
        raise CommandError(f"{name}: select edges (PICKMODE, EDGE) or a body first")
    if m.selection_kind == "BODY":
        groups = {bid: list(m.bodies[bid].entity_ids["EDGE"]) for bid in m.selection}
    else:
        groups = {}
        for gid in m.selection:
            groups.setdefault(m.entity_owner("EDGE", gid)[0], []).append(gid)
    msgs = []
    for bid, edges in groups.items():
        maker_cls = BRepFilletAPI_MakeFillet if name == "FILLET" else BRepFilletAPI_MakeChamfer
        mk = maker_cls(m.bodies[bid].shape)
        for gid in edges:
            mk.Add(size, _as_edge(m.entity_shape("EDGE", gid)))
        mk.Build()
        if not mk.IsDone():
            raise CommandError(f"{name}: kernel failed on body {bid} (size too large?)")
        shape = mk.Shape()
        m.remove_body(bid)
        msgs.append(_added(p, shape, f"{name} {size:g} on {len(edges)} edges of body {bid}"))
    return "\n".join(msgs)


@command("FILLET", Arg("r"), help="Round the selected edges (or all edges of selected bodies) with radius r.")
def fillet(p: Processor, r):
    return _blend(p, "FILLET", r)


@command("CHAMFER", Arg("d"), help="Bevel the selected edges (or all edges of selected bodies) by distance d.")
def chamfer(p: Processor, d):
    return _blend(p, "CHAMFER", d)


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


@command(
    "SEL",
    Arg("mode", str, help="S, A, U, NONE or ALL"),
    Arg("kind", str, "", help="BODY, FACE, EDGE or VERTEX"),
    Arg("id1", int, 0), Arg("id2", int, 0),
    help="Select by ID range: SEL, S, FACE, 3, 6 selects faces 3..6. SEL, NONE clears.",
)
def sel(p: Processor, mode, kind, id1, id2):
    m = p.model
    if mode == "NONE":
        m.select_none()
        return "selection cleared"
    if not kind:
        raise CommandError("SEL: kind is required (BODY, FACE, EDGE or VERTEX)")
    if mode == "ALL":
        ids = _all_ids(p, kind)
        m.select(kind, ids, "S")
    else:
        if id1 <= 0:
            raise CommandError("SEL: give an ID (or a range id1, id2)")
        ids = list(range(id1, (id2 or id1) + 1))
        m.select(kind, ids, mode)
    return _describe_selection(p)


def _all_ids(p: Processor, kind: str) -> list[int]:
    k = kind.upper()
    if k == "BODY":
        return sorted(p.model.bodies)
    return [g for b in p.model.bodies.values() for g in b.entity_ids[k]]


@command(
    "PICKMODE",
    Arg("kind", str, help="BODY, FACE, EDGE or VERTEX"),
    help="What a viewport click selects.",
)
def pickmode(p: Processor, kind):
    if kind not in SELECT_KINDS:
        raise CommandError(f"PICKMODE: use one of {', '.join(SELECT_KINDS)}")
    if p.view:
        p.view.set_pick_mode(kind)
    return f"picking {kind}"


@command("VIEW", Arg("name", str, "ISO", help=", ".join(VIEWS)), help="Standard view direction.")
def view(p: Processor, name):
    if name not in VIEWS:
        raise CommandError(f"VIEW: use one of {', '.join(VIEWS)}")
    if p.view:
        p.view.set_view(name)
    return f"view {name}"


@command("FIT", help="Zoom to fit all bodies.")
def fit(p: Processor):
    if p.view:
        p.view.fit()


@command("CLEAR", help="Delete everything and restart IDs.")
def clear(p: Processor):
    p.model.clear()
    return "model cleared"


@command("LIST", help="List bodies and the current selection.", logged=False)
def list_(p: Processor):
    m = p.model
    lines = [f"{len(m.bodies)} bodies"]
    for b in m.bodies.values():
        f = b.entity_ids["FACE"]
        lines.append(f"  body {b.id} {b.name}: faces {f[0]}-{f[-1]}" if f else f"  body {b.id} {b.name}")
    lines.append(_describe_selection(p))
    return "\n".join(lines)


@command("HELP", Arg("name", str, "", help="command name"), help="List commands, or show one.", logged=False)
def help_(p: Processor, name):
    if not name:
        return "\n".join(f"{c.name:<9} {c.help}" for c in REGISTRY.values())
    c = REGISTRY.get(name)
    if c is None:
        raise CommandError(f"HELP: unknown command {name!r}")
    sig = ", ".join([c.name] + [a.name if a.default is None else f"[{a.name}]" for a in c.args])
    lines = [sig, c.help] + [f"  {a.name}: {a.help}" for a in c.args if a.help]
    return "\n".join(lines)


def _describe_selection(p: Processor) -> str:
    m = p.model
    if not m.selection:
        return "selection: none"
    ids = ", ".join(str(i) for i in m.selection)
    return f"selection: {m.selection_kind} {ids}"
