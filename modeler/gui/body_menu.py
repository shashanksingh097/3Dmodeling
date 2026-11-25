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

import numpy as np


@dataclass
class MenuItem:
    label: str  # "" is a separator
    commands: list[str] = field(default_factory=list)  # run in order
    form: str = ""  # open this command's fill-in form instead, pre-filled with ``commands[0]``
    ask: str = ""  # ask for a text first; "{}" in the command takes it (rename)
    find_entry: int = 0  # select this history entry (by uid) instead of running anything
    edit_part: str = ""  # open this part's recipe in a part window (Edit part)
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


def part_item(part: str, sources: dict | None) -> MenuItem:
    """Edit part (defined in this project) or Open part (read from a part file)."""
    import os

    got = (sources or {}).get(part.upper())
    name = part.lower()
    if not got:
        return MenuItem(f"Edit part {name}…", edit_part=part)
    path, kind = got
    if kind == "linked":
        return MenuItem(f"Open part {name} ({os.path.basename(path)})…", edit_part=part)
    if kind == "copy":
        return MenuItem(f"Open part {name} (its file is missing)", edit_part=part, enabled=False)
    return MenuItem(f"Open part file {name} ({os.path.basename(path)}, loaded as a copy)…", edit_part=part)


def mate_ready(model) -> bool:
    """Two faces, edges or vertices picked on two different bodies: they can be mated."""
    if model.selection_kind not in ("FACE", "EDGE", "VERTEX") or len(model.selection) != 2:
        return False
    try:
        a, b = (model.entity_owner(model.selection_kind, g)[0] for g in model.selection)
    except Exception:  # noqa: BLE001 - a stale pick
        return False
    return a != b


def body_items(model, bid: int, sources: dict | None = None) -> list[MenuItem]:
    """The menu for a right click on body ``bid`` in the 3D view (or a tree row).
    ``sources`` is the processor's ``part_files``: which parts come from a file."""
    ids = menu_target(model, bid)
    one = len(ids) == 1
    t = target_text(ids)
    head = _name(model, bid) if one else f"{len(ids)} selected bodies"
    items = [MenuItem(head, enabled=False, title=True)]
    items += view_items(model, ids)
    items += everything_items(model)
    items.append(SEPARATOR)
    items.append(MenuItem("Zoom to", [f"FIT, {t}"]))
    if mate_ready(model):
        items.append(MenuItem("Mate the two picked…", form="MATE"))
    items += clash_items(model, ids, bid)
    if one:
        items.append(MenuItem("Rename…", [f"NAME, {bid}, {{}}"], ask=f"New name for {_name(model, bid)}:"))
    sel = "SEL" if not one else str(bid)
    items.append(MenuItem("Colour…", [f"COLOR, {sel}, "], form="COLOR"))
    items.append(MenuItem("Layer…", [f"LAYER, , ADD, {sel}"], form="LAYER"))
    items.append(MenuItem("Material…", [f"MATERIAL, {sel}, "], form="MATERIAL"))
    items.append(MenuItem("Wrap in one closed skin…", [f"WRAPSKIN, {sel}, 1"], form="WRAPSKIN"))
    items += analysis_items(model, ids, bid)
    if one:
        if bid in model.instances:
            part = model.instances[bid][0]
            items.append(part_item(part, sources))
            items.append(MenuItem(f"Explode (instance of {part})", [f"EXPLODE, {bid}"]))
        uid = model.origin("BODY", bid)
        items.append(MenuItem("Find the step that made it", find_entry=uid, enabled=uid > 0))
        items += feature_items(model, bid)
        items += point_items(model, bid)
    items += sheet_items(model)
    items.append(SEPARATOR)
    items.append(MenuItem("Delete" if one else f"Delete {len(ids)} bodies", [f"DELETE, {b}" for b in ids]))
    return items


def analysis_items(model, ids: list[int], clicked: int) -> list[MenuItem]:
    """Getting parts ready for the analysis app (PLAN items 80-82): only for solids."""
    from ..geometry import meshbody as mb
    from ..geometry import robust

    solid = [b for b in ids if b in model.bodies and not mb.is_mesh(model.bodies[b].shape)
             and robust.solids(model.bodies[b].shape)]
    if len(solid) != len(ids) or not ids:
        return []
    if len(ids) == 1:
        b = ids[0]
        return [MenuItem("Analysis: middle surface", [f"MIDSURFACE, {b}"]),
                MenuItem("Analysis: fluid volume inside", [f"FLUIDVOLUME, {b}"]),
                MenuItem("Analysis: air round it…", [f"ENCLOSURE, {b}, BOX, 10"], form="ENCLOSURE"),
                MenuItem("Analysis: merge faces on one surface", [f"MERGEFACES, {b}"])]
    t = " ".join(map(str, ids))
    out = [MenuItem("Analysis: share faces where they touch", [f'SHAREFACES, "{t}"']),
           MenuItem("Analysis: beam lines", [f'BEAMS, "{t}"'])]
    if len(ids) == 2:
        a = clicked if clicked in ids else ids[0]
        b = ids[1] if ids[0] == a else ids[0]
        out.append(MenuItem(f"Analysis: imprint {_name(model, b)} on {_name(model, a)}", [f"IMPRINT, {a}, {b}"]))
    return out


def clash_items(model, ids: list[int], clicked: int) -> list[MenuItem]:
    """Two bodies picked (PLAN item 79): fix a clash between them, seen first, then done. The body
    clicked is the one that changes."""
    if len(ids) != 2:
        return []
    a = clicked if clicked in ids else ids[0]
    b = ids[1] if ids[0] == a else ids[0]
    na, nb = _name(model, a), _name(model, b)
    return [MenuItem(f"Clash: see {nb} cut out of {na}", [f"CLASHFIX, {a}, {b}, CUT, 0, AUTO, PREVIEW"]),
            MenuItem(f"Clash: cut {nb} out of {na}", [f"CLASHFIX, {a}, {b}, CUT"]),
            MenuItem(f"Clash: see {na} moved clear of {nb}", [f"CLASHFIX, {a}, {b}, MOVE, 0, AUTO, PREVIEW"]),
            MenuItem(f"Clash: move {na} clear of {nb}", [f"CLASHFIX, {a}, {b}, MOVE"])]


def point_items(model, bid: int) -> list[MenuItem]:
    """Point clouds (PLAN item 77): fit a shape to the points around a picked point, or to all."""
    from ..geometry import pointcloud as pc

    if not pc.is_points(model.bodies[bid].shape):
        return []
    items = [SEPARATOR]
    if model.selection_kind == "VERTEX" and len(model.selection) == 1:
        try:
            owner = model.entity_owner("VERTEX", model.selection[0])[0]
            v = model.entity_shape("VERTEX", model.selection[0])
        except Exception:  # noqa: BLE001 - a stale pick
            owner = None
        if owner == bid:
            from OCP.BRep import BRep_Tool
            from OCP.TopoDS import TopoDS

            as_vertex = getattr(TopoDS, "Vertex_s", None) or TopoDS.Vertex
            q = (getattr(BRep_Tool, "Pnt_s", None) or BRep_Tool.Pnt)(as_vertex(v))
            pts = pc.arrays(model.bodies[bid].shape)
            r = 0.1 * float(np.linalg.norm(np.ptp(pts, axis=0)))
            at = ", ".join(f"{c:.6g}" for c in (q.X(), q.Y(), q.Z()))
            items.append(MenuItem("Fit a shape to the points around the pick…",
                                  [f"FITPOINTS, {bid}, AUTO, {at}, {r:.4g}"], form="FITPOINTS"))
    items.append(MenuItem("Fit a shape to all the points…", [f"FITPOINTS, {bid}, AUTO"], form="FITPOINTS"))
    items.append(MenuItem("Measure against a model…", [f"DEVIATION, {bid}, "], form="DEVIATION"))
    return items


def picked_feature(model, bid: int):
    """(face ID, the found feature it belongs to or None) when one face of body bid is picked."""
    if model.selection_kind != "FACE" or len(model.selection) != 1:
        return None
    gid = next(iter(model.selection))
    try:
        owner, idx = model.entity_owner("FACE", gid)
    except Exception:  # noqa: BLE001 - a stale pick
        return None
    if owner != bid:
        return None
    from ..geometry import found, robust

    shape = model.body(bid).shape
    if not robust.solids(shape):
        return gid, None
    try:
        feats = found.find(shape, ("HOLE", "FILLET", "CHAMFER"))
    except Exception:  # noqa: BLE001 - the menu must open whatever the shape
        feats = []
    return gid, next((f for f in feats if idx in f.faces), None)


def feature_items(model, bid: int) -> list[MenuItem]:
    """Features of a solid (PLAN item 70): list them, and for a picked face select the ones
    like it, change their size or remove them, all in one go."""
    from ..geometry import robust
    from ..lang.expr import fmt_num

    if not robust.solids(model.body(bid).shape):
        return []
    items = [SEPARATOR, MenuItem("List its holes, rounds and chamfers", [f"FEATURES, {bid}"])]
    got = picked_feature(model, bid)
    if got is None:
        return items
    gid, feat = got
    items.append(MenuItem("Select similar", [f"SEL, S, FACE, LIKE, {gid}"]))
    items.append(MenuItem("Select similar in every body", [f"SEL, S, FACE, LIKE, {gid}, ALL"]))
    if feat is not None:
        word = {"HOLE": "holes", "FILLET": "rounds", "CHAMFER": "chamfers"}[feat.kind]
        size = fmt_num(round(feat.size, 6))
        items.append(MenuItem(f"Change the size of every {size} {word[:-1]}…",
                              [f"RESIZE, {bid}, {feat.kind}, EQ, {size}, {size}"], form="RESIZE"))
        items.append(MenuItem(f"Remove every {size} {word[:-1]}", [f"DEFEATURE, {bid}, {feat.kind}, EQ, {size}"]))
    return items


def empty_items(model) -> list[MenuItem]:
    """The menu for a right click on empty space in the 3D view."""
    return everything_items(model) + [SEPARATOR, MenuItem("Fit all", ["FIT"])] + sheet_items(model)


TABLE_LABELS = (("PARTS", "parts list and balloons"), ("HOLES", "hole table"), ("REVISIONS", "revision table"))


def sheet_items(model) -> list[MenuItem]:
    """Drawing sheets (PLAN item 72): add or take off a sheet's tables, or start a sheet."""
    sheets = list(getattr(model, "drawsheets", {}).values())
    if not sheets and not model.bodies:
        return []
    items = [SEPARATOR]
    if not sheets:
        items.append(MenuItem("New drawing sheet with tables…",
                              ["DRAWSHEET, sheet1, STANDARD, 0, ALL, AUTO, , , , , ALL"], form="DRAWSHEET"))
        return items
    for s in sheets[:4]:
        have = [w for w in (s.get("tables") or "").split("+") if w]
        name = s["name"]
        for word, label in TABLE_LABELS:
            if word in have:
                left = [w for w in have if w != word and not (word == "PARTS" and w == "BALLOONS")]
                items.append(MenuItem(f"Sheet {name}: take off the {label}",
                                      [f"SHEETTABLE, {name}, {'+'.join(left) or 'NONE'}"]))
            else:
                items.append(MenuItem(f"Sheet {name}: add a {label}",
                                      [f"SHEETTABLE, {name}, {'+'.join(have + [word])}"]))
    return items


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
