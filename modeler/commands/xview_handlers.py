"""Exploded views (PLAN item 24): XSTEP records how parts move apart, XSHOW shows it.

An exploded view is a named list of steps, each moving some bodies by a vector:

    XSTEP, apart, lid, 0, 0, 40            ! step 1: the lid comes up
    XSTEP, apart, "screw_1 screw_2", 0, 0, 70
    XSHOW, apart                           ! show it, with trail lines from each part to its place
    XSHOW, apart, 0.5                      ! half way
    XSHOW                                  ! back together

XSTEP is a history step (the view is saved with the project); it does not move anything.
XSHOW is not a history step: it moves the bodies for the eye (and for pictures), adds the
trails as thin lines, and the model goes back as it was before the next command that changes
anything (or before UNDO, a rebuild, SAVE ...). A body in several steps moves by their sum.
"""

from __future__ import annotations

import re

from .processor import Arg, CommandError, Processor, Text, command

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _body_list(p: Processor, what: str, text: str) -> list[int]:
    from .processor import REGISTRY

    words = [w for w in re.split(r"[\s;]+", text.strip().strip('"')) if w]
    if not words:
        raise CommandError(f"{what}: name the bodies that move (IDs or names, with spaces between, or SEL)")
    out: list[int] = []
    for w in words:
        if w.upper() == "SEL":
            m = p.model
            if m.selection_kind != "BODY" or not m.selection:
                raise CommandError(f"{what}: SEL stands for the selected bodies, and no bodies are selected")
            out += [b for b in m.selection if b not in out]
            continue
        b = p._body_ref(REGISTRY["XSTEP"], w)
        if b not in p.model.bodies:
            raise CommandError(f"{what}: there is no body {w}")
        if b not in out:
            out.append(b)
    return out


@command(
    "XSTEP",
    Arg("view", Text, help="the exploded view's name"),
    Arg("bodies", Text, help="the bodies that move in this step: IDs or names with spaces between, or SEL"),
    Arg("dx", float, 0.0), Arg("dy", float, 0.0), Arg("dz", float, 0.0),
    help="Add a step to an exploded view: XSTEP, apart, lid, 0, 0, 40 moves the lid up by 40 in view APART "
         "(nothing moves now: XSHOW shows the view) · XSTEP, apart, CLEAR forgets the view",
)
def xstep(p: Processor, view, bodies, dx, dy, dz):
    name = view.strip().strip('"')
    if not _NAME.match(name):
        raise CommandError(f"XSTEP: {name!r} is not a name (letters, digits and _, starting with a letter)")
    key = name.upper()
    views = p.model.xviews
    if bodies.strip().upper() == "CLEAR":
        if key not in views:
            raise CommandError(f"XSTEP: there is no exploded view {key}")
        del views[key]
        return f"exploded view {key} forgotten"
    if dx == dy == dz == 0:
        raise CommandError("XSTEP: the step does not move anything (give dx, dy, dz)")
    ids = _body_list(p, "XSTEP", bodies)
    steps = list(views.get(key, []))
    steps.append((tuple(ids), (float(dx), float(dy), float(dz))))
    views[key] = steps
    who = ", ".join(_label(p, b) for b in ids)
    return f"exploded view {key}, step {len(steps)}: {who} by ({dx:g}, {dy:g}, {dz:g})"


def _label(p: Processor, b: int) -> str:
    body = p.model.bodies.get(b)
    if body is None:
        return str(b)
    return str(b) if body.name == f"body{b}" else f"{b} '{body.name}'"


def _centre(shape) -> tuple[float, float, float]:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    (getattr(BRepBndLib, "Add_s", None) or BRepBndLib.Add)(shape, box, True)
    a, b = box.CornerMin(), box.CornerMax()
    return ((a.X() + b.X()) / 2, (a.Y() + b.Y()) / 2, (a.Z() + b.Z()) / 2)


def offsets(steps, factor: float = 1.0) -> dict[int, tuple[float, float, float]]:
    """Each body's total move in a view: the sum of its steps, times ``factor``."""
    out: dict[int, list[float]] = {}
    for ids, v in steps:
        for b in ids:
            acc = out.setdefault(b, [0.0, 0.0, 0.0])
            for i in range(3):
                acc[i] += v[i] * factor
    return {b: tuple(v) for b, v in out.items()}


def trail_points(steps, start: tuple[float, float, float], body: int, factor: float):
    """The corner points of a body's trail: its centre, then after each of its steps in turn."""
    pts = [tuple(start)]
    cur = list(start)
    for ids, v in steps:
        if body in ids:
            cur = [cur[i] + v[i] * factor for i in range(3)]
            pts.append(tuple(cur))
    return pts


@command(
    "XSHOW",
    Arg("view", Text, "", "an exploded view (none: put the parts back; LIST: the views)"),
    Arg("factor", float, 1.0, "how far: 1 the whole way, 0.5 half way"),
    Arg("trails", str, "YES", "YES: thin lines from each part back to its place; NO"),
    session=True,
    help="Show an exploded view: XSHOW, apart moves the parts apart along the view's steps with trail lines "
         "(not a history step: the parts go back before the next command) · XSHOW, apart, 0.5 half way · "
         "XSHOW puts them back · XSHOW, LIST lists the views",
)
def xshow(p: Processor, view, factor, trails):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon
    from OCP.gp import gp_Pnt, gp_Trsf, gp_Vec

    from .handlers import _transform

    name = view.strip().strip('"').upper()
    was = p.unexplode()
    m = p.model
    if not name:
        return "the parts are back in place" if was else "no exploded view is shown"
    if name == "LIST":
        if not m.xviews:
            return "no exploded views (make one with XSTEP)"
        return "\n".join(f"{k}: {len(v)} step{'s' if len(v) != 1 else ''}, "
                         f"{len(offsets(v))} bod{'ies' if len(offsets(v)) != 1 else 'y'}" for k, v in m.xviews.items())
    if name not in m.xviews:
        known = ", ".join(m.xviews) or "none yet; make one with XSTEP"
        raise CommandError(f"XSHOW: there is no exploded view {name} (views: {known})")
    if trails not in ("YES", "NO"):
        raise CommandError("XSHOW: trails is YES or NO")
    if not 0 <= factor <= 10:
        raise CommandError("XSHOW: the factor is 0 to 10")
    steps = m.xviews[name]
    moves = offsets(steps, factor)
    missing = [b for b in moves if b not in m.bodies]
    snap = m.snapshot()
    try:
        starts = {}
        for b, v in moves.items():
            if b in missing:
                continue
            starts[b] = _centre(m.body(b).shape)
            t = gp_Trsf()
            t.SetTranslation(gp_Vec(*v))
            _transform(p, b, t, "XSHOW", copy=False)
        lines = 0
        if trails == "YES" and factor > 0:
            for b, c in starts.items():
                pts = trail_points(steps, c, b, factor)
                if len(pts) < 2:
                    continue
                poly = BRepBuilderAPI_MakePolygon()
                for q in pts:
                    poly.Add(gp_Pnt(*q))
                body = m.add_body(poly.Wire(), name=f"trail_{b}")
                m.set_style(body.id, color=(0.45, 0.45, 0.45))
                lines += 1
    except Exception:
        m.restore(snap)
        raise
    p.exploded = snap
    msg = f"exploded view {name}" + (f" x{factor:g}" if factor != 1 else "") + \
          f": {len(starts)} bod{'ies' if len(starts) != 1 else 'y'} moved" + (f", {lines} trails" if lines else "")
    if missing:
        msg += f"; bodies {', '.join(map(str, missing))} are gone (left out)"
    return msg + ". The parts go back before the next command (or XSHOW alone)"
