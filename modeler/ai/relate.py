"""Where parts are relative to each other, whether a body breaks design rules, and
whether two bodies are the same shape: as short answers with IDs.

Used by the RELATE, DESIGNCHECK and COMPARE commands, the SAMESHAPE and
PROBLEMS queries, and the assistant's ``placement``, ``check_design`` and
``compare_bodies`` tools.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE

from ..core import datum as dt
from ..geometry import contact as ct
from ..geometry import features as ft
from ..geometry import recognize as rc
from ..geometry import robust
from .describe import DescribeError, find_body, num, vec

if TYPE_CHECKING:
    from ..commands.processor import Processor

AXES = "XYZ"
LIMIT = 50


def _label(p: "Processor", bid: int) -> dict[str, Any]:
    name = p.model.bodies[bid].name
    return {"id": bid, "name": name} if name else {"id": bid}


def _face_id(p: "Processor", bid: int, idx: int) -> int:
    return p.model.bodies[bid].entity_ids["FACE"][idx - 1]


# ---- placement ---------------------------------------------------------------------------------


def _axis_relation(lo_a, hi_a, lo_b, hi_b, tol) -> dict[str, Any]:
    if hi_a <= lo_b + tol:
        return {"a_is": "on the - side", "gap": num(max(0.0, lo_b - hi_a))}
    if hi_b <= lo_a + tol:
        return {"a_is": "on the + side", "gap": num(max(0.0, lo_a - hi_b))}
    if lo_a >= lo_b - tol and hi_a <= hi_b + tol:
        return {"a_is": "within", "overlap": num(hi_a - lo_a)}
    if lo_b >= lo_a - tol and hi_b <= hi_a + tol:
        return {"a_is": "around", "overlap": num(hi_b - lo_b)}
    return {"a_is": "overlapping", "overlap": num(min(hi_a, hi_b) - max(lo_a, lo_b))}


def _planes(shape) -> list[tuple[int, dt.P3, float]]:
    """(face index, outward normal, offset along it) of every flat face."""
    out = []
    m = rc.shape_map(shape, TopAbs_FACE)
    for i in range(1, m.Extent() + 1):
        got = ft.face_plane(m.FindKey(i))
        if got:
            c, n = got
            out.append((i, n, dt.dot(n, c)))
    return out


def placement(p: "Processor", a, b, tol: float = 0.0) -> dict[str, Any]:
    """How body a sits relative to body b: along each axis (on which side and how far, within,
    around, overlapping), the offset between their centres (and the axes they are centred on),
    what a rests on, flat faces that are flush, and round faces on the same axis."""
    ia, ib = find_body(p, a), find_body(p, b)
    if ia == ib:
        raise DescribeError("give two different bodies")
    sa, sb = p.model.bodies[ia].shape, p.model.bodies[ib].shape
    ba, bb = ct.box_of(sa), ct.box_of(sb)
    t = float(tol) if tol and tol > 0 else max(1e-6, 1e-6 * ct.size_of(ba, bb)) + p.model.tolerance
    axes = {}
    for k, ax in enumerate(AXES):
        axes[ax] = _axis_relation(ba[k], ba[k + 3], bb[k], bb[k + 3], t)
    ca = [(ba[k] + ba[k + 3]) / 2 for k in range(3)]
    cb = [(bb[k] + bb[k + 3]) / 2 for k in range(3)]
    off = [x - y for x, y in zip(ca, cb)]
    out: dict[str, Any] = {"rev": p.model.revision, "unit": p.model.units.lower(), "a": _label(p, ia),
                           "b": _label(p, ib), "axes": axes, "centre_offset": vec(off),
                           "centred_on": [AXES[k] for k in range(3) if abs(off[k]) <= t]}
    both_solid = bool(robust.solids(sa) and robust.solids(sb))
    if both_solid:
        c = ct.contact(sa, sb, t)
        out["contact"] = c.state + (f" ({c.kind})" if c.state == "touch" else "")
        if c.state == "touch" and c.kind == "face":
            sides = set()
            ma = rc.shape_map(sa, TopAbs_FACE)
            for i in c.faces_a:
                got = ft.face_plane(ma.FindKey(i))
                if got:
                    sides.add(_dir_word(got[1]))
            if sides:
                out["rests"] = [_rest_text(s) for s in sorted(sides)]
    flush = []
    pa, pb = _planes(sa), _planes(sb)
    for i, na, da in pa:
        for j, nb, db in pb:
            if dt.dot(na, nb) > 1 - 1e-9 and abs(da - db) <= t:
                flush.append({"normal": vec(na), "face_a": _face_id(p, ia, i), "face_b": _face_id(p, ib, j)})
    if flush:
        out["flush"] = flush[:LIMIT]
        if len(flush) > LIMIT:
            out["more_flush"] = len(flush) - LIMIT
    coax = []
    if both_solid:
        for r1 in ct.rounds(sa, t):
            for r2 in ct.rounds(sb, t):
                if abs(abs(dt.dot(r1.d, r2.d)) - 1) > 1e-9:
                    continue
                rel = dt.sub(r2.loc, r1.loc)
                along = dt.dot(rel, r1.d)
                if math.dist(rel, [x * along for x in r1.d]) <= t:
                    coax.append({"d_a": num(2 * r1.r), "d_b": num(2 * r2.r), "axis": vec(r1.d),
                                 "a_hole": r1.hole, "b_hole": r2.hole})
    if coax:
        out["coaxial"] = coax[:LIMIT]
    return out


def _dir_word(n) -> str:
    for k, ax in enumerate(AXES):
        if abs(abs(n[k]) - 1) < 1e-9:
            return ("+" if n[k] > 0 else "-") + ax
    return "(" + ", ".join(f"{num(x, 3):g}" for x in n) + ")"


def _rest_text(side: str) -> str:
    """Words for "a touches b with its face pointing ``side``"."""
    if side == "-Z":
        return "a rests on top of b (a's -Z face on b)"
    if side == "+Z":
        return "a is under b (a's +Z face against b)"
    return f"a's {side} face is against b"


# ---- design rules ----------------------------------------------------------------------------------


def _length(shape) -> float:
    g = GProp_GProps()
    BRepGProp.LinearProperties_s(shape, g)
    return g.Mass()


def _area(shape) -> float:
    g = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, g)
    return g.Mass()


def design_check(p: "Processor", body, min_wall: float = 0.0, min_edge: float = 0.0,
                 limit: int = 20) -> dict[str, Any]:
    """Rule checks on one body, each problem with IDs: broken (not valid, open edges, inside out),
    in loose pieces, not a solid, edges shorter than ``min_edge``, narrow sliver faces, walls
    thinner than ``min_wall`` (when given) and faces that cut through each other."""
    bid = find_body(p, body)
    b = p.model.bodies[bid]
    shape = b.shape
    size = ct.size_of(ct.box_of(shape))
    small = float(min_edge) if min_edge and min_edge > 0 else 1e-3 * max(size, 1e-9)
    problems: list[dict[str, Any]] = []
    rep = robust.report(shape)
    checked = ["valid", "closed", "pieces", "small_edges", "slivers"]
    if not rep["valid"]:
        problems.append({"rule": "valid", "message": "the kernel finds the shape broken; try HEAL"})
    if rep["open_edges"]:
        problems.append({"rule": "closed", "message": f"{rep['open_edges']} edges have a face on one side only "
                                                      "(an open shell, not a closed solid)"})
    if rep["solids"] == 0:
        problems.append({"rule": "solid", "message": "not a solid (a surface, a curve or an open shell)"})
    elif rep["solids"] > 1:
        problems.append({"rule": "pieces", "message": f"{rep['solids']} separate pieces in one body"})
    if rep["solids"] and rep["volume"] <= 0:
        problems.append({"rule": "inside_out", "message": "the volume is not positive (turned inside out)"})
    em = b.maps.get("EDGE")
    if em is not None:
        short = []
        for k in range(1, em.Extent() + 1):
            ln = _length(em.FindKey(k))
            if ln < small and not _degenerate(em.FindKey(k)):
                short.append((ln, b.entity_ids["EDGE"][k - 1]))
        if short:
            short.sort()
            problems.append({"rule": "small_edges", "message": f"{len(short)} edges shorter than {num(small):g}",
                             "edges": [i for _, i in short[:limit]],
                             "shortest": num(short[0][0])})
    fm = b.maps.get("FACE")
    if fm is not None:
        slivers = []
        for k in range(1, fm.Extent() + 1):
            f = fm.FindKey(k)
            area = _area(f)
            perim = sum(_length(e) for e in _edges(f))
            width = 2 * area / perim if perim > 0 else 0.0  # about the width of a long narrow strip
            if width < small / 2:
                slivers.append((width, b.entity_ids["FACE"][k - 1]))
        if slivers:
            slivers.sort()
            problems.append({"rule": "slivers", "message": f"{len(slivers)} faces narrower than about "
                                                           f"{num(small):g} (slivers)",
                             "faces": [i for _, i in slivers[:limit]]})
    if min_wall and min_wall > 0 and rep["solids"]:
        from .probe import wall_thickness

        checked.append("min_wall")
        thin = wall_thickness(p, bid, float(min_wall), limit)
        if thin["thinnest"]:
            problems.append({"rule": "min_wall", "message": f"walls thinner than {num(min_wall):g}: thinnest "
                                                            f"{thin['min']:g}",
                             "spots": thin["thinnest"][:limit]})
    if rep["faces"] <= 400:
        checked.append("self_intersection")
        if robust.self_intersects(shape):
            problems.append({"rule": "self_intersection", "message": "faces of the body cut through each other"})
    return {"rev": p.model.revision, "unit": p.model.units.lower(), "body": _label(p, bid),
            "ok": not problems, "problems": problems, "checked": checked, "small": num(small)}


def _edges(face):
    from OCP.TopExp import TopExp_Explorer

    exp = TopExp_Explorer(face, TopAbs_EDGE)
    while exp.More():
        yield exp.Current()
        exp.Next()


def _degenerate(edge) -> bool:
    from OCP.BRep import BRep_Tool

    return BRep_Tool.Degenerated_s(rc.as_edge(edge))


# ---- same shape? -----------------------------------------------------------------------------------


def _props(shape) -> dict[str, Any]:
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, g)
    c = g.CentreOfMass()
    moments = sorted(g.PrincipalProperties().Moments())
    ga = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, ga)
    types: dict[str, int] = {}
    m = rc.shape_map(shape, TopAbs_FACE)
    for i in range(1, m.Extent() + 1):
        t = rc.surface_type(m.FindKey(i))
        types[t] = types.get(t, 0) + 1
    return {"volume": g.Mass(), "area": ga.Mass(), "centre": (c.X(), c.Y(), c.Z()), "moments": moments,
            "faces": m.Extent(), "face_types": types}


def _close(x: float, y: float, rel: float) -> bool:
    return abs(x - y) <= rel * max(abs(x), abs(y), 1e-12)


def _fills(moved, target, vol: float, rel: float) -> bool:
    common = BRepAlgoAPI_Common(moved, target)
    return common.IsDone() and abs(robust.volume(common.Shape()) - vol) <= max(rel, 1e-9) * vol * 10


def compare(p: "Processor", a, b, rel: float = 1e-6) -> dict[str, Any]:
    """Are two bodies the same shape? Compares volume, area, faces by type and the principal
    moments; when they match, finds whether b is a plain moved copy of a or its mirror image
    (in a plane square to X, Y or Z), otherwise lists what differs."""
    ia, ib = find_body(p, a), find_body(p, b)
    if ia == ib:
        raise DescribeError("give two different bodies")
    sa, sb = p.model.bodies[ia].shape, p.model.bodies[ib].shape
    if not (robust.solids(sa) and robust.solids(sb)):
        raise DescribeError("compare needs two solid bodies")
    pa, pb = _props(sa), _props(sb)
    diffs = {}
    for key in ("volume", "area"):
        if not _close(pa[key], pb[key], rel):
            diffs[key] = {"a": num(pa[key]), "b": num(pb[key]), "b_minus_a": num(pb[key] - pa[key])}
    if pa["face_types"] != pb["face_types"]:
        diffs["faces"] = {"a": pa["face_types"], "b": pb["face_types"]}
    if any(not _close(x, y, max(rel, 1e-6) * 10) for x, y in zip(pa["moments"], pb["moments"])):
        diffs["inertia"] = {"a": [num(x) for x in pa["moments"]], "b": [num(x) for x in pb["moments"]]}
    out: dict[str, Any] = {"rev": p.model.revision, "unit": p.model.units.lower(), "a": _label(p, ia),
                           "b": _label(p, ib)}
    if diffs:
        out.update({"same": False, "differs": diffs})
        return out
    move = dt.sub(pb["centre"], pa["centre"])
    t = gp_Trsf()
    t.SetTranslation(gp_Vec(*move))
    if _fills(BRepBuilderAPI_Transform(sa, t, True).Shape(), sb, pb["volume"], rel):
        out.update({"same": True, "how": "moved copy", "move": vec(move)})
        return out
    mid = [(x + y) / 2 for x, y in zip(pa["centre"], pb["centre"])]
    for k, ax in enumerate(AXES):
        n = [0.0, 0.0, 0.0]
        n[k] = 1.0
        m = gp_Trsf()
        m.SetMirror(gp_Ax2(gp_Pnt(*mid), gp_Dir(*n)))
        mirrored = BRepBuilderAPI_Transform(sa, m, True).Shape()
        # the mirror plane through the midpoint maps a's centre onto b's only along its normal;
        # move along the plane to finish
        mc = _props_centre(mirrored)
        shift = dt.sub(pb["centre"], mc)
        tt = gp_Trsf()
        tt.SetTranslation(gp_Vec(*shift))
        if _fills(BRepBuilderAPI_Transform(mirrored, tt, True).Shape(), sb, pb["volume"], rel):
            row = {"same": True, "how": "mirror image", "mirror_normal": ax, "plane_at": num(mid[k])}
            if math.hypot(*shift) > 1e-9 * max(1.0, ct.size_of(ct.box_of(sa))):
                row["then_moved"] = vec(shift)
            out.update(row)
            return out
    out.update({"same": True, "how": "same size and mass properties, but turned (not a plain move or mirror)",
                "move_of_centre": vec(move)})
    return out


def _props_centre(shape):
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, g)
    c = g.CentreOfMass()
    return (c.X(), c.Y(), c.Z())
