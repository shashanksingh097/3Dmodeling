"""Sheet metal: SHEET (a plate from a sketch), FLANGE (bend a wall up or down along an edge) and
UNFOLD (the flat pattern, as a body and as a DXF for cutting). See geometry/sheetmetal.py.

A sheet metal body remembers its plane, thickness, bend radius, K-factor and
its flanges, so UNFOLD knows how to lay it flat. HOLE, SUBTRACT and the like
keep that record (holes through the plate show in the flat pattern).
"""

from __future__ import annotations

import dataclasses
import os

import numpy as np

from ..geometry import robust
from ..geometry import sheetmetal as smt
from ..lang.expr import fmt_num
from .processor import Arg, BodyRef, CommandError, Path, Processor, Text, command


def _sheet(p: Processor, bid: int, what: str) -> smt.Sheet:
    p.model.body(bid)
    sh = p.model.sheets.get(bid)
    if sh is None:
        raise CommandError(f"{what}: body {bid} is not sheet metal (SHEET makes a sheet metal plate from a sketch)")
    return sh


@command(
    "SHEET",
    Arg("sketch", Text, help="a sketch whose closed profile is the plate's outline"),
    Arg("t", help="the sheet thickness"),
    Arg("r", float, -1.0, "the inside bend radius for its flanges (default: the thickness)"),
    Arg("k", float, smt.K_FACTOR, "the K-factor: where the neutral line sits in a bend, 0..1 of the thickness"),
    help="Start a sheet metal part: a plate of thickness t cut from a sketch's outline (holes in the sketch are "
         "holes in the plate): SHEET, s1, 2 · SHEET, s1, 1.5, 3 (bend radius 3) · SHEET, s1, 2, 2, 0.4 (K-factor "
         "0.4). Then FLANGE bends walls along its edges and UNFOLD gives the flat pattern",
)
def sheet(p: Processor, sketch, t, r, k):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.gp import gp_Vec

    from .handlers import _added, _compound
    from .sketch_handlers import _mark_used, _profile

    if t <= 0:
        raise CommandError("SHEET: the thickness must be more than 0")
    if r < 0:
        r = t
    if not 0 <= k <= 1:
        raise CommandError("SHEET: the K-factor is between 0 and 1 (usually 0.3 to 0.5)")
    sk, faces, note = _profile(p, sketch, "SHEET")
    fr = sk.frame
    solids = []
    for f in faces:
        prism = BRepPrimAPI_MakePrism(f, gp_Vec(*(c * t for c in fr.z)))
        prism.Build()
        if not prism.IsDone():
            raise CommandError(f"SHEET: the kernel could not make a plate of sketch {sk.name}")
        solids.append(prism.Shape())
    shape = solids[0] if len(solids) == 1 else _compound(solids)
    if not robust.checked_ok(shape, True):
        raise CommandError(f"SHEET: the plate made from sketch {sk.name} is not a valid solid")
    m = p.model
    body = m.add_body(shape)
    m.sheets[body.id] = smt.Sheet(tuple(fr.origin), tuple(fr.x), tuple(fr.y), tuple(fr.z), float(t), float(r),
                                  float(k))
    _mark_used(p, sk, f"SHEET body {body.id}")
    return _added(p, body, f"SHEET {sk.name}, thickness {fmt_num(t)}, bend radius {fmt_num(r)}, K {k:g}{note}")


def _line_ends(p: Processor, gid: int, what: str):
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_CurveType
    from OCP.TopoDS import TopoDS

    from ..core.model import ModelError

    try:
        bid, _ = p.model.entity_owner("EDGE", gid)
        e = p.model.entity_shape("EDGE", gid)
    except ModelError as exc:
        raise CommandError(f"{what}: {exc}") from None
    c = BRepAdaptor_Curve((getattr(TopoDS, "Edge_s", None) or TopoDS.Edge)(e))
    if c.GetType() != GeomAbs_CurveType.GeomAbs_Line:
        raise CommandError(f"{what}: edge {gid} is not straight; a flange bends along a straight edge")
    a, b = c.Value(c.FirstParameter()), c.Value(c.LastParameter())
    return bid, np.array([a.X(), a.Y(), a.Z()]), np.array([b.X(), b.Y(), b.Z()])


def _inside(shape, q) -> bool:
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_State

    c = BRepClass3d_SolidClassifier(shape, gp_Pnt(*map(float, q)), 1e-7)
    return c.State() == TopAbs_State.TopAbs_IN


@command(
    "FLANGE",
    Arg("edge", int, 0, "a straight edge of the plate's top or bottom face (0: the selected edges)"),
    Arg("length", help="the flat wall's length after the bend"),
    Arg("angle", float, 90.0, "the bend angle in degrees, 1 to 180"),
    Arg("r", float, -1.0, "the inside bend radius (default: the sheet's)"),
    help="Bend a wall along an edge of a sheet metal plate: FLANGE, 12, 20 (a 20 long wall at 90 degrees) · "
         "FLANGE, 12, 15, 45 · FLANGE, , 10 (every selected edge). An edge of the top face bends up, one of the "
         "bottom face bends down; the bend starts at the edge, so the part grows past it",
)
def flange(p: Processor, edge, length, angle, r):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse

    from .handlers import _added, combine

    m = p.model
    if edge:
        edges = [edge]
    elif m.selection_kind == "EDGE" and m.selection:
        edges = list(m.selection)
    else:
        raise CommandError("FLANGE: give an edge (FLANGE, 12, 20) or select edges first")
    if length < 0:
        raise CommandError("FLANGE: the length cannot be negative")
    if not 0 < angle <= 180:
        raise CommandError("FLANGE: the angle is more than 0 and at most 180 degrees")
    # every edge is found before the first change (their numbers change with each flange)
    plan = []
    for gid in edges:
        bid, a, b = _line_ends(p, gid, "FLANGE")
        sh = _sheet(p, bid, "FLANGE")
        rr = sh.r if r < 0 else r
        try:
            a, b, top = smt.edge_side(sh, a, b, a)  # order fixed below from the material side
        except smt.SheetError as exc:
            raise CommandError(f"FLANGE: edge {gid}: {exc}") from None
        out = smt._outward(sh, a, b)
        mid = (np.asarray(a) + np.asarray(b)) / 2
        h = -sh.t / 2 if top else sh.t / 2
        probe = mid + out * min(sh.t, np.linalg.norm(np.asarray(b) - np.asarray(a))) * 0.25 + h * np.asarray(sh.n)
        if _inside(m.body(bid).shape, probe):
            a, b = b, a
            out = -out
        plan.append((gid, bid, a, b, top, out, rr))
    msgs = []
    for gid, bid, a, b, top, out, rr in plan:
        sh = m.sheets[bid]  # FLANGE keeps the body's ID, so later edges of the list still find it
        try:
            tool = smt.flange_solid(sh, a, b, top, angle, length, rr)
        except smt.SheetError as exc:
            raise CommandError(f"FLANGE: edge {gid}: {exc}") from None
        base = m.body(bid).shape
        shape, maker = combine(p, "UNION", BRepAlgoAPI_Fuse, base, [tool], bid, merge=True)
        # the bend edge on the base plane: for a down flange the edge itself; for an up one, below it
        n = np.asarray(sh.n, float)
        a0 = np.asarray(a, float) - (sh.t * n if top else 0)
        b0 = np.asarray(b, float) - (sh.t * n if top else 0)
        rec = smt.Flange(tuple(a0), tuple(b0), tuple(out), top, float(angle), float(length), float(rr))
        new = m.replace([bid], shape, maker, same_id=True)
        m.sheets[new.id] = dataclasses.replace(sh, flanges=sh.flanges + (rec,))
        word = "up" if top else "down"
        msgs.append(_added(p, new, f"FLANGE on edge {gid}: {fmt_num(length)} long, {angle:g} degrees {word}, "
                                   f"bend radius {fmt_num(rr)}"))
    return "\n".join(msgs)

@command(
    "SBEND",
    Arg("b", BodyRef, help="a flat sheet metal plate"),
    Arg("sketch", Text, help="a sketch with one straight line: the bend line, seen square to the plate"),
    Arg("angle", float, 90.0, "the bend angle in degrees, 1 to 180"),
    Arg("r", float, -1.0, "the inside bend radius (default: the sheet's)"),
    Arg("dir", str, "UP", "UP bends towards the sheet's top side, DOWN away from it"),
    Arg("side", str, "SMALL", "SMALL: the smaller side of the line turns; FLIP: the bigger one"),
    help="Bend a sheet metal plate along a sketched line: SBEND, 1, s2 (the smaller side turns up 90 degrees) "
         "· SBEND, 1, s2, 45, 1, DOWN · SBEND, 1, s2, 90, , UP, FLIP. The bend starts at the line; UNFOLD lays "
         "it flat again with the bend allowance",
)
def sbend(p: Processor, b, sketch, angle, r, dir, side):  # noqa: A002 - the argument's name in the language
    from ..sketch import profile as prof
    from .handlers import _added
    from .sketch_handlers import _mark_used

    if dir not in ("UP", "DOWN"):
        raise CommandError("SBEND: dir is UP or DOWN")
    if side not in ("SMALL", "FLIP"):
        raise CommandError("SBEND: side is SMALL or FLIP")
    m = p.model
    sh = _sheet(p, b, "SBEND")
    try:
        sk = m.sketch(sketch)
    except Exception as exc:  # noqa: BLE001 - no such sketch, said plainly
        raise CommandError(f"SBEND: {exc}") from None
    if m.active_sketch == sk.name.upper():
        m.set_active_sketch(None)
    lines = [g for g in sk.geos.values() if g.kind == "LINE" and not g.construction]
    if len(lines) != 1 or any(g.kind not in ("LINE", "POINT") and not g.construction for g in sk.geos.values()):
        raise CommandError(f"SBEND: sketch {sk.name} must hold one straight line (the bend line)")
    from OCP.BRepAdaptor import BRepAdaptor_Curve

    c = BRepAdaptor_Curve(prof.edge(sk, lines[0]))
    p0, p1 = c.Value(c.FirstParameter()), c.Value(c.LastParameter())
    rr = sh.r if r < 0 else r
    try:
        shape, rec = smt.sketched_bend(sh, m.body(b).shape, (p0.X(), p0.Y(), p0.Z()), (p1.X(), p1.Y(), p1.Z()),
                                       angle, rr, dir == "UP", side == "FLIP")
    except smt.SheetError as exc:
        raise CommandError(f"SBEND: body {b}: {exc}") from None
    for fl in sh.flanges:  # flanges already made must stay on the side that does not move
        mid = (np.asarray(fl.a) + np.asarray(fl.b)) / 2 - np.asarray(rec.a)
        if mid @ np.asarray(rec.out) > 1e-6:
            raise CommandError("SBEND: a flange is on the side that would turn; bend first, then add flanges")
    new = m.replace([b], shape, None, same_id=True)
    m.sheets[new.id] = dataclasses.replace(sh, flanges=sh.flanges + (rec,))
    _mark_used(p, sk, f"SBEND on body {b}")
    return _added(p, new, f"SBEND body {b} along {sk.name}: {angle:g} degrees {dir.lower()}, bend radius "
                          f"{fmt_num(rr)}, {fmt_num(float(np.linalg.norm(np.subtract(rec.b, rec.a))))} long")



@command(
    "UNFOLD",
    Arg("b", BodyRef, help="a sheet metal body"),
    Arg("file", Path, "", "also write the flat pattern to this .dxf (cut outline, bend lines, bend notes)"),
    Arg("body", str, "YES", "YES: also make the flat blank as a body beside the part · NO: only the file"),
    help="Lay a sheet metal part flat: UNFOLD, 1 (the flat blank, as a body beside the part) · UNFOLD, 1, "
         "blank.dxf (and a DXF to cut it from: layer OUTLINE, bend lines on BEND with their angle and direction) "
         "· UNFOLD, 1, blank.dxf, NO (only the file). Each bend takes angle × (r + K × t) of flat length",
)
def unfold(p: Processor, b, file, body):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.gp import gp_Trsf, gp_Vec

    from .handlers import _added

    if body not in ("YES", "NO"):
        raise CommandError("UNFOLD: body is YES or NO")
    if body == "NO" and not file:
        raise CommandError("UNFOLD: with body NO, give a .dxf file to write")
    m = p.model
    sh = _sheet(p, b, "UNFOLD")
    shape = m.body(b).shape
    try:
        flat = smt.flat_pattern(sh, shape)
    except smt.SheetError as exc:
        raise CommandError(f"UNFOLD: body {b}: {exc}") from None
    w, h = flat.size
    note = (f"flat blank {w:.2f} × {h:.2f} ({len(sh.flanges)} bend"
            f"{'s' if len(sh.flanges) != 1 else ''}, K {sh.k:g})")
    msgs = []
    if file:
        path = file if os.path.splitext(file)[1] else file + ".dxf"
        try:
            text = smt.dxf(sh, flat, robust.diagonal(flat.face) / 800 + 1e-6, m.units)
            with open(path, "w", encoding="ascii", errors="replace") as fh:
                fh.write(text)
        except OSError as exc:
            raise CommandError(f"UNFOLD: cannot write {path} ({exc})") from None
        msgs.append(f"UNFOLD body {b}: {note}, written to {path}")
    if body == "YES":
        prism = BRepPrimAPI_MakePrism(flat.face, gp_Vec(*(c * sh.t for c in sh.n)))
        prism.Build()
        lo_part = _extent(sh, shape)
        lo_flat = _extent(sh, flat.face)
        gap = max(w, h) * 0.25 + sh.t
        shift = (lo_part[1] - lo_flat[0]) + gap  # beside the part, along the sheet's x
        tr = gp_Trsf()
        tr.SetTranslation(gp_Vec(*(c * shift for c in sh.x)))
        blank = BRepBuilderAPI_Transform(prism.Shape(), tr, True).Shape()
        new = m.add_body(blank)
        moved = dataclasses.replace(sh, origin=tuple(np.asarray(sh.origin) + shift * np.asarray(sh.x)), flanges=())
        m.sheets[new.id] = moved
        msgs.append(_added(p, new, f"UNFOLD body {b}: {note}"))
    return "\n".join(msgs)


def _extent(sh: smt.Sheet, shape) -> tuple[float, float]:
    """Smallest and largest coordinate along the sheet's x."""
    lo, hi = smt._box(sh, shape)
    return lo[0], hi[0]


@command(
    "SHEETINFO",
    Arg("b", BodyRef, help="a sheet metal body"),
    logged=False,
    help="What a sheet metal body is made of: thickness, bend radius, K-factor and each flange: SHEETINFO, 1",
)
def sheetinfo(p: Processor, b):
    sh = _sheet(p, b, "SHEETINFO")
    lines = [f"body {b}: sheet {fmt_num(sh.t)} thick, bend radius {fmt_num(sh.r)}, K-factor {sh.k:g}, "
             f"{len(sh.flanges)} flange{'s' if len(sh.flanges) != 1 else ''}"]
    for i, f in enumerate(sh.flanges, 1):
        ln = float(np.linalg.norm(np.asarray(f.b) - np.asarray(f.a)))
        lines.append(f"  {i}: {'up' if f.up else 'down'} {f.angle:g} degrees, wall {fmt_num(f.length)}, radius "
                     f"{fmt_num(f.radius)}, along {fmt_num(ln)}; flat length {fmt_num(sh.allowance(f.angle, f.radius))}"
                     f" + {fmt_num(f.length)}")
    p.give_report("SHEETINFO", {"body": b, "t": sh.t, "r": sh.r, "k": sh.k, "flanges": [
        {"up": bool(f.up), "angle": f.angle, "wall": f.length, "radius": f.radius,
         "along": round(float(np.linalg.norm(np.asarray(f.b) - np.asarray(f.a))), 4),
         "bend_allowance": round(float(sh.allowance(f.angle, f.radius)), 6)} for f in sh.flanges]})
    return "\n".join(lines)
