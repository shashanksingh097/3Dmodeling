"""Implicit shapes and lattices (M6b): IMPLICIT and LATTICE.

Both make mesh bodies (see geometry/implicit.py for the fields and the
meshing, geometry/meshbody.py for mesh bodies).
"""

from __future__ import annotations

import numpy as np

from ..core.model import ModelError
from ..geometry import implicit as im
from ..geometry import meshbody as mb
from ..geometry import robust
from ..lang.expr import fmt_num
from ..lang.script import is_ident
from .processor import Arg, BodyRef, CommandError, Processor, Raw, Text, command


def _lookup(p: Processor):
    def get(key: str):
        try:
            return p._lookup(key)
        except Exception:  # noqa: BLE001 - not a parameter
            raise KeyError(key) from None

    return get


def _tidy(pts: np.ndarray, t: np.ndarray, step: float) -> tuple[np.ndarray, np.ndarray]:
    """Grid meshes have many tiny triangles: merge them where the surface moves
    less than a twentieth of the grid step."""
    if len(t) > 20_000:
        try:
            return mb.simplify(pts, t, step / 20)
        except mb.MeshError:
            return pts, t
    return pts, t


@command(
    "IMPLICIT",
    Arg("name", Text, help="name of the body, and of the field for later fields"),
    Arg("f", Raw, help="the field in x, y, z: the shape is where it is at most 0"),
    Arg("x0", float, help="the box to build it in: one corner"), Arg("y0", float), Arg("z0", float),
    Arg("x1", float, help="the opposite corner"), Arg("y1", float), Arg("z1", float),
    Arg("step", float, 0.0, "grid step (default: the box's largest side / 80); smaller is finer and slower"),
    help="A shape given by an equation: the body is where f(x, y, z) <= 0, inside a box: IMPLICIT, name, f, "
         "x0,y0,z0, x1,y1,z1 [, step]. f is written like any expression, in x, y, z and parameters, with "
         "BALL(cx,cy,cz,r), BOX(cx,cy,cz,sx,sy,sz[,r]), ROD(x1,y1,z1,x2,y2,z2,r), TORUS(cx,cy,cz,R,r), "
         "CYLZ(cx,cy,r), GYROID/SCHWARZ/DIAMOND(cell), SMIN(a,b,k) and SMAX(a,b,k) (smooth union and "
         "intersection with a blend about k wide), SDIFF(a,b,k), MIN, MAX, ABS, SQRT, SIN (degrees) ... and the "
         "names of earlier IMPLICIT shapes. The result is a mesh body; where the box cuts the shape it is closed "
         "flat.",
)
def implicit(p: Processor, name, f, x0, y0, z0, x1, y1, z1, step):
    m = p.model
    if not is_ident(name):
        raise CommandError(f"IMPLICIT: {name!r} is not a valid name (letters, digits, _)")
    key = name.upper()
    if key in ("X", "Y", "Z", "LAST", "SEL", "ALL"):
        raise CommandError(f"IMPLICIT: {name} is reserved")
    box = (min(x0, x1), min(y0, y1), min(z0, z1), max(x0, x1), max(y0, y1), max(z0, z1))
    size = max(box[3] - box[0], box[4] - box[1], box[5] - box[2])
    step = step or size / 80
    try:
        fn = im.compile_field(f, _lookup(p), m.fields)
        pts, t = im.mesh_field(fn, box, step)
    except im.FieldError as exc:
        raise CommandError(f"IMPLICIT: {exc}") from None
    if len(t) == 0:
        raise CommandError("IMPLICIT: the shape is too thin for the grid step to see; use a smaller step")
    pts, t = _tidy(pts, t, step)
    old = m.body_by_name(name)
    new = mb.make_shape(pts, t)
    try:
        if old is not None:  # the same name again: a new shape for the same body
            from ..geometry.nurbs import SameTopology

            body = m.replace([old.id], new, SameTopology(old.shape, new), same_id=True)
        else:
            body = m.add_body(new, name)
    except ModelError as exc:
        raise CommandError(f"IMPLICIT: {exc}") from None
    m.fields = {**m.fields, key: im.FieldDef(name, f.strip(), box, fn)}
    from .handlers import _added

    return _added(p, body, f"IMPLICIT {name} (grid step {fmt_num(round(step, 6))})")


@command(
    "LATTICE",
    Arg("b", BodyRef),
    Arg("kind", str, help="GYROID, SCHWARZ or DIAMOND (walls), or CUBIC, BCC or OCTET (struts)"),
    Arg("cell", help="size of one repeat of the pattern"),
    Arg("thickness", help="wall thickness, or strut diameter"),
    Arg("skin", float, 0.0, "a solid outer wall this thick around the lattice (0: lattice to the edge)"),
    Arg("step", float, 0.0, "grid step (default: a third of the thickness, at least cell / 40)"),
    help="Fill a body with a lattice: LATTICE, b, kind, cell, thickness [, skin [, step]]. GYROID, SCHWARZ "
         "and DIAMOND are smooth walls; CUBIC, BCC and OCTET are struts. With a skin the body keeps a closed "
         "outer wall of that thickness (exact solids only). The body becomes a mesh body with the same ID.",
)
def lattice(p: Processor, b, kind, cell, thickness, skin, step):
    m = p.model
    body = m.body(b)
    shape = body.shape
    is_mesh = mb.is_mesh(shape)
    if not is_mesh and not robust.solids(shape):
        raise CommandError(f"LATTICE: body {b} is not a solid")
    if is_mesh and not mb.info(shape).closed:
        raise CommandError(f"LATTICE: mesh body {b} is not closed, so it has no inside to fill")
    if skin < 0:
        raise CommandError("LATTICE: the skin cannot be negative")
    from .mesh_handlers import default_deflection

    defl = default_deflection(p, shape)
    outer = mb.triangles_of(shape, defl)
    lo, hi = outer[0].min(axis=0), outer[0].max(axis=0)
    step = step or max(thickness / 3, cell / 40)
    try:
        field = im.lattice_field(kind, cell, thickness, origin=tuple(lo))
        lat = im.mesh_field(field, (*(lo - step), *(hi + step)), step)
    except im.FieldError as exc:
        raise CommandError(f"LATTICE: {exc}") from None
    if len(lat[1]) == 0:
        raise CommandError("LATTICE: the walls are too thin for the grid step; give a smaller step")
    try:
        # everything stays in manifold3d until the end: converting is what takes the time
        lat_m = mb.to_manifold(*lat, what="the lattice").simplify(step / 20)
        outer_m = mb.to_manifold(*outer, what=f"body {b}")
        if skin > 0:
            if is_mesh:
                raise CommandError("LATTICE: a skin needs an exact solid (the inside is found by offsetting its "
                                   "faces); run LATTICE before TOMESH, or use skin 0")
            from ..geometry import features as ft

            inner_shape, _ = ft.offset_shape(shape, -skin)
            if inner_shape is None or not robust.solids(inner_shape) or robust.volume(inner_shape) <= 0:
                raise CommandError(f"LATTICE: the kernel could not make the inside of body {b} {fmt_num(skin)} "
                                   "in from its faces; try a thinner skin")
            inner_m = mb.to_manifold(*mb.triangles_of(inner_shape, defl), what="the inside")
            result = (outer_m - inner_m) + (lat_m ^ inner_m)
        else:
            result = lat_m ^ outer_m
        pts, t = mb.from_manifold(result) if not result.is_empty() else (None, np.empty((0, 3)))
    except mb.MeshError as exc:
        raise CommandError(f"LATTICE: {exc}") from None
    if len(t) == 0:
        raise CommandError("LATTICE: nothing is left; the cell may be bigger than the body")
    before = mb.volume(*outer)
    new = mb.make_shape(pts, t)
    from .handlers import _added

    try:
        body = m.replace([b], new, _Fresh(), same_id=True)
    except ModelError as exc:
        raise CommandError(f"LATTICE: {exc}") from None
    left = mb.volume(pts, t) / before * 100 if before > 0 else 0.0
    what = f"LATTICE {kind.lower()} in body {b}, cell {fmt_num(cell)}, thickness {fmt_num(thickness)}"
    if skin:
        what += f", skin {fmt_num(skin)}"
    return _added(p, body, what) + f"; {left:.0f}% of the volume is left"


class _Fresh:
    def IsDeleted(self, _old) -> bool:  # noqa: N802
        return True

    def Modified(self, _old):  # noqa: N802
        return []
