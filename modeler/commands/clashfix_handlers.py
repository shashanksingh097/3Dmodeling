"""CLASHFIX (PLAN item 79): fix an overlap CLASH found, by cutting it out of one part or moving the
part clear, with a preview first (``..., PREVIEW`` changes nothing, marks the result in the view and
says what would happen; it is not kept in the history)."""

from __future__ import annotations

import numpy as np
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.gp import gp_Trsf, gp_Vec

from ..geometry import meshbody as mb
from ..geometry import robust
from .processor import REGISTRY, Arg, BodyRef, CommandError, Processor, command

DIRS = {"X": (1, 0, 0), "-X": (-1, 0, 0), "Y": (0, 1, 0), "-Y": (0, -1, 0), "Z": (0, 0, 1), "-Z": (0, 0, -1)}


def overlap(sa, sb, p: Processor | None = None) -> float:
    """The volume two bodies have in common (0 when they only touch)."""
    if mb.is_mesh(sa) or mb.is_mesh(sb):
        from .mesh_handlers import default_deflection

        defl = default_deflection(p, sb if mb.is_mesh(sa) else sa) if p is not None else 0.1
        return mb.overlap_volume(sa, sb, defl)
    com = BRepAlgoAPI_Common(sa, sb)
    if not com.IsDone() or robust.is_empty(com.Shape()):
        return 0.0
    return max(0.0, robust.volume(com.Shape()))


def moved(shape, v) -> object:
    t = gp_Trsf()
    t.SetTranslation(gp_Vec(*map(float, v)))
    if mb.is_mesh(shape):
        return mb.transformed(shape, t)
    return BRepBuilderAPI_Transform(shape, t, True).Shape()


def _corners(shape) -> np.ndarray:
    from .queries import bbox

    b = bbox(shape)
    return np.array([[x, y, z] for x in (b[0], b[3]) for y in (b[1], b[4]) for z in (b[2], b[5])])


def _centre(shape) -> np.ndarray:
    return _corners(shape).mean(axis=0)


def _clear(sa, sb, clearance: float, tiny: float, p) -> bool:
    if overlap(sa, sb, p) > tiny:
        return False
    if clearance <= 0:
        return True
    from ..geometry import features as ft

    try:
        d, _, _ = ft.distance(sa, sb)
    except ft.FeatureError:
        return False
    return d >= clearance * (1 - 1e-6)


def move_clear(p: Processor, sa, sb, direction: str, clearance: float) -> tuple[np.ndarray, list[tuple[str, float]]]:
    """The shortest move of ``sa`` that clears ``sb`` (by ``clearance``): along the six axes and
    straight away from ``sb`` for AUTO, or along the given direction. Returns (move, tried)."""
    tiny = 1e-9 * max(1.0, robust.volume(sa) if not mb.is_mesh(sa) else mb.info(sa).volume)  # as CLASH
    ca, cb = _corners(sa), _corners(sb)
    if direction == "AUTO":
        away = _centre(sa) - _centre(sb)
        dirs = [(k, np.array(v, float)) for k, v in DIRS.items()]
        if np.linalg.norm(away) > 1e-9:
            dirs.append(("AWAY", away / np.linalg.norm(away)))
    else:
        dirs = [(direction, np.array(DIRS[direction], float))]
    # the move that surely clears along d: until the boxes no longer overlap along it
    cands = []
    for name, d in dirs:
        top = float((cb @ d).max() - (ca @ d).min()) + clearance + 1e-6
        cands.append((max(top, 0.0), name, d))
    cands.sort(key=lambda c: c[0])
    if _clear(sa, sb, clearance, tiny, p):
        return np.zeros(3), []
    best, tried = None, []
    for top, name, d in cands:
        if best is not None and top <= 0:
            continue
        lo, hi = 0.0, top
        for _ in range(22):  # halve the step until it is a millionth of the move
            mid = (lo + hi) / 2
            if _clear(moved(sa, mid * d), sb, clearance, tiny, p):
                hi = mid
            else:
                lo = mid
        for k in range(5):  # a round number when one in the last step clears (35, not 35.00001)
            c = round(hi, k)
            if lo < c <= hi and _clear(moved(sa, c * d), sb, clearance, tiny, p):
                hi = c
                break
        tried.append((name, hi))
        if best is None or hi < float(np.linalg.norm(best)):
            best = hi * d
    return best, tried


def _cut(p: Processor, a: int, sa, sb, clearance: float):
    tool = sb
    if clearance > 0:
        if mb.is_mesh(sb):
            raise CommandError("CLASHFIX: a clearance around a mesh body cannot be cut; give 0")
        from ..geometry import features as ft

        grown, _ = ft.offset_shape(sb, clearance)
        if grown is None or not robust.solids(grown):
            raise CommandError(f"CLASHFIX: body {sb} could not be grown by {clearance:g} for the clearance")
        tool = grown
    if mb.is_mesh(sa) or mb.is_mesh(tool):
        pa = mb.arrays(sa) if mb.is_mesh(sa) else mb.triangles_of(sa, 0.01 * robust.diagonal(sa))
        pb = mb.arrays(tool) if mb.is_mesh(tool) else mb.triangles_of(tool, 0.01 * robust.diagonal(tool))
        try:
            pts, t = mb.boolean("SUBTRACT", pa, [pb])
        except mb.MeshError as exc:
            raise CommandError(f"CLASHFIX: {exc}") from None
        from .handlers import _NoHistory

        return mb.make_shape(pts, t), _NoHistory()
    from .handlers import combine

    return combine(p, "CLASHFIX", BRepAlgoAPI_Cut, sa, [tool], a)


@command(
    "CLASHFIX",
    Arg("a", BodyRef, help="the part to change"),
    Arg("b", BodyRef, help="the part it clashes with (it stays as it is)"),
    Arg("how", str, "CUT", "CUT: cut b's shape out of a; MOVE: move a the shortest way clear of b"),
    Arg("clear", float, 0.0, "a gap to leave between them (0: they may touch)"),
    Arg("dir", str, "AUTO", "for MOVE: X, -X, Y, -Y, Z, -Z, or AUTO (the shortest of those and straight away)"),
    Arg("show", str, "DO", "DO, or PREVIEW to only show and say what it would do (not kept)"),
    help="Fix a clash: CLASHFIX, a, b, CUT cuts the overlap out of a (b stays); CLASHFIX, a, b, MOVE moves a the "
         "shortest way clear of b. Add PREVIEW at the end to see it first: the cut-away piece or the moved part "
         "is marked in the view and nothing changes. CLASH lists the clashes",
)
def clashfix(p: Processor, a, b, how, clear, dir, show):  # noqa: A002 - the argument's name in the command
    m = p.model
    marks = getattr(p.view, "set_marks", None) if p.view else None
    if how not in ("CUT", "MOVE"):
        raise CommandError("CLASHFIX: how is CUT or MOVE")
    if dir not in ("AUTO", *DIRS):
        raise CommandError("CLASHFIX: the direction is AUTO, X, -X, Y, -Y, Z or -Z")
    if show not in ("DO", "PREVIEW"):
        raise CommandError("CLASHFIX: the last word is DO or PREVIEW")
    if clear < 0:
        raise CommandError("CLASHFIX: the clearance cannot be negative")
    if a == b:
        raise CommandError("CLASHFIX: give two different bodies")
    sa, sb = m.body(a).shape, m.body(b).shape
    for bid, s in ((a, sa), (b, sb)):
        if not (robust.solids(s) or (mb.is_mesh(s) and mb.info(s).closed)):
            raise CommandError(f"CLASHFIX: body {bid} is not a solid")
    preview = show == "PREVIEW"
    units = m.units.lower()
    vol = overlap(sa, sb, p)
    if vol <= 1e-9 * max(1.0, robust.volume(sa) if not mb.is_mesh(sa) else 1.0) and clear <= 0:
        if marks:
            marks([])
        return f"CLASHFIX: bodies {a} and {b} do not overlap; nothing to fix"
    d = {"a": a, "b": b, "how": how, "clearance": clear, "overlap": round(vol, 6), "preview": preview}
    if how == "CUT":
        shape, maker = _cut(p, a, sa, sb, clear)
        removed = (robust.volume(sa) - robust.volume(shape)) if not mb.is_mesh(shape) else \
            mb.info(sa).volume - mb.info(shape).volume if mb.is_mesh(sa) else vol
        d["removed"] = round(float(removed), 6)
        words = f"cut {removed:.6g} {units}3 out of body {a} where body {b} is" + (
            f" (with {clear:g} clearance)" if clear else "")
        if preview:
            if marks and not mb.is_mesh(sa) and not mb.is_mesh(sb):
                com = BRepAlgoAPI_Common(sa, sb if not clear else _cut_tool(sb, clear))
                marks([com.Shape()] if com.IsDone() else [])
            p.give_report("CLASHFIX", d)
            return f"CLASHFIX preview: would {words}; marked in the view. Run it without PREVIEW to do it"
        body = m.replace([a], shape, maker, same_id=True)
    else:
        move, tried = move_clear(p, sa, sb, dir, clear)
        if move is None:
            raise CommandError(f"CLASHFIX: no move along {dir} clears body {b}")
        d["move"] = [round(float(x), 6) for x in move]
        d["tried"] = {k: round(v, 6) for k, v in tried}
        far = float(np.linalg.norm(move))
        words = (f"move body {a} by ({', '.join(f'{x:.4g}' for x in move)}), {far:.4g} {units}, clear of body {b}"
                 + (f" with {clear:g} clearance" if clear else ""))
        if preview:
            if marks:
                marks([moved(sa, move)])
            p.give_report("CLASHFIX", d)
            others = ", ".join(f"{k} {v:.4g}" for k, v in tried if k)
            return f"CLASHFIX preview: would {words} (moves tried: {others}); marked in the view. Run it " \
                   "without PREVIEW to do it"
        from .handlers import _transform

        t = gp_Trsf()
        t.SetTranslation(gp_Vec(*map(float, move)))
        _transform(p, a, t, "moved", copy=False)
        body = m.body(a)
    if marks:
        marks([])
    p.give_report("CLASHFIX", d)
    name = "" if body.name == f"body{body.id}" else f" '{body.name}'"
    return f"CLASHFIX: {words}" + (f" -> body {body.id}{name}" if how == "CUT" else "")


def _cut_tool(sb, clear):
    from ..geometry import features as ft

    grown, _ = ft.offset_shape(sb, clear)
    return grown if grown is not None else sb


REGISTRY["CLASHFIX"].query_word = "PREVIEW"
