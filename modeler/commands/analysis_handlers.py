"""ANALYZE: how smooth, how curved, and how well drafted a body's faces are,
in words and as colours in the view (see geometry/analysis.py)."""

from __future__ import annotations

from dataclasses import dataclass

from ..geometry import analysis as an
from .processor import REGISTRY, Arg, CommandError, Processor, Raw, command


@dataclass
class Analysis:
    """What the view shows: one body coloured by one analysis."""

    body: int
    mode: str
    direction: tuple
    angle: float
    field: object = None  # STRESS: the result (geometry/fea.py Result), whose .at(points) colours the faces
    scale: float = 0.0  # STRESS: the value drawn red


def _direction(p: Processor, mode: str, dx: float, dy: float, dz: float) -> tuple:
    if (dx, dy, dz) != (0, 0, 0):
        return (dx, dy, dz)
    if mode == "ZEBRA":  # stripes as seen from where the view looks from
        look = getattr(p.view, "eye_direction", None) if p.view else None
        d = look() if look else None
        return tuple(d) if d else (0.4, -0.6, 0.7)
    return (0.0, 0.0, 1.0)


@command(
    "ANALYZE",
    Arg("body", Raw, "", help="the body to look at; OFF (or empty) ends the analysis"),
    Arg("mode", str, "ZEBRA", "ZEBRA (smooth joins), CURVATURE (mean), GAUSS, or DRAFT"),
    Arg("dx", float, 0.0, "ZEBRA: where the light comes from (default: the view); DRAFT: the pull direction "
                          "(default +Z)"),
    Arg("dy", float, 0.0), Arg("dz", float, 0.0),
    Arg("angle", float, 1.0, "DRAFT: the least draft angle in degrees"),
    logged=False,
    help="Check a body's surfaces, in words and as colours in the view: ANALYZE, b (zebra stripes, and every "
         "join between faces judged G2, G1 or creased) · ANALYZE, b, CURVATURE (red curves out, blue in) · "
         "ANALYZE, b, GAUSS (dome, saddle or flat) · ANALYZE, b, DRAFT, 0, 0, 1, 2 (green and blue come out "
         "of the mould, red is too steep) · ANALYZE, OFF.",
)
def analyze(p: Processor, body, mode, dx, dy, dz, angle):
    word = body.strip()
    hook = getattr(p.view, "show_analysis", None) if p.view else None
    if not word or word.upper() == "OFF":
        p.analysis = None
        if hook:
            hook(None)
        return "analysis ended"
    bid = p._body_arg(REGISTRY["ANALYZE"], word)
    if mode not in an.MODES:
        raise CommandError(f"ANALYZE: the mode is one of {', '.join(an.MODES)}, got {mode}")
    shape = p.model.body(bid).shape
    if not p.model.body(bid).entity_ids["FACE"]:
        raise CommandError(f"ANALYZE: body {bid} has no faces (it is a curve)")
    if mode == "DRAFT" and not 0 <= angle < 90:
        raise CommandError("ANALYZE: the draft angle is from 0 to 90 degrees")
    d = _direction(p, mode, dx, dy, dz)
    if mode == "ZEBRA":
        msg = an.describe_joins(an.joins(shape, an.ids_of(p.model, bid, "EDGE")))
    else:
        try:
            m = an.mesh(shape)
        except ValueError as exc:
            raise CommandError(f"ANALYZE: {exc}") from None
        if mode == "DRAFT":
            msg = an.draft(m, d, angle, an.face_ids(p.model, bid, m))
        else:
            msg = an.curvature(m, gauss=mode == "GAUSS")
    p.analysis = Analysis(bid, mode, d, angle)
    if hook:
        hook(p.analysis)
    return f"ANALYZE body {bid}, {mode}: {msg}"


# ---- CONTINUITY, COMB, INSPECT ----------------------------------------------------------------------
def _exact_body(p: Processor, raw: str, what: str):
    from ..geometry import meshbody as mb
    from ..geometry import robust

    bid = p._body_arg(REGISTRY[what], raw)
    if bid not in p.model.bodies:
        raise CommandError(f"{what}: no body {raw.strip()}")
    shape = p.model.bodies[bid].shape
    if mb.is_mesh(shape):
        raise CommandError(f"{what}: body {bid} is a mesh body; it has no surfaces to judge (CHECK, {bid}, FLAWS "
                           "checks a mesh)")
    if not robust.count(shape, robust.TopAbs_FACE):
        raise CommandError(f"{what}: body {bid} has no faces")
    return bid, shape


def _xyz(v) -> str:
    return "(" + ", ".join(f"{x:.4g}" for x in v) + ")"


@command(
    "CONTINUITY",
    Arg("b", Raw, help="the body"),
    Arg("tol", float, 0.0, "faces further apart than this along an edge do not meet (0: a ten-thousandth of the size)"),
    Arg("fmt", str, "TEXT", "TEXT or JSON"),
    logged=False,
    help="How well the faces of a body join: CONTINUITY, b [, tol [, JSON]] judges every edge between two faces "
         "as open (a gap), sharp, a kink (a crease of a few degrees, nearly tangent), G1 (tangent, the curvature "
         "jumps) or G2 (curvature carries on), with the worst gap and angle.",
)
def continuity_cmd(p: Processor, b, tol, fmt):
    import json

    from ..geometry import inspect_surf as ins
    from ..geometry import robust

    bid, shape = _exact_body(p, b, "CONTINUITY")
    if tol < 0:
        raise CommandError("CONTINUITY: the tolerance cannot be negative")
    tol = tol or 1e-4 * robust.diagonal(shape)
    joints, open_edges = ins.continuity(shape, an.ids_of(p.model, bid, "EDGE"), an.ids_of(p.model, bid, "FACE"), tol)
    by = {k: [j for j in joints if j.kind == k] for k in ("open", "sharp", "kink", "G1", "G2")}
    if fmt == "JSON":
        return json.dumps({"body": bid, "tolerance": tol, "open_edges": open_edges,
                           "counts": {k: len(v) for k, v in by.items()},
                           "joins": [j.as_dict() for j in joints]}, separators=(",", ":"))
    worst_gap = max(joints, key=lambda j: j.gap, default=None)
    smooth = [j for j in joints if j.kind in ("kink", "G1", "G2")]
    worst_ang = max(smooth, key=lambda j: j.angle, default=None)
    lines = [f"body {bid}: {len(joints)} joins between faces: " + ", ".join(
        f"{len(by[k])} {name}" for k, name in (("G2", "G2 (curvature carries on)"), ("G1", "G1 (tangent)"),
                                               ("kink", "kinks"), ("sharp", "sharp"), ("open", "open")))]
    if worst_gap is not None:
        lines.append(f"  largest gap {worst_gap.gap:.3g} (edge {worst_gap.edge}); tolerance {tol:.3g}")
    if worst_ang is not None:
        lines.append(f"  of the smooth joins the largest angle is {worst_ang.angle:.3g} degrees (edge {worst_ang.edge})")
    for j in by["open"][:10]:
        lines.append(f"  open: edge {j.edge} between faces {j.faces[0]} and {j.faces[1]}: gap {j.gap:.3g} at {_xyz(j.at)}")
    for j in by["kink"][:10]:
        lines.append(f"  kink: edge {j.edge} between faces {j.faces[0]} and {j.faces[1]}: {j.angle:.3g} degrees at "
                     f"{_xyz(j.at)} (nearly tangent: meant to be smooth?)")
    if by["G1"]:
        ids = ", ".join(str(j.edge) for j in by["G1"][:12]) + (" ..." if len(by["G1"]) > 12 else "")
        lines.append(f"  G1 (the curvature jumps; zebra stripes kink there): edges {ids}")
    if open_edges:
        lines.append(f"  {open_edges} edge{'s' if open_edges != 1 else ''} with one face only (the skin is open)")
    return "\n".join(lines)


@command(
    "COMB",
    Arg("what", Raw, help="a body (all its edges), EDGE, n (one edge), or OFF"),
    Arg("n", Raw, "", "with EDGE: the edge ID"),
    Arg("scale", float, 0.0, "tooth length per unit of curvature (0: the longest tooth a tenth of the size)"),
    logged=False,
    help="Curvature combs: COMB, EDGE, 12 draws a comb on edge 12 (a tooth at each point, as long as the "
         "curvature there) and says its tightest bend and where the bend changes side · COMB, b does every "
         "curved edge of a body · COMB, OFF hides the combs.",
)
def comb_cmd(p: Processor, what, n, scale):
    from ..geometry import inspect_surf as ins
    from ..geometry import robust

    hook = getattr(p.view, "show_toolpath", None) if p.view else None
    word = what.strip().upper()
    if word == "OFF":
        if hook:
            hook(None)
        return "combs hidden"
    if scale < 0:
        raise CommandError("COMB: the scale cannot be negative")
    m = p.model
    if word == "EDGE":
        try:
            gid = int(p.evaluate(n))
        except Exception:  # noqa: BLE001
            raise CommandError("COMB: give an edge ID: COMB, EDGE, 12") from None
        try:
            edges = [(gid, m.entity_shape("EDGE", gid))]
            bid = m.entity_owner("EDGE", gid)[0]
        except Exception:  # noqa: BLE001
            raise CommandError(f"COMB: there is no edge {gid}") from None
    else:
        bid, _shape = _exact_body(p, what, "COMB")
        edges = [(g, m.entity_shape("EDGE", g)) for g in m.bodies[bid].entity_ids["EDGE"]]
    size = robust.diagonal(m.bodies[bid].shape)
    combs = []
    for gid, e in edges:
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.GeomAbs import GeomAbs_Line

        if BRepAdaptor_Curve(an._as_edge(e)).GetType() == GeomAbs_Line:
            continue
        combs.append(ins.comb(e, gid, scale=scale or 1.0, size=size))
    if not combs:
        return "no curved edges: every edge is straight (no curvature to show)"
    if scale == 0:  # one scale for all, so the teeth compare: the longest a tenth of the size
        big = max(float(abs(c.curvature).max()) for c in combs)
        sc = 0.1 * size / big if big > 0 else 0.0
        for c in combs:
            c.tips = c.points + (c.tips - c.points) * sc
    if hook:
        hook(ins.comb_shape(combs))
    tight = min(combs, key=lambda c: c.tightest)
    lines = [f"{len(combs)} curved edge{'s' if len(combs) != 1 else ''}: tightest bend radius {tight.tightest:.4g} "
             f"(edge {tight.edge})"]
    for c in combs[:12]:
        bend = "straight" if c.tightest == float("inf") else f"tightest radius {c.tightest:.4g}"
        inf = f", the bend changes side {c.inflections} time{'s' if c.inflections != 1 else ''}" if c.inflections else ""
        lines.append(f"  edge {c.edge}: {bend}{inf}")
    if len(combs) > 12:
        lines.append(f"  and {len(combs) - 12} more edges")
    lines.append("  COMB, OFF hides the combs")
    return "\n".join(lines)


@command(
    "INSPECT",
    Arg("b", Raw, help="the body"),
    Arg("tol", float, 0.0, "gaps and slivers smaller than this count (0: a ten-thousandth of the size)"),
    Arg("fmt", str, "TEXT", "TEXT or JSON"),
    logged=False,
    help="Places on a body worth a second look: INSPECT, b lists kinks (nearly tangent creases), gaps between "
         "faces, open edges, the tightest bend, the thinnest wall, sliver and tiny faces, each with its IDs.",
)
def inspect_cmd(p: Processor, b, tol, fmt):
    import json

    from ..geometry import inspect_surf as ins
    from ..geometry import robust

    bid, shape = _exact_body(p, b, "INSPECT")
    if tol < 0:
        raise CommandError("INSPECT: the tolerance cannot be negative")
    tol = tol or 1e-4 * robust.diagonal(shape)
    out = ins.inspect(shape, an.ids_of(p.model, bid, "EDGE"), an.ids_of(p.model, bid, "FACE"),
                      list(p.model.bodies[bid].entity_ids["FACE"]), tol)
    out["body"] = bid
    if fmt == "JSON":
        return json.dumps(out, separators=(",", ":"))
    n = out["suspicious"]
    lines = [f"body {bid}: " + (f"{n} place{'s' if n != 1 else ''} worth a second look" if n else
                                "nothing suspicious") + f" (tolerance {tol:.3g})"]
    for k in out["kinks"][:10]:
        lines.append(f"  kink: edge {k['edge']}, {k['angle']:.3g} degrees between faces {k['faces'][0]} and "
                     f"{k['faces'][1]}: nearly tangent, meant to be smooth?")
    for g in out["gaps"][:10]:
        lines.append(f"  gap: edge {g['edge']}, faces {g['faces'][0]} and {g['faces'][1]} are {g['gap']:.3g} apart")
    if out["open_edges"]:
        lines.append(f"  {out['open_edges']} open edges (the skin is not closed): HEAL, {bid}")
    for s in out["slivers"][:10]:
        lines.append(f"  sliver: face {s['face']}, {s['width']:.3g} wide")
    if out["tiny_faces"]:
        lines.append(f"  tiny faces: {', '.join(map(str, out['tiny_faces'][:10]))}")
    r = out["smallest_radius"]
    if r:
        lines.append(f"  tightest bend: radius {r['radius']:.4g} on face {r['face']} at {_xyz(r['at'])}"
                     + (" (very tight for the part's size)" if out["tight"] else ""))
    else:
        lines.append("  every face is flat")
    w = out.get("thinnest_wall")
    if w:
        lines.append(f"  thinnest wall: {w['t']:.4g} on face {w['face']} at {_xyz(w['at'])}")
    if out["g1"]:
        lines.append(f"  {len(out['g1'])} G1 joins (tangent, the curvature jumps): CONTINUITY, {bid} lists them")
    return "\n".join(lines)
