"""Sculpting mesh bodies (M7): SCULPT runs one brush stroke, MASK freezes
regions, STROKE records the points of a stroke.

A stroke's points are kept by name (``S1``, ``S2`` ...) in the session and
saved with the project (``strokes.npz``), so a history line stays short and
sculpting replays like every other step:

    STROKE, S1, "0,-10,17.3  0,0,20  0,10,17.3"   ! (made by the Sculpt tool when you draw)
    SCULPT, head, DRAW, 3, 0.5, S1, X
"""

from __future__ import annotations

import re

import numpy as np

from ..core.model import Event
from ..geometry import meshbody as mb
from ..geometry import sculpt as sc
from ..lang.expr import fmt_num
from .mesh_handlers import _need_mesh, _swap
from .processor import Arg, BodyRef, CommandError, Processor, Text, command

_NAME = re.compile(r"^[A-Za-z_]\w*$")


def parse_points(text: str) -> np.ndarray:
    """ "x,y,z  x,y,z ..." (commas or spaces; semicolons allowed between points) -> N x 3."""
    nums = [float(v) for v in re.split(r"[,\s;]+", text.strip()) if v]
    if not nums or len(nums) % 3:
        raise CommandError("a stroke is x, y, z for each point (a multiple of 3 numbers)")
    return np.asarray(nums, dtype=float).reshape(-1, 3)


def format_points(pts: np.ndarray, digits: int = 4) -> str:
    return "  ".join(",".join(fmt_num(round(float(v), digits)) for v in p) for p in np.asarray(pts).reshape(-1, 3))


def new_stroke_name(p: Processor) -> str:
    """The next free stroke name, S1, S2 ..."""
    n = len(p.strokes) + 1
    while f"S{n}" in p.strokes:
        n += 1
    return f"S{n}"


def _stroke_points(p: Processor, text: str, what: str) -> np.ndarray:
    raw = text.strip()
    if _NAME.match(raw):
        pts = p.strokes.get(raw.upper())
        if pts is None:
            raise CommandError(f"{what}: there is no stroke named {raw} (STROKE, {raw}, \"x,y,z ...\" records one)")
        return pts
    return parse_points(raw)


@command(
    "STROKE",
    Arg("name", str, help="S1, S2 ..."),
    Arg("points", Text, "", "x,y,z for each point, in quotes; empty: keep the points already stored"),
    help="Record the points of a sculpt stroke under a name, for SCULPT: STROKE, S1, \"0,0,20  5,0,19\". The "
         "Sculpt tool writes these for you; the points are saved with the project.",
)
def stroke_cmd(p: Processor, name, points):
    if not _NAME.match(name):
        raise CommandError(f"STROKE: {name} is not a name (letters, digits, _)")
    if points.strip():
        p.strokes[name.upper()] = parse_points(points)
    elif name.upper() not in p.strokes:
        raise CommandError(f"STROKE: {name} has no points yet: give them")
    return f"stroke {name.upper()}: {len(p.strokes[name.upper()])} points"


@command(
    "SCULPT",
    Arg("b", BodyRef),
    Arg("brush", str, help=", ".join(sc.BRUSHES)),
    Arg("radius", help="the brush radius"),
    Arg("strength", help="how far one dab moves, -1 to 1 as a part of the radius (negative: the other way)"),
    Arg("stroke", Text, help="a stroke name (S1) or the points in quotes"),
    Arg("sym", str, "", "mirror the stroke in x = 0, y = 0 and/or z = 0: X, Y, Z, XY ..."),
    Arg("detail", float, 0.0, "first split the triangles near the stroke until no edge there is longer than "
                              "this, so the brush has enough points to shape, and afterwards join edges the "
                              "brush squeezed shorter than 0.4 times it (0: keep the triangles)"),
    help="Run one sculpt brush stroke over a mesh body: SCULPT, b, brush, radius, strength, stroke [, sym "
         "[, detail]]. "
         "Brushes: DRAW (raise along the surface), CLAY (build up flat layers), INFLATE, SMOOTH, FLATTEN, "
         "PINCH, CREASE (a sharp groove), GRAB (move what is under the first point to the last). A masked "
         "region (MASK) does not move. TOMESH a solid first; REMESH it so there are enough points to move.",
)
def sculpt_cmd(p: Processor, b, brush, radius, strength, stroke, sym, detail):
    pts, t = _need_mesh(p, b, "SCULPT")
    path = _stroke_points(p, stroke, "SCULPT")
    mask = p.model.masks.get(b)
    if mask is not None and len(mask) != len(pts):
        mask = None
    added = joined = 0
    try:
        if detail < 0:
            raise sc.SculptError("the detail size is 0 (off) or more")
        if detail > 0:
            if float(radius) / detail > 200:
                raise sc.SculptError(f"a detail of {fmt_num(detail)} is too fine for a radius of {fmt_num(radius)} "
                                     f"(use at least {fmt_num(float(radius) / 200)})")
            centres = sc.resample(path, float(radius) * sc.SPACING)
            centres = np.vstack([centres * s for s in sc._mirrors(sym)])
            pts, t, mask, added = sc.refine_near(pts, t, detail, centres, float(radius) * 1.25, mask)
            if len(t) > mb.MAX_MESH_BODY_TRIANGLES:
                raise sc.SculptError(f"that makes {len(t):,} triangles, more than {mb.MAX_MESH_BODY_TRIANGLES:,}; "
                                     f"use a larger detail size")
        new, rep = sc.stroke(pts, t, brush, float(radius), float(strength), path, sym, mask)
        if detail > 0 and rep.moved:  # join what the brush squeezed together
            new, t, mask, joined = sc.collapse_near(new, t, detail * sc.JOIN, centres, float(radius) * 1.25, mask)
    except sc.SculptError as exc:
        raise CommandError(f"SCULPT: {exc}") from None
    if rep.moved == 0:
        raise CommandError(f"SCULPT: the stroke is not near body {b} (no point within {fmt_num(radius)} of it)")
    msg = _swap(p, b, new, t, f"SCULPT {brush.upper()} on body {b}", moved_only=not (added or joined))
    if mask is not None and len(mask) == len(new):
        p.model.masks[b] = mask  # the same points (or the new ones given their edge's mask): it still fits
    more = f", {added:,} points added for detail" if added else ""
    more += f", {joined:,} squeezed together joined" if joined else ""
    return f"{msg}; {rep.moved:,} points moved (at most {fmt_num(round(rep.largest, 4))}), {rep.dabs} dabs{more}"


@command(
    "MASK",
    Arg("b", BodyRef),
    Arg("mode", str, help="PAINT, ERASE, CLEAR, ALL, INVERT"),
    Arg("x", float, 0.0),
    Arg("y", float, 0.0),
    Arg("z", float, 0.0),
    Arg("r", float, 0.0, "the radius of the soft sphere PAINT and ERASE use"),
    Arg("value", float, 1.0, "how frozen, 0 to 1"),
    Arg("stroke", Text, "", "PAINT or ERASE along a stroke (a name or points) instead of at x, y, z"),
    help="Freeze part of a mesh body so sculpting leaves it alone: MASK, b, PAINT, x, y, z, r freezes a soft "
         "sphere; ERASE unfreezes one; CLEAR unfreezes all; ALL freezes all; INVERT swaps frozen and free. "
         "With a stroke (MASK, b, PAINT, 0,0,0, r, 1, S3) it paints along the stroke.",
)
def mask_cmd(p: Processor, b, mode, x, y, z, r, value, stroke):
    pts, _t = _need_mesh(p, b, "MASK")
    mode = mode.upper()
    old = p.model.masks.get(b)
    if old is not None and len(old) != len(pts):
        old = None  # the mesh changed (REMESH ...): the old mask no longer fits
    if mode in ("PAINT", "ERASE"):
        if r <= 0:
            raise CommandError(f"MASK: {mode} needs a radius")
        if not 0 < value <= 1:
            raise CommandError("MASK: the value is above 0 and at most 1")
        centres = [(x, y, z)]
        if stroke.strip():
            centres = sc.resample(_stroke_points(p, stroke, "MASK"), r * sc.SPACING)
        new = old
        for c in centres:
            new = sc.sphere_mask(pts, c, r, value, new, mode)
    elif mode == "CLEAR":
        p.model.masks.pop(b, None)
        p.model._emit(Event("mask", b))
        return f"mask on body {b} cleared"
    elif mode == "ALL":
        new = np.ones(len(pts))
    elif mode == "INVERT":
        new = 1.0 - (old if old is not None else np.zeros(len(pts)))
    else:
        raise CommandError("MASK: use PAINT, ERASE, CLEAR, ALL or INVERT")
    p.model.masks[b] = new
    p.model._emit(Event("mask", b))
    frozen = int(np.count_nonzero(new > 0.5))
    return f"mask on body {b}: {frozen:,} of {len(pts):,} points frozen"


def describe_mask(p: Processor, b: int) -> str:
    m = p.model.masks.get(b)
    if m is None:
        return "no mask"
    pts, _ = mb.arrays(p.model.body(b).shape)
    if len(m) != len(pts):
        return "a mask from before the mesh changed (ignored)"
    return f"{int(np.count_nonzero(m > 0.5)):,} of {len(m):,} points frozen"
