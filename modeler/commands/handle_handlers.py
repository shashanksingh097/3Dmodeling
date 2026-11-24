"""HANDLES: the drag handles for what is picked, as text and data (PLAN item 68).

The 3D view's drag handles (gui/drag_handles.py) write ordinary MOVE, ROTATE,
PUSHPULL and MOVEFACE steps. HANDLES says which handles a pick would show and
the step each one writes, so a script or the assistant can do the same thing a
drag does without guessing.
"""

from __future__ import annotations

from ..lang.expr import fmt_num
from .processor import Arg, CommandError, Processor, command


@command(
    "HANDLES",
    Arg("step", float, 1.0, "the grid a drag snaps to (lengths)"),
    Arg("angle", float, 5.0, "the steps a ring snaps to (degrees)"),
    logged=False,
    help="List the drag handles the 3D view shows for what is picked, and the step a drag of each writes: a "
         "body has arrows (MOVE along X, Y, Z) and rings (ROTATE about X, Y, Z through its middle); picked faces "
         "of a solid have a pull arrow (PUSHPULL along their normal) and small arrows (MOVEFACE). Pick first: "
         "PICK, BODY, 3 then HANDLES.",
)
def handles(p: Processor, step, angle):
    from ..gui import drag_handles as dh

    if step <= 0 or angle <= 0:
        raise CommandError("HANDLES: the snap steps must be more than 0")
    hs = dh.Handles.for_model(p.model, step, angle)
    data = dh.describe(hs)
    p.give_report("HANDLES", data)
    if not hs.mode:
        return "no handles: pick one body, or faces of one solid (PICK, BODY, 1 or PICK, FACE, 6)"
    what = f"body {hs.body}" if hs.mode == "BODY" else f"face{'s' if len(hs.faces) > 1 else ''} " \
           f"{', '.join(map(str, hs.faces))} of body {hs.body}"
    lines = [f"handles on {what} at ({', '.join(fmt_num(round(c, 4)) for c in hs.centre)}); "
             f"drags snap to {fmt_num(step)} and {fmt_num(angle)} deg (Shift drags freely)"]
    if hs.jointed:
        lines.append("  the body is held by joints: after a drag the joint solver moves the rest of the linkage")
    names = {"MOVE": "arrow", "TURN": "ring", "PULL": "pull arrow", "SLIDE": "small arrow"}
    for r in data["handles"]:
        lines.append(f"  {r['handle']} {names[r['kind']]}: a drag of 1 writes {r['writes']}")
    return "\n".join(lines)
