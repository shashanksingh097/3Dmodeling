"""STRESS: a first strength check of one solid (geometry/fea.py), in words and as colours."""

from __future__ import annotations

import re

import numpy as np

from ..geometry import fea
from ..lang.expr import fmt_num
from .processor import Arg, BodyRef, CommandError, Processor, Text, command


def _faces(p: Processor, text: str, bid: int, what: str, role: str) -> list:
    from .rib_handlers import _face

    words = [w for w in re.split(r"[\s;]+", text.strip().strip('"')) if w]
    if not words:
        raise CommandError(f"{what}: give the {role} faces by number (like \"3 7\"), or SEL for the selected ones")
    ids: list[int] = []
    for w in words:
        if w.upper() == "SEL":
            m = p.model
            if m.selection_kind != "FACE" or not m.selection:
                raise CommandError(f"{what}: SEL stands for the selected faces, and no faces are selected")
            ids += list(m.selection)
            continue
        if w.upper() in p.model.named_sets:  # a set saved with CM
            kind, got = p.model.named_sets[w.upper()]
            if kind != "FACE":
                raise CommandError(f"{what}: set {w} holds {kind.lower()}s, not faces")
            ids += list(got)
            continue
        try:
            ids.append(int(w))
        except ValueError:
            raise CommandError(f"{what}: {w!r} is not a face number or a set of faces (CM)") from None
    out = []
    for gid in ids:
        owner, f = _face(p, gid, what)
        if owner != bid:
            raise CommandError(f"{what}: face {gid} is on body {owner}, not on body {bid}")
        out.append((gid, f))
    return out


@command(
    "STRESS",
    Arg("b", BodyRef, help="a solid body"),
    Arg("fixed", Text, help="the faces held still: face numbers with spaces between (\"3 7\"), a set saved "
                            "with CM, or SEL"),
    Arg("loaded", Text, help="the faces the load acts on"),
    Arg("kind", str, "FORCE", "FORCE: fx, fy, fz in N, shared over the loaded faces · PRESSURE: fx in MPa "
                              "(N/mm2), pushing into the faces"),
    Arg("fx", float, 0.0), Arg("fy", float, 0.0), Arg("fz", float, 0.0),
    Arg("h", float, 0.0, "the cell size (0: about 8000 cells in the part); smaller is finer and slower"),
    logged=False,
    help="A first strength check: STRESS, b, \"3\", \"8\", FORCE, 0, 0, -500 (face 3 held, 500 N down on face "
         "8) · STRESS, b, \"3\", \"8\", PRESSURE, 2 · ANALYZE, OFF ends the colours. Gives the largest stress, "
         "deflection and safety factor from the body's MATERIAL (steel if none); mm, N, MPa",
)
def stress(p: Processor, b, fixed, loaded, kind, fx, fy, fz, h):
    from .analysis_handlers import Analysis

    if kind not in ("FORCE", "PRESSURE"):
        raise CommandError("STRESS: kind is FORCE or PRESSURE")
    m = p.model
    body = m.body(b)
    from ..geometry import meshbody as mb
    from ..geometry import robust

    if mb.is_mesh(body.shape) or not robust.solids(body.shape):
        raise CommandError(f"STRESS: body {b} is not a solid (a mesh body: make it a solid first, TOSOLID)")
    mat = (body.material or "STEEL").upper()
    if mat not in fea.ELASTIC:
        raise CommandError(f"STRESS: no stiffness for material {mat} (it is not linear enough for this check); "
                           f"known: {', '.join(fea.ELASTIC)}")
    el = fea.ELASTIC[mat]
    vol = robust.volume(body.shape)
    if h < 0:
        raise CommandError("STRESS: the cell size cannot be negative")
    h = h or (vol / 8000) ** (1 / 3)
    held = _faces(p, fixed, b, "STRESS", "fixed")
    pushed = _faces(p, loaded, b, "STRESS", "loaded")
    try:
        grid = fea.voxelize(body.shape, h)
        if len(grid.cells) > 200_000:
            raise CommandError(f"STRESS: {len(grid.cells):,} cells is too many; give a bigger cell size")
        reach = 0.9 * float(grid.h.max())
        fixed_nodes = np.unique(np.concatenate([fea.nodes_near(grid, fea.face_samples(f, h)[0], reach)
                                                for _g, f in held]))
        if len(fixed_nodes) == 0:
            raise CommandError("STRESS: no part of the grid touches the fixed faces; use a smaller cell size")
        loads = []
        for gid, f in pushed:
            pts, area, nrm = fea.face_samples(f, h)
            nodes = fea.nodes_near(grid, pts, reach)
            nodes = np.setdiff1d(nodes, fixed_nodes)
            if len(nodes) == 0:
                raise CommandError(f"STRESS: face {gid} has no free grid nodes near it (is it also fixed?)")
            if kind == "PRESSURE":
                force = -fx * area * nrm
            else:
                force = np.array([fx, fy, fz]) * area / sum(fea.face_samples(f2, h)[1] for _g, f2 in pushed)
            loads.append((nodes, force))
        if kind == "FORCE" and fx == fy == fz == 0:
            raise CommandError("STRESS: the force is zero (give fx, fy, fz in N)")
        res = fea.solve(grid, el, mat, fixed_nodes, loads)
    except fea.FeaError as exc:
        raise CommandError(f"STRESS: body {b}: {exc}") from None
    peak, where = res.peak()
    p995 = float(np.percentile(res.vm, 99.5))
    defl, dwhere = res.deflection()
    sf = el.yield_ / peak if peak > 0 else float("inf")
    sf_bulk = el.yield_ / p995 if p995 > 0 else float("inf")
    p.analysis = Analysis(b, "STRESS", (0.0, 0.0, 1.0), 0.0, field=res, scale=max(p995, 1e-30))
    hook = getattr(p.view, "show_analysis", None) if p.view else None
    if hook:
        hook(p.analysis)

    def at(q):
        return "(" + ", ".join(fmt_num(round(float(v), 2)) for v in q) + ")"

    word = "holds" if sf_bulk >= 1.5 else ("is close to yielding" if sf_bulk >= 1 else "yields")
    lines = [
        f"STRESS body {b} ({mat.lower()}, E {el.E:g} MPa, yield {el.yield_:g} MPa): {len(grid.cells):,} cells of "
        f"{' × '.join(fmt_num(round(float(v), 3)) for v in grid.h)}, {res.fixed} nodes held, {res.loaded} loaded, total load "
        f"{at(res.force)} N; solved in {res.seconds:.1f} s",
        f"largest stress {peak:.4g} MPa at {at(where)}; 99.5% of the part is under {p995:.4g} MPa",
        f"largest deflection {defl:.4g} mm at {at(dwhere)}",
        f"safety factor {sf:.3g} on the peak, {sf_bulk:.3g} on the 99.5% value: the part {word}",
        "colours: blue none, red the 99.5% value, magenta above it (ANALYZE, OFF ends them). Peaks at sharp inside "
        "corners and at a fixed face's edge depend on the cell size: try a smaller h to see if they settle",
    ]
    return "\n".join(lines)


def _setup(p: Processor, what: str, b, fixed, loaded, kind, fx, fy, fz, h, cells: int):
    """The body's grid, held nodes and loads, shared by STRESS-like checks."""
    if kind not in ("FORCE", "PRESSURE"):
        raise CommandError(f"{what}: kind is FORCE or PRESSURE")
    from ..geometry import meshbody as mb
    from ..geometry import robust

    body = p.model.body(b)
    if mb.is_mesh(body.shape) or not robust.solids(body.shape):
        raise CommandError(f"{what}: body {b} is not a solid (a mesh body: make it a solid first, TOSOLID)")
    mat = (body.material or "STEEL").upper()
    if mat not in fea.ELASTIC:
        raise CommandError(f"{what}: no stiffness for material {mat}; known: {', '.join(fea.ELASTIC)}")
    if h < 0:
        raise CommandError(f"{what}: the cell size cannot be negative")
    h = h or (robust.volume(body.shape) / cells) ** (1 / 3)
    held = _faces(p, fixed, b, what, "fixed")
    pushed = _faces(p, loaded, b, what, "loaded")
    if kind == "FORCE" and fx == fy == fz == 0:
        raise CommandError(f"{what}: the force is zero (give fx, fy, fz in N)")
    grid = fea.voxelize(body.shape, h)
    reach = 0.9 * float(grid.h.max())
    fixed_nodes = np.unique(np.concatenate([fea.nodes_near(grid, fea.face_samples(f, h)[0], reach)
                                            for _g, f in held]))
    if len(fixed_nodes) == 0:
        raise CommandError(f"{what}: no part of the grid touches the fixed faces; use a smaller cell size")
    loads = []
    total_area = sum(fea.face_samples(f2, h)[1] for _g, f2 in pushed)
    for gid, f in pushed:
        pts, area, nrm = fea.face_samples(f, h)
        nodes = np.setdiff1d(fea.nodes_near(grid, pts, reach), fixed_nodes)
        if len(nodes) == 0:
            raise CommandError(f"{what}: face {gid} has no free grid nodes near it (is it also fixed?)")
        force = -fx * area * nrm if kind == "PRESSURE" else np.array([fx, fy, fz]) * area / total_area
        loads.append((nodes, force))
    return body, mat, grid, fixed_nodes, loads


@command(
    "TOPOPT",
    Arg("b", BodyRef, help="a solid body: the space the part may fill"),
    Arg("fixed", Text, help="the faces held still (numbers, a CM set, or SEL)"),
    Arg("loaded", Text, help="the faces the load acts on"),
    Arg("kind", str, "FORCE", "FORCE (fx, fy, fz in N) or PRESSURE (fx in MPa)"),
    Arg("fx", float, 0.0), Arg("fy", float, 0.0), Arg("fz", float, 0.0),
    Arg("keep", float, 0.3, "the share of the material to keep, 0.02 to 1 (0.3: 30%)"),
    Arg("rounds", int, 40, "at most this many rounds (each one is a solve)"),
    Arg("h", float, 0.0, "the cell size (0: about 3000 cells in the part)"),
    Arg("name", Text, "", "the new mesh body's name (default topo_k)"),
    help="Where does the material carry the load? TOPOPT, b, \"3\", \"8\", FORCE, 0, 0, -500, 0.3 keeps the "
         "30% of body b that makes it stiffest with face 3 held and 500 N on face 8, as a new mesh body (the "
         "first body is hidden). A quick suggestion on a coarse grid to model a real part after; check the "
         "part you make with STRESS",
)
def topopt(p: Processor, b, fixed, loaded, kind, fx, fy, fz, keep, rounds, h, name):
    from ..core.model import ModelError
    from ..geometry import meshbody as mb
    from ..geometry import topopt as to
    from ..lang.script import is_ident

    if rounds < 1 or rounds > 200:
        raise CommandError("TOPOPT: rounds is 1 to 200")
    m = p.model
    if name and not is_ident(name):
        raise CommandError(f"TOPOPT: {name!r} is not a valid name (letters, digits, _)")
    try:
        body, mat, grid, fixed_nodes, loads = _setup(p, "TOPOPT", b, fixed, loaded, kind, fx, fy, fz, h, 3000)
        if len(grid.cells) > 60_000:
            raise CommandError(f"TOPOPT: {len(grid.cells):,} cells is too many for a quick look; give a bigger "
                               "cell size")
        # cells touching the held and loaded nodes stay solid
        touch = np.zeros(len(grid.nodes), bool)
        touch[fixed_nodes] = True
        for nodes, _f in loads:
            touch[nodes] = True
        passive = touch[grid.conn].any(axis=1)
        res = to.optimise(grid, fea.ELASTIC[mat], fixed_nodes, loads, keep, passive, rounds)
        pts, t = to.mesh(res)
    except fea.FeaError as exc:
        raise CommandError(f"TOPOPT: body {b}: {exc}") from None
    if len(t) == 0:
        raise CommandError("TOPOPT: nothing is left; keep more material")
    step = float(grid.h.min())
    pts = mb.smooth(pts, t, 3, 0.5)
    try:  # trim to the part (the outline was carried past its curved faces)
        pts, t = mb.boolean("INTERSECT", (pts, t), [mb.triangles_of(body.shape, step / 10)])
        pts, t = mb.drop_specks(pts, t)
    except mb.MeshError:
        pass
    if len(t) == 0:
        raise CommandError("TOPOPT: nothing is left; keep more material")
    if len(t) > 20_000:
        try:
            pts, t = mb.simplify(pts, t, step / 20)
        except mb.MeshError:
            pass
    k = 1
    while not name and m.body_by_name(f"topo_{k}") is not None:
        k += 1
    name = name or f"topo_{k}"
    try:
        new = m.add_body(mb.make_shape(pts, t), name)
    except ModelError as exc:
        raise CommandError(f"TOPOPT: {exc}") from None
    m.forget_view(b)
    m.set_hidden(b, True)
    vol = mb.volume(pts, t)
    from ..geometry import robust

    start = robust.volume(body.shape)
    return (f"TOPOPT body {b} ({mat.lower()}): {len(grid.cells):,} cells, {res.rounds} rounds"
            f"{'' if res.converged else ' (stopped before it settled: give more rounds)'} in {res.seconds:.1f} s; "
            f"kept {vol / start:.0%} of the volume ({fmt_num(round(vol, 1))} of {fmt_num(round(start, 1))} mm3) as "
            f"body {new.id} {name} (body {b} hidden). A suggestion to model a part after: check that part with STRESS")
