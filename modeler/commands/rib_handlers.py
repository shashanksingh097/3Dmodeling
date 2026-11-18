"""RIB, LIP and WRAP (geometry/ribs.py): thin walls from an open sketch line, the keyed rim of
an enclosure's halves, and sketches wrapped onto a cylinder."""

from __future__ import annotations

import numpy as np

from ..core.model import ModelError
from ..geometry import ribs
from ..geometry import robust
from ..lang.expr import fmt_num
from .processor import Arg, BodyRef, CommandError, Processor, Text, command


def _face(p: Processor, gid: int, what: str):
    from OCP.TopoDS import TopoDS

    if not gid:
        m = p.model
        if m.selection_kind != "FACE" or len(m.selection) != 1:
            raise CommandError(f"{what}: give a face, or select one face first")
        gid = m.selection[0]
    try:
        bid, _ = p.model.entity_owner("FACE", gid)
        f = p.model.entity_shape("FACE", gid)
    except ModelError as exc:
        raise CommandError(f"{what}: {exc}") from None
    return bid, (getattr(TopoDS, "Face_s", None) or TopoDS.Face)(f)


def _combine(p: Processor, bid: int, tool, add: bool, what: str, said: str) -> str:
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse

    from .handlers import _added, combine

    m = p.model
    base = m.body(bid).shape
    before = robust.volume(base)
    shape, maker = combine(p, "UNION" if add else "SUBTRACT", BRepAlgoAPI_Fuse if add else BRepAlgoAPI_Cut,
                           base, [tool], bid, merge=add)
    after = robust.volume(shape)
    if abs(after - before) < 1e-9 * max(1.0, before):
        raise CommandError(f"{what}: nothing changed: the new shape {'is all inside' if add else 'misses'} "
                           f"body {bid}")
    new = m.replace([bid], shape, maker, same_id=True)
    return _added(p, new, said)


@command(
    "RIB",
    Arg("sketch", Text, help="a sketch with one open line, arc or chain: the rib's top edge"),
    Arg("t", help="the rib's thickness (half on each side of the sketch plane)"),
    Arg("b", BodyRef, 0, "the body (default: the one the sketch was drawn on)"),
    Arg("side", str, "IN", "IN fills towards the middle of the part, FLIP the other side"),
    help="A thin wall from an open sketch line down to the part's faces: RIB, s2, 2 (a 2 thick rib under "
         "the line in sketch s2) · RIB, s2, 2, box, FLIP. Draw the sketch square to the walls it joins; the "
         "line's ends carry on straight until they meet the part",
)
def rib(p: Processor, sketch, t, b, side):
    from ..sketch import profile as prof
    from .sketch_handlers import _mark_used

    if side not in ("IN", "FLIP"):
        raise CommandError("RIB: side is IN or FLIP")
    m = p.model
    try:
        sk = m.sketch(sketch)
    except ModelError as exc:
        raise CommandError(f"RIB: {exc}") from None
    if m.active_sketch == sk.name.upper():
        m.set_active_sketch(None)
    edges = [prof.edge(sk, g) for g in sk.geos.values() if g.kind != "POINT" and not g.construction]
    if not edges:
        raise CommandError(f"RIB: sketch {sk.name} has no lines")
    bid = b or sk.base_body
    if not bid or bid not in m.bodies:
        raise CommandError(f"RIB: say which body the rib joins: RIB, {sk.name}, {fmt_num(t)}, body")
    try:
        wire = ribs.chain(edges)
        tool = ribs.rib_solid(wire, sk.frame.z, t, m.body(bid).shape, flip=side == "FLIP")
    except ribs.RibError as exc:
        raise CommandError(f"RIB: sketch {sk.name}: {exc}") from None
    msg = _combine(p, bid, tool, True, "RIB", f"RIB {sk.name}, {fmt_num(t)} thick, on body {bid}")
    _mark_used(p, sk, f"RIB on body {bid}")
    return msg


@command(
    "LIP",
    Arg("face", int, 0, "the flat rim face (the open edge of a shelled half); 0: the selected face"),
    Arg("h", help="how far the lip stands up (for GROOVE: how deep)"),
    Arg("w", help="the band's width, from the inside edge of the rim"),
    Arg("mode", str, "LIP", "LIP raises the band, GROOVE cuts it away"),
    Arg("clear", float, 0.0, "GROOVE only: the gap added to the width and depth, so a lip fits in it"),
    help="Key two halves of an enclosure together: LIP, 12, 2, 1 (a band 1 wide along the inside edge of rim "
         "face 12 stands up 2) · LIP, 30, 2, 1, GROOVE, 0.2 (on the other half, the same band cut 2.2 deep and "
         "1.2 wide). On a face without a hole the band runs along its outline",
)
def lip(p: Processor, face, h, w, mode, clear):
    if mode not in ("LIP", "GROOVE"):
        raise CommandError("LIP: mode is LIP or GROOVE")
    if h <= 0 or w <= 0 or clear < 0:
        raise CommandError("LIP: the height and width must be more than 0, and the clearance 0 or more")
    face = face or (p.model.selection[0] if p.model.selection_kind == "FACE" and p.model.selection else 0)
    bid, f = _face(p, face, "LIP")
    try:
        if mode == "LIP":
            tool = ribs.lip_solid(f, h, w)
        else:
            tool = ribs.lip_solid(f, -(h + clear), w + clear)
    except ribs.RibError as exc:
        raise CommandError(f"LIP: face {face}: {exc}") from None
    what = (f"LIP on face {face}: {fmt_num(w)} wide, {fmt_num(h)} high" if mode == "LIP" else
            f"GROOVE in face {face}: {fmt_num(w + clear)} wide, {fmt_num(h + clear)} deep")
    return _combine(p, bid, tool, mode == "LIP", "LIP", what)


@command(
    "WRAP",
    Arg("sketch", Text, help="a sketch on a plane parallel to the cylinder's axis"),
    Arg("face", int, 0, "a cylindrical face to wrap it onto; 0: the selected face"),
    Arg("h", help="how far it stands out (ADD) or sinks in (CUT)"),
    Arg("mode", str, "ADD", "ADD (embossed) or CUT (engraved)"),
    help="Wrap a sketch's profiles round a cylinder, raised or cut: WRAP, s3, 7, 1 (stands 1 out of face 7) · "
         "WRAP, s3, 7, 0.5, CUT. The sketch's direction across the axis becomes length round the cylinder, so "
         "shapes keep their size; it starts where the sketch plane faces the cylinder",
)
def wrap(p: Processor, sketch, face, h, mode):
    from .sketch_handlers import _mark_used, _profile

    if mode not in ("ADD", "CUT"):
        raise CommandError("WRAP: mode is ADD or CUT")
    if h <= 0:
        raise CommandError("WRAP: the height must be more than 0")
    face = face or (p.model.selection[0] if p.model.selection_kind == "FACE" and p.model.selection else 0)
    bid, f = _face(p, face, "WRAP")
    sk, faces, note = _profile(p, sketch, "WRAP")
    try:
        cyl = ribs.cylinder_of(f)
        wrapped, R = ribs.wrap_faces(faces, sk.frame, cyl)
        tools = [_thick(wf, h if mode == "ADD" else -h, cyl) for wf in wrapped]
    except ribs.RibError as exc:
        raise CommandError(f"WRAP: {exc}") from None
    tool = tools[0] if len(tools) == 1 else ribs._compound(tools)
    how = "raised" if mode == "ADD" else "cut"
    msg = _combine(p, bid, tool, mode == "ADD", "WRAP",
                   f"WRAP {sk.name} round face {face} (radius {fmt_num(R)}), {how} {fmt_num(h)}{note}")
    _mark_used(p, sk, f"WRAP on body {bid}")
    return msg


def _thick(face, h: float, cyl):
    """Thicken so that positive h goes away from the axis, whatever way the face points."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    s = ribs.wrap_solid(face, h)
    g = GProp_GProps()
    (getattr(BRepGProp, "VolumeProperties_s", None) or BRepGProp.VolumeProperties)(s, g)
    c = g.CentreOfMass()
    ax = cyl.Position()
    o = np.array([ax.Location().X(), ax.Location().Y(), ax.Location().Z()])
    a = np.array([ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z()])
    d = np.array([c.X(), c.Y(), c.Z()]) - o
    r = float(np.linalg.norm(d - (d @ a) * a))
    if (r - cyl.Radius()) * h < 0:
        s = ribs.wrap_solid(face, -h)
    return s
