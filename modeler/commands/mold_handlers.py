"""PARTING and MOLD: mould tools (geometry/molding.py)."""

from __future__ import annotations

from ..geometry import analysis as an
from ..geometry import molding as mo
from ..geometry import robust
from ..lang.expr import fmt_num
from .processor import Arg, BodyRef, CommandError, Processor, command


def _ids(p: Processor, bid: int, part: mo.Parting, which) -> list[int]:
    ids = an.face_ids(p.model, bid, part.mesh)
    return sorted({ids[f.index] for f in part.faces if which(f) and ids[f.index] is not None})


def _list(ids: list[int], most: int = 12) -> str:
    s = ", ".join(str(i) for i in ids[:most])
    return s + (f" and {len(ids) - most} more" if len(ids) > most else "")


@command(
    "PARTING",
    Arg("b", BodyRef, help="a solid part"),
    Arg("dx", float, 0.0, "the pull direction: the mould opens along it (default +Z)"), Arg("dy", float, 0.0),
    Arg("dz", float, 1.0),
    Arg("angle", float, 1.0, "the least draft angle in degrees: steeper faces need draft"),
    logged=False,
    help="Which faces come out of which half of a mould pulled along (dx,dy,dz): PARTING, cover · PARTING, "
         "cover, 1,0,0, 2. It lists the faces that need draft, undercuts (faces whose way out is blocked by the "
         "part itself) and the parting line, colours the part (green and blue come out of the two halves, red "
         "is too steep) and marks the parting line. ANALYZE, OFF ends the colours.",
)
def parting(p: Processor, b, dx, dy, dz, angle):
    from .analysis_handlers import Analysis

    if not 0 <= angle < 90:
        raise CommandError("PARTING: the draft angle is from 0 to 90 degrees")
    shape = p.model.body(b).shape
    try:
        part = mo.parting(shape, (dx, dy, dz), angle)
    except (mo.MoldError, ValueError) as exc:
        raise CommandError(f"PARTING: {exc}") from None
    total = sum(f.area for f in part.faces) or 1.0
    pct = lambda side: 100.0 * part.area(side) / total  # noqa: E731
    lines = [f"PARTING body {b}, pulled along {mo.angle_text(part.direction)} with at least {fmt_num(angle)}° of "
             f"draft: {pct('+'):.0f}% of the area comes out with the + half, {pct('-'):.0f}% with the - half, "
             f"{pct('steep'):.0f}% is too steep, {pct('both'):.0f}% is on faces the parting line crosses"]
    steep = _ids(p, b, part, lambda f: f.side == "steep")
    if steep:
        lines.append(f"  needs draft: faces {_list(steep)} (DRAFT, {fmt_num(max(angle, 1.0))} on them)")
    under = _ids(p, b, part, lambda f: f.undercut > 1e-3 * f.area)
    if under:
        lines.append(f"  UNDERCUTS: faces {_list(under)} are blocked by the part on their way out: they need a side "
                     f"action, or another pull direction")
    split = _ids(p, b, part, lambda f: f.side == "both")
    if split:
        lines.append(f"  the parting line crosses faces {_list(split)} (SPLIT them there for a clean line)")
    if part.edges:
        lo, hi = part.levels
        where = (f"flat, at {fmt_num(round(lo, 6))} along the pull" if part.flat else
                 f"stepped, from {fmt_num(round(lo, 6))} to {fmt_num(round(hi, 6))} along the pull")
        lines.append(f"  parting line: {len(part.edges)} edge{'s' if len(part.edges) != 1 else ''}, {where}")
    elif not split:
        lines.append("  no parting line found: every face comes out on one side")
    ok = not steep and not under
    lines.append("ready for a two-part mould" if ok else "fix the faces above before making the mould")
    p.analysis = Analysis(b, "DRAFT", tuple(float(x) for x in part.direction), angle)
    hook = getattr(p.view, "show_analysis", None) if p.view else None
    if hook:
        hook(p.analysis)
    marks = getattr(p.view, "set_marks", None) if p.view else None
    if marks:
        marks(list(part.edges))
    return "\n".join(lines)


@command(
    "MOLD",
    Arg("b", BodyRef, help="a solid part"),
    Arg("margin", float, 0.0, "the wall round the part (0: a fifth of the part's size)"),
    Arg("shrink", float, 0.0, "shrink allowance in percent: the cavity is this much bigger (ABS about 0.5)"),
    Arg("dx", float, 0.0, "the pull direction (default +Z)"), Arg("dy", float, 0.0), Arg("dz", float, 1.0),
    Arg("level", str, "", "where to split, along the pull (default: a flat parting line, else the widest place)"),
    help="The two halves of a mould for a part: a block round it with the part's shape inside, split across "
         "the pull direction: MOLD, cover · MOLD, cover, 8, 0.5 · MOLD, cover, 8, 0.5, 0,0,1, 12.5. The halves "
         "are new bodies named after the part (cover_top, cover_bottom); the part stays. Check it first with "
         "PARTING.",
)
def mold(p: Processor, b, margin, shrink, dx, dy, dz, level):
    from .handlers import _added

    m = p.model
    body = m.body(b)
    shape = body.shape
    if not robust.solids(shape):
        raise CommandError(f"MOLD: body {b} is not a solid")
    if margin < 0:
        raise CommandError("MOLD: the margin cannot be negative")
    margin = margin or 0.2 * robust.diagonal(shape) / 1.7320508
    try:
        part = mo.parting(shape, (dx, dy, dz), 0.0, undercuts=False)
        if level.strip():
            try:
                lv, why = float(p.evaluate(level)), "where asked"
            except Exception:
                raise CommandError(f"MOLD: the level must be a number, got {level!r}") from None
        else:
            lv, why = mo.default_level(shape, part)
        top, bottom = mo.halves(shape, part.direction, lv, margin, shrink)
    except mo.MoldError as exc:
        raise CommandError(f"MOLD: {exc}") from None
    base = body.name if body.name != f"body{b}" else f"part{b}"
    msgs = []
    for shp, half in ((top, "top"), (bottom, "bottom")):
        new = m.add_body(shp)
        name = f"{base}_{half}"
        k = 2
        while m.body_by_name(name) is not None or name.upper() in p.params:
            name = f"{base}_{half}{k}"
            k += 1
        m.rename(new.id, name)
        msgs.append(_added(p, m.body(new.id), f"MOLD {half} half"))
    head = (f"MOLD of body {b}: split at {fmt_num(round(lv, 6))} along {mo.angle_text(part.direction)} ({why}), "
            f"wall {fmt_num(round(margin, 4))}" + (f", shrink {fmt_num(shrink)}%" if shrink else ""))
    return "\n".join([head, *msgs])
