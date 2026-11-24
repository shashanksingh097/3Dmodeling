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
    edit_part: str = ""  # open this part's recipe in a part window (Edit part)
    enabled: bool = True
    title: bool = False  # a heading, not an action
    first: list[str] = field(default_factory=list)  # run these, then open ``form`` (Fillet its edges: SEL, then FILLET)
    icon: str = ""  # for the small toolbar beside a pick (gui/icons.py)
    short: str = ""  # its name on that toolbar (a word or two)


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


def _tools_for_menu(model, bid: int, processor) -> list[MenuItem]:
    """The pick's tools, when the right click is on the picked thing (or its body)."""
    if processor is None or not model.selection:
        return []
    if bid not in selected_bodies(model):
        return []
    try:
        return pick_tools(processor)
    except Exception:  # noqa: BLE001 - the menu must open whatever the pick
        return []


def body_items(model, bid: int, sources: dict | None = None, processor=None) -> list[MenuItem]:
    """The menu for a right click on body ``bid`` in the 3D view (or a tree row).
    ``sources`` is the processor's ``part_files``: which parts come from a file."""
    ids = menu_target(model, bid)
    one = len(ids) == 1
    t = target_text(ids)
    head = _name(model, bid) if one else f"{len(ids)} selected bodies"
    items = []
    tools = _tools_for_menu(model, bid, processor)
    if tools:
        what = {"FACE": "face", "EDGE": "edge", "VERTEX": "vertex", "BODY": "body"}[model.selection_kind]
        n = len(model.selection)
        items.append(MenuItem(f"The picked {what}" if n == 1 else f"The {n} picked {what}s"
                              if what != "body" else f"The {n} picked bodies", enabled=False, title=True))
        items += tools
        items.append(SEPARATOR)
    items.append(MenuItem(head, enabled=False, title=True))
    items += view_items(model, ids)
    items += everything_items(model)
    items.append(SEPARATOR)
    items.append(MenuItem("Zoom to", [f"FIT, {t}"]))
    if mate_ready(model):
        items.append(MenuItem("Mate the two picked…", form="MATE"))
    if one:
        items.append(MenuItem("Rename…", [f"NAME, {bid}, {{}}"], ask=f"New name for {_name(model, bid)}:"))
    sel = "SEL" if not one else str(bid)
    items.append(MenuItem("Colour…", [f"COLOR, {sel}, "], form="COLOR"))
    items.append(MenuItem("Layer…", [f"LAYER, , ADD, {sel}"], form="LAYER"))
    items.append(MenuItem("Material…", [f"MATERIAL, {sel}, "], form="MATERIAL"))
    if one:
        if bid in model.instances:
            part = model.instances[bid][0]
            items.append(part_item(part, sources))
            items.append(MenuItem(f"Explode (instance of {part})", [f"EXPLODE, {bid}"]))
        uid = model.origin("BODY", bid)
        items.append(MenuItem("Find the step that made it", find_entry=uid, enabled=uid > 0))
        items += feature_items(model, bid)
    items.append(SEPARATOR)
    items.append(MenuItem("Delete" if one else f"Delete {len(ids)} bodies", [f"DELETE, {b}" for b in ids]))
    return items


# ---- the tools that fit what is picked (PLAN item 85) ----------------------------------------
PICK_TOOLS_SETTING = "view/pickTools"  # the small toolbar beside a fresh pick (on unless turned off)
BAR_SIZE = 6  # how many tools the small toolbar shows (the rest are on the right-click menu)


def _surface_type(shape) -> str:
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_SurfaceType as T
    from OCP.TopoDS import TopoDS

    cast = getattr(TopoDS, "Face_s", None) or TopoDS.Face
    t = BRepAdaptor_Surface(cast(shape)).GetType()
    return {T.GeomAbs_Plane: "PLANE", T.GeomAbs_Cylinder: "CYLINDER", T.GeomAbs_Cone: "CONE",
            T.GeomAbs_Sphere: "SPHERE", T.GeomAbs_Torus: "TORUS"}.get(t, "FREEFORM")


def _curve_type(shape) -> str:
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_CurveType as T
    from OCP.TopoDS import TopoDS

    cast = getattr(TopoDS, "Edge_s", None) or TopoDS.Edge
    t = BRepAdaptor_Curve(cast(shape)).GetType()
    return {T.GeomAbs_Line: "LINE", T.GeomAbs_Circle: "CIRCLE"}.get(t, "CURVE")


def _next_name(p, command: str) -> str:
    from . import forms as F

    try:
        return F.initial(p, F.spec(command)).get("name", "") or ""
    except Exception:  # noqa: BLE001 - no form: let the command pick
        return ""


def pick_tools(p) -> list[MenuItem]:
    """The modelling tools that fit the current pick, best first. The right-click
    menu shows them all under a heading; the small toolbar beside a fresh pick
    shows the first few. Every item only writes command text or opens a form."""
    m = p.model
    kind, sel = m.selection_kind, list(m.selection)
    if not sel or m.active_sketch:
        return []
    n = len(sel)
    items: list[MenuItem] = []
    add = items.append
    if kind == "FACE":
        try:
            types = [_surface_type(m.entity_shape("FACE", g)) for g in sel]
        except Exception:  # noqa: BLE001 - a stale pick
            return []
        flat = all(t == "PLANE" for t in types)
        round_ = all(t in ("CYLINDER", "CONE") for t in types)
        if n == 1 and flat:
            name = _next_name(p, "SKETCH") or "s1"
            add(MenuItem("Sketch on this face", short="Sketch", commands=[f"SKETCH, {name}, FACE, {sel[0]}"], icon="sketch"))
        add(MenuItem("Pull…" if n == 1 else f"Pull {n} faces…", short="Pull", form="PUSHPULL", icon="pushpull"))
        if flat and n == 1:
            add(MenuItem("Hole…", short="Hole", form="HOLE", icon="hole"))
        if round_:
            add(MenuItem("Thread…", short="Thread", form="THREAD", icon="thread"))
        add(MenuItem("Fillet its edges…" if n == 1 else "Fillet their edges…", short="Fillet edges", form="FILLET",
                     first=["SEL, S, EDGE, OF, FACE"], icon="fillet"))
        add(MenuItem("Shell (open this face)…" if n == 1 else f"Shell (open {n} faces)…", short="Shell", form="SHELL",
                     icon="shell"))
        add(MenuItem("Move face…" if n == 1 else "Move faces…", short="Move face", form="MOVEFACE", icon="moveface"))
        if n == 1 and flat:
            name = _next_name(p, "PLANE") or "P1"
            add(MenuItem("Work plane on it", short="Plane", commands=[f"PLANE, {name}, FACE, {sel[0]}"], icon="plane"))
        if n == 1 and round_:
            name = _next_name(p, "AXIS") or "A1"
            add(MenuItem("Axis through it", short="Axis", commands=[f"AXIS, {name}, FACE, {sel[0]}"], icon="axis"))
        if n == 2:
            add(MenuItem("Distance and angle", short="Measure", commands=["DIST", "ANGLE"] if flat else ["DIST"], icon="measure"))
            add(MenuItem("Mate the two…", short="Mate", form="MATE", icon="mate"))
            add(MenuItem("Joint between the two…", short="Joint", form="JOINT", icon="joint"))
        if n == 1:
            add(MenuItem("Faces that meet it smoothly", short="Smooth faces", commands=[f"SEL, S, FACE, TANGENT, {sel[0]}"], icon="pick_face"))
        add(MenuItem("Delete face (close the gap)" if n == 1 else f"Delete {n} faces (close the gap)", ["DELFACE"],
                     short="Delete",
                     icon="delface"))
    elif kind == "EDGE":
        add(MenuItem("Fillet…" if n == 1 else f"Fillet {n} edges…", short="Fillet", form="FILLET", icon="fillet"))
        add(MenuItem("Chamfer…" if n == 1 else f"Chamfer {n} edges…", short="Chamfer", form="CHAMFER", icon="chamfer"))
        if n == 1:
            add(MenuItem("Loop round its face", short="Loop", commands=[f"SEL, S, EDGE, LOOP, {sel[0]}"], icon="pick_edge"))
            add(MenuItem("Tangent chain", short="Chain", commands=[f"SEL, S, EDGE, CHAIN, {sel[0]}"], icon="pick_edge"))
            try:
                ctype = _curve_type(m.entity_shape("EDGE", sel[0]))
            except Exception:  # noqa: BLE001
                ctype = ""
            if ctype in ("LINE", "CIRCLE"):
                name = _next_name(p, "AXIS") or "A1"
                add(MenuItem("Axis along it" if ctype == "LINE" else "Axis through its centre", short="Axis",
                             commands=[f"AXIS, {name}, EDGE, {sel[0]}"], icon="axis"))
        if n == 2:
            add(MenuItem("Distance and angle", short="Measure", commands=["DIST", "ANGLE"], icon="measure"))
            add(MenuItem("Joint between the two…", short="Joint", form="JOINT", icon="joint"))
    elif kind == "VERTEX":
        if n == 2:
            add(MenuItem("Distance", short="Measure", commands=["DIST"], icon="measure"))
        if n == 3:
            name = _next_name(p, "PLANE") or "P1"
            add(MenuItem("Work plane through the three", short="Plane", commands=[f"PLANE, {name}, 3P, " + ", ".join(f'CENT({v}, "VERTEX")' for v in sel)],
                         icon="plane"))
    elif kind == "BODY":
        names = " ".join(str(b) for b in sel)
        add(MenuItem("Move…" if n == 1 else f"Move {n} bodies…", short="Move", form="MOVE", icon="move"))
        add(MenuItem("Rotate…", short="Rotate", form="ROTATE", icon="rotate"))
        add(MenuItem("Mirror…", short="Mirror", form="MIRROR", icon="mirror"))
        add(MenuItem("Array…", short="Array", form="ARRAY", icon="array"))
        if n >= 2:
            add(MenuItem(f"Union of the {n}", short="Union", commands=[f"UNION, {sel[0]}, SEL"], icon="union"))
            add(MenuItem(f"Subtract the others from body {sel[0]}", short="Subtract",
                         commands=["SEL, U, BODY, ID, " + str(sel[0]), f"SUBTRACT, {sel[0]}, SEL"], icon="subtract"))
            add(MenuItem(f"Intersect the {n}", short="Intersect", commands=[f"INTERSECT, {', '.join(map(str, sel[:9]))}"], icon="intersect"))
        if n == 2:
            add(MenuItem("Distance", short="Measure", commands=["DIST"], icon="measure"))
        add(MenuItem("Check", short="Check", commands=[f"CHECK, {sel[0]}"] if n == 1 else [f"CHECK, {b}" for b in sel], icon="check"))
        add(MenuItem("Mass and volume", short="Mass", commands=["MASSPROP"], icon="measure"))
        _ = names
    return items


def tools_rows(p) -> list[dict]:
    """The tools for the current pick as data (TOOLS, the assistant's suggest_tools)."""
    rows = []
    for it in pick_tools(p):
        row = {"label": it.label}
        if it.first:
            row["first"] = list(it.first)
        if it.form:
            row["form"] = it.form
            row["runs"] = f"{it.form}, ... (its form opens, filled in from the pick)"
        else:
            row["runs"] = " / ".join(it.commands)
        rows.append(row)
    return rows


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
