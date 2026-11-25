"""REPEAT: run the last step again on a new pick (PLAN item 90).

The processor remembers the last typed or clicked step that changed the model
(``Processor.last_tool``; picking, undo and history edits do not count). REPEAT
runs it again as a new step, so a FILLET, HOLE or PUSHPULL can be used on pick
after pick. ``REPEAT, EDGE, 5 9`` picks first (as PICK does), and a SEL line
before REPEAT picks by a rule: ``SEL, S, EDGE, RADIUS, EQ, 4`` then ``REPEAT``.
In the window, Enter on an empty command line is REPEAT.
"""

from __future__ import annotations

from .processor import Arg, CommandError, Processor, Raw, command


def repeat_line(p: Processor) -> str:
    return p.last_tool


@command(
    "REPEAT",
    Arg("kind", Raw, "", help="pick first: FACE, EDGE, VERTEX or BODY (or SHOW: say what REPEAT would run)"),
    Arg("ids", Raw, "", help="the IDs to pick, e.g. 5 9 12"),
    logged=False,
    help="Run the last step that changed the model again, on the current pick: FILLET on these edges, then "
         "PICK the next ones and REPEAT. REPEAT, EDGE, 5 9 picks edges 5 and 9 first. SEL, S, EDGE, RADIUS, "
         "EQ, 4 then REPEAT does the same to every edge the rule finds. REPEAT, SHOW says what it would run. "
         "In the window, Enter on an empty command line (or right click > Repeat) is REPEAT.",
)
def repeat(p: Processor, kind, ids):
    line = repeat_line(p)
    kind = (kind or "").strip().upper()
    if kind == "SHOW":
        return f"REPEAT runs: {line}" if line else "nothing to repeat yet"
    if not line:
        raise CommandError("REPEAT: nothing to repeat yet: run a step that changes the model first "
                           "(FILLET, HOLE, PUSHPULL ...)")
    if kind:
        if not (ids or "").strip():
            raise CommandError("REPEAT: give the IDs to pick, e.g. REPEAT, EDGE, 5 9")
        r = p.run_unit(f"PICK, {kind}, {ids.strip()}")
        if not r.ok:
            raise CommandError(f"REPEAT: {r.message}")
    r = p.run_unit(line)
    if not r.ok:
        p.last_failure = {"line": line, "message": r.message}
        raise CommandError(f"REPEAT ({line}): {r.message}")
    out = f"repeated {line}" + (f": {r.message}" if r.message else "")
    return out + (f"\nCHECK: {r.warning}" if r.warning else "")
