"""GRAVITY: does the assembly stand up, and is every part held? (geometry/gravity.py)"""

from __future__ import annotations

import re

import numpy as np

from ..geometry import gravity as gv
from .processor import REGISTRY, Arg, CommandError, Processor, Raw, Text, command


def _bodies(p: Processor, text: str) -> list[int]:
    words = [w for w in re.split(r"[\s;]+", text.strip().strip('"')) if w]
    return [p._body_ref(REGISTRY["GRAVITY"], w) for w in words]


def _name(p: Processor, bid) -> str:
    if bid == "floor":
        return "the floor"
    b = p.model.bodies[bid]
    return f"{b.name} ({bid})" if b.name and b.name != f"body{bid}" else f"body {bid}"


@command(
    "GRAVITY",
    Arg("ground", Raw, "FLOOR", "what stays put: FLOOR (a floor under the lowest part) or a body; OFF ends the "
                                "marks"),
    Arg("fastened", Text, "", "bodies bolted, glued or welded to what they touch (\"3 7\" or names)"),
    Arg("dx", float, 0.0), Arg("dy", float, 0.0), Arg("dz", float, -1.0, "gravity's direction (default -Z)"),
    Arg("gap", float, 0.0, "parts closer than this but not touching are reported as a gap (0: 0.5% of the "
                           "assembly's size)"),
    logged=False,
    help="Will the assembly stand up? Every shown solid is checked: floating parts (not connected to the "
         "ground), parts resting on others (and how far their centre of mass is from tipping off), parts held "
         "only at their sides, small gaps, overlaps, and the whole on the floor: GRAVITY · GRAVITY, base · "
         "GRAVITY, FLOOR, \"bolt_1 bolt_2\". Problem parts are marked in the view; GRAVITY, OFF clears them",
)
def gravity(p: Processor, ground, fastened, dx, dy, dz, gap):
    from ..geometry import contact as ct
    from ..geometry import meshbody as mb
    from ..geometry import robust

    m = p.model
    marks = getattr(p.view, "set_marks", None) if p.view else None
    word = ground.strip() or "FLOOR"
    if word.upper() == "OFF":
        if marks:
            marks([])
        return "gravity marks cleared"
    down = np.array([dx, dy, dz], float)
    if np.linalg.norm(down) < 1e-12:
        raise CommandError("GRAVITY: the direction is zero")
    down /= np.linalg.norm(down)
    if gap < 0:
        raise CommandError("GRAVITY: the gap cannot be negative")
    ids = [b for b in m.shown_ids() if not mb.is_mesh(m.bodies[b].shape) and robust.solids(m.bodies[b].shape)]
    ground_id = None if word.upper() == "FLOOR" else p._body_ref(REGISTRY["GRAVITY"], word)
    if ground_id is not None and ground_id not in ids:
        raise CommandError(f"GRAVITY: {_name(p, ground_id)} is not a shown solid")
    held = set(_bodies(p, fastened))
    if len(ids) < (1 if ground_id is None else 2):
        raise CommandError("GRAVITY: there are no parts to check (it looks at the shown solid bodies)")
    parts = []
    for b in ids:
        dens = m.density(b) or 1000.0
        mass, c = gv.mass_centre(m.bodies[b].shape, dens * 1e-9)  # kg from mm3
        parts.append(gv.Part(b, m.bodies[b].shape, mass, c, ground=b == ground_id, fastened=b in held))
    shapes = [pt.shape for pt in parts]
    tol = ct.default_tol(*shapes)
    size = ct.size_of(*(ct.box_of(s) for s in shapes))
    near = gap or 0.005 * size
    if ground_id is None:
        slab, _level = gv.floor_block(shapes, down)
        parts.append(gv.Part("floor", slab, 0.0, np.zeros(3), ground=True))
    res = gv.check(parts, down, tol, near)
    names = [_name(p, pt.key) for pt in parts]
    lines = [f"GRAVITY: {len(ids)} part{'s' if len(ids) != 1 else ''}, gravity along "
             f"({', '.join(f'{v:.3g}' for v in down)}), standing on {names[-1] if ground_id is None else names[[pt.key for pt in parts].index(ground_id)]}"]
    bad: list[int] = []
    for v in res.verdicts:
        pt = parts[v.part]
        if pt.ground:
            continue
        who = ", ".join(names[k] for k in v.on)
        if v.state == "floats":
            lines.append(f"  {names[v.part]}: FLOATS, not connected to the ground: it would fall")
            bad.append(pt.key)
        elif v.state == "sides":
            lines.append(f"  {names[v.part]}: held only at its sides by {who}, nothing under it: it needs a "
                         f"fastener (or list it as fastened)")
            bad.append(pt.key)
        elif v.state == "tips":
            lines.append(f"  {names[v.part]}: TIPS off {who}: its centre of mass is {abs(v.margin):.3g} past "
                         f"the edge of what holds it" if v.margin < 0 else
                         f"  {names[v.part]}: balanced on an edge or a point of {who}: it would tip")
            bad.append(pt.key)
        elif v.state == "held":
            lines.append(f"  {names[v.part]}: held ({'fastened' if pt.fastened else 'pressed into ' + who})")
        else:
            lines.append(f"  {names[v.part]}: rests on {who}, its centre of mass {v.margin:.3g} inside the edge")
    for ln in res.links:
        a, b = names[ln.a], names[ln.b]
        if ln.state == "gap":
            lines.append(f"  gap: {a} and {b} are {ln.distance:.3g} apart: were they meant to touch?")
        elif ln.state == "overlap":
            lines.append(f"  overlap: {a} and {b} cut into each other (a press fit, or a mistake?)")
    if res.whole_margin is not None:
        if res.whole_margin > tol:
            lines.append(f"on the floor: it stands; the centre of mass is {res.whole_margin:.3g} inside the "
                         f"footprint, so it can lean {res.whole_angle:.3g}° before it tips")
        else:
            lines.append(f"on the floor: it TIPS over; the centre of mass is {abs(res.whole_margin):.3g} "
                         f"outside the footprint")
            bad += [pt.key for pt in parts if not pt.ground]
    elif ground_id is None:
        lines.append("on the floor: nothing touches the floor")
    keys = list(dict.fromkeys(k for k in bad if k != "floor"))
    lines.append("everything is held" if not keys and (res.whole_margin is None or res.whole_margin > tol)
                 else f"{len(keys)} part{'s' if len(keys) != 1 else ''} to look at"
                 + (" (marked in the view; GRAVITY, OFF clears the marks)" if marks else ""))
    if marks:
        marks([m.bodies[k].shape for k in keys])
    return "\n".join(lines)
