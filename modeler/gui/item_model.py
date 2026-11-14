"""What the item panel under the model tree shows, without Qt.

For the body picked in the tree it lists every step that made it (its
lineage, commands/lineage.py), split into single lines where a step is a
block: the lines of a ``*PART`` recipe or of a ``*DO`` loop. Each line can
be edited in its fill-in form; the edit goes back into that history entry
with ``HIST, EDIT``, so changing a bolt part's ``THREAD`` line rebuilds
every bolt placed from it. The parameters those steps use are listed with
their values and can be changed the same way the Parameters panel does.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..commands.lineage import body_steps
from ..lang.expr import format_value
from ..lang.script import strip_comment
from . import forms as F

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_INST = re.compile(r"^\s*INST\s*,\s*([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
_PART = re.compile(r"^\s*\*PART\s*,\s*([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)


@dataclass
class StepLine:
    row: int  # 0-based history entry
    line: int | None  # 0-based line inside the entry, None for a one-line entry
    text: str  # the command, without its comment
    depth: int = 0  # 0: the entry itself, 1: a line inside it
    form: bool = False  # opens in a fill-in form
    sweep: bool = False  # opens in the sweep editor
    warning: str = ""


@dataclass
class ItemInfo:
    bid: int
    title: str
    lines: list[StepLine] = field(default_factory=list)
    params: list[tuple[str, str]] = field(default_factory=list)  # (NAME, value as text) used by the steps
    part: str = ""  # for an instance: the part's name
    copies: int = 0  # for an instance: how many bodies come from the same part
    values: str = ""  # for an instance: its own values, "D=8, L=30"


def _has_form(text: str) -> bool:
    try:
        F.parse(text)
        return True
    except Exception:  # noqa: BLE001 - FormError, or a line no form understands
        return False


def _is_sweep(text: str) -> bool:
    return text.strip().upper().startswith("SWEEP")


def entry_lines(p, row: int) -> list[StepLine]:
    """One history entry as lines: itself, or for a block its inner code lines."""
    e = p.history[row]
    code = [(i, strip_comment(raw).strip()) for i, raw in enumerate(e.text.splitlines())]
    code = [(i, c) for i, c in code if c]
    if len(code) == 1:
        i, c = code[0]
        return [StepLine(row, None, c, 0, _has_form(c), _is_sweep(c), e.warning)]
    out = [StepLine(row, code[0][0], code[0][1], 0, False, False, e.warning)]  # the *PART or *DO line
    for i, c in code[1:]:
        if c.upper().startswith(("*END", "*ENDPART", "*ENDDO", "*ENDIF")):
            continue
        out.append(StepLine(row, i, c, 1, _has_form(c), _is_sweep(c)))
    return out


def params_used(p, texts: list[str]) -> list[tuple[str, str]]:
    """The model parameters these lines mention, in the order they first appear."""
    seen: list[str] = []
    for t in texts:
        for name in _IDENT.findall(t):
            key = name.upper()
            # (a parameter set inside a loop, such as X, is not one you can change here)
            if key in p.params and key not in seen and p.entry_for_param(key) is not None:
                seen.append(key)
    return [(k, format_value(p.params[k])) for k in seen]


def item_info(p, bid: int) -> ItemInfo:
    m = p.model
    b = m.bodies[bid]
    rows = body_steps(p, bid)
    mine = m.instances[bid][0].upper() if bid in m.instances else ""
    lines: list[StepLine] = []
    for row in rows:
        for ln in entry_lines(p, row):
            inst = _INST.match(ln.text)
            if ln.depth and inst and inst.group(1).upper() != mine:
                continue  # a loop that also places other parts: not this body's line
            lines.append(ln)
    info = ItemInfo(bid, f"{b.name} (body {bid})" if b.name and b.name.lower() != f"body{bid}" else f"body {bid}",
                    lines)
    # the part's own parameters (D, L inside *PART) are not model parameters;
    # the parameters of the steps outside the part are
    outside = [ln.text for ln in lines if not _PART.match(p.history[ln.row].text)]
    info.params = params_used(p, outside)
    if bid in m.instances:
        part, values = m.instances[bid]
        info.part = part.lower()
        info.copies = sum(1 for v in m.instances.values() if v[0].upper() == part.upper())
        info.values = ", ".join(f"{k}={format_value(v)}" for k, v in values)
        info.title = f"{info.title}: {info.part}" + (f" ({info.values})" if info.values else "")
    return info


def line_note(p, info: ItemInfo, ln: StepLine) -> str:
    """What editing this line changes, in words (a tooltip)."""
    e = p.history[ln.row]
    m = _PART.match(e.text)
    if m:
        n = sum(1 for v in p.model.instances.values() if v[0].upper() == m.group(1).upper())
        return f"in the recipe of part {m.group(1).lower()}: changes all {n} placed cop{'y' if n == 1 else 'ies'}"
    if ln.depth:
        return f"inside history step {ln.row + 1} (a loop): changes every body that step makes"
    return f"history step {ln.row + 1}"


def param_edit(p, name: str, new: str) -> str | None:
    """The HIST, EDIT that gives a parameter a new value or expression (None: it
    is set inside a block and is edited in the History panel)."""
    from ..lang.expr import format_value as fv

    entry = p.entry_for_param(name)
    if entry is None or not new.strip():
        return None
    lines = p.history[entry - 1].text.splitlines()
    comment = lines[-1][len(strip_comment(lines[-1])):].strip()
    lines[-1] = f"{name} = {new.strip()}" + (f"    {comment}" if comment else "")
    return f"HIST, EDIT, {entry}, {fv(chr(10).join(lines))}"
