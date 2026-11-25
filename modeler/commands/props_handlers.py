"""PROPS: one table of a body's properties, where each value can be changed (PLAN item 91).

The table holds the body's name, where it is (the centre of its box), a turn
row, the values of the steps that made it, its colour, layer and material,
and read-only numbers (size, volume, area, mass). Changing a value writes the
ordinary step and nothing else:

    name        NAME, b, new
    x, y, z     MOVE, b, dx, dy, dz           (the centre moves to the new value)
    turn        ROTATE, b, angle, centre, axis  ("Z 90": 90 degrees about Z, through the centre)
    colour      COLOR, b, value
    layer       LAYER, value, ADD, b
    material    MATERIAL, b, value
    5.dx        HIST, EDIT, 5, ...            (argument dx of history step 5)

``PROPS, b`` prints it, ``PROPS, b, key, value`` changes one value, ``PROPS, b, JSON``
gives it as data (the Properties panel and the assistant's ``properties`` tool).
"""

from __future__ import annotations

import json
import re
from typing import Any

from .processor import REGISTRY, Arg, CommandError, Processor, Raw, Text, command

MAX_STEPS = 4  # the steps that made a body whose values the table shows (the last ones)
_PLACE = ("x", "y", "z", "angle", "dx", "dy", "dz")  # INST's place arguments after the part
AXES = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}


def _r(v: float) -> float:
    return round(float(v), 4) + 0.0


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(c * 255))) for c in rgb)


def body_of(p: Processor, raw: str) -> int:
    """A body from an ID, a name, LAST or SEL (the first selected body, or the body of the first pick)."""
    s = (raw or "SEL").strip()
    m = p.model
    if s.upper() == "SEL":
        if not m.selection:
            raise CommandError("PROPS: pick a body (or a face of it) first, or give its name")
        gid = m.selection[0]
        return gid if m.selection_kind == "BODY" else m.entity_owner(m.selection_kind, gid)[0]
    bid = p._body_ref(REGISTRY["PROPS"], s)
    if bid not in m.bodies:
        raise CommandError(f"PROPS: no body {s}")
    return bid


def _label(p: Processor, bid: int) -> str:
    b = p.model.bodies[bid]
    return b.name if b.name and b.name.lower() != f"body{bid}" else str(bid)


def _centre(p: Processor, bid: int) -> tuple[float, float, float]:
    from .queries import bbox

    bb = bbox(p.model.bodies[bid].shape)
    return tuple(_r((bb[i] + bb[3 + i]) / 2) for i in range(3))


# steps that do not shape the body: their values are rows of their own (name, where, look)
NOT_SHAPE = frozenset({"NAME", "MATERIAL", "COLOR", "LAYER", "MOVE", "ROTATE", "PICK", "SEL", "CMSEL", "PICKMODE",
                       "FADE", "UNFADE", "DISPLAY", "NOTE", "PROPERTY"})
_NAMED = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$")


def step_rows(p: Processor, bid: int) -> list[dict[str, Any]]:
    """The size values of the steps that shaped the body: one row per argument (body
    names are left out); the first step and the last few when there are many."""
    from ..ai.diagnose import _split_cmd
    from .lineage import body_steps

    shaped = []
    for j in body_steps(p, bid):
        split = _split_cmd(p.history[j].text)
        if split and split[1].upper() not in NOT_SHAPE:
            shaped.append((j, split))
    if len(shaped) > MAX_STEPS:
        shaped = shaped[:1] + shaped[-(MAX_STEPS - 1):]
    rows: list[dict[str, Any]] = []
    for j, split in shaped:
        rows += args_rows(p, j, split)
    return rows


def args_rows(p: Processor, j: int, split, bodies: bool = False) -> list[dict[str, Any]]:
    """One row per argument of history row ``j`` (``split`` from diagnose._split_cmd);
    body arguments only with ``bodies``."""
    from .processor import BodyRef

    rows: list[dict[str, Any]] = []
    word = split[1].upper()
    cmd = REGISTRY.get(word)
    args = cmd.args if cmd is not None else []
    for k, val in enumerate(split[2]):
        if val == "":
            continue
        a = args[k] if k < len(args) else None
        if not bodies and a is not None and (a.type is BodyRef or a.name in ("part",)):
            continue
        name = a.name if a is not None else f"a{k + 1}"
        if word in ("INST", "LINK") and 1 <= k <= len(_PLACE):
            name = _PLACE[k - 1]
        named = _NAMED.match(val)
        if named and word in ("INST", "LINK") and named.group(1).upper() not in ("NAME",):
            name, val = named.group(1).upper(), named.group(2)
        rows.append({"key": f"{j + 1}.{name}", "value": val, "step": j + 1, "command": word, "arg": k,
                     "named": bool(named and word in ("INST", "LINK")),
                     "group": f"step {j + 1}: {word}", "edit": "HIST, EDIT", "about": ""})
    if word == "INST" and split[2]:
        # the part's values this copy leaves at their defaults: a change adds NAME=value
        part = p.parts.get(split[2][0].strip().upper())
        given = {r["key"].split(".", 1)[1].upper() for r in rows}
        for pname, default in (getattr(part, "params", None) or []):
            if pname.upper() not in given:
                rows.append({"key": f"{j + 1}.{pname.upper()}", "value": str(default), "step": j + 1,
                             "command": word, "arg": None, "named": True, "group": f"step {j + 1}: {word}",
                             "edit": "HIST, EDIT", "about": f"the part's default ({split[2][0].strip()})"})
    return rows


_STEP = re.compile(r"^\s*(?:STEP\s*|#)(\d+)\s*$", re.I)


def step_of(p: Processor, raw: str) -> int | None:
    """``STEP 5`` or ``#5``: history step 5 (1-based), else None."""
    m = _STEP.match(raw or "")
    if not m:
        return None
    n = int(m.group(1))
    if not 1 <= n <= p.cursor:
        raise CommandError(f"PROPS: there are {p.cursor} history steps; give 1 to {p.cursor}")
    return n


def step_properties(p: Processor, n: int) -> dict[str, Any]:
    from ..ai.diagnose import _split_cmd
    from .lineage import made_by

    e = p.history[n - 1]
    split = _split_cmd(e.text)
    rows = args_rows(p, n - 1, split, bodies=True) if split else []
    made = made_by(p, n - 1)
    return {"step": n, "label": e.label, "units": p.model.units.lower(), "ok": e.ok,
            "made": made, "rows": rows,
            "note": "" if split else "a block of several lines: edit it in the History panel"}


def set_step_line(p: Processor, n: int, key: str, value: str) -> str:
    rows = step_properties(p, n)["rows"]
    k = key.strip().lower()
    row = next((r for r in rows if r["key"].lower() == k or r["key"].split(".", 1)[1].lower() == k), None)
    if row is None:
        raise CommandError(f"PROPS: step {n} has no value {key}; it has: "
                           + ", ".join(r["key"].split(".", 1)[1] for r in rows))
    return _edit_line(p, row, value)


def _edit_line(p: Processor, step: dict[str, Any], v: str) -> str:
    from ..ai.diagnose import _join, _split_cmd
    from ..lang.expr import format_value

    e = p.history[step["step"] - 1]
    comments, word, args = _split_cmd(e.text)
    args = list(args)
    if step["arg"] is None:  # a part value left at its default: add it
        args.append(f"{step['key'].split('.', 1)[1]}={v}")
    else:
        old = args[step["arg"]]
        args[step["arg"]] = (old.split("=", 1)[0].rstrip() + "=" + v) if step.get("named") else v
    return f"HIST, EDIT, {step['step']}, {format_value(_join(comments, word, args))}"


def properties(p: Processor, bid: int) -> dict[str, Any]:
    from .selinfo import body_numbers

    m = p.model
    b = m.bodies[bid]
    nums = body_numbers(p, bid)
    rows: list[dict[str, Any]] = []

    def add(key, value, group, edit="", about=""):
        rows.append({"key": key, "value": value, "group": group, "edit": edit, "about": about})

    add("id", bid, "body")
    add("name", "" if b.name.lower() == f"body{bid}" else b.name, "body", "NAME")
    if bid in m.instances:
        add("part", m.instances[bid][0].lower(), "body", "", "a copy of this part (INST)")
    if nums.get("kind"):
        add("kind", nums["kind"], "body")
    c = _centre(p, bid)
    for axis, v in zip("xyz", c):
        add(axis, v, "where", "MOVE", f"the centre of its box in {axis.upper()}; a new value moves the body")
    add("turn", "", "where", "ROTATE", "type an axis and an angle, e.g. Z 90: turns it about its centre")
    add("colour", _hex(b.color) if b.color else "", "look", "COLOR",
        "its own colour; empty: the colour of its layer or material")
    add("layer", b.layer.lower(), "look", "LAYER")
    add("material", b.material.lower(), "look", "MATERIAL")
    for key in ("size", "volume", "area", "mass_kg", "centre"):
        if key in nums:
            add("centre of mass" if key == "centre" else key.replace("_kg", " (kg)"), nums[key], "numbers")
    return {"body": bid, "label": _label(p, bid), "units": m.units.lower(), "rows": rows + step_rows(p, bid)}


def set_line(p: Processor, bid: int, key: str, value: str) -> str:
    """The ordinary step that changes one property."""
    ref = _label(p, bid)
    k = key.strip().lower()
    v = value.strip()
    if k == "name":
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", v):
            raise CommandError("PROPS: a name is a word of letters, digits and _ that starts with a letter")
        return f"NAME, {ref}, {v}"
    if k in ("x", "y", "z"):
        try:
            new = float(p.evaluator.eval(v))
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"PROPS: {k} needs a number ({exc})") from None
        c = _centre(p, bid)
        d = [0.0, 0.0, 0.0]
        d["xyz".index(k)] = _r(new - c["xyz".index(k)])
        if all(abs(x) < 1e-9 for x in d):
            raise CommandError(f"PROPS: the body is already at {k} = {v}")
        return "MOVE, {}, {}".format(ref, ", ".join(_num(x) for x in d))
    if k == "turn":
        m = re.match(r"^\s*([XYZ])\s*[, ]\s*(-?[\d.]+)\s*$", v, re.I)
        if not m:
            raise CommandError("PROPS: turn is an axis and an angle in degrees, e.g. Z 90")
        ax = AXES[m.group(1).upper()]
        c = _centre(p, bid)
        return "ROTATE, {}, {}, {}, {}".format(ref, m.group(2), ", ".join(_num(x) for x in c),
                                               ", ".join(str(a) for a in ax))
    if k in ("colour", "color"):
        return f"COLOR, {ref}, {v or 'DEFAULT'}"
    if k == "layer":
        v = v or "DEFAULT"
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", v):
            raise CommandError("PROPS: a layer name is a word of letters, digits and _")
        new = "" if v.upper() in p.model.layers else f"LAYER, {v}, NEW\n"
        return f"{new}LAYER, {v}, ADD, {ref}"
    if k == "material":
        return f"MATERIAL, {ref}, {v or 'NONE'}"
    step = next((r for r in step_rows(p, bid) if r["key"].lower() == k), None)
    if step is not None:
        return _edit_line(p, step, v)
    keys = [r["key"] for r in properties(p, bid)["rows"] if r["edit"]]
    raise CommandError(f"PROPS: {key} cannot be changed here; these can: {', '.join(keys)}")


def _num(x: float) -> str:
    s = f"{x:.6f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def table_text(d: dict[str, Any]) -> str:
    if "step" in d and "body" not in d:
        made = d.get("made") or []
        lines = [f"step {d['step']}: {d['label']}" + ("" if d.get("ok", True) else " (FAILED)")
                 + (f", made bod{'y' if len(made) == 1 else 'ies'} {', '.join(map(str, made))}" if made else "")
                 + f", in {d['units']}:"]
        if d.get("note"):
            lines.append("  " + d["note"])
    else:
        lines = [f"properties of body {d['body']}" + (f" ({d['label']})" if d["label"] != str(d["body"]) else "")
                 + f", in {d['units']}:"]
    group = None
    for r in d["rows"]:
        if r["group"] != group:
            group = r["group"]
            lines.append(f"  {group}")
        v = r["value"]
        if isinstance(v, (list, tuple)):
            v = ", ".join(_num(x) for x in v)
        elif isinstance(v, float):
            v = _num(v)
        mark = " *" if r["edit"] else ""
        lines.append(f"    {r['key']:<16} {v}{mark}")
    lines.append("  (* can be changed: PROPS, b, key, value)")
    return "\n".join(lines)


@command(
    "PROPS",
    Arg("b", Raw, "SEL", help="a body (name, ID, LAST), SEL (the picked body, or the body of the pick), "
                              "or a history step: STEP 5 (or #5)"),
    Arg("key", Raw, "", help="what to change: name, x, y, z, turn, colour, layer, material, or a step value "
                             "such as 5.dx (or JSON for the table as data)"),
    Arg("value", Text, "", help="the new value"),
    logged=False,
    help="One table of a body's properties: name, where it is, the values of the steps that made it, colour, "
         "layer, material and its numbers (size, volume, area, mass). PROPS, bracket prints it · "
         "PROPS, bracket, x, 40 moves its centre to x = 40 (a MOVE step) · PROPS, bracket, 3.dx, 25 changes "
         "argument dx of step 3 (HIST, EDIT) · PROPS, bracket, colour, red · PROPS, bracket, turn, Z 90 · "
         "PROPS, STEP 5 lists the values of history step 5 and PROPS, STEP 5, dx, 30 changes one. "
         "PROPS, bracket, JSON. Each change is the ordinary step, so Undo takes it back.",
)
def props(p: Processor, b, key, value):
    key = (key or "").strip()
    n = step_of(p, b)
    if n is not None:
        table = step_properties(p, n)
    else:
        bid = body_of(p, b)
        table = None
    if not key or key.upper() == "JSON":
        table = table or properties(p, bid)
        return json.dumps(table) if key else table_text(table)
    v = (value or "").strip().strip('"')
    text = set_step_line(p, n, key, v) if n is not None else set_line(p, bid, key, v)
    out = []
    for line in text.splitlines():
        r = p.run_unit(line)
        if not r.ok:
            raise CommandError(f"PROPS ({line}): {r.message}")
        out.append(line + (f": {r.message.splitlines()[0]}" if r.message else ""))
    return "\n".join(out)
