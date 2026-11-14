"""What the model tree shows, without Qt.

:func:`tree_nodes` turns the processor's state into a list of groups:
parts with their placed instances, loose bodies, sketches, datums and
named sets. The Qt widget (gui/model_tree.py) only draws these nodes and
sends commands; this module is tested headless.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..commands.lineage import body_steps


@dataclass
class Node:
    key: str  # stable across refreshes: "body:3", "part:BOLT", "group:bodies" ...
    label: str
    kind: str  # "group", "part", "body", "sketch", "datum", "set"
    ids: list[int] = field(default_factory=list)  # the bodies this row stands for
    children: list["Node"] = field(default_factory=list)
    shown: bool | None = None  # None: not a body row (no eye)
    state: str = ""  # "faded", "hidden", "layer off" ... shown in the second column
    color: tuple | None = None
    badge: str = ""  # "warning" when a step that made it needs a look
    tip: str = ""


def _body_node(p, bid: int, steps_cache: dict[int, list[int]]) -> Node:
    m = p.model
    b = m.bodies[bid]
    default = not b.name or b.name.lower() == f"body{bid}"
    if default:
        label = f"{m.instances[bid][0].lower()}  ({bid})" if bid in m.instances else f"body {bid}"
    else:
        label = f"{b.name}  ({bid})"
    state = []
    if not m.is_shown(bid):
        lay = m.layer_of(bid)
        state.append("layer off" if not lay.visible and bid not in m.view_hidden and bid not in m.hidden
                     else "hidden")
    if bid in m.faded:
        state.append("faded")
    rows = steps_cache.setdefault(bid, body_steps(p, bid))
    warn = [j for j in rows if p.history[j].warning]
    tip = [label]
    if bid in m.instances:
        part, values = m.instances[bid]
        vals = ", ".join(f"{k}={v:g}" if isinstance(v, (int, float)) else f"{k}={v}" for k, v in values)
        tip.append(f"instance of {part.lower()}" + (f" ({vals})" if vals else ""))
    if b.layer and b.layer.upper() != "DEFAULT":
        tip.append(f"layer {b.layer}")
    if b.material:
        tip.append(b.material.lower())
    if rows:
        tip.append("made by:")
        tip += [f"  {j + 1}: {p.history[j].label}" for j in rows[-8:]]
        if len(rows) > 8:
            tip.insert(-8, f"  ... {len(rows) - 8} earlier steps")
    if warn:
        tip.append("needs a look: " + p.history[warn[-1]].warning.splitlines()[0])
    return Node(f"body:{bid}", label, "body", [bid], shown=m.is_shown(bid), state=", ".join(state),
                color=m.display_color(bid), badge="warning" if warn else "", tip="\n".join(tip))


def _group(key: str, label: str, kind: str, children: list[Node]) -> Node:
    ids = [i for c in children for i in c.ids]
    shown = None
    if ids:
        shown = all(c.shown for c in children if c.shown is not None)
    return Node(key, f"{label} ({len(children)})", kind, ids, children, shown=shown if ids else None)


def tree_nodes(p) -> list[Node]:
    """The top-level groups of the model tree, empty ones left out."""
    m = p.model
    cache: dict[int, list[int]] = {}
    by_part: dict[str, list[int]] = {}
    loose: list[int] = []
    for bid in sorted(m.bodies):
        if bid in m.instances:
            by_part.setdefault(m.instances[bid][0].upper(), []).append(bid)
        else:
            loose.append(bid)
    out: list[Node] = []
    if by_part:
        parts = []
        for name in sorted(by_part):
            kids = [_body_node(p, b, cache) for b in by_part[name]]
            node = _group(f"part:{name}", name.lower(), "part", kids)
            node.tip = f"part {name.lower()}: {len(kids)} placed"
            parts.append(node)
        out.append(Node("group:parts", f"Parts ({len(parts)})", "group",
                        [i for n in parts for i in n.ids], parts,
                        shown=all(n.shown for n in parts)))
    if loose:
        out.append(_group("group:bodies", "Bodies", "group", [_body_node(p, b, cache) for b in loose]))
    if m.sketches:
        kids = [Node(f"sketch:{n}", n.lower(), "sketch",
                     tip=f"sketch {n.lower()}" + (" (open)" if m.active_sketch == n else ""))
                for n in sorted(m.sketches)]
        out.append(Node("group:sketches", f"Sketches ({len(kids)})", "group", children=kids))
    if m.datums:
        kids = [Node(f"datum:{n}", n.lower(), "datum", tip=f"{d.kind.lower()} {n.lower()}")
                for n, d in sorted(m.datums.items())]
        out.append(Node("group:datums", f"Datums ({len(kids)})", "group", children=kids))
    if m.named_sets:
        kids = [Node(f"set:{n}", f"{n.lower()}  ({kind.lower()}, {len(ids)})", "set",
                     tip=f"named set {n.lower()}: {len(ids)} {kind.lower()}{'s' if len(ids) != 1 else ''}")
                for n, (kind, ids) in sorted(m.named_sets.items())]
        out.append(Node("group:sets", f"Named sets ({len(kids)})", "group", children=kids))
    return out


def walk(nodes: list[Node]):
    for n in nodes:
        yield n
        yield from walk(n.children)


def find(nodes: list[Node], key: str) -> Node | None:
    return next((n for n in walk(nodes) if n.key == key), None)


def eye_command(node: Node, show: bool) -> str:
    """What ticking or unticking a row's eye sends (a view step)."""
    return f"DISPLAY, {'SHOW' if show else 'HIDE'}, {' '.join(map(str, node.ids))}"


def pick_command(model, bid: int, add: bool) -> str:
    """What clicking a body row sends: pick it, or with Ctrl add/remove it."""
    if not add:
        return f"PICK, BODY, {bid}"
    selected = model.selection_kind == "BODY" and bid in model.selection
    return f"PICK, BODY, {bid}, {'U' if selected else 'A'}"
