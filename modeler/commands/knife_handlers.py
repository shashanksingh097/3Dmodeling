"""KNIFE (M6c): cut a body along a stroke (see geometry/knife.py).

The GUI's Knife tool draws the stroke on screen, turns it into a SPLINE on a
plane across the view, and runs KNIFE with the view direction, so a cut is
two history lines that can be edited like any other.
"""

from __future__ import annotations

import numpy as np

from ..core.model import ModelError
from ..geometry import features as ft
from ..geometry import knife as kn
from ..geometry import meshbody as mb
from ..geometry import robust
from ..lang.expr import fmt_num
from .processor import Arg, BodyRef, CommandError, Processor, command

# a cut with no width through a mesh body leaves a gap this thin (a share of the body's size)
HAIRLINE = 1e-5


def _is_curve(shape) -> bool:
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE

    return robust.count(shape, TopAbs_FACE) == 0 and robust.count(shape, TopAbs_EDGE) > 0


@command(
    "KNIFE",
    Arg("b", BodyRef, help="the body to cut"),
    Arg("stroke", BodyRef, help="the curve to cut along (LINE, POLYLINE, SPLINE ...), as seen from the direction"),
    Arg("width", float, 0.0, "0: split into pieces; more: cut a slot this wide along the stroke"),
    Arg("dx", float, 0.0, "the direction to cut along (default: across the stroke's plane)"), Arg("dy", float, 0.0),
    Arg("dz", float, 0.0),
    help="Cut a body along a stroke, straight through it along a direction (the view direction when drawn with "
         "the Knife tool): KNIFE, b, stroke [, width [, dx, dy, dz]]. An open stroke is carried on straight past "
         "the body; a closed one cuts out what is inside it. Width 0 splits the body into pieces (the biggest "
         "keeps its ID); a width cuts a slot. The stroke is hidden afterwards. Works on solids and mesh bodies.",
)
def knife(p: Processor, b, stroke, width, dx, dy, dz):
    from .handlers import _added

    m = p.model
    if stroke == b:
        raise CommandError("KNIFE: a body cannot cut itself; give a curve as the stroke")
    body, curve = m.body(b), m.body(stroke)
    if not _is_curve(curve.shape):
        raise CommandError(f"KNIFE: body {stroke} is not a curve; draw the stroke with LINE, POLYLINE or SPLINE "
                           "(or the Knife tool)")
    if width < 0:
        raise CommandError("KNIFE: the width cannot be negative")
    is_mesh = mb.is_mesh(body.shape)
    if not is_mesh and not robust.solids(body.shape):
        raise CommandError(f"KNIFE: body {b} is not a solid")
    direction = (dx, dy, dz) if any((dx, dy, dz)) else None
    try:
        cut = kn.Cut(body.shape, curve.shape, direction)
        if is_mesh:
            pieces, maker = _mesh_pieces(p, b, body.shape, cut, width), _Fresh()
        else:
            pieces, maker = _solid_pieces(body.shape, cut, width)
    except kn.KnifeError as exc:
        raise CommandError(f"KNIFE: {exc}") from None
    except mb.MeshError as exc:
        raise CommandError(f"KNIFE: {exc}") from None
    if not pieces:
        raise CommandError(f"KNIFE: nothing of body {b} is left")
    if width == 0 and len(pieces) < 2:
        raise CommandError(f"KNIFE: the stroke does not cut through body {b} (seen along the direction it misses "
                           "the body, or only touches it)")
    vols = [_volume(s) for s in pieces]
    order = sorted(range(len(pieces)), key=lambda i: -vols[i])
    try:
        first = m.replace([b], pieces[order[0]], maker, same_id=True)
        others = [m.add_body(pieces[i], "", (maker, [body])) for i in order[1:]]
    except ModelError as exc:
        raise CommandError(f"KNIFE: {exc}") from None
    m.set_hidden(stroke, True)
    m.last_body = first.id
    what = f"KNIFE body {b} along curve {stroke}" + (f", slot {fmt_num(width)} wide" if width else "")
    msg = _added(p, first, what)
    if others:
        msg += "; other pieces: bodies " + ", ".join(str(o.id) for o in others)
    elif width:
        msg += "; still one piece"
    return msg


def _volume(shape) -> float:
    if mb.is_mesh(shape):
        return mb.info(shape).volume
    return robust.volume(shape)


def _solid_pieces(shape, cut: kn.Cut, width: float):
    if width == 0:
        pieces, maker = ft.split(shape, [cut.sheet()])
    else:
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut

        op = BRepAlgoAPI_Cut(shape, cut.kerf(width))
        if not op.IsDone():
            raise kn.KnifeError("the kernel could not cut the slot")
        pieces, maker = robust.solids(op.Shape()), op
    for s in pieces:
        if not robust.is_valid(s):
            raise kn.KnifeError("a piece is not a valid shape; the cut probably grazes an edge or a face, "
                                "move the stroke a little")
    return pieces, maker


def _mesh_pieces(p: Processor, b: int, shape, cut: kn.Cut, width: float):
    from .mesh_handlers import default_deflection

    pts, t = mb.arrays(shape)
    man = mb.to_manifold(pts, t, what=f"body {b}")
    size = float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0)))
    defl = default_deflection(p, shape)

    def tool(s):
        return mb.to_manifold(*mb.triangles_of(s, defl), what="the cut")

    if cut.closed and width == 0:
        inside = tool(cut.inside())
        parts = [*(man ^ inside).decompose(), *(man - inside).decompose()]
    else:
        parts = (man - tool(cut.kerf(width or HAIRLINE * size))).decompose()
    out = []
    for part in parts:
        if part.is_empty():
            continue
        q, tt = mb.from_manifold(part)
        if len(tt):
            out.append(mb.make_shape(q, tt))
    return out


class _Fresh:
    def IsDeleted(self, _old) -> bool:  # noqa: N802
        return True

    def Modified(self, _old):  # noqa: N802
        return []
