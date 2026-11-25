"""Commands that make everyday work quicker (PLAN M15, items 83-94).

SELINFO (item 86): the numbers of what is picked (commands/selinfo.py).
TOOLS (item 85): the modelling tools that fit what is picked, the same list
the right-click menu and the small toolbar beside a pick show.
"""

from __future__ import annotations

from .processor import Arg, Processor, Raw, command


@command(
    "TOOLS",
    Arg("fmt", str, "TEXT", help="TEXT or JSON"),
    logged=False,
    help="List the modelling tools that fit what is picked now, best first, and what each runs: "
         "a flat face offers Sketch on this face, Pull, Hole, Shell ...; edges Fillet, Chamfer, Loop, Tangent "
         "chain; two faces Distance, Mate, Joint; bodies Move, Mirror, Union ... The right-click menu and the "
         "small toolbar beside a pick show the same list. TOOLS, JSON gives it as data.",
)
def tools(p: Processor, fmt):
    import json

    from ..gui import body_menu as bm

    rows = bm.tools_rows(p)
    if fmt == "JSON":
        return json.dumps({"selection": {"kind": p.model.selection_kind, "ids": list(p.model.selection)},
                           "tools": rows})
    if not rows:
        return "nothing is picked: pick a face, an edge, a vertex or a body first"
    m = p.model
    n = len(m.selection)
    head = f"{n} {m.selection_kind.lower()}{'s' if n != 1 else ''} picked; tools that fit:"
    lines = [head]
    for i, r in enumerate(rows, 1):
        first = f"{' then '.join(r['first'])}, then " if r.get("first") else ""
        lines.append(f"  {i}. {r['label']}: {first}{r['runs']}")
    return "\n".join(lines)


@command(
    "SELINFO",
    Arg("kind", str, "", help="FACE, EDGE, VERTEX or BODY (default: what is picked), or JSON"),
    Arg("ids", Raw, "", help="IDs, several with spaces: \"3 5 7\" (default: the picked ones)"),
    Arg("fmt", str, "TEXT", help="TEXT or JSON"),
    logged=False,
    help="The numbers of what is picked: a face's type, area and radius; an edge's length, radius and arc "
         "angle; a vertex's position; a body's volume, area, size and mass (from its MATERIAL). Several picks "
         "add a total; two picks add the distance between them and the angle. SELINFO (the picked) · "
         "SELINFO, JSON · SELINFO, FACE, \"3 5\" · SELINFO, BODY, 2, JSON. The status bar shows the same line.",
)
def selinfo(p: Processor, kind, ids, fmt):
    import json

    from ..core.model import ModelError, check_kind
    from . import selinfo as si
    from .processor import CommandError

    kind = (kind or "").strip().upper()
    if kind == "JSON":
        kind, fmt = "", "JSON"
    raw = (ids or "").strip().strip('"')
    if raw.upper() == "JSON":
        raw, fmt = "", "JSON"
    fmt = (fmt or "TEXT").upper()
    if fmt not in ("TEXT", "JSON"):
        raise CommandError("SELINFO: the format is TEXT or JSON")
    got_ids = None
    if kind:
        try:
            kind = check_kind(kind)
        except ModelError as exc:
            raise CommandError(f"SELINFO: {exc}") from None
        if raw:
            try:
                if kind == "BODY":
                    from .processor import REGISTRY

                    got_ids = [p._body_ref(REGISTRY["SELINFO"], w) for w in raw.replace(",", " ").split()]
                else:
                    got_ids = [int(w) for w in raw.replace(",", " ").split()]
            except ValueError:
                raise CommandError(f"SELINFO: the IDs are whole numbers: {raw}") from None
            except CommandError as exc:
                raise CommandError(f"SELINFO: {exc}") from None
            for g in got_ids:
                try:
                    if kind == "BODY":
                        p.model.body(g)
                    else:
                        p.model.entity_owner(kind, g)
                except ModelError as exc:
                    raise CommandError(f"SELINFO: {exc}") from None
        elif kind != p.model.selection_kind:
            got_ids = []
    elif raw:
        raise CommandError("SELINFO: say the kind before the IDs: SELINFO, FACE, \"3 5\"")
    info = si.selection_info(p, kind or None, got_ids)
    p.give_report("SELINFO", info)
    if fmt == "JSON":
        return json.dumps(info)
    return si.report_text(info)
