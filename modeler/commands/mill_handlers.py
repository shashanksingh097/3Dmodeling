"""MILL: 2.5D milling paths from flat faces (geometry/milling.py), written as G-code and shown in the view."""

from __future__ import annotations

import os

from ..geometry import milling as ml
from .processor import REGISTRY, Arg, CommandError, Path, Processor, Raw, Text, command
from .stress_handlers import _faces


@command(
    "MILL",
    Arg("b", Raw, help="a solid body; OFF hides the path"),
    Arg("op", str, "", help="FACE (flatten a face), POCKET (clear down to a floor), OUTLINE (cut around a face's "
                        "outline, down to the bottom)"),
    Arg("faces", Text, "", help="flat faces facing up (+Z; OUTLINE: or down): numbers (\"5 9\"), a set saved with CM, or SEL"),
    Arg("tool", float, 6.0, "the end mill's diameter, mm"),
    Arg("down", float, 0.0, "the depth of each cut, mm (0: half the tool's diameter)"),
    Arg("over", float, 0.0, "POCKET, FACE: the sideways step between passes, mm (0: 40% of the tool's diameter)"),
    Arg("file", Path, "", "the G-code file to write (.nc); none: just show the path"),
    Arg("feed", float, 600.0, "the cutting feed, mm/min (plunges at a third of it)"),
    Arg("speed", float, 10000.0, "the spindle speed, rpm"),
    logged=False,
    help="2.5D milling paths along Z, shown in the view and written as G-code: MILL, b, POCKET, \"9\", 6, 2 "
         "(clear down to floor face 9 with a 6 mm mill, 2 mm a cut) · MILL, b, OUTLINE, \"12\", 6, 3, , part.nc "
         "· MILL, b, FACE, \"5\", 20. MILL, OFF hides the path. Coordinates are the part's: set the machine "
         "zero where the part's is",
)
def mill(p: Processor, b, op, faces, tool, down, over, file, feed, speed):
    from ..geometry import robust

    hook = getattr(p.view, "show_toolpath", None) if p.view else None
    if b.strip().upper() in ("OFF", ""):
        p.toolpath = None
        if hook:
            hook(None)
        return "milling path hidden"
    b = p._body_arg(REGISTRY["MILL"], b.strip())
    if op not in ml.OPS:
        raise CommandError(f"MILL: the operation is one of {', '.join(ml.OPS)}")
    if tool <= 0 or down < 0 or over < 0 or feed <= 0 or speed < 0:
        raise CommandError("MILL: the tool size and feed must be positive, the steps not negative")
    down = down or tool / 2
    over = over or 0.4 * tool
    if over > tool:
        raise CommandError(f"MILL: a stepover of {over:g} is wider than the tool ({tool:g}): it leaves ridges")
    body = p.model.body(b)
    if not robust.solids(body.shape):
        raise CommandError(f"MILL: body {b} is not a solid")
    lo, hi = _bounds(body.shape)
    top, bottom = hi[2], lo[2]
    path = ml.Path()
    for gid, f in _faces(p, faces, b, "MILL", "milled"):
        try:
            if op == "POCKET":
                got = ml.pocket(f, top, tool, down, over)
            elif op == "OUTLINE":
                got = ml.outline(f, top, bottom, tool, down)
            else:
                got = ml.facing(f, top, tool, down, over)
        except ml.MillError as exc:
            raise CommandError(f"MILL: face {gid}: {exc}") from None
        path.runs += got.runs
        path.notes += [f"face {gid}: {n}" for n in got.notes]
        path.safe = max(path.safe, got.safe)
    p.toolpath = ml.shape(path)
    if hook:
        hook(p.toolpath)
    lo_p, hi_p = path.bounds()
    mins = ml.minutes(path, feed)
    lines = [f"MILL {op.lower()} on body {b}: {len(path.runs)} passes with a {tool:g} mm mill, {down:g} a cut"
             + (f", {over:g} apart" if op != "OUTLINE" else "")
             + f"; {path.cut_length():.0f} mm of cutting, about {mins:.1f} min at {feed:g} mm/min",
             f"the tool goes from z {lo_p[2]:.4g} up to {path.safe:.4g} (safe height), x {lo_p[0]:.4g} to "
             f"{hi_p[0]:.4g}, y {lo_p[1]:.4g} to {hi_p[1]:.4g}"]
    lines += path.notes
    if file:
        out = file if os.path.splitext(file)[1] else file + ".nc"
        try:
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(ml.gcode(path, feed, speed, f"{op.lower()} of {body.name or 'body ' + str(b)}"))
        except OSError as exc:
            raise CommandError(f"MILL: cannot write {out} ({exc})") from None
        lines.append(f"G-code written to {out}")
    lines.append("the path shows in the view (MILL, OFF hides it). Check it in your machine's simulator before "
                 "cutting")
    return "\n".join(lines)


def _bounds(shape):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    bb = Bnd_Box()
    (getattr(BRepBndLib, "AddOptimal_s", None) or BRepBndLib.AddOptimal)(shape, bb, False, False)
    a, c = bb.CornerMin(), bb.CornerMax()
    return (a.X(), a.Y(), a.Z()), (c.X(), c.Y(), c.Z())
