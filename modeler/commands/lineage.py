"""Which history steps made a body: its lineage.

While an entry runs, the model records what it did to bodies (core/model.py
``Lineage``): the bodies it made, used up, restyled and read. A body's steps
are the entries that made or changed it, then, walking back, the steps of
every body those entries read. A body placed from a part also lists the
``*PART`` definition it came from.

The model tree uses this to say what made an item, and ``STEPS, b`` prints
it. The same record can later tell a rebuild which steps it can skip.
"""

from __future__ import annotations

import re

from .layer_handlers import target_bodies
from .processor import Arg, Processor, Raw, command

_PART = re.compile(r"^\s*\*PART\s*,\s*([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)


def part_entry(p: Processor, name: str, before: int) -> int | None:
    """The row (0-based) of the last ``*PART, name`` before row ``before``."""
    for j in range(min(before, p.cursor) - 1, -1, -1):
        e = p.history[j]
        m = _PART.match(e.text)
        if m and m.group(1).upper() == name.upper() and e.ok and not e.suppressed:
            return j
    return None


def body_steps(p: Processor, bid: int) -> list[int]:
    """Rows (0-based, in order) of the applied steps that made or changed body ``bid``."""
    rows: set[int] = set()
    seen: set[tuple[int, int]] = set()
    todo = [(bid, p.cursor)]
    while todo:
        b, before = todo.pop()
        if (b, before) in seen:
            continue
        seen.add((b, before))
        for j in range(min(before, p.cursor) - 1, -1, -1):
            e = p.history[j]
            lin = e.lineage
            if lin is None or e.suppressed or not e.ok:
                continue
            if b not in lin.made and b not in lin.changed:
                continue
            rows.add(j)
            if b in lin.made:
                for r in lin.inputs.get(b, lin.reads | lin.used) - {b}:
                    # (j + 1: an input may have been made earlier in the same entry, in a loop)
                    todo.append((r, j + 1))
                if b not in lin.used:  # a new body: nothing earlier made this one
                    break
    m = p.model
    if bid in m.instances:
        first = min(rows) if rows else p.cursor
        k = part_entry(p, m.instances[bid][0], first)
        if k is not None:
            rows.add(k)
    return sorted(rows)


def made_by(p: Processor, row: int) -> list[int]:
    """Bodies that exist now and that history row ``row`` made or changed."""
    if not 0 <= row < len(p.history) or p.history[row].lineage is None:
        return []
    lin = p.history[row].lineage
    return [b for b in sorted(p.model.bodies) if b in lin.made or b in lin.changed]


@command(
    "STEPS",
    Arg("b", Raw, "SEL", "a body, SEL or LAST"),
    logged=False,
    help="List the history steps that made a body, in order, including the steps of the bodies it was made "
         "from and, for a part instance, the *PART it came from: STEPS, bolt · STEPS, SEL.",
)
def steps(p: Processor, b):
    out = []
    for bid in target_bodies(p, "STEPS", b):
        rows = body_steps(p, bid)
        out.append(f"body {bid} {p.model.bodies[bid].name}: {len(rows)} step{'s' if len(rows) != 1 else ''}")
        out += [f"  {j + 1}: {p.history[j].label}" for j in rows]
    return "\n".join(out)
