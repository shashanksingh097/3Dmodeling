"""What the right-click menu on bodies offers, without Qt.

The same menu opens on a body in the 3D view, on History rows (for the
bodies a step made) and later on the model tree. Like every other GUI
action it only writes command text: :func:`body_items` says which items to
show and what each one sends, and the window turns them into a QMenu. Kept
free of Qt so it is tested headless.

Showing, hiding and fading are view steps (``DISPLAY``, ``FADE``,
``UNFADE``): they do not add history entries.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MenuItem:
    label: str  # "" is a separator
    commands: list[str] = field(default_factory=list)  # run in order
    form: str = ""  # open this command's fill-in form instead, pre-filled with ``commands[0]``
    ask: str = ""  # ask for a text first; "{}" in the command takes it (rename)
    find_entry: int = 0  # select this history entry (by uid) instead of running anything
    enabled: bool = True
    title: bool = False  # a heading, not an action


SEPARATOR = MenuItem("")


def selected_bodies(model) -> list[int]:
    """The bodies the selection covers (bodies, or the owners of picked faces/edges/vertices)."""
    if model.selection_kind == "BODY":
        return [b for b in model.selection if b in model.bodies]
    out: list[int] = []
    for gid in model.selection:
        try:
            bid = model.entity_owner(model.selection_kind, gid)[0]
        except Exception:  # noqa: BLE001 - a stale pick has no owner
            continue
        if bid not in out:
            out.append(bid)
    return out


def _name(model, bid: int) -> str:
    b = model.bodies[bid]
    text = f"{b.name} (body {bid})" if b.name and b.name != f"body{bid}" else f"body {bid}"
    if bid in model.instances:
        text += f", a {model.instances[bid][0].lower()}"
    return text


def menu_target(model, bid: int) -> list[int]:
    """The bodies a right click on ``bid`` acts on: the whole selection when
    the click is on a selected body, else just that body."""
    sel = selected_bodies(model)
    return sel if bid in sel and len(sel) > 1 else [bid]


def target_text(ids: list[int]) -> str:
    return " ".join(str(b) for b in ids)


def view_items(model, ids: list[int], what: str = "") -> list[MenuItem]:
    """Show, hide and fade for these bodies (view steps)."""
    t = target_text(ids)
    one = len(ids) == 1
    this = what or ("this" if one else f"these {len(ids)}")
    items: list[MenuItem] = []
    if any(model.is_shown(b) for b in ids):
        items.append(MenuItem(f"Hide {this}", [f"DISPLAY, HIDE, {t}"]))
    if any(not model.is_shown(b) for b in ids):
        items.append(MenuItem(f"Show {this}", [f"DISPLAY, SHOW, {t}"]))
    others = [b for b in model.bodies if b not in ids]
    items.append(MenuItem(f"Show only {this}", [f"DISPLAY, ONLY, {t}"], enabled=bool(others) or not all(model.is_shown(b) for b in ids)))
    if all(b in model.faded for b in ids):
        items.append(MenuItem(f"Make {this} solid", [f"UNFADE, {t}"]))
    else:
        items.append(MenuItem(f"Fade {this}", [f"FADE, {t}"]))
    items.append(MenuItem("Fade all others", [f"FADE, OTHERS, , {t}"], enabled=bool(others)))
    return items


def everything_items(model) -> list[MenuItem]:
    items = [MenuItem("Show everything", ["DISPLAY, ALL"], enabled=bool(model.bodies))]
    if any(b in model.bodies for b in model.faded):
        items.append(MenuItem("Make all solid", ["UNFADE, ALL"]))
    if model.has_view_changes():
        items.append(MenuItem("Back to the model's own view", ["DISPLAY, MODEL"]))
    return items


def body_items(model, bid: int) -> list[MenuItem]:
    """The menu for a right click on body ``bid`` in the 3D view (or a tree row)."""
    ids = menu_target(model, bid)
    one = len(ids) == 1
    t = target_text(ids)
    head = _name(model, bid) if one else f"{len(ids)} selected bodies"
    items = [MenuItem(head, enabled=False, title=True)]
    items += view_items(model, ids)
    items += everything_items(model)
    items.append(SEPARATOR)
    items.append(MenuItem("Zoom to", [f"FIT, {t}"]))
    if one:
        items.append(MenuItem("Rename…", [f"NAME, {bid}, {{}}"], ask=f"New name for {_name(model, bid)}:"))
    sel = "SEL" if not one else str(bid)
    items.append(MenuItem("Colour…", [f"COLOR, {sel}, "], form="COLOR"))
    items.append(MenuItem("Layer…", [f"LAYER, , ADD, {sel}"], form="LAYER"))
    items.append(MenuItem("Material…", [f"MATERIAL, {sel}, "], form="MATERIAL"))
    if one:
        if bid in model.instances:
            part = model.instances[bid][0]
            items.append(MenuItem(f"Explode (instance of {part})", [f"EXPLODE, {bid}"]))
        uid = model.origin("BODY", bid)
        items.append(MenuItem("Find the step that made it", find_entry=uid, enabled=uid > 0))
    items.append(SEPARATOR)
    items.append(MenuItem("Delete" if one else f"Delete {len(ids)} bodies", [f"DELETE, {b}" for b in ids]))
    return items


def empty_items(model) -> list[MenuItem]:
    """The menu for a right click on empty space in the 3D view."""
    return everything_items(model) + [SEPARATOR, MenuItem("Fit all", ["FIT"])]


def entry_bodies(processor, row: int) -> list[int]:
    """Bodies that exist now and were made by history entry ``row`` (0-based)."""
    m = processor.model
    if not 0 <= row < len(processor.history):
        return []
    uid = processor.history[row].uid
    return [b for b in sorted(m.bodies) if m.origin("BODY", b) == uid]


def entry_items(processor, row: int) -> list[MenuItem]:
    """View actions for the bodies a History row made (a submenu there)."""
    ids = entry_bodies(processor, row)
    if not ids:
        return []
    return view_items(processor.model, ids) + [MenuItem("Zoom to", [f"FIT, {target_text(ids)}"])]
