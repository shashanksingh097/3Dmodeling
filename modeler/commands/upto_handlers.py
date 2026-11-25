"""Up-to moves and pulls (PLAN item 108): UPTO moves a body, or pulls picked faces, until they
reach another face, edge or vertex.

    UPTO, box, FACE, 12              move box along the face's normal until its leading side is on it
    UPTO, box, VERTEX, 7, Z, 2       move box along Z until its leading side is 2 short of vertex 7
    UPTO, SEL, FACE, 12              pull the picked flat faces until they are level with face 12

The target is reached by a plane through it: a face's middle point (along its normal for a flat
face), an edge's middle (a round edge's centre), or a vertex. A body moves along ``axis`` (X, Y, Z,
or NORMAL, the target face's normal, the default for a face) by just enough that its side facing
the target touches that plane; ``offset`` stops short of it (negative: past it). Picked faces move
along their own normals (PUSHPULL with the distance worked out). One history step either way.
"""

from __future__ import annotations

from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Ellipse, GeomAbs_Plane
from OCP.gp import gp_Trsf, gp_Vec
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_VERTEX
from OCP.BRep import BRep_Tool

from ..core.model import ModelError
from ..geometry.features import as_edge, as_face, as_vertex
from ..geometry import robust
from ..lang.expr import fmt_num
from .processor import Arg, CommandError, Processor, Raw, command

P3 = tuple[float, float, float]
AXES = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a, b) -> P3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def target(p: Processor, kind: str, gid: int) -> tuple[P3, P3 | None, str]:
    """(a point on it, its normal when it is a flat face, how to name it)."""
    from ..geometry import recognize as rc

    m = p.model
    try:
        shape = m.entity_shape(kind, gid)
    except (ModelError, KeyError, IndexError):
        raise CommandError(f"UPTO: there is no {kind.lower()} {gid}") from None
    if kind == "FACE":
        pt, n = rc.face_normal_at_middle(shape)
        from OCP.BRepAdaptor import BRepAdaptor_Surface

        flat = BRepAdaptor_Surface(as_face(shape)).GetType() == GeomAbs_Plane
        return tuple(pt), (tuple(n) if flat else None), f"face {gid}"
    if kind == "EDGE":
        c = BRepAdaptor_Curve(as_edge(shape))
        if c.GetType() in (GeomAbs_Circle, GeomAbs_Ellipse):
            loc = (c.Circle() if c.GetType() == GeomAbs_Circle else c.Ellipse()).Location()
            return (loc.X(), loc.Y(), loc.Z()), None, f"the centre of edge {gid}"
        q = c.Value((c.FirstParameter() + c.LastParameter()) / 2)
        return (q.X(), q.Y(), q.Z()), None, f"the middle of edge {gid}"
    if kind == "VERTEX":
        q = BRep_Tool.Pnt_s(as_vertex(shape))
        return (q.X(), q.Y(), q.Z()), None, f"vertex {gid}"
    raise CommandError("UPTO: the target is FACE, EDGE or VERTEX")


def _vertices(shape) -> list[P3]:
    out = []
    ex = TopExp_Explorer(shape, TopAbs_VERTEX)
    while ex.More():
        q = BRep_Tool.Pnt_s(as_vertex(ex.Current()))
        out.append((q.X(), q.Y(), q.Z()))
        ex.Next()
    return out


def _extent(shape, d: P3) -> tuple[float, float]:
    """Lowest and highest reach of a shape along unit direction d (exact for round sides too: the
    shape is turned so d is Z, and its tight box read)."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Quaternion, gp_Vec as _V

    q = gp_Quaternion(_V(*d), _V(0.0, 0.0, 1.0))
    t = gp_Trsf()
    t.SetRotation(q)
    turned = BRepBuilderAPI_Transform(shape, t, True).Shape()
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(turned, box, False, False)
    if box.IsVoid():
        raise CommandError("UPTO: the body has no size")
    return box.CornerMin().Z(), box.CornerMax().Z()


def _num(v: float) -> str:
    return fmt_num(round(v, 6) + 0.0)


@command(
    "UPTO",
    Arg("what", Raw, help="the body to move, or SEL (the picked faces) or FACES 6 7 for faces to pull"),
    Arg("kind", str, help="what to go up to: FACE, EDGE or VERTEX"),
    Arg("n", int, help="its number"),
    Arg("axis", str, "", "for a body: X, Y, Z or NORMAL (the target face's normal; the default for a face)"),
    Arg("offset", float, 0.0, "stop this far short of the target (negative: go past it)"),
    help="Move a body, or pull picked faces, up to another face, edge or vertex: UPTO, box, FACE, 12 moves box "
         "along the face's normal until it touches the face's plane · UPTO, box, VERTEX, 7, Z lines its side up "
         "with vertex 7 along Z · UPTO, SEL, FACE, 12 pulls the picked flat faces level with face 12. The target "
         "counts as the plane through it square to the direction (a round edge: its centre). offset stops short. "
         "FACES 6 7 names the faces to pull instead of picking them.",
)
def upto(p: Processor, what, kind, n, axis, offset):
    kind = kind.upper()
    if kind not in ("FACE", "EDGE", "VERTEX"):
        raise CommandError("UPTO: the target is FACE, EDGE or VERTEX")
    pt, normal, label = target(p, kind, n)
    w = what.strip().upper()
    if w == "SEL":
        from .shape_handlers import _faces

        return _pull(p, _faces(p, "UPTO"), pt, label, offset)
    if w.startswith("FACES"):
        return _pull(p, _named_faces(p, w[5:]), pt, label, offset)
    bid = _body(p, what)
    return _move(p, bid, pt, normal, label, axis.upper(), offset)


def _body(p: Processor, raw: str) -> int:
    s = raw.strip()
    b = p.model.body_by_name(s)
    if b is not None:
        return b.id
    try:
        bid = int(p.evaluate(s))
    except Exception:  # noqa: BLE001 - told the same way
        raise CommandError(f"UPTO: {s or '(nothing)'} is not a body (a name or an ID), or SEL for picked faces") from None
    if bid not in p.model.bodies:
        raise CommandError(f"UPTO: there is no body {bid}")
    return bid


def _move(p: Processor, bid: int, pt: P3, normal, label: str, axis: str, offset: float) -> str:
    from .handlers import _transform

    if not axis:
        axis = "NORMAL" if normal is not None else ""
    if axis == "NORMAL":
        if normal is None:
            raise CommandError(f"UPTO: {label} is not a flat face; give the axis (X, Y or Z)")
        d = normal
    elif axis in AXES:
        d = AXES[axis]
    else:
        raise CommandError("UPTO: give the axis to move along: X, Y, Z or NORMAL")
    shape = p.model.body(bid).shape
    lo, hi = _extent(shape, d)
    level = _dot(pt, d)
    if lo - 1e-9 <= level <= hi + 1e-9:
        raise CommandError(f"UPTO: {label} is level with body {bid} already (inside its reach along {axis.lower()})")
    if level > hi:  # ahead: the high side goes to it
        move = level - hi - offset
    else:  # behind: the low side goes to it
        move = level - lo + offset
    t = gp_Trsf()
    vec = tuple(c * move for c in d)
    t.SetTranslation(gp_Vec(*vec))
    shift = ", ".join(_num(c) for c in vec)
    return _transform(p, bid, t, f"moved by ({shift}) up to {label}:", copy=False)


def _named_faces(p: Processor, text: str) -> dict[int, list[int]]:
    """FACES 6 7 9: the faces by body."""
    out: dict[int, list[int]] = {}
    nums = text.replace(",", " ").split()
    if not nums:
        raise CommandError("UPTO: give the faces to pull: FACES 6 7")
    for word in nums:
        try:
            gid = int(word)
            bid, _ = p.model.entity_owner("FACE", gid)
        except (ValueError, ModelError, KeyError, IndexError):
            raise CommandError(f"UPTO: there is no face {word}") from None
        out.setdefault(bid, []).append(gid)
    for bid in out:
        if not robust.solids(p.model.body(bid).shape):
            raise CommandError(f"UPTO: body {bid} is not a solid")
    return out


def _pull(p: Processor, groups: dict[int, list[int]], pt: P3, label: str, offset: float) -> str:
    from ..geometry import direct as de
    from ..geometry import recognize as rc
    from .handlers import _added

    m = p.model
    msgs = []
    for bid, fids in groups.items():
        body = m.body(bid)
        ds = []
        for f in fids:
            q, nf = rc.face_normal_at_middle(m.entity_shape("FACE", f))
            ds.append(_dot(_sub(pt, tuple(q)), tuple(nf)) - offset)
        if all(abs(d) < 1e-9 for d in ds):
            raise CommandError(f"UPTO: the picked faces are level with {label} already")
        before = robust.volume(body.shape)
        try:
            shape, maker = de.push_pull(body.shape, [m.entity_shape("FACE", f) for f in fids], ds)
        except de.DirectError as exc:
            raise CommandError(f"UPTO: body {bid}: {exc}") from None
        if robust.is_empty(shape) or not robust.is_valid(shape) or robust.volume(shape) <= 0:
            raise CommandError(f"UPTO: pulling to {label} gives an invalid body {bid} (a face would pass through "
                               "another)")
        new = m.replace([bid], robust.unwrap(shape), maker, same_id=True)
        change = robust.volume(shape) - before
        dist = ", ".join(_num(d) for d in ds)
        msgs.append(_added(p, new, f"UPTO {label}: face{'s' if len(fids) > 1 else ''} {', '.join(map(str, fids))} "
                                   f"of body {bid} pulled {dist} (volume {'+' if change >= 0 else '-'}"
                                   f"{_num(abs(change))})"))
    return "\n".join(msgs)
