"""NURBS freeform: control-point curves and surfaces, editing their points,
weights, knots and degree, surfaces from a net, a network or a loop of
curves, and sewing surfaces into one skin or a solid.

Every edit is a command and a history entry, so dragging a control point in
the view writes ``MOVEPT`` and a later edit of an earlier step re-runs it.
"""

from __future__ import annotations

import math

from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp

from ..core.model import ModelError
from ..geometry import nurbs as nb
from ..geometry import robust
from ..lang.expr import ExprError, Vec, fmt_num, format_value
from ..lang.script import is_ident
from .curve_handlers import _curve, _new
from .processor import REGISTRY, Arg, BodyRef, CommandError, Processor, Raw, command

try:  # OCP 7.x
    from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape as _AncestorMap
except ImportError:  # OCP 8.x
    from OCP.collections import (  # type: ignore[no-redef]
        IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as _AncestorMap,
    )

_MAX_POINTS = 32


def _run(what: str, fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except nb.NurbsError as exc:
        raise CommandError(f"{what}: {exc}") from None
    except nb.CurveError as exc:
        raise CommandError(f"{what}: {exc}") from None


def _geometry(p: Processor, bid: int, what: str, need_whole: bool = True):
    body = p.model.body(bid)
    try:
        return nb.geometry_of(body.shape, need_whole)
    except nb.CurveError as exc:
        raise CommandError(f"{what}: body {bid}: {exc}") from None


def _put_back(p: Processor, bid: int, g, what: str) -> str:
    """Replace body ``bid`` by a shape made from geometry ``g``, keeping its ID (and its
    entity IDs when it has as many faces, edges and vertices as before)."""
    from .handlers import _added

    m = p.model
    old = m.body(bid).shape
    new = _run(what, nb.shape_of, g)
    if not robust.is_valid(new):
        raise CommandError(f"{what}: the edited shape is not valid (a control point may make it fold over itself)")
    maker = nb.SameTopology(old, new)
    try:
        body = m.replace([bid], new, maker, same_id=True)
    except ModelError as exc:
        raise CommandError(f"{what}: {exc}") from None
    return _added(p, body, what)


def _index(p: Processor, raw: str, what: str) -> tuple[int, ...]:
    try:
        v = p.evaluate(raw)
    except ExprError as exc:
        raise CommandError(f"{what}: {exc}") from None
    if isinstance(v, Vec):
        vals = list(v)
    elif isinstance(v, (int, float)) and not isinstance(v, bool):
        vals = [v]
    else:
        raise CommandError(f"{what}: a control point is a number (curve) or (i, j) (surface), got {format_value(v)}")
    if not all(float(x).is_integer() for x in vals):
        raise CommandError(f"{what}: control point numbers are whole numbers, got {format_value(v)}")
    return tuple(int(x) for x in vals)


def _label(idx: tuple[int, ...]) -> str:
    return str(idx[0]) if len(idx) == 1 else f"({idx[0]}, {idx[1]})"


def _items(p: Processor, raws, what: str, words: tuple[str, ...] = ()) -> list:
    """Arguments as a list of ('WORD', w), ('BODY', id), ('SEL', None) or ('POINT', (x, y, z))."""
    out = []
    cmd = REGISTRY[what]
    for raw in (r.strip() for r in raws):
        if not raw:
            continue
        up = raw.upper()
        if is_ident(raw) and up in words:
            out.append(("WORD", up))
        elif up == "SEL":
            out.append(("SEL", None))
        elif raw.startswith("("):
            try:
                v = p.evaluate(raw)
            except ExprError as exc:
                raise CommandError(f"{what}: {exc}") from None
            if not isinstance(v, Vec) or len(v) < 2:
                raise CommandError(f"{what}: {raw} is not a point")
            out.append(("POINT", (v[0], v[1], v[2] if len(v) > 2 else 0.0)))
        else:
            out.append(("BODY", p._body_arg(cmd, raw)))
    return out


def _split_weight(raw: str) -> tuple[str, str]:
    """``(x, y, z, w)`` -> ("(x, y, z)", "w"); anything else is left as it is."""
    import ast

    try:
        node = ast.parse(raw.strip(), mode="eval").body
    except SyntaxError:
        return raw, ""
    if isinstance(node, ast.Tuple) and len(node.elts) == 4:
        return "(" + ", ".join(ast.unparse(e) for e in node.elts[:3]) + ")", ast.unparse(node.elts[3])
    return raw, ""


def _selected_bodies(p: Processor, what: str) -> list[int]:
    m = p.model
    if m.selection_kind != "BODY" or not m.selection:
        raise CommandError(f"{what}: SEL stands for the selected bodies, and no bodies are selected")
    return list(m.selection)


# =============================================================================
# NURBS curves
# =============================================================================


@command(
    "NURBS",
    Arg("deg", int, 3, "degree: 1 straight segments, 2, 3 (smooth, the usual), up to 25"),
    *[Arg(f"p{i}", Raw, "") for i in range(1, _MAX_POINTS + 1)],
    help="Curve from control points (it starts and ends on the first and last; in between the points pull it "
         "like magnets): NURBS, 3, (0,0,0), (10,8,0), (20,-8,0), (30,0,0) · a fourth number is the point's weight "
         "(how hard it pulls, default 1): (10,8,0,2) · end with CLOSE for a smooth closed loop.",
)
def nurbs(p: Processor, deg, **pts):
    raws = [r for r in pts.values() if r.strip()]
    closed = bool(raws) and raws[-1].strip().upper() == "CLOSE"
    if closed:
        raws = raws[:-1]
    points, ws = [], []
    for k, raw in enumerate(raws):
        text, wtext = _split_weight(raw)
        try:
            v = p.evaluate(text)
            w = p.evaluate(wtext) if wtext else 1.0
        except ExprError as exc:
            raise CommandError(f"NURBS: point {k + 1}: {exc}") from None
        if not isinstance(v, Vec):
            raise CommandError(f"NURBS: point {k + 1} must be (x, y, z) or (x, y, z, weight), got {format_value(v)}")
        if isinstance(w, bool) or not isinstance(w, (int, float)):
            raise CommandError(f"NURBS: point {k + 1}: the weight must be a number, got {format_value(w)}")
        points.append((v[0], v[1], v[2] if len(v) > 2 else 0.0))
        ws.append(float(w))
    if not closed and 2 <= len(points) <= deg:
        p.warn(f"NURBS: {len(points)} control points allow at most degree {len(points) - 1}, so that is used")
        deg = len(points) - 1
    g = _run("NURBS", nb.make_curve, points, deg, ws, closed)
    rational = any(abs(w - 1) > 1e-12 for w in ws)
    what = f"NURBS degree {deg}, {len(points)} control points{' (weighted)' if rational else ''}"
    return _curve(p, lambda: nb.curve_shape(g), what=what)


@command(
    "MOVEPT",
    Arg("body", BodyRef, help="a curve or a single surface"),
    Arg("i", Raw, help="which control point: 3 on a curve, (2, 3) on a surface (row, point in the row)"),
    Arg("dx", float, 0.0), Arg("dy", float, 0.0), Arg("dz", float, 0.0),
    Arg("mode", str, "BY", "BY: move by (dx, dy, dz); TO: move to the point (dx, dy, dz)"),
    help="Move one control point of a curve or surface; the shape follows it smoothly: MOVEPT, c, 3, 0, 5, 0 "
         "(point 3 up 5 in y) · MOVEPT, s, (2, 3), 0, 0, 4 · MOVEPT, c, 3, 10, 5, 0, TO. Dragging a control point "
         "in the view writes this command. Lines, arcs, circles and plain faces are turned into their exact NURBS "
         "first.",
)
def movept(p: Processor, body, i, dx, dy, dz, mode):
    if mode not in ("BY", "TO"):
        raise CommandError("MOVEPT: the mode is BY (move by) or TO (move to)")
    g = _geometry(p, body, "MOVEPT")
    idx = _index(p, i, "MOVEPT")
    start = _run("MOVEPT", nb.pole, g, idx)
    to = (dx, dy, dz) if mode == "TO" else (start[0] + dx, start[1] + dy, start[2] + dz)
    _run("MOVEPT", nb.move_pole, g, idx, to)
    return _put_back(p, body, g, f"MOVEPT point {_label(idx)} of body {body} to "
                                 f"({fmt_num(to[0])}, {fmt_num(to[1])}, {fmt_num(to[2])})")


@command(
    "WEIGHT",
    Arg("body", BodyRef, help="a curve or a single surface"),
    Arg("i", Raw, help="which control point: 3 on a curve, (2, 3) on a surface"),
    Arg("w", help="the weight: 1 is normal, more pulls the shape closer to the point, less lets it go"),
    help="Set how hard one control point pulls: WEIGHT, c, 2, 3 · a weight of 0.7071 on the middle point of a "
         "three-point degree-2 curve with a right-angle corner makes an exact quarter circle.",
)
def weight(p: Processor, body, i, w):
    g = _geometry(p, body, "WEIGHT")
    idx = _index(p, i, "WEIGHT")
    _run("WEIGHT", nb.set_weight, g, idx, w)
    return _put_back(p, body, g, f"WEIGHT of point {_label(idx)} of body {body} = {fmt_num(w)}")


def _direction(d: str, what: str) -> str:
    if d not in ("U", "V", "BOTH"):
        raise CommandError(f"{what}: the direction is U, V or BOTH")
    return d


@command(
    "KNOT",
    Arg("body", BodyRef, help="a curve or a single surface"),
    Arg("t", help="where, from 0 (start) to 1 (end)"),
    Arg("dir", str, "U", "on a surface: U or V"),
    Arg("mult", int, 1, "how many times (more makes a sharper join possible; at most the degree)"),
    help="Add a knot, which adds control points there without changing the shape, so the shape can be "
         "edited in more detail at that place: KNOT, c, 0.5 · KNOT, s, 0.25, V.",
)
def knot(p: Processor, body, t, dir, mult):
    d = _direction(dir, "KNOT")
    if d == "BOTH":
        raise CommandError("KNOT: give U or V")
    g = _geometry(p, body, "KNOT")
    added = _run("KNOT", nb.insert_knot, g, t, mult, d)
    where = "" if isinstance(g, nb.Geom_BSplineCurve) else f" along {d}"
    note = f"{added} control point{'s' if added != 1 else ''} added" if added else "it was there already"
    return _put_back(p, body, g, f"KNOT at {fmt_num(t)}{where} of body {body} ({note})")


@command(
    "DEGREE",
    Arg("body", BodyRef, help="a curve or a single surface"),
    Arg("deg", int, help="the new degree (higher than now: the shape does not change)"),
    Arg("dir", str, "BOTH", "on a surface: U, V or BOTH"),
    help="Raise the degree of a curve or surface without changing its shape; it gets more control points and "
         "bends more smoothly when they are moved: DEGREE, c, 5. REBUILD makes a lower degree.",
)
def degree(p: Processor, body, deg, dir):
    d = _direction(dir, "DEGREE")
    g = _geometry(p, body, "DEGREE")
    _run("DEGREE", nb.elevate, g, deg, d)
    n = g.NbPoles() if isinstance(g, nb.Geom_BSplineCurve) else f"{g.NbUPoles()} x {g.NbVPoles()}"
    return _put_back(p, body, g, f"DEGREE {deg} for body {body} ({n} control points)")


@command(
    "REBUILD",
    Arg("body", BodyRef, help="a curve (of any pieces) or a single surface"),
    Arg("n", int, help="control points (along u, for a surface)"),
    Arg("deg", int, 3, "degree"),
    Arg("nv", int, 0, "surface: control points along v (default: n)"),
    Arg("degv", int, 0, "surface: degree along v (default: deg)"),
    help="Remake a curve or surface as one smooth NURBS with a chosen number of control points, so it is "
         "easy to edit: REBUILD, path, 8 (a polyline or a chain of curves becomes one curve; sharp corners "
         "round off) · REBUILD, s, 6, 3, 5. Says how far the new shape is from the old one.",
)
def rebuild(p: Processor, body, n, deg, nv, degv):
    m = p.model
    shape = m.body(body).shape
    kind = nb.kind_of(shape)
    if not 1 <= deg <= 9 or (degv and not 1 <= degv <= 9):
        raise CommandError("REBUILD: the degree must be from 1 to 9")
    if kind == "curve":
        if not deg + 1 <= n <= 200:
            raise CommandError(f"REBUILD: a degree {deg} curve needs {deg + 1} to 200 control points")
        g, dev = _run("REBUILD", nb.rebuild_curve, shape, n, deg)
        what = f"REBUILD body {body}: curve, {n} control points, degree {deg}"
    elif kind == "surface":
        nv = nv or n
        degv = degv or deg
        if not (deg + 1 <= n <= 100 and degv + 1 <= nv <= 100):
            raise CommandError("REBUILD: a surface needs (degree + 1) to 100 control points each way")
        g, dev = _run("REBUILD", nb.rebuild_surface, shape, n, nv, deg, degv)
        what = f"REBUILD body {body}: surface, {n} x {nv} control points, degree {deg} x {degv}"
    else:
        raise CommandError(f"REBUILD: body {body} is not a curve or a single surface")
    size = robust.diagonal(shape)
    if dev > 1e-3 * max(size, 1.0):
        p.warn(f"REBUILD: the new shape is up to {dev:.3g} away from the old one; use more control points to keep "
               "closer to it")
    return _put_back(p, body, g, f"{what}, within {dev:.2g} of the old one")


@command(
    "POLES",
    Arg("body", BodyRef, help="a curve or a single surface"),
    logged=False,
    help="List the control points (and weights) of a curve or surface, with the numbers MOVEPT uses.",
)
def poles_(p: Processor, body):
    g = _geometry(p, body, "POLES", need_whole=False)
    return f"body {body}: " + nb.describe(g)


@command(
    "CPOINTS",
    Arg("body", Raw, "", help="a curve or single surface; OFF (or empty) hides the control points"),
    logged=False,
    help="Show the control points of a curve or surface in the view, to drag them with the mouse (each drag "
         "is a MOVEPT command): CPOINTS, c · CPOINTS, OFF.",
)
def cpoints(p: Processor, body):
    word = body.strip()
    if not word or word.upper() == "OFF":
        p.control_points = None
        msg = "control points hidden"
    else:
        bid = p._body_arg(REGISTRY["CPOINTS"], word)
        g = _geometry(p, bid, "CPOINTS", need_whole=False)
        p.control_points = bid
        n = g.NbPoles() if isinstance(g, nb.Geom_BSplineCurve) else f"{g.NbUPoles()} x {g.NbVPoles()}"
        msg = f"showing the {n} control points of body {bid}; drag one to move it"
    hook = getattr(p.view, "show_control_points", None) if p.view else None
    if hook:
        hook(p.control_points)
    return msg


# =============================================================================
# Surfaces
# =============================================================================


@command(
    "NSURF",
    Arg("deg", int, 3, "degree across the rows (along the rows, the curves' own degree is kept)"),
    *[Arg(f"c{i}", Raw, "") for i in range(1, 17)],
    help="Surface from rows of control points: each curve given is one row (its control points, not the curve "
         "itself, are used, so the surface is pulled towards the rows rather than passing through the middle "
         "ones): NSURF, 3, r1, r2, r3, r4. Rows with different point counts are matched first. LOFT passes "
         "through the curves instead.",
)
def nsurf(p: Processor, deg, **cs):
    items = _items(p, cs.values(), "NSURF")
    ids = []
    for kind, v in items:
        if kind == "SEL":
            ids += _selected_bodies(p, "NSURF")
        elif kind == "BODY":
            ids.append(v)
        else:
            raise CommandError("NSURF: give the row curves")
    if len(ids) < 2:
        raise CommandError("NSURF: give at least 2 row curves")
    curves = [_geometry(p, b, "NSURF") for b in ids]
    if any(not isinstance(c, nb.Geom_BSplineCurve) for c in curves):
        raise CommandError("NSURF: every row must be a curve")
    g = _run("NSURF", nb.net_surface, curves, deg)
    return _new(p, _run("NSURF", nb.surface_shape, g),
                f"NSURF from {len(ids)} rows ({g.NbUPoles()} x {g.NbVPoles()} control points)", solid=False)


@command(
    "NETWORK",
    *[Arg(f"a{i}", Raw, "") for i in range(1, 33)],
    help="Surface through a network of curves: the curves one way, then ACROSS, then the curves the other way; "
         "every curve must meet every curve of the other set: NETWORK, u1, u2, u3, ACROSS, v1, v2, v3. The "
         "surface passes through all of them. Give each set in order across the other.",
)
def network(p: Processor, **raws):
    items = _items(p, raws.values(), "NETWORK", ("ACROSS",))
    sets: list[list[int]] = [[]]
    for kind, v in items:
        if kind == "WORD":
            if len(sets) == 2:
                raise CommandError("NETWORK: ACROSS can only be given once")
            sets.append([])
        elif kind == "BODY":
            sets[-1].append(v)
        else:
            raise CommandError("NETWORK: give curve bodies, with ACROSS between the two sets")
    if len(sets) != 2:
        raise CommandError("NETWORK: write the curves one way, ACROSS, then the curves the other way")
    us, vs = sets
    if len(us) < 2 or len(vs) < 2:
        raise CommandError("NETWORK: give at least 2 curves each side of ACROSS")
    m = p.model
    for b in us + vs:
        if nb.kind_of(m.body(b).shape) != "curve":
            raise CommandError(f"NETWORK: body {b} is not a curve")
    g, gap = _run("NETWORK", nb.network, [m.body(b).shape for b in us], [m.body(b).shape for b in vs])
    size = robust.diagonal(m.body(us[0]).shape)
    if gap > 1e-4 * max(size, 1.0):
        p.warn(f"NETWORK: some curves only come within {gap:.3g} of each other; the surface goes between them")
    return _new(p, _run("NETWORK", nb.surface_shape, g),
                f"NETWORK of {len(us)} x {len(vs)} curves", solid=False)


def _edge_with_face(p: Processor, gid: int, what: str):
    """(edge, face of its surface body or None) for a selected edge."""
    m = p.model
    bid, _ = m.entity_owner("EDGE", gid)
    shape = m.body(bid).shape
    edge = nb._as_edge(m.entity_shape("EDGE", gid))
    amap = _AncestorMap()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, amap)
    faces = []
    idx = amap.FindIndex(edge)
    if idx > 0:
        faces = list(amap.FindFromIndex(idx))
    if len(faces) > 1:
        raise CommandError(f"{what}: edge {gid} lies between {len(faces)} faces of body {bid}, so it is not clear "
                           "which one the patch should flow on from; use an edge of an open surface")
    return edge, (nb._as_face(faces[0]) if faces else None)


@command(
    "FILL",
    Arg("cont", str, "G1", "how smoothly the patch meets the faces of picked edges: G0 (touching), G1 (no crease), "
        "G2 (no change in curvature)"),
    *[Arg(f"a{i}", Raw, "") for i in range(1, 25)],
    help="Fill a hole with a smooth patch: give the curves around it (bodies), or SEL for the picked edges of "
         "surfaces; along a picked edge the patch flows on from that surface (G1 or G2). After THROUGH, curves "
         "and points the patch must also pass through: FILL, G2, SEL · FILL, G0, c1, c2, c3, c4, THROUGH, "
         "(10, 10, 6).",
)
def fill(p: Processor, cont, **raws):
    if cont not in nb.CONTINUITY:
        raise CommandError("FILL: the smoothness is G0, G1 or G2")
    m = p.model
    items = _items(p, raws.values(), "FILL", ("THROUGH",))
    boundary, inner_edges, inner_pts = [], [], []
    through = False
    for kind, v in items:
        if kind == "WORD":
            through = True
            continue
        if kind == "SEL":
            if m.selection_kind == "EDGE" and m.selection:
                for gid in m.selection:
                    e, f = _edge_with_face(p, gid, "FILL")
                    (inner_edges.append(e) if through else boundary.append((e, f, cont)))
            elif m.selection_kind == "BODY" and m.selection:
                for b in m.selection:
                    for e in _curve_edges(p, b):
                        (inner_edges.append(e) if through else boundary.append((e, None, "G0")))
            else:
                raise CommandError("FILL: SEL stands for the picked edges (or curve bodies), and nothing is picked")
        elif kind == "BODY":
            for e in _curve_edges(p, v):
                (inner_edges.append(e) if through else boundary.append((e, None, "G0")))
        elif kind == "POINT":
            if not through:
                raise CommandError("FILL: points go after THROUGH; the boundary is made of curves")
            inner_pts.append(v)
    if not boundary:
        raise CommandError("FILL: give the curves around the hole, or SEL with the hole's edges picked")
    gap = nb.boundary_loop_gap([e for e, _, _ in boundary])
    size = max(robust.diagonal(e) for e, _, _ in boundary)
    if gap > 1e-3 * max(size, 1.0):
        raise CommandError(f"FILL: the curves do not close into a loop (a gap of {gap:.3g}); their ends must meet")
    if cont != "G0" and not any(f is not None for _, f, _ in boundary):
        p.warn(f"FILL: {cont} needs edges of surfaces to flow on from (pick them and give SEL); "
               "the patch only touches the curves")
    face, errs = _run("FILL", nb.fill, boundary, inner_edges, inner_pts)
    worst = errs["G0"]
    if worst > 1e-2 * max(size, 1.0):
        p.warn(f"FILL: the patch is up to {worst:.3g} away from its boundary curves")
    note = ""
    if any(f is not None and c != "G0" for _, f, c in boundary):
        note = f"{cont}, meets the surfaces within {math.degrees(errs['G1']):.2g} degrees"
        if cont == "G2":
            note += f" and {errs['G2']:.2g} in curvature"
        note += ", "
    return _new(p, face, f"FILL patch ({note}{len(boundary)} sides)", solid=False)


def _curve_edges(p: Processor, bid: int) -> list:
    shape = p.model.body(bid).shape
    if nb.kind_of(shape) != "curve":
        raise CommandError(f"FILL: body {bid} is not a curve (pick a surface's edges and give SEL instead)")
    return [nb._as_edge(e) for e in nb._subs(shape, TopAbs_EDGE)]


@command(
    "SEW",
    *[Arg(f"b{i}", Raw, "") for i in range(1, 25)],
    help="Sew surfaces whose edges meet into one skin; a skin that closes becomes a solid: SEW, top, bottom, "
         "side · SEW, SEL. The surfaces are used up.",
)
def sew_(p: Processor, **raws):
    from .handlers import _added

    m = p.model
    ids: list[int] = []
    for kind, v in _items(p, raws.values(), "SEW"):
        if kind == "SEL":
            ids += _selected_bodies(p, "SEW")
        elif kind == "BODY":
            ids.append(v)
        else:
            raise CommandError("SEW: give the surface bodies")
    if len(dict.fromkeys(ids)) != len(ids):
        raise CommandError("SEW: a body is given twice")
    if not ids:
        raise CommandError("SEW: give the surfaces to sew")
    for b in ids:
        if not nb._subs(m.body(b).shape, TopAbs_FACE):
            raise CommandError(f"SEW: body {b} has no faces")
    shapes = [m.body(b).shape for b in ids]
    size = max(robust.diagonal(s) for s in shapes)
    tol = max(1e-4, 1e-4 * size, 10 * m.tolerance)
    out, sew, free = _run("SEW", nb.sew, shapes, tol)
    try:
        body = m.replace(ids, out, nb.SewMaker(sew, out))
    except ModelError as exc:
        raise CommandError(f"SEW: {exc}") from None
    if robust.solids(out):
        kind = f"a closed solid, volume {robust.volume(out):.4g}"
    else:
        kind = f"an open skin with {free} free edge{'s' if free != 1 else ''}"
        if free:
            p.warn(f"SEW: {free} edge{'s' if free != 1 else ''} did not meet another surface, so no solid was made")
    return _added(p, body, f"SEW {len(ids)} surface{'s' if len(ids) > 1 else ''} into {kind}")
