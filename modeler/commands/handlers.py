"""The M0 command set: a few primitives, picking/selection and view commands."""

from __future__ import annotations

from OCP.BRepPrimAPI import (
    BRepPrimAPI_MakeBox,
    BRepPrimAPI_MakeCylinder,
    BRepPrimAPI_MakeSphere,
)
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

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
