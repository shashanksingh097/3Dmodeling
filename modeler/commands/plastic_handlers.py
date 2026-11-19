"""BOSS, SNAP and VENT: features for moulded plastic parts (geometry/plastic.py)."""

from __future__ import annotations

import math

from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.gp import gp_Ax2, gp_Ax3, gp_Dir, gp_Pnt, gp_Trsf

from ..geometry import plastic as pl
from ..geometry import robust
from ..lang.expr import fmt_num
from .processor import Arg, BodyRef, CommandError, Processor, command


def _put(shape, origin, up, xdir=None, what: str = ""):
    """Move a feature built about +Z at the origin to ``origin``, its +Z along ``up`` (and +X along xdir)."""
    if math.hypot(*up) < 1e-12:
        raise CommandError(f"{what}: the up direction cannot be (0, 0, 0)")
    if xdir is None:
        ax = gp_Ax2(gp_Pnt(*origin), gp_Dir(*up))
    else:
        u = gp_Dir(*up)
        if math.hypot(*xdir) < 1e-12:
            raise CommandError(f"{what}: the hook direction cannot be (0, 0, 0)")
        x = gp_Dir(*xdir)
        if abs(u.Dot(x)) > 0.999:
            raise CommandError(f"{what}: the hook direction cannot be along the up direction")
        ax = gp_Ax2(gp_Pnt(*origin), u, x)  # (x is made square to up)
    t = gp_Trsf()
    t.SetTransformation(gp_Ax3(ax), gp_Ax3())
    return BRepBuilderAPI_Transform(shape, t, True).Shape()


def _add_to(p: Processor, bid: int, tool, what: str) -> str:
    from .handlers import _added, combine

    m = p.model
    body = m.body(bid)
    if not robust.solids(body.shape):
        raise CommandError(f"{what}: body {bid} is not a solid")
    shape, maker = combine(p, what, BRepAlgoAPI_Fuse, body.shape, [tool], bid)
    new = m.replace([bid], shape, maker, same_id=True)
    return _added(p, new, what)


@command(
    "BOSS",
    Arg("b", BodyRef, help="the part to add the boss to"),
    Arg("x"), Arg("y"), Arg("z", help="the foot of the boss, on a face of the part"),
    Arg("h", help="height"), Arg("od", help="outside diameter"),
    Arg("hole", float, 0.0, "hole diameter for the screw (0: none)"),
    Arg("ribs", float, 4.0, "support ribs round it (0 to 12)"),
    Arg("depth", float, 0.0, "hole depth from the top (0: down to the foot)"),
    Arg("dx", float, 0.0, "the way the boss stands up (default +Z)"), Arg("dy", float, 0.0), Arg("dz", float, 1.0),
    help="A screw boss with support ribs, standing on a face of a part: BOSS, case, 20,15,2, 10, 7, 2.5 "
         "(10 tall, 7 across, a 2.5 hole for a self-tapping M3, 4 ribs) · BOSS, case, 20,15,2, 10, 7, 2.5, 0 (no "
         "ribs). The foot sits at (x,y,z); the ribs reach 0.75 x od out from the boss.",
)
def boss(p: Processor, b, x, y, z, h, od, hole, ribs, depth, dx, dy, dz):
    from .feature_handlers import world_dir, world_point

    if ribs != int(ribs):
        raise CommandError("BOSS: ribs must be a whole number")
    try:
        shape, cutter = pl.boss(h, od, hole, int(ribs), hole_depth=depth)
        if cutter is not None:
            shape = pl._bool("cut", shape, cutter)
    except pl.PlasticError as exc:
        raise CommandError(f"BOSS: {exc}") from None
    tool = _put(shape, world_point(p, x, y, z), world_dir(p, (dx, dy, dz)), what="BOSS")
    what = (f"BOSS {fmt_num(h)} tall, {fmt_num(od)} across" + (f", hole {fmt_num(hole)}" if hole else "")
            + (f" {fmt_num(depth)} deep" if hole and depth else "") + f", {int(ribs)} rib{'s' if ribs != 1 else ''}")
    return _add_to(p, b, tool, what)


@command(
    "SNAP",
    Arg("b", BodyRef, help="the part to add the hook to"),
    Arg("x"), Arg("y"), Arg("z", help="the root of the hook, on a face of the part (the hook side of the beam)"),
    Arg("length", help="the beam's length, root to tip"), Arg("width"), Arg("thickness", help="the beam's thickness"),
    Arg("overhang", float, 0.0, "how far the catch sticks out (0: the thickness)"),
    Arg("dx", float, 0.0, "the way the beam stands up (default +Z)"), Arg("dy", float, 0.0), Arg("dz", float, 1.0),
    Arg("hx", float, 1.0, "the way the catch faces (default +X)"), Arg("hy", float, 0.0), Arg("hz", float, 0.0),
    Arg("lead", float, 30.0, "the angle of the slope that pushes it in, from the beam (degrees)"),
    Arg("catch", float, 90.0, "the angle of the catch (90: it holds for good, less: it can be pulled apart)"),
    help="A cantilever snap hook standing on a face of a part: SNAP, lid, 0,20,2, 12, 6, 1.5 (12 long, 6 wide, "
         "1.5 thick, the catch facing +X) · SNAP, lid, 0,20,2, 12, 6, 1.5, 1, , , , -1,0,0 (catch 1, facing -X) "
         "· SNAP, ..., , , , , , , , 30, 45 (a catch that lets go). The mating part needs a window or a lip "
         "for the catch.",
)
def snap(p: Processor, b, x, y, z, length, width, thickness, overhang, dx, dy, dz, hx, hy, hz, lead, catch):
    from .feature_handlers import world_dir, world_point

    try:
        shape, z_catch = pl.snap_hook(length, width, thickness, overhang, lead, catch)
    except pl.PlasticError as exc:
        raise CommandError(f"SNAP: {exc}") from None
    tool = _put(shape, world_point(p, x, y, z), world_dir(p, (dx, dy, dz)), world_dir(p, (hx, hy, hz)), "SNAP")
    over = overhang or thickness
    # bending strain to push the catch past the overhang (a cantilever: 1.5 t y / L^2)
    strain = 1.5 * thickness * over / z_catch ** 2 * 100
    what = (f"SNAP {fmt_num(length)} long, {fmt_num(width)} wide, {fmt_num(thickness)} thick, catch "
            f"{fmt_num(over)} at {fmt_num(round(z_catch, 4))} from the root; bending strain to snap in about "
            f"{strain:.2g}%" + (" (more than the 2 to 5% most plastics take: make it longer or thinner)"
                                if strain > 5 else ""))
    return _add_to(p, b, tool, what)


def _face_frame(face):
    """(centre, outward normal, in-plane X) of a flat face."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepGProp import BRepGProp
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_REVERSED

    ad = BRepAdaptor_Surface(face)
    if ad.GetType() != GeomAbs_Plane:
        raise CommandError("VENT: the face must be flat")
    pln = ad.Plane()
    n = pln.Axis().Direction()
    if face.Orientation() == TopAbs_REVERSED:
        n = n.Reversed()
    g = GProp_GProps()
    (getattr(BRepGProp, "SurfaceProperties_s", None) or BRepGProp.SurfaceProperties)(face, g)
    c = g.CentreOfMass()
    xd = pln.Position().XDirection()
    return (c.X(), c.Y(), c.Z()), (n.X(), n.Y(), n.Z()), (xd.X(), xd.Y(), xd.Z())


@command(
    "VENT",
    Arg("count", help="number of slots"), Arg("length", help="slot length"), Arg("width", help="slot width"),
    Arg("pitch", float, 0.0, "distance from one slot to the next (0: twice the width)"),
    Arg("angle", float, 0.0, "turn the slots in the face (degrees)"),
    Arg("depth", float, 0.0, "how deep to cut (0: through the wall under the face)"),
    Arg("u", float, 0.0, "move the grille along the slots from the face's centre"),
    Arg("v", float, 0.0, "move it across the slots"),
    help="A vent: a grille of slots cut through the wall under the selected flat face, centred on the face: "
         "PICK, FACE, 12 then VENT, 6, 20, 2 (six slots 20 x 2, 4 apart) · VENT, 6, 20, 2, 3, 90 (turned 90°) · "
         "VENT, 4, 15, 2, , , , 10 (moved 10 along the slots).",
)
def vent(p: Processor, count, length, width, pitch, angle, depth, u, v):
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.TopAbs import TopAbs_IN, TopAbs_ON

    from ..geometry.probe import Rays, material_spans
    from .handlers import _added, combine

    m = p.model
    if count != int(count) or not 1 <= count <= 200:
        raise CommandError("VENT: the number of slots must be a whole number from 1 to 200")
    if width <= 0 or length < width:
        raise CommandError("VENT: the width must be positive and the length at least the width")
    pitch = pitch or 2 * width
    if pitch <= width and count > 1:
        raise CommandError("VENT: the pitch must be more than the width, or the slots run into each other")
    if depth < 0:
        raise CommandError("VENT: the depth cannot be negative")
    if m.selection_kind != "FACE" or len(m.selection) != 1:
        raise CommandError("VENT: select one flat face first, e.g. PICK, FACE, 12")
    gid = m.selection[0] if isinstance(m.selection, list) else next(iter(m.selection))
    bid = m.entity_owner("FACE", gid)[0]
    body = m.body(bid)
    face = m.entity_shape("FACE", gid)
    from OCP.TopoDS import TopoDS

    face = (getattr(TopoDS, "Face_s", None) or TopoDS.Face)(face)
    c, n, xd = _face_frame(face)
    a = math.radians(angle)
    # the slot direction: the face's X turned by the angle about the normal
    nx = (n[1] * xd[2] - n[2] * xd[1], n[2] * xd[0] - n[0] * xd[2], n[0] * xd[1] - n[1] * xd[0])  # n x X
    sd = tuple(math.cos(a) * xd[i] + math.sin(a) * nx[i] for i in range(3))
    cd = (n[1] * sd[2] - n[2] * sd[1], n[2] * sd[0] - n[0] * sd[2], n[0] * sd[1] - n[1] * sd[0])  # across
    centre = tuple(c[i] + u * sd[i] + v * cd[i] for i in range(3))
    size = robust.diagonal(body.shape)
    if not depth:
        start = tuple(centre[i] + n[i] * 1e-4 * size for i in range(3))
        spans = material_spans(Rays(body.shape).hits(start, tuple(-q for q in n)), False)
        if not spans:
            raise CommandError("VENT: there is no wall under the centre of the face; give the depth")
        depth = spans[0][1] - 1e-4 * size
    offsets = pl.vent_centres(int(count), pitch)
    half = length / 2
    outside = []
    for off in offsets:
        for along in (-half + width / 2, half - width / 2):
            q = tuple(centre[i] + along * sd[i] + off * cd[i] for i in range(3))
            st = BRepClass_FaceClassifier(face, gp_Pnt(*q), 1e-6).State()
            if st not in (TopAbs_IN, TopAbs_ON):
                outside.append(off)
                break
    if outside:
        raise CommandError(f"VENT: {len(outside)} of the {int(count)} slots run off the face; use fewer, shorter "
                           f"or closer slots, or turn them (angle)")
    lift = 0.01 * size + 1.0
    tools = []
    for off in offsets:
        s = pl.slot(length, width, depth + lift + 0.01 * size)
        s = _put(s, (0.0, off, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), "VENT")
        tools.append(s)
    # the slots, built along X and spaced along Y on Z = -lift ... , turned onto the face going in
    t = gp_Trsf()
    t.SetTransformation(gp_Ax3(gp_Ax2(gp_Pnt(*[centre[i] + n[i] * lift for i in range(3)]),
                                      gp_Dir(*[-q for q in n]), gp_Dir(*sd))), gp_Ax3())
    tools = [BRepBuilderAPI_Transform(s, t, True).Shape() for s in tools]
    shape, maker = combine(p, "VENT", BRepAlgoAPI_Cut, body.shape, tools, bid)
    new = m.replace([bid], shape, maker, same_id=True)
    return _added(p, new, f"VENT {int(count)} slot{'s' if count != 1 else ''} {fmt_num(length)} x "
                          f"{fmt_num(width)}, {fmt_num(pitch)} apart, {fmt_num(round(depth, 4))} deep, in face {gid}")
