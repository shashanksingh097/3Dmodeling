"""What the Features toolbar sends: command text built from the selection.

Pure functions over the processor (no Qt), so they are tested headless.
Each returns the command lines to run, or raises ``NeedInput`` with a
message for the status bar when the selection does not fit.
"""

from __future__ import annotations

from ..commands import Processor
from ..lang.expr import fmt_num


class NeedInput(Exception):
    pass


def _r(v: float) -> str:
    return fmt_num(round(v, 6) + 0.0)


def free_name(p: Processor, prefix: str) -> str:
    taken = {k.upper() for k in p.model.datums} | {b.name.upper() for b in p.model.bodies.values()} | set(p.params)
    taken |= {k.upper() for k in p.model.sketches} | set(p.parts)
    i = 1
    while f"{prefix}{i}".upper() in taken:
        i += 1
    return f"{prefix}{i}"


def _flat_face(p: Processor, what: str) -> int:
    m = p.model
    if m.selection_kind != "FACE" or len(m.selection) != 1:
        raise NeedInput(f"{what}: pick one flat face first")
    from ..geometry.features import face_plane

    gid = m.selection[0]
    if face_plane(m.entity_shape("FACE", gid)) is None:
        raise NeedInput(f"{what}: face {gid} is curved; pick a flat face")
    return gid


def plane_on_face(p: Processor) -> list[str]:
    gid = _flat_face(p, "Plane")
    return [f"PLANE, {free_name(p, 'P')}, FACE, {gid}"]


def workplane_on_face(p: Processor) -> list[str]:
    if p.model.workplane is not None:
        return ["WORKPLANE, OFF"]
    gid = _flat_face(p, "Work plane")
    name = free_name(p, "WP")
    return [f"PLANE, {name}, FACE, {gid}", f"WORKPLANE, {name}"]


def hole_on_face(p: Processor, d: float) -> list[str]:
    """A through hole at the middle of the picked flat face."""
    gid = _flat_face(p, "Hole")
    m = p.model
    from ..commands.queries import centre

    bid = m.entity_owner("FACE", gid)[0]
    c = centre("FACE", m.entity_shape("FACE", gid))
    body = m.bodies[bid].name if not m.bodies[bid].name.startswith("body") else str(bid)
    if m.workplane is not None:  # HOLE reads its point in the work plane
        c = m.workplane.local(c)
    return [f"HOLE, {body}, {_r(c[0])}, {_r(c[1])}, {_r(c[2])}, {_r(d)}"]


def two_selected(p: Processor, what: str) -> list[str]:
    if len(p.model.selection) != 2:
        raise NeedInput(f"{what}: select two things first (click one, Ctrl+click the other)")
    return [what]


def faces_selected(p: Processor, what: str, value: float | None) -> list[str]:
    m = p.model
    if what == "SHELL" and m.selection_kind == "BODY" and m.selection:
        return [f"SHELL, {_r(value)}"]
    if m.selection_kind != "FACE" or not m.selection:
        raise NeedInput(f"{what}: select faces first" + (" (or bodies, for a closed hollow part)" if what == "SHELL" else ""))
    return [what if value is None else f"{what}, {_r(value)}"]


def section_toggle(p: Processor) -> list[str]:
    if p.section is not None:
        return ["SECTION, OFF"]
    planes = [d for d in p.model.datums.values() if d.kind == "PLANE"]
    return [f"SECTION, {planes[-1].name if planes else 'XY'}"]
