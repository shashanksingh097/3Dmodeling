"""Layers, colours and materials: LAYER, COLOR, MATERIAL, ISOLATE.

Every body sits on one layer. A layer can be switched off (its bodies are
not drawn), locked (its bodies cannot be changed, used up or deleted) and
given a colour. New bodies go on the current layer; a body made from other
bodies (a boolean, a fillet, a move) stays on the layer of its first input,
with its colour and material, and so does a copy.

A body is drawn in its own colour if it has one, else in its layer's colour,
else in its material's colour, else in the plain default grey.
"""

from __future__ import annotations

from dataclasses import replace

from ..core.model import DEFAULT_LAYER, MATERIALS, Layer, Material
from ..lang.expr import ExprError, Vec, fmt_num
from ..lang.script import is_ident
from .processor import REGISTRY, Arg, CommandError, Processor, Raw, Text, command

# Colour names a person can type. Values are 0..255 RGB.
COLORS: dict[str, tuple[int, int, int]] = {
    "RED": (214, 64, 56), "ORANGE": (240, 140, 40), "YELLOW": (236, 200, 50), "GREEN": (70, 170, 90),
    "TEAL": (40, 160, 160), "CYAN": (80, 200, 230), "BLUE": (60, 110, 210), "NAVY": (36, 56, 120),
    "PURPLE": (136, 84, 196), "MAGENTA": (210, 70, 170), "PINK": (240, 150, 180), "BROWN": (140, 90, 50),
    "WHITE": (240, 240, 240), "GREY": (150, 150, 155), "GRAY": (150, 150, 155), "BLACK": (40, 40, 44),
}

LAYER_ACTIONS = ("CURRENT", "NEW", "ON", "OFF", "LOCK", "UNLOCK", "COLOR", "ADD", "RENAME", "DELETE")


# ---- argument helpers --------------------------------------------------------------

def parse_color(p: Processor, what: str, c: str, g: str = "", b: str = "") -> tuple[float, float, float] | None:
    """A colour from a name (RED), a hex code (#ff8800), three numbers 0..255
    (given as three arguments or one point value), or DEFAULT/NONE for none."""
    s = c.strip()
    if not s:
        raise CommandError(f"{what}: give a colour: a name ({', '.join(list(COLORS)[:6])} ...), #rrggbb, or r, g, b (0..255)")
    if s[:1] in "\"'" and s[-1:] == s[:1]:
        s = s[1:-1].strip()
    up = s.upper()
    if up in ("DEFAULT", "NONE", "BYLAYER"):
        return None
    if up in COLORS:
        r, gg, bb = COLORS[up]
        return (r / 255.0, gg / 255.0, bb / 255.0)
    if s.startswith("#"):
        h = s[1:]
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        try:
            if len(h) != 6:
                raise ValueError
            r, gg, bb = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            raise CommandError(f"{what}: {s!r} is not a colour code (use #rrggbb)") from None
        return (r / 255.0, gg / 255.0, bb / 255.0)
    try:
        if g.strip() or b.strip():
            vals = [p.evaluate(x) for x in (c, g, b) if x.strip()]
        else:
            v = p.evaluate(c)
            if isinstance(v, str):
                return parse_color(p, what, v)
            vals = list(v) if isinstance(v, Vec) else [v]
    except ExprError:
        if is_ident(s):
            raise CommandError(f"{what}: unknown colour {s!r} (names: {', '.join(COLORS)}; or #rrggbb, or r, g, b)") from None
        raise CommandError(f"{what}: {s!r} is not a colour") from None
    if len(vals) != 3 or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in vals):
        raise CommandError(f"{what}: a colour is three numbers r, g, b from 0 to 255")
    if any(x < 0 or x > 255 for x in vals):
        raise CommandError(f"{what}: colour values go from 0 to 255")
    return tuple(float(x) / 255.0 for x in vals)  # type: ignore[return-value]


def color_text(c: tuple[float, float, float] | None) -> str:
    if c is None:
        return "default"
    rgb = tuple(round(x * 255) for x in c)
    for name, v in COLORS.items():
        if v == rgb:
            return name.lower()
    return "#%02x%02x%02x" % rgb


def target_bodies(p: Processor, what: str, raw: str) -> list[int]:
    """Bodies from a target argument: a body (ID, name, LAST), SEL (the
    selected bodies, or the bodies of the selected faces/edges/vertices) or ALL."""
    m = p.model
    s = raw.strip().upper()
    if s == "ALL":
        if not m.bodies:
            raise CommandError(f"{what}: there are no bodies")
        return sorted(m.bodies)
    if s == "SEL":
        if not m.selection:
            raise CommandError(f"{what}: nothing is selected")
        if m.selection_kind == "BODY":
            return list(m.selection)
        out: list[int] = []
        for gid in m.selection:
            bid = m.entity_owner(m.selection_kind, gid)[0]
            if bid not in out:
                out.append(bid)
        return out
    if s == "LAST":
        if not m.last_body or m.last_body not in m.bodies:
            raise CommandError(f"{what}: there is no last body")
        return [m.last_body]
    bid = p._body_arg(REGISTRY[what], raw)
    m.body(bid)
    return [bid]


def _ids_text(ids: list[int]) -> str:
    if len(ids) == 1:
        return f"body {ids[0]}"
    shown = ", ".join(map(str, ids[:8])) + ("..." if len(ids) > 8 else "")
    return f"{len(ids)} bodies ({shown})"


def _layer_name(what: str, name: str) -> str:
    n = name.strip()
    if not is_ident(n):
        raise CommandError(f"{what}: {n!r} is not a valid layer name (letters, digits, _)")
    if n.upper() in ("ALL", "SEL", "LAST"):
        raise CommandError(f"{what}: {n} is reserved")
    return n


# ---- LAYER --------------------------------------------------------------------------

@command(
    "LAYER",
    Arg("name", Text, help="layer name (ALL with ON, OFF, LOCK, UNLOCK)"),
    Arg("action", str, "CURRENT", help=", ".join(LAYER_ACTIONS)),
    Arg("value", Raw, "", "for COLOR: a colour; for ADD: bodies (a body, SEL or ALL); for RENAME: the new name"),
    Arg("g", Raw, "", "green, when the colour is given as r, g, b"),
    Arg("b", Raw, "", "blue"),
    help=(
        "Organise bodies in layers: LAYER, pipes makes the layer (if new) and draws new bodies on it · "
        "LAYER, pipes, NEW [, colour] makes it without switching · LAYER, pipes, OFF / ON shows or hides its bodies · "
        "LAYER, pipes, LOCK / UNLOCK protects them from changes · LAYER, pipes, COLOR, blue · "
        "LAYER, pipes, ADD, SEL moves bodies onto it · LAYER, pipes, RENAME, ducts · "
        "LAYER, pipes, DELETE (its bodies go to DEFAULT) · LAYER, ALL, ON"
    ),
)
def layer(p: Processor, name, action, value, g, b):
    m = p.model
    what = "LAYER"
    if action not in LAYER_ACTIONS:
        raise CommandError(f"LAYER: unknown action {action!r} (use {', '.join(LAYER_ACTIONS)})")
    if name.strip().upper() == "ALL":
        flags = {"ON": ("visible", True), "OFF": ("visible", False), "LOCK": ("locked", True), "UNLOCK": ("locked", False)}
        if action not in flags:
            raise CommandError("LAYER, ALL: only ON, OFF, LOCK or UNLOCK")
        key, val = flags[action]
        for lay in list(m.layers.values()):
            if getattr(lay, key) != val:
                m.put_layer(replace(lay, **{key: val}))
        return f"all {len(m.layers)} layers {action.lower()}"
    name = _layer_name(what, name)
    key = name.upper()
    exists = key in m.layers
    if action in ("CURRENT", "NEW"):
        made = ""
        if not exists:
            col = parse_color(p, what, value, g, b) if value.strip() else None
            m.put_layer(Layer(name, col))
            made = f"new layer {name}" + (f" ({color_text(col)})" if col else "")
        elif action == "NEW":
            raise CommandError(f"LAYER: layer {m.layers[key].name} already exists")
        elif value.strip():
            raise CommandError(f"LAYER: {m.layers[key].name} already exists; set its colour with LAYER, {name}, COLOR, ...")
        if action == "NEW":
            return made
        m.set_current_layer(name)
        return (made + "; " if made else "") + f"new bodies go on layer {m.layers[key].name}"
    if not exists:
        raise CommandError(f"LAYER: no layer named {name!r} (layers: {', '.join(l.name for l in m.layers.values())}). "
                           f"LAYER, {name} makes it")
    lay = m.layers[key]
    count = sum(1 for x in m.bodies.values() if x.layer.upper() == key)
    if action in ("ON", "OFF"):
        m.put_layer(replace(lay, visible=action == "ON"))
        return f"layer {lay.name} {'shown' if action == 'ON' else 'hidden'} ({count} bod{'y' if count == 1 else 'ies'})"
    if action in ("LOCK", "UNLOCK"):
        m.put_layer(replace(lay, locked=action == "LOCK"))
        return f"layer {lay.name} {action.lower()}ed ({count} bod{'y' if count == 1 else 'ies'})"
    if action == "COLOR":
        col = parse_color(p, what, value, g, b)
        m.put_layer(replace(lay, color=col))
        return f"layer {lay.name} colour {color_text(col)}"
    if action == "ADD":
        if lay.locked:
            raise CommandError(f"LAYER: layer {lay.name} is locked (LAYER, {lay.name}, UNLOCK first)")
        ids = target_bodies(p, "LAYER", value or "SEL")
        for bid in ids:
            m.set_style(bid, layer=lay.name)
        return f"{_ids_text(ids)} now on layer {lay.name}"
    if action == "RENAME":
        new = _layer_name(what, value.strip().strip("\"'"))
        m.rename_layer(lay.name, new)
        return f"layer {lay.name} is now {new}"
    # DELETE
    moved = m.delete_layer(lay.name)
    return f"deleted layer {lay.name}" + (f"; {moved} bod{'y' if moved == 1 else 'ies'} moved to {DEFAULT_LAYER}" if moved else "")


# ---- COLOR --------------------------------------------------------------------------

@command(
    "COLOR",
    Arg("target", Raw, help="a body, SEL or ALL"),
    Arg("color", Raw, help="a name (RED, BLUE ...), #rrggbb, r (0..255), or DEFAULT to draw it by layer or material"),
    Arg("g", Raw, "", "green (0..255), when the colour is r, g, b"),
    Arg("b", Raw, "", "blue (0..255)"),
    help="Colour bodies: COLOR, bracket, RED · COLOR, SEL, #3080ff · COLOR, LAST, 255, 128, 0 · COLOR, ALL, DEFAULT.",
)
def color(p: Processor, target, color, g, b):
    col = parse_color(p, "COLOR", color, g, b)
    ids = target_bodies(p, "COLOR", target)
    for bid in ids:
        p.model.set_style(bid, color=col)
    return f"{_ids_text(ids)} colour {color_text(col)}" + (" (by layer or material)" if col is None else "")


# ---- MATERIAL -----------------------------------------------------------------------

@command(
    "MATERIAL",
    Arg("target", Raw, help="a body, SEL or ALL"),
    Arg("name", Text, help="STEEL, ALUMINIUM, BRASS, ABS ... or a new name with a density; NONE takes it off"),
    Arg("density", float, 0.0, "kg/m3, to make a new material (or change one you made)"),
    Arg("color", Raw, "", "colour of a new material"),
    help=("Give bodies a material: MATERIAL, SEL, ALUMINIUM. MASSPROP then gives the mass without a density. "
          "A new one: MATERIAL, LAST, CFRP, 1600, BLACK. Built in: " + ", ".join(MATERIALS) + "."),
)
def material(p: Processor, target, name, density, color):
    m = p.model
    n = name.strip()
    if density < 0:
        raise CommandError("MATERIAL: the density cannot be negative")
    if n.upper() == "NONE":
        mat = None
    elif density:
        if not is_ident(n):
            raise CommandError(f"MATERIAL: {n!r} is not a valid material name (letters, digits, _)")
        key = n.upper()
        try:
            known = m.material(n)
        except Exception:
            known = None
        if known is not None and known.name in MATERIALS and known.density != density:
            raise CommandError(f"MATERIAL: {known.name} is built in ({fmt_num(known.density)} kg/m3); "
                               "give your material another name")
        col = parse_color(p, "MATERIAL", color) if color.strip() else (known.color if known else None)
        mat = Material(known.name if known else key, density, col, known.transparency if known else 0.0)
        if mat != known:
            m.put_material(mat)
    else:
        if color.strip():
            raise CommandError("MATERIAL: a colour is only for a new material (give its density too)")
        mat = m.material(n)
    ids = target_bodies(p, "MATERIAL", target)
    for bid in ids:
        m.set_style(bid, material=mat.name if mat else "")
    if mat is None:
        return f"{_ids_text(ids)}: no material"
    return f"{_ids_text(ids)}: {mat.name.lower()} ({fmt_num(mat.density)} kg/m3)"


# ---- ISOLATE ------------------------------------------------------------------------

@command(
    "ISOLATE",
    Arg("target", Raw, "SEL", "a body, SEL, or a layer name"),
    help="Show only these bodies and hide every other one: ISOLATE, SEL · ISOLATE, bracket · ISOLATE, pipes "
         "(a layer). SHOW, ALL brings the others back.",
)
def isolate(p: Processor, target):
    m = p.model
    s = target.strip()
    ids: list[int]
    if s.upper() not in ("SEL", "ALL", "LAST") and m.body_by_name(s) is None and s.upper() in m.layers:
        lay = m.layers[s.upper()]
        ids = [i for i, b in m.bodies.items() if b.layer.upper() == lay.name.upper()]
        if not ids:
            raise CommandError(f"ISOLATE: layer {lay.name} has no bodies")
        if not lay.visible:
            m.put_layer(replace(lay, visible=True))
    else:
        ids = target_bodies(p, "ISOLATE", s)
    keep = set(ids)
    for bid in sorted(m.bodies):
        m.set_hidden(bid, bid not in keep)
    off = [lay.name for i in ids for lay in [m.layer_of(i)] if not lay.visible]
    msg = f"showing only {_ids_text(ids)}"
    if off:
        msg += f" (on hidden layer {', '.join(sorted(set(off)))}: LAYER, name, ON to see them)"
    return msg


# ---- listing ------------------------------------------------------------------------

def layers_listing(p: Processor) -> list[str]:
    m = p.model
    lines = ["layers:"]
    for key, lay in m.layers.items():
        n = sum(1 for b in m.bodies.values() if b.layer.upper() == key)
        flags = [("current" if key == m.current_layer else ""), ("" if lay.visible else "off"),
                 ("locked" if lay.locked else "")]
        flags = [f for f in flags if f]
        lines.append(f"  {lay.name}: {n} bod{'y' if n == 1 else 'ies'}, colour {color_text(lay.color)}"
                     + (f" [{', '.join(flags)}]" if flags else ""))
    return lines


def materials_listing(p: Processor) -> list[str]:
    m = p.model
    used: dict[str, int] = {}
    for b in m.bodies.values():
        if b.material:
            used[b.material.upper()] = used.get(b.material.upper(), 0) + 1
    lines = ["materials:"]
    for key, mat in m.materials.items():
        n = used.get(key, 0)
        lines.append(f"  {mat.name}: {fmt_num(mat.density)} kg/m3, {color_text(mat.color)}"
                     + (f", {n} bod{'y' if n == 1 else 'ies'}" if n else "") + ("" if key in MATERIALS else " (yours)"))
    return lines
