"""Commands that make everyday work quicker (PLAN M15, items 83-94).

TOOLS (item 85): the modelling tools that fit what is picked, the same list
the right-click menu and the small toolbar beside a pick show.
"""

from __future__ import annotations

from .processor import Arg, Processor, command


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
