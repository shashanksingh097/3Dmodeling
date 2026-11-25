"""WRAPSKIN (PLAN item 78, geometry/shrinkwrap.py): one clean closed skin around bodies."""

from __future__ import annotations

import re

from ..geometry import meshbody as mb
from ..geometry import shrinkwrap as sw
from .processor import REGISTRY, Arg, CommandError, Processor, Raw, command


def wrap_targets(p: Processor, what: str, cmd: str) -> list[int]:
    words = [w for w in re.split(r"[\s;]+", str(what).strip().strip('"')) if w]
    m = p.model
    if not words or [w.upper() for w in words] == ["ALL"]:
        ids = [b for b in sorted(m.bodies) if m.is_shown(b)]
    elif [w.upper() for w in words] == ["SEL"]:
        if m.selection_kind != "BODY" or not m.selection:
            raise CommandError(f"{cmd}: SEL needs bodies selected first")
        ids = sorted(set(m.selection))
    else:
        ids = [p._body_ref(REGISTRY[cmd], w) for w in words]
    if not ids:
        raise CommandError(f"{cmd}: there are no bodies to wrap")
    return ids


@command(
    "WRAPSKIN",
    Arg("what", Raw, "ALL", "a body, several (\"3 7\" or names), SEL, or ALL (every shown body)"),
    Arg("gap", float, 1.0, "holes, slits and gaps narrower than about twice this are closed over; loose bits "
                           "this close are joined"),
    Arg("cell", float, 0.0, "the grid step: smaller is finer and slower (0: half the gap, or what fits)"),
    help="Shrinkwrap: one clean, closed skin around a messy mesh or a whole assembly: WRAPSKIN, ALL, 2 wraps "
         "every shown body with holes, overlaps, inner voids and gaps under about 4 closed over, for printing, "
         "a quick outside shape or a simplified look (a new mesh body; the bodies stay)",
)
def wrapskin(p: Processor, what, gap, cell):
    from .handlers import _added

    if gap <= 0:
        raise CommandError("WRAPSKIN: the gap must be positive")
    if cell < 0:
        raise CommandError("WRAPSKIN: the cell cannot be negative")
    ids = wrap_targets(p, what, "WRAPSKIN")
    try:
        skin = sw.wrap([p.model.body(b).shape for b in ids], gap, cell)
    except sw.WrapError as exc:
        raise CommandError(f"WRAPSKIN: {exc}") from None
    body = p.model.add_body(mb.make_shape(skin.points, skin.tris))
    info = mb.info(body.shape)
    pieces = mb.pieces(skin.points, skin.tris)
    d = {"bodies": ids, "gap": gap, "cell": skin.cell, "triangles": info.triangles, "closed": info.closed,
         "volume": round(info.volume, 6), "pieces": pieces, "new_body": body.id}
    p.give_report("WRAPSKIN", d)
    what_txt = f"body {ids[0]}" if len(ids) == 1 else f"{len(ids)} bodies"
    notes = [f"{pieces} separate pieces (further apart than the gap)" if pieces > 1 else "one piece"]
    return _added(p, body, f"WRAPSKIN {what_txt} (gap {gap:g}, cell {skin.cell:.3g}; {', '.join(notes)}; "
                           f"volume {info.volume:.6g})")
