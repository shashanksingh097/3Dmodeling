"""Editing in a cross-section (PLAN item 96): SECTIONEDIT.

``SECTIONEDIT, plane [, offset [, b]]`` cuts the view open at the plane (like SECTION) and lists the
lines of the cut, each with the face of the solid behind it. In the 3D view a click on a cut line
picks that face and the drag handles (item 68) pull it, with a typed value, so a change in the
section is an ordinary ``PICK, FACE, id`` and ``PUSHPULL, d`` in the history. "Draw on the cut"
starts a sketch on the plane (``SKETCH``), and EXTRUDE ... ADD / CUT adds or removes material.
``SECTIONEDIT, OFF`` ends it. Not kept in the history: it is a view and a list, like SECTION.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core import datum as dt
from ..geometry import meshbody as mb
from ..geometry import robust
from ..geometry import section_edit as se
from ..lang.expr import fmt_num
from .feature_handlers import plane_ref
from .processor import Arg, BodyRef, CommandError, Processor, Raw, command


@dataclass
class SectionEdit:
    plane: object  # core.datums.Datum, moved by the offset
    base: str  # the plane as typed (XY, a datum name)
    offset: float
    bodies: list[int]
    lines: dict[int, list] = field(default_factory=dict)  # body id -> [geometry.section_edit.CutLine]

    def all_lines(self) -> list[tuple[int, object]]:
        return [(b, ln) for b in self.bodies for ln in self.lines.get(b, [])]


def _n(v: float) -> str:
    return fmt_num(round(v, 6) + 0.0)


def _face_id(p: Processor, bid: int):
    def gid(face) -> int:
        try:
            return p.model.find_entity(bid, "FACE", face)
        except Exception:
            return 0
    return gid


def cut(model, d, bodies: list[int]) -> dict[int, list]:
    """body id -> its cut lines, for the bodies the plane cuts."""
    out = {}
    for bid in bodies:
        shape = model.body(bid).shape
        if mb.is_mesh(shape) or not robust.solids(shape):
            continue
        try:
            lines = se.cut_lines(shape, d.origin, d.z, d.x)
        except se.SectionError:
            continue
        if lines:
            out[bid] = lines
    return out


def draw_commands(state: SectionEdit, sketch: str) -> list[str]:
    """The steps that start a sketch on the section plane (a datum plane first when it is moved)."""
    if not state.offset:
        return [f"SKETCH, {sketch}, {state.base}"]
    plane = f"{sketch}_plane"
    base = state.base.upper()
    first = (f"PLANE, {plane}, {base}, {_n(state.offset)}" if base in dt.BASE_PLANES
             else f"PLANE, {plane}, OFFSET, {state.base}, {_n(state.offset)}")
    return [first, f"SKETCH, {sketch}, {plane}"]


def free_sketch_name(p: Processor) -> str:
    k = 1
    while f"CUT{k}" in p.model.sketches or f"CUT{k}_PLANE" in {n.upper() for n in p.model.datums}:
        k += 1
    return f"cut{k}"


def report(p: Processor, state: SectionEdit) -> dict:
    d = state.plane
    r = lambda v: [round(c, 6) + 0.0 for c in v]
    sketch = free_sketch_name(p)
    return {"plane": state.base, "offset": state.offset, "origin": r(d.origin), "normal": r(d.z),
            "bodies": [{"body": b, "lines": se.lines_as_data(state.lines[b], _face_id(p, b))}
                       for b in state.bodies if b in state.lines],
            "pull": "PICK, FACE, <face>, then PUSHPULL, d (d > 0 moves the line along push)",
            "draw": draw_commands(state, sketch)}


@command(
    "SECTIONEDIT",
    Arg("plane", Raw, "OFF", "a datum plane, XY/YZ/ZX, or OFF"),
    Arg("offset", float, 0.0, "move the plane this far along its normal"),
    Arg("b", BodyRef, 0, "only this body (default: every body shown)"),
    logged=False,
    help="Edit a part in a cross-section: SECTIONEDIT, XY, 5 cuts the view open at the plane and lists the "
         "lines of the cut, each with the face behind it. Click a line in the 3D view and drag its arrow (or "
         "type a value) to move that face: the history gets PICK, FACE, id and PUSHPULL, d. \"Draw on the cut\" "
         "starts a sketch on the plane; EXTRUDE, sketch, d, ADD or CUT then adds or removes material. "
         "SECTIONEDIT, OFF ends it. Not kept in the history.",
)
def sectionedit(p: Processor, plane, offset, b):
    word = plane.strip()
    hook = getattr(p.view, "set_section_edit", None) if p.view else None
    if not word or word.upper() == "OFF":
        p.section_edit = None
        p.section = None
        sec_hook = getattr(p.view, "set_section", None) if p.view else None
        if sec_hook:
            sec_hook(None)
        if hook:
            hook(None)
        return "section editing off"
    d = plane_ref(p, word, "SECTIONEDIT")
    if offset:
        d = dt.Datum("PLANE", d.name, dt.add(d.origin, dt.mul(d.z, offset)), d.z, d.x)
    bodies = [b] if b else list(p.model.shown_ids())
    if b:
        p.model.body(b)
    state = SectionEdit(d, word, offset, bodies)
    state.lines = cut(p.model, d, bodies)
    if not state.lines:
        raise CommandError(f"SECTIONEDIT: the plane {word}" + (f" moved {_n(offset)}" if offset else "")
                           + " cuts no solid" + (f" (body {b})" if b else ""))
    state.bodies = [x for x in bodies if x in state.lines]
    p.section_edit = state
    p.section = [(d, "BELOW")]
    sec_hook = getattr(p.view, "set_section", None) if p.view else None
    if sec_hook:
        sec_hook(p.section)
    if hook:
        hook(state)
    data = report(p, state)
    p.give_report("SECTIONEDIT", data)
    out = [f"section editing at plane {word}" + (f" moved {_n(offset)}" if offset else "")
           + f": {sum(len(x['lines']) for x in data['bodies'])} lines"]
    for bd in data["bodies"]:
        out.append(f"  body {bd['body']}:")
        for ln in bd["lines"]:
            extra = f", radius {_n(ln['radius'])}" if ln["kind"] == "arc" else ""
            push = (" push (" + ", ".join(_n(c) for c in ln["push"]) + ")") if "push" in ln else ""
            out.append(f"    line {ln['line']}: face {ln['face']}, {ln['kind']} {_n(ln['length'])} long{extra},{push}")
    out.append("  click a line and drag its arrow to move the face (PICK, FACE, id then PUSHPULL, d); "
               f"draw on the cut: {'; '.join(data['draw'])}")
    return "\n".join(out)


def refresh(model, state: SectionEdit) -> SectionEdit:
    """Cut again after the model changed (a PUSHPULL, an undo, a body made anew under a new ID)."""
    alive = [b for b in state.bodies if b in model.bodies] or list(model.shown_ids())
    state.lines = cut(model, state.plane, alive)
    state.bodies = [b for b in alive if b in state.lines]
    return state
