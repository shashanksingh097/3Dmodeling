"""Freeform surface operations: BLEND between surfaces, EXTEND and TRIM a
surface, and MOVEFACE / REPLACEFACE on solids (see geometry/surface_ops.py)."""

from __future__ import annotations

from OCP.TopAbs import TopAbs_FACE

from ..core.model import ModelError
from ..geometry import nurbs as nb
from ..geometry import robust
from ..geometry import surface_ops as so
from ..lang.expr import fmt_num
from .curve_handlers import _new
from .nurbs_handlers import _edge_with_face, _geometry, _put_back
from .processor import Arg, BodyRef, CommandError, Processor, Raw, command


def _run(what: str, fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except nb.CurveError as exc:
        raise CommandError(f"{what}: {exc}") from None


def _edge_ids(p: Processor, raws: list[str], what: str) -> list[int]:
    m = p.model
    out: list[int] = []
    for raw in (r.strip() for r in raws):
        if not raw:
            continue
        if raw.upper() == "SEL":
            if m.selection_kind != "EDGE" or not m.selection:
                raise CommandError(f"{what}: SEL stands for the picked edges, and no edges are picked")
            out += list(m.selection)
            continue
        v = p.evaluate(raw)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not float(v).is_integer():
            raise CommandError(f"{what}: an edge is given by its ID, got {raw}")
        out.append(int(v))
    for gid in out:
        try:
            m.entity_owner("EDGE", gid)
        except ModelError as exc:
            raise CommandError(f"{what}: {exc}") from None
    return out


# =============================================================================
# BLEND
# =============================================================================


@command(
    "BLEND",
    Arg("cont", str, "G1", "G1 (no crease where it meets the surfaces) or G2 (no jump in curvature either)"),
    Arg("e1", Raw, "SEL", "the first edge (its ID), or SEL for the two picked edges"),
    Arg("e2", Raw, "", "the second edge"),
    Arg("bulge", float, 1.0, "how far the blend swings out before it turns (1 is even; more is fuller)"),
    help="Bridge the gap between two surfaces with a smooth surface that meets each one along an edge: pick an "
         "edge of each and BLEND, G2 · BLEND, G1, 12, 31 · BLEND, G2, SEL, , 1.5 (fuller). The surfaces stay; "
         "SEW them with the blend to make one skin.",
)
def blend(p: Processor, cont, e1, e2, bulge):
    if cont not in ("G1", "G2"):
        raise CommandError("BLEND: the smoothness is G1 or G2")
    ids = _edge_ids(p, [e1, e2], "BLEND")
    if len(ids) != 2:
        raise CommandError(f"BLEND: give two edges, one on each surface (got {len(ids)})")
    sides = []
    for gid in ids:
        edge, face = _edge_with_face(p, gid, "BLEND")
        if face is None:
            raise CommandError(f"BLEND: edge {gid} is not on a surface")
        sides.append((edge, face))
    if p.model.entity_owner("EDGE", ids[0])[0] == p.model.entity_owner("EDGE", ids[1])[0] and \
            sides[0][1].IsSame(sides[1][1]):
        raise CommandError("BLEND: both edges are on the same face; pick an edge of each surface")
    face, worst = _run("BLEND", so.blend, sides[0], sides[1], cont, bulge)
    if worst > 0.5:
        p.warn(f"BLEND: the blend meets the surfaces within {worst:.2g} degrees (a long or twisted gap); "
               "try another bulge")
    return _new(p, face, f"BLEND {cont} between edges {ids[0]} and {ids[1]} (meets within {worst:.2g} degrees)",
                solid=False)


# =============================================================================
# EXTEND and TRIM
# =============================================================================


def _side_of_edge(p: Processor, bid: int, g) -> str | None:
    """U0/U1/V0/V1 for a picked edge of this body, if one is picked."""
    m = p.model
    if m.selection_kind != "EDGE" or not m.selection:
        return None
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.gp import gp_Pnt

    from .queries import centre

    for gid in m.selection:
        if m.entity_owner("EDGE", gid)[0] != bid:
            continue
        c = centre("EDGE", m.entity_shape("EDGE", gid))
        pr = GeomAPI_ProjectPointOnSurf(gp_Pnt(*c), g)
        u, v = pr.LowerDistanceParameters()
        u0, u1, v0, v1 = g.Bounds()
        gaps = {"U0": (u - u0) / (u1 - u0), "U1": (u1 - u) / (u1 - u0), "V0": (v - v0) / (v1 - v0),
                "V1": (v1 - v) / (v1 - v0)}
        return min(gaps, key=gaps.get)
    return None


@command(
    "EXTEND",
    Arg("body", BodyRef, help="a single surface"),
    Arg("d", help="how far to carry it on"),
    Arg("side", str, "", "U0, U1, V0, V1 or ALL; left out: the side whose edge is picked (else ALL)"),
    help="Carry a surface on past an edge the way it was going: pick its edge, then EXTEND, s, 5 · EXTEND, s, 5, "
         "ALL · EXTEND, s, 3, V1. POLES and the edge's place tell which side is U0 (start of u) and so on.",
)
def extend(p: Processor, body, d, side):
    if d <= 0:
        raise CommandError("EXTEND: the distance must be greater than 0")
    g = _geometry(p, body, "EXTEND")
    if isinstance(g, nb.Geom_BSplineCurve):
        raise CommandError("EXTEND: body is a curve; EXTEND works on a surface")
    side = side or _side_of_edge(p, body, g) or "ALL"
    new = _run("EXTEND", so.extend, g, d, side)
    return _put_back(p, body, new, f"EXTEND body {body} by {fmt_num(d)} at {side}")


@command(
    "TRIM",
    Arg("body", BodyRef, help="the surface to trim"),
    Arg("curve", BodyRef, help="the cutting curve; it is laid onto the surface along the surface's normal"),
    Arg("x", float, help="a point on (or near) the piece to remove"), Arg("y", float), Arg("z", float),
    Arg("mode", str, "REMOVE", "REMOVE that piece (default) or KEEP only it"),
    help="Cut a surface with a curve and remove the piece nearest a point: TRIM, s, c, 10, 5, 0 · keep only that "
         "piece: TRIM, s, c, 10, 5, 0, KEEP. The curve must cross the surface from edge to edge, or close into "
         "a loop on it (a hole).",
)
def trim(p: Processor, body, curve, x, y, z, mode):
    from .handlers import _added

    if mode not in ("REMOVE", "KEEP"):
        raise CommandError("TRIM: the mode is REMOVE or KEEP")
    m = p.model
    shape = m.body(body).shape
    faces = nb._subs(shape, TopAbs_FACE)
    if len(faces) != 1:
        raise CommandError(f"TRIM: body {body} is not a single surface")
    if nb.kind_of(m.body(curve).shape) != "curve":
        raise CommandError(f"TRIM: body {curve} is not a curve")
    out, n, maker = _run("TRIM", so.trim, nb._as_face(faces[0]), m.body(curve).shape, (x, y, z), mode == "KEEP")
    try:
        new = m.replace([body], out, maker, same_id=True)
    except ModelError as exc:
        raise CommandError(f"TRIM: {exc}") from None
    what = "kept the piece" if mode == "KEEP" else "removed the piece"
    return _added(p, new, f"TRIM body {body} by curve {curve}: {n} pieces, {what} nearest "
                          f"({fmt_num(x)}, {fmt_num(y)}, {fmt_num(z)})")


@command(
    "PROJECT",
    Arg("curve", BodyRef, help="the curve to lay onto the surface"),
    Arg("surface", BodyRef, help="a surface (or any body: its faces)"),
    Arg("dx", float, 0.0, "direction to project along; all 0 = along the surface's normal"),
    Arg("dy", float, 0.0), Arg("dz", float, 0.0),
    help="Lay a curve onto a surface as a new curve (the original stays): along the surface's normal, PROJECT, "
         "c, hull · or straight along a direction, PROJECT, c, dome, 0, 0, -1. The new curve can be a path for "
         "SWEEP ... NORMAL, or cut the surface with TRIM.",
)
def project(p: Processor, curve, surface, dx, dy, dz):
    m = p.model
    if nb.kind_of(m.body(curve).shape) != "curve":
        raise CommandError(f"PROJECT: body {curve} is not a curve")
    if not nb._subs(m.body(surface).shape, TopAbs_FACE):
        raise CommandError(f"PROJECT: body {surface} has no faces to lay the curve on")
    d = None if dx == dy == dz == 0 else (dx, dy, dz)
    shape, n = _run("PROJECT", so.project, m.body(curve).shape, m.body(surface).shape, d)
    how = "along the surface's normal" if d is None else f"along ({fmt_num(dx)}, {fmt_num(dy)}, {fmt_num(dz)})"
    b = m.add_body(shape)
    if n == 1:
        from ..geometry import sweep as sw

        kind = "closed" if shape.Closed() else "open"
        return (f"PROJECT curve {curve} onto body {surface} {how} -> curve {b.id} ({kind}, length "
                f"{fmt_num(round(sw.PathSampler(shape).length, 4))})")
    p.warn(f"PROJECT: the curve lands on the surface in {n} separate pieces, so it is not one path")
    return f"PROJECT curve {curve} onto body {surface} {how} -> body {b.id} ({n} pieces)"


# =============================================================================
# Faces of solids
# =============================================================================


def _replace(p: Processor, what: str, make_new) -> str:
    from .handlers import _added
    from .shape_handlers import _faces

    m = p.model
    msgs = []
    for bid, fids in _faces(p, what).items():
        body = m.body(bid)
        before = robust.volume(body.shape)
        shape = body.shape
        replaced = []
        for fid in fids:
            face = nb._as_face(m.entity_shape("FACE", fid))
            tool = make_new(face)
            if replaced:  # the face as it is after the earlier ones: the result's face on the same surface
                now = so.SurfaceMatch(body.shape, shape, []).Modified(face)
                if len(now) != 1:
                    raise CommandError(f"{what}: face {fid} was changed by an earlier face; give it in a step of "
                                       "its own")
                face = now[0]
            try:
                shape, _ = so.replace_face(shape, face, tool, robust.diagonal(shape))
            except nb.CurveError as exc:
                raise CommandError(f"{what}: face {fid}: {exc}") from None
            shape, _, _ = robust.merge_faces(robust.unwrap(shape))
            replaced.append((nb._as_face(m.entity_shape("FACE", fid)), tool))
        maker = so.SurfaceMatch(body.shape, shape, replaced)
        if robust.is_empty(shape) or not robust.is_valid(shape) or len(robust.solids(shape)) != 1:
            raise CommandError(f"{what}: body {bid} would not stay one valid solid (the new surface may not reach "
                               "across the whole face, or it cuts the body in two)")
        new = m.replace([bid], shape, maker, same_id=True)
        change = robust.volume(shape) - before
        msgs.append(_added(p, new, f"{what} face{'s' if len(fids) > 1 else ''} {', '.join(map(str, fids))} of body "
                                   f"{bid} (volume {'+' if change >= 0 else '-'}{abs(change):.4g})"))
    return "\n".join(msgs)


@command(
    "MOVEFACE",
    Arg("dx"), Arg("dy"), Arg("dz"),
    help="Move the picked faces of a solid by a distance in any direction; the faces around them stretch or "
         "shrink to meet them: PICK, FACE, 7 then MOVEFACE, 0, 0, 3. A flat face moved along itself does not "
         "change; for a move along the normal, PUSHPULL does the same.",
)
def moveface(p: Processor, dx, dy, dz):
    if dx == dy == dz == 0:
        raise CommandError("MOVEFACE: the move cannot be (0, 0, 0)")
    return _replace(p, "MOVEFACE", lambda face: so.moved(face, (dx, dy, dz)))


@command(
    "REPLACEFACE",
    Arg("surface", BodyRef, help="a surface body: the picked faces take its shape"),
    help="Give the picked faces of a solid the shape of a surface: the solid is grown or cut back to it, and the "
         "faces around stretch to meet it: PICK, FACE, 7 then REPLACEFACE, dome. The surface is carried on past "
         "its edges as far as needed and stays as it is.",
)
def replaceface(p: Processor, surface):
    shape = p.model.body(surface).shape
    faces = nb._subs(shape, TopAbs_FACE)
    if len(faces) != 1:
        raise CommandError(f"REPLACEFACE: body {surface} must be a single surface")
    tool = nb._as_face(faces[0])
    return _replace(p, "REPLACEFACE", lambda face: tool)
