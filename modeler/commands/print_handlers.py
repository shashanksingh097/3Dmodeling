"""PRINTCHECK: is a solid ready to 3D print? (geometry/printing.py), in words and as colours."""

from __future__ import annotations

import re

import numpy as np

from ..geometry import printing as prt
from .processor import Arg, BodyRef, CommandError, Processor, Text, command


def parse_up(text: str) -> tuple | str:
    """+Z, -X ..., BEST, or three numbers."""
    w = text.strip().strip('"').upper().replace(" ", "")
    if not w:
        return prt.DIRECTIONS["+Z"]
    if w == "BEST":
        return "BEST"
    if w in prt.DIRECTIONS:
        return prt.DIRECTIONS[w]
    if w in ("X", "Y", "Z"):
        return prt.DIRECTIONS["+" + w]
    parts = [q for q in re.split(r"[,;]+", text.strip().strip('"').replace(" ", ",")) if q]
    try:
        v = tuple(float(q) for q in parts)
    except ValueError:
        v = ()
    if len(v) != 3 or not any(v):
        raise CommandError(f"PRINTCHECK: the build direction is +Z, -X ..., BEST, or three numbers like "
                           f"\"0 0 1\"; got {text!r}")
    return v


def _dir_text(up) -> str:
    u = prt.unit(up)
    for k, d in prt.DIRECTIONS.items():
        if np.allclose(u, d):
            return k
    return "(" + ", ".join(f"{x:.3g}" for x in u) + ")"


@command(
    "PRINTCHECK",
    Arg("b", BodyRef, help="a solid body"),
    Arg("up", Text, "+Z", "the build direction, up from the bed: +Z, -X ..., three numbers, or BEST (tries the "
                          "six directions and uses the one needing least support)"),
    Arg("angle", float, 45.0, "the steepest overhang the printer manages without support, degrees from vertical"),
    Arg("wall", float, 0.8, "the thinnest wall it prints (about two nozzle widths); 0 skips the wall check"),
    logged=False,
    help="Check a solid before 3D printing: PRINTCHECK, b (built along +Z, 45° overhangs, 0.8 walls) · "
         "PRINTCHECK, b, BEST · PRINTCHECK, b, -Y, 50, 1.2. Colours: blue on the bed, red needs support. "
         "ANALYZE, OFF ends them",
)
def printcheck(p: Processor, b, up, angle, wall):
    from ..geometry import analysis as an
    from ..geometry import meshbody as mb
    from ..geometry import probe as pr
    from ..geometry import robust
    from .analysis_handlers import Analysis

    if not 0 < angle < 90:
        raise CommandError("PRINTCHECK: the overhang angle is between 0 and 90 degrees")
    if wall < 0:
        raise CommandError("PRINTCHECK: the wall thickness cannot be negative")
    m = p.model
    body = m.body(b)
    if mb.is_mesh(body.shape) or not robust.solids(body.shape):
        raise CommandError(f"PRINTCHECK: body {b} is not a solid (a mesh body: make it a solid first, TOSOLID)")
    want = parse_up(up)
    try:
        mesh = an.mesh(body.shape, fine=0.5)
    except ValueError as exc:
        raise CommandError(f"PRINTCHECK: body {b}: {exc}") from None
    fids = an.face_ids(m, b, mesh)
    lines = []
    if want == "BEST":
        ranked = prt.best_direction(mesh, angle)
        lines.append("build directions, least support first: " + "; ".join(
            f"{k} {r.overhang_area:.4g} needs support, {r.base_area:.4g} on the bed" for k, r in ranked))
        want = prt.DIRECTIONS[ranked[0][0]]
    rep = prt.check(mesh, want, angle)
    faces = sorted({fids[i] for i in rep.overhang_faces if fids[i] is not None})
    head = (f"PRINTCHECK body {b}, built along {_dir_text(want)}: {rep.footprint[0]:.4g} × {rep.footprint[1]:.4g} "
            f"on the bed, {rep.height:.4g} high")
    lines.insert(0, head)
    problems = 0
    if rep.base_area <= 1e-6 * rep.area:
        lines.append("bed: it touches the bed only at points or edges: give it a flat face to stand on, or a brim")
        problems += 1
    else:
        lines.append(f"bed: {rep.base_area:.4g} of flat face on the bed")
    if rep.overhang_area > 1e-6 * rep.area:
        lines.append(f"overhangs: {rep.overhang_area:.4g} ({100 * rep.overhang_area / rep.area:.0f}% of the surface) "
                     f"hangs over more than {angle:g}° and needs support, lowest {rep.lowest_overhang:.4g} above "
                     f"the bed" + (f" (faces {an._ids_list(faces)})" if faces else ""))
        problems += 1
    else:
        lines.append(f"overhangs: none past {angle:g}°")
    if wall > 0:
        thin = [s for s in pr.wall_thickness(body.shape) if s.thickness < wall]
        if thin:
            ids = sorted({body.entity_ids["FACE"][body.maps["FACE"].FindIndex(s.face) - 1]
                          for s in thin if body.maps["FACE"].FindIndex(s.face)})
            lines.append(f"walls: thinnest {thin[0].thickness:.4g}, under {wall:g} on faces {an._ids_list(ids)}")
            problems += 1
        else:
            lines.append(f"walls: none thinner than {wall:g}")
    holes = prt.hollows(body.shape)
    if holes:
        lines.append(f"hollows: {len(holes)} closed inside ({', '.join(f'{v:.4g}' for v in holes)}): resin or powder "
                     f"stays trapped, and a filament printer fills them with support: add a drain hole")
        problems += 1
    else:
        lines.append("hollows: none closed inside")
    nsol = len(robust.solids(body.shape))
    if nsol > 1:
        lines.append(f"pieces: {nsol} separate solids, printed as separate parts")
    lines.append("ready to print" if not problems else
                 f"{problems} thing{'s' if problems > 1 else ''} to look at; colours: blue on the bed, red needs "
                 f"support (ANALYZE, OFF ends them)")
    p.analysis = Analysis(b, "PRINT", tuple(float(x) for x in prt.unit(want)), angle)
    hook = getattr(p.view, "show_analysis", None) if p.view else None
    if hook:
        hook(p.analysis)
    return "\n".join(lines)
