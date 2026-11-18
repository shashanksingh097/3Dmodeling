"""Mesh bodies (M6): TOMESH, TOSOLID, SMOOTH, REMESH, SIMPLIFY, and the mesh
route of UNION / SUBTRACT / INTERSECT (see geometry/meshbody.py).

A mesh body is one face that carries a triangulation. It keeps its body ID
and its one face ID through every mesh command, so picks and names survive.
"""

from __future__ import annotations

import numpy as np

from ..core.model import UNITS, ModelError
from ..geometry import meshbody as mb
from ..geometry import nurbs as nb
from ..geometry import robust
from ..lang.expr import fmt_num
from .processor import Arg, BodyRef, CommandError, Processor, command

# Commands that take a mesh body. Every other command that names a mesh body
# is refused with a pointer to TOSOLID, instead of a kernel error.
MESH_OK = {
    "MOVE", "ROTATE", "COPY", "MIRROR", "DELETE", "NAME", "HIDE", "SHOW", "UNION", "SUBTRACT", "INTERSECT",
    "EXPORT", "COLOR", "LAYER", "MATERIAL", "FADE", "UNFADE", "DISPLAY", "ISOLATE", "DESCRIBE", "MASSPROP",
    "STEPS", "TOSOLID", "TOMESH", "SMOOTH", "REMESH", "SIMPLIFY", "BEND", "TWIST", "TAPER", "STRETCH", "FLOW",
    "LIST", "FIT", "ASSERT", "DIST", "CLASH", "PROBE", "ECHO", "PICK", "SEL", "CM", "CMSEL", "CMDEL", "PICKMODE",
    "RELATE", "CHECK", "LATTICE", "KNIFE", "DRAWING", "SCULPT", "MASK", "FITSURF",
}


def check_mesh_use(p: Processor, cmd_name: str, bid: int) -> None:
    """Refuse a command that cannot work on a mesh body, saying what to do instead."""
    if cmd_name in MESH_OK:
        return
    body = p.model.bodies.get(bid)
    if body is not None and mb.is_mesh(body.shape):
        raise CommandError(f"{cmd_name}: body {bid} is a mesh body ({mb.info(body.shape).triangles:,} triangles); "
                           f"{cmd_name} needs faces and edges. TOSOLID, {bid} turns it into a faceted solid first "
                           "(up to 100,000 triangles), or use the mesh commands: UNION, SUBTRACT, INTERSECT, "
                           "SMOOTH, REMESH, SIMPLIFY")


def is_mesh_body(p: Processor, bid: int) -> bool:
    return mb.is_mesh(p.model.body(bid).shape)


def describe(shape) -> str:
    """The size part of a body message: '(mesh, 12,000 triangles, closed)'."""
    _pts, t = mb.arrays(shape)  # (not mb.info: its volume and area take a while on a big mesh)
    return f"(mesh, {len(t):,} triangles{'' if mb.closed(t) else ', open'})"


def default_deflection(p: Processor, shape) -> float:
    """How far triangles may sit from a curved face: a thousandth of the body's size, at most 0.1 mm."""
    size = robust.diagonal(shape)
    return max(min(size * 1e-3, 0.1 * UNITS["MM"] / UNITS[p.model.units]), size * 1e-5, 1e-6)


def mesh_of(p: Processor, bid: int, deflection: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    shape = p.model.body(bid).shape
    if mb.is_mesh(shape):
        return mb.arrays(shape)
    if not robust.solids(shape):
        raise CommandError(f"body {bid} is not a solid (a surface or a curve), so it has no inside to combine")
    return mb.triangles_of(shape, deflection or default_deflection(p, shape))


def _swap(p: Processor, bid: int, pts: np.ndarray, t: np.ndarray, what: str, moved_only: bool = False) -> str:
    """Put new triangles into body ``bid``: it keeps its ID, name and face ID. ``moved_only``: the
    same triangles with some points moved (sculpting), which is much quicker to build."""
    from .handlers import _added

    if len(t) == 0:
        raise CommandError(f"{what}: no triangles are left")
    old = p.model.body(bid).shape
    new = mb.moved_shape(old, pts) if moved_only else mb.make_shape(pts, t)
    try:
        body = p.model.replace([bid], new, nb.SameTopology(old, new), same_id=True)
    except ModelError as exc:
        raise CommandError(f"{what}: {exc}") from None
    return _added(p, body, what)


def boolean(p: Processor, name: str, a: int, tools: list[int]):
    """UNION / SUBTRACT / INTERSECT when any input is a mesh body: everything is
    meshed, combined in manifold3d, and the result is a mesh body."""
    meshes = []
    for b in [a, *tools]:
        try:
            meshes.append(mesh_of(p, b))
        except CommandError as exc:
            raise CommandError(f"{name}: {exc}") from None
    try:
        pts, t = mb.boolean(name, meshes[0], meshes[1:])
    except mb.MeshError as exc:
        raise CommandError(f"{name}: {exc}") from None
    if len(t) == 0:
        from .handlers import _EMPTY

        raise CommandError(f"{name}: " + _EMPTY[name].format(a=a))
    if name == "UNION":
        n = mb.pieces(pts, t)
        if n > 1:
            p.warn(f"UNION: the bodies do not all touch, so the result is one mesh body made of {n} separate pieces")
    return mb.make_shape(pts, t)


@command(
    "TOMESH",
    Arg("b", BodyRef),
    Arg("deflection", float, 0.0, "how far a triangle may sit from a curved face (default: a thousandth of "
                                  "the body's size, at most 0.1 mm)"),
    help="Turn a solid into a mesh body: TOMESH, b [, deflection]. It keeps its ID; booleans with other mesh "
         "bodies then run on triangles (fast at any size), and SMOOTH, REMESH and SIMPLIFY work on it. "
         "TOSOLID turns it back into a faceted solid.",
)
def tomesh(p: Processor, b, deflection):
    shape = p.model.body(b).shape
    if mb.is_mesh(shape):
        return f"body {b} is already a mesh body {describe(shape)}"
    if deflection < 0:
        raise CommandError("TOMESH: the deflection cannot be negative")
    if not robust.solids(shape):
        raise CommandError(f"TOMESH: body {b} is not a solid; only solids become mesh bodies")
    pts, t = mb.triangles_of(shape, deflection or default_deflection(p, shape))
    return _swap(p, b, pts, t, f"TOMESH body {b}")


@command(
    "TOSOLID",
    Arg("b", BodyRef),
    help="Turn a mesh body into a faceted solid (one flat face per triangle, up to 100,000 triangles), so "
         "commands that need faces and edges (SPLIT, SECTION, HOLE, SHELL ...) can use it: TOSOLID, b. "
         "SIMPLIFY a big mesh first.",
)
def tosolid(p: Processor, b):
    from ..geometry import meshfiles
    from .handlers import _added
    from .project_handlers import MAX_MESH_TRIANGLES

    shape = p.model.body(b).shape
    if not mb.is_mesh(shape):
        return f"body {b} is not a mesh body"
    pts, t = mb.arrays(shape)
    if len(t) > MAX_MESH_TRIANGLES:
        raise CommandError(f"TOSOLID: body {b} has {len(t):,} triangles; up to {MAX_MESH_TRIANGLES:,} can become "
                           f"faces. SIMPLIFY, {b}, tolerance first")
    pieces = meshfiles.mesh_to_pieces(pts, t)
    if not pieces:
        raise CommandError(f"TOSOLID: body {b} has no triangles with area")
    if len(pieces) == 1:
        new = pieces[0].shape
    else:
        from OCP.BRep import BRep_Builder
        from OCP.TopoDS import TopoDS_Compound

        new, bld = TopoDS_Compound(), BRep_Builder()
        bld.MakeCompound(new)
        for pc in pieces:
            bld.Add(new, pc.shape)
    open_ = sum(1 for pc in pieces if not pc.closed)
    if open_:
        p.warn(f"TOSOLID: {open_} piece(s) of body {b} are open, so they became surfaces, not solids")
    try:
        body = p.model.replace([b], new, _Fresh(), same_id=True)
    except ModelError as exc:
        raise CommandError(f"TOSOLID: {exc}") from None
    return _added(p, body, f"TOSOLID body {b}")


class _Fresh:
    """A maker with no history: the new faces get new IDs."""

    def IsDeleted(self, _old) -> bool:  # noqa: N802
        return True

    def Modified(self, _old):  # noqa: N802
        return []


def _need_mesh(p: Processor, b: int, what: str):
    shape = p.model.body(b).shape
    if not mb.is_mesh(shape):
        raise CommandError(f"{what}: body {b} is not a mesh body; TOMESH, {b} makes it one")
    return mb.arrays(shape)


@command(
    "SMOOTH",
    Arg("b", BodyRef),
    Arg("steps", int, 5, "how many smoothing passes (more: smoother)"),
    Arg("strength", float, 0.5, "how far each pass moves a point towards its neighbours, 0 to 1"),
    help="Smooth a mesh body: bumps and noise go, the body keeps its size (Taubin smoothing): SMOOTH, b "
         "[, steps, strength]. Long thin triangles are split first, so corners are not pulled far in.",
)
def smooth(p: Processor, b, steps, strength):
    pts, t = _need_mesh(p, b, "SMOOTH")
    if steps < 1 or not 0 < strength <= 1:
        raise CommandError("SMOOTH: steps is 1 or more, and the strength is above 0 and at most 1")
    # long thin triangles next to small ones would pull their corners far in:
    # split long edges first, so every point moves about as far as its neighbours are
    lengths = mb.edge_lengths(pts, t)
    typical = float(np.median(lengths))
    note = ""
    if lengths.max() > 3 * typical:
        try:
            pts, t2 = mb.refine(pts, t, 2 * typical)
        except mb.MeshError as exc:
            raise CommandError(f"SMOOTH: {exc}") from None
        if len(t2) > mb.MAX_MESH_BODY_TRIANGLES:
            raise CommandError(f"SMOOTH: body {b} has very uneven triangles; REMESH it to an even size first")
        note = f"; long triangles split first, {len(t):,} -> {len(t2):,}"
        t = t2
    new = mb.smooth(pts, t, steps, strength)
    return _swap(p, b, new, t, f"SMOOTH body {b} ({steps} passes{note})")


@command(
    "REMESH",
    Arg("b", BodyRef),
    Arg("length", help="the longest an edge may be"),
    help="Make a mesh body's triangles finer: every edge longer than length is split, and the shape stays the "
         "same: REMESH, b, length. Use it before SMOOTH, and to give flat regions enough points to bend.",
)
def remesh(p: Processor, b, length):
    pts, t = _need_mesh(p, b, "REMESH")
    if length <= 0:
        raise CommandError("REMESH: the length must be positive")
    size = float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0)))
    if size / length > 2000:
        raise CommandError(f"REMESH: {fmt_num(length)} is too fine for a body {fmt_num(size)} across "
                           f"(it would make millions of triangles); use at least {fmt_num(size / 2000)}")
    mask = p.model.masks.get(b)
    if mask is not None and len(mask) != len(pts):
        mask = None
    try:
        if mask is None:
            new_pts, new_t = mb.refine(pts, t, length)
        else:  # split edges in place, so the points keep their order and the sculpt mask still fits
            from ..geometry import sculpt as sc

            new_pts, new_t, mask, _ = sc.refine_near(pts, t, length, None, 0.0, mask, passes=30, relax=0)
    except mb.MeshError as exc:
        raise CommandError(f"REMESH: {exc}") from None
    if len(new_t) > mb.MAX_MESH_BODY_TRIANGLES:
        raise CommandError(f"REMESH: that makes {len(new_t):,} triangles, more than "
                           f"{mb.MAX_MESH_BODY_TRIANGLES:,}; use a longer length")
    msg = _swap(p, b, new_pts, new_t, f"REMESH body {b} to edges of at most {fmt_num(length)}")
    if mask is not None:
        p.model.masks[b] = mask
        msg += "; the sculpt mask is kept"
    return msg


@command(
    "SIMPLIFY",
    Arg("b", BodyRef),
    Arg("tolerance", help="how far the surface may move"),
    help="Use fewer triangles on a mesh body without moving its surface more than tolerance: SIMPLIFY, b, "
         "tolerance. Flat regions lose the most triangles.",
)
def simplify(p: Processor, b, tolerance):
    pts, t = _need_mesh(p, b, "SIMPLIFY")
    if tolerance <= 0:
        raise CommandError("SIMPLIFY: the tolerance must be positive")
    try:
        new_pts, new_t = mb.simplify(pts, t, tolerance)
    except mb.MeshError as exc:
        raise CommandError(f"SIMPLIFY: {exc}") from None
    return _swap(p, b, new_pts, new_t, f"SIMPLIFY body {b} from {len(t):,} triangles")


# =============================================================================
# Fitting smooth surfaces to meshes (scan to CAD)
# =============================================================================
@command(
    "FITSURF",
    Arg("b", BodyRef),
    Arg("region", str, "ALL", "ALL, MASK (the points painted with MASK) or UNMASKED"),
    Arg("tol", float, 0.0, "largest distance from the mesh allowed (0: 0.1% of the body's size)"),
    Arg("trim", str, "YES", "YES: cut the surface to the region's outline; NO: keep the whole rectangle"),
    help="Fit a smooth NURBS surface to a mesh body, for scan to CAD: FITSURF, b gives a solid for a closed "
         "rounded mesh, or a face for an open scan · FITSURF, b, MASK fits only the region painted with MASK "
         "(it must not fold back on itself; fit a shape in pieces) · tol: the largest distance allowed; the "
         "control grid gets finer until it is met · the mesh stays; the new body is added",
)
def fitsurf(p: Processor, b, region, tol, trim):
    from ..geometry import meshfit as mf
    from .handlers import _added

    pts, t = _need_mesh(p, b, "FITSURF")
    region, trim = region.upper(), trim.upper()
    if region not in ("ALL", "MASK", "UNMASKED"):
        raise CommandError("FITSURF: the region is ALL, MASK or UNMASKED")
    if trim not in ("YES", "NO"):
        raise CommandError("FITSURF: trim is YES or NO")
    if tol < 0:
        raise CommandError("FITSURF: the tolerance cannot be negative")
    size = float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0)))
    tol = tol or 1e-3 * size
    keep = None
    if region != "ALL":
        m = p.model.masks.get(b)
        if m is None or len(m) != len(pts):
            raise CommandError(f"FITSURF: body {b} has no mask; paint the region with MASK, {b}, PAINT first")
        keep = m > 0.5 if region == "MASK" else m <= 0.5
    try:
        if keep is None and mb._closed(t):
            fit = mf.fit_closed(pts, t, tol)
            kind = "solid"
        else:
            pp, tt, pieces = mf.patch(pts, t, keep)
            if pieces > 1:
                p.warn(f"FITSURF: the region is in {pieces} separate pieces; only the biggest was fitted")
            fit = mf.fit_patch(pp, tt, tol, trim=trim == "YES")
            kind = "face"
    except mf.FitError as exc:
        raise CommandError(f"FITSURF: {exc}") from None
    except nb.NurbsError as exc:
        raise CommandError(f"FITSURF: {exc}") from None
    u = p.model.units.lower()
    if not fit.reached:
        p.warn(f"FITSURF: the finest grid ({fit.poles[0]} x {fit.poles[1]}) is still up to "
               f"{fit.max_dev:.3g} {u} away (asked {tol:.3g}); fit smaller regions for more detail, or a "
               f"denser mesh (REMESH)")
    body = p.model.add_body(fit.shape)
    return _added(p, body, f"FITSURF body {b} ({kind}, {fit.poles[0]} x {fit.poles[1]} control points, "
                           f"off by at most {fit.max_dev:.3g} {u}, {fit.mean_dev:.2g} on average)")
