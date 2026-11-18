"""Scan to CAD, part 2 (geometry/scanfit.py): SEGMENT shows a mesh's regions and what each is
(plane, cylinder, sphere or freeform); RECONSTRUCT makes an exact solid from them."""

from __future__ import annotations

from collections import Counter

import numpy as np

from ..geometry import meshbody as mb
from ..geometry import robust
from ..geometry import scanfit as sf
from .mesh_handlers import MESH_OK, _need_mesh
from .processor import Arg, BodyRef, CommandError, Processor, command

MESH_OK.update({"SEGMENT", "RECONSTRUCT"})


def _regions(p: Processor, b: int, angle: float, tol: float, what: str):
    pts, t = _need_mesh(p, b, what)
    if not 1 <= angle <= 89:
        raise CommandError(f"{what}: the angle is 1 to 89 degrees")
    if tol < 0:
        raise CommandError(f"{what}: the tolerance cannot be negative")
    size = float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0)))
    tol = tol or 2e-3 * size
    labels = sf.segment(pts, t, angle)
    return pts, t, sf.recognise(pts, t, labels, tol), tol


def _summary(regions) -> str:
    c = Counter(r.shape.kind for r in regions)
    names = {"PLANE": "plane", "CYLINDER": "cylinder", "SPHERE": "sphere", "FREEFORM": "freeform"}
    return ", ".join(f"{c[k]} {names[k]}{'s' if c[k] != 1 else ''}" for k in names if c[k])


@command(
    "SEGMENT",
    Arg("b", BodyRef, help="a mesh body (a scan, an STL)"),
    Arg("angle", float, 25.0, "a bend sharper than this between triangles starts a new region (degrees)"),
    Arg("tol", float, 0.0, "how far points may be from a plane, cylinder or sphere to count as one "
                           "(0: 0.2% of the body's size)"),
    logged=False,
    help="Split a mesh into regions at its sharp edges and say what each is: SEGMENT, scan lists every region "
         "with its size and its plane, cylinder (or bore), sphere, or freeform fit · RECONSTRUCT makes the "
         "exact solid from them",
)
def segment(p: Processor, b, angle, tol):
    _pts, _t, regions, tol = _regions(p, b, angle, tol, "SEGMENT")
    lines = [f"body {b}: {len(regions)} regions ({_summary(regions)}), within {tol:.4g}:"]
    total = sum(r.area for r in regions) or 1.0
    for i, r in enumerate(regions[:60], 1):
        fit = f"{r.shape.words()}, off by up to {r.shape.worst:.3g}" if r.shape.kind != "FREEFORM" else "freeform"
        lines.append(f"  {i}: {len(r.tris):,} triangles, {100 * r.area / total:.1f}% of the area: {fit}")
    if len(regions) > 60:
        lines.append(f"  ... and {len(regions) - 60} more")
    return "\n".join(lines)


@command(
    "RECONSTRUCT",
    Arg("b", BodyRef, help="a closed mesh body made of flat, cylindrical and spherical faces"),
    Arg("angle", float, 25.0, "a bend sharper than this starts a new face (degrees)"),
    Arg("tol", float, 0.0, "how far the mesh may be from each fitted face (0: 0.2% of the body's size)"),
    help="Scan to CAD for machined parts: RECONSTRUCT, scan splits the mesh at its sharp edges, fits each "
         "region exactly as a plane, cylinder or sphere, and joins them into one solid (new body; the mesh "
         "stays). Rounded freeform regions are refused: fit those with FITSURF",
)
def reconstruct(p: Processor, b, angle, tol):
    from .handlers import _added

    pts, t, regions, tol = _regions(p, b, angle, tol, "RECONSTRUCT")
    if not mb.closed(t):
        raise CommandError(f"RECONSTRUCT: body {b} is open; it needs a closed mesh to know its inside")
    try:
        shape, cells, kept = sf.reconstruct(pts, t, regions)
    except sf.ScanError as exc:
        raise CommandError(f"RECONSTRUCT: body {b}: {exc}") from None
    if not robust.solids(shape) or not robust.checked_ok(shape, True):
        raise CommandError(f"RECONSTRUCT: body {b}: the joined faces do not make a valid solid "
                           "(try a smaller angle, or a larger tolerance)")
    vol = robust.volume(shape)
    mesh_vol = abs(mb.volume(pts, t))
    diff = 100 * (vol - mesh_vol) / mesh_vol if mesh_vol else 0.0
    body = p.model.add_body(shape)
    return _added(p, body, f"RECONSTRUCT body {b}: {len(regions)} faces fitted ({_summary(regions)}) within "
                           f"{tol:.3g}; volume {vol:.6g}, {diff:+.2f}% against the mesh")
