"""Scan to CAD, part 2 (geometry/scanfit.py): SEGMENT shows a mesh's regions and what each is
(plane, cylinder, sphere or freeform); RECONSTRUCT makes an exact solid from them."""

from __future__ import annotations

from collections import Counter

import numpy as np

from ..geometry import meshbody as mb
from ..geometry import robust
from ..geometry import scanfit as sf
from .mesh_handlers import MESH_OK, _need_mesh
from .processor import Arg, BodyRef, CommandError, Processor, command

MESH_OK.update({"SEGMENT", "RECONSTRUCT", "DEVIATION"})


def _regions(p: Processor, b: int, angle: float, tol: float, what: str):
    pts, t = _need_mesh(p, b, what)
    if not 1 <= angle <= 89:
        raise CommandError(f"{what}: the angle is 1 to 89 degrees")
    if tol < 0:
        raise CommandError(f"{what}: the tolerance cannot be negative")
    size = float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0)))
    tol = tol or 2e-3 * size
    labels = sf.segment(pts, t, angle)
    return pts, t, sf.recognise(pts, t, labels, tol), tol


def _summary(regions) -> str:
    c = Counter(r.shape.kind for r in regions)
    names = {"PLANE": "plane", "CYLINDER": "cylinder", "SPHERE": "sphere", "FREEFORM": "freeform"}
    return ", ".join(f"{c[k]} {names[k]}{'s' if c[k] != 1 else ''}" for k in names if c[k])


@command(
    "SEGMENT",
    Arg("b", BodyRef, help="a mesh body (a scan, an STL)"),
    Arg("angle", float, 25.0, "a bend sharper than this between triangles starts a new region (degrees)"),
    Arg("tol", float, 0.0, "how far points may be from a plane, cylinder or sphere to count as one "
                           "(0: 0.2% of the body's size)"),
    logged=False,
    help="Split a mesh into regions at its sharp edges and say what each is: SEGMENT, scan lists every region "
         "with its size and its plane, cylinder (or bore), sphere, or freeform fit · RECONSTRUCT makes the "
         "exact solid from them",
)
def segment(p: Processor, b, angle, tol):
    _pts, _t, regions, tol = _regions(p, b, angle, tol, "SEGMENT")
    lines = [f"body {b}: {len(regions)} regions ({_summary(regions)}), within {tol:.4g}:"]
    total = sum(r.area for r in regions) or 1.0
    for i, r in enumerate(regions[:60], 1):
        fit = f"{r.shape.words()}, off by up to {r.shape.worst:.3g}" if r.shape.kind != "FREEFORM" else "freeform"
        lines.append(f"  {i}: {len(r.tris):,} triangles, {100 * r.area / total:.1f}% of the area: {fit}")
    if len(regions) > 60:
        lines.append(f"  ... and {len(regions) - 60} more")
    return "\n".join(lines)


@command(
    "RECONSTRUCT",
    Arg("b", BodyRef, help="a closed mesh body made of flat, cylindrical and spherical faces"),
    Arg("angle", float, 25.0, "a bend sharper than this starts a new face (degrees)"),
    Arg("tol", float, 0.0, "how far the mesh may be from each fitted face (0: 0.2% of the body's size)"),
    help="Scan to CAD for machined parts: RECONSTRUCT, scan splits the mesh at its sharp edges, fits each "
         "region exactly as a plane, cylinder or sphere, and joins them into one solid (new body; the mesh "
         "stays). Rounded freeform regions are refused: fit those with FITSURF",
)
def reconstruct(p: Processor, b, angle, tol):
    from .handlers import _added

    pts, t, regions, tol = _regions(p, b, angle, tol, "RECONSTRUCT")
    if not mb.closed(t):
        raise CommandError(f"RECONSTRUCT: body {b} is open; it needs a closed mesh to know its inside")
    try:
        shape, _cells, _kept = sf.reconstruct(pts, t, regions)
    except sf.ScanError as exc:
        raise CommandError(f"RECONSTRUCT: body {b}: {exc}") from None
    if not robust.solids(shape) or not robust.checked_ok(shape, True):
        raise CommandError(f"RECONSTRUCT: body {b}: the joined faces do not make a valid solid "
                           "(try a smaller angle, or a larger tolerance)")
    vol = robust.volume(shape)
    mesh_vol = abs(mb.volume(pts, t))
    diff = 100 * (vol - mesh_vol) / mesh_vol if mesh_vol else 0.0
    body = p.model.add_body(shape)
    # how far the mesh is from what was made, face by face (faces trimmed against each other can
    # move a region's edge; the fit alone does not show that)
    from ..geometry import deviation as dv

    check = ""
    try:
        r = dv.deviation(pts, t, shape, tol, body.entity_ids.get("FACE"))
        check = (f"; the mesh is within ±{tol:.3g} at {100 * r.within:.1f}% of its points (largest "
                 f"{r.largest_out:+.3g} / {r.largest_in:+.3g}, RMS {r.rms:.3g})")
        off = [f.face for f in r.faces if f.points and f.within < 0.99]
        if off:
            p.warn(f"RECONSTRUCT: faces {', '.join(map(str, off[:10]))} of body {body.id} are off the mesh by more "
                   f"than {tol:.3g} in places; DEVIATION, {b}, {body.id}, {tol:.3g} shows where")
    except ValueError:
        pass
    return _added(p, body, f"RECONSTRUCT body {b}: {len(regions)} faces fitted ({_summary(regions)}) within "
                           f"{tol:.3g}; volume {vol:.6g}, {diff:+.2f}% against the mesh{check}")


# ---- DEVIATION: how far a scan is from the model -------------------------------------------------
def _xyz(v) -> str:
    return "(" + ", ".join(f"{x:.4g}" for x in v) + ")"


def deviation_text(r, scan: int, body: int) -> list[str]:
    tol = r.tol
    lines = [f"DEVIATION scan {scan} to body {body} (tolerance ±{tol:.4g}): {100 * r.within:.1f}% of "
             f"{r.points:,} points within; largest {r.largest_out:+.4g} / {r.largest_in:+.4g}, "
             f"mean {r.mean:+.4g}, RMS {r.rms:.4g}" + ("; tolerance met" if r.as_dict()["met"] else "")]
    off = [f for f in r.faces if f.points and f.within < 0.999999]
    if off:
        lines.append("  faces off the tolerance (worst first):")
        for f in sorted(off, key=lambda f: f.within)[:12]:
            lines.append(f"    face {f.face}: {100 * f.within:.1f}% within, RMS {f.rms:.4g}, worst {f.worst:+.4g} "
                         f"({f.points:,} points)")
        if len(off) > 12:
            lines.append(f"    and {len(off) - 12} more faces")
    elif r.faces:
        lines.append(f"  every face within ±{tol:.4g}")
    if r.outliers:
        x, y, z, d = r.outlier_worst
        lines.append(f"  outliers: {r.outliers:,} points more than {5 * tol:.4g} off in small separate pieces of the "
                     f"scan, left out of the numbers "
                     f"(the worst {d:+.4g} at {_xyz((x, y, z))})")
    if r.holes:
        big = r.holes[0]
        lines.append(f"  holes in the scan: {len(r.holes)} (the largest {big['length']:.4g} round, at "
                     f"{_xyz(big['centre'])}); the model is not measured there")
    if r.low:
        ids = ", ".join(str(f.face) for f in r.low[:10]) + (f" and {len(r.low) - 10} more" if len(r.low) > 10 else "")
        lines.append(f"  low confidence: the scan covers little of face{'s' if len(r.low) != 1 else ''} {ids} "
                     f"(under {int(100 * 0.8)}% of the area), so the numbers say little there")
    lines.append("  colours on the scan: green within the tolerance, yellow to red outside the model, cyan to blue "
                 "inside it, magenta or dark blue past three tolerances (ANALYZE, OFF ends them)")
    return lines


@command(
    "DEVIATION",
    Arg("scan", BodyRef, help="the scan: a mesh body (or any body: its points are measured)"),
    Arg("b", BodyRef, help="the model to measure against (an exact body)"),
    Arg("tol", float, 0.0, "the tolerance band, ± (0: 0.1% of the model's size)"),
    Arg("fmt", str, "TEXT", "TEXT or JSON"),
    logged=False,
    help="How far a scan is from the model: DEVIATION, scan, body [, tolerance [, JSON]] gives the share of "
         "points within ±tolerance, the largest distance out and in, the mean and RMS, the same for each face "
         "of the model, outliers, holes in the scan and faces it hardly covers; and colours the scan in the "
         "view by tolerance band. Positive is outside the model.",
)
def deviation_cmd(p: Processor, scan, b, tol, fmt):
    import json

    from ..geometry import deviation as dv
    from .analysis_handlers import Analysis

    if fmt not in ("TEXT", "JSON"):
        raise CommandError("DEVIATION: the format is TEXT or JSON")
    if scan == b:
        raise CommandError("DEVIATION: the scan and the model are the same body")
    if tol < 0:
        raise CommandError("DEVIATION: the tolerance cannot be negative")
    model = p.model.body(b)
    if mb.is_mesh(model.shape):
        raise CommandError(f"DEVIATION: body {b} is a mesh body; measure against an exact body (FITSURF or "
                           "RECONSTRUCT makes one)")
    if not robust.count(model.shape, robust.TopAbs_FACE):
        raise CommandError(f"DEVIATION: body {b} has no faces")
    shape = p.model.body(scan).shape
    from ..geometry import pointcloud as pc

    points_only = pc.is_points(shape)
    if points_only:  # a point cloud: no triangles, so no holes or pieces to look at
        pts, t = pc.arrays(shape), None
    elif mb.is_mesh(shape):
        pts, t = mb.arrays(shape)
    else:
        from ..geometry import analysis as an

        m = an.mesh(shape)
        pts, t = m.nodes, m.tris
    pts = np.asarray(pts, float)
    tol = tol or 1e-3 * robust.diagonal(model.shape)
    try:
        r = dv.deviation(pts, None if t is None else np.asarray(t), model.shape, tol, model.entity_ids.get("FACE"))
    except ValueError as exc:
        raise CommandError(f"DEVIATION: {exc}") from None
    d = {"scan": scan, "body": b, **r.as_dict()}
    p.give_report("DEVIATION", d)
    if points_only:  # the colours go on triangles; a cloud shows none
        return json.dumps(d, indent=1) if fmt == "JSON" else "\n".join(deviation_text(r, scan, b)[:-1])
    tg = dv.target(model.shape, min(tol / 4, robust.diagonal(model.shape) / 1000))
    p.analysis = Analysis(scan, "DEVIATION", (0.0, 0.0, 1.0), 0.0, field=dv.Field(tg), scale=tol)
    hook = getattr(p.view, "show_analysis", None) if p.view else None
    if hook:
        hook(p.analysis)
    if fmt == "JSON":
        return json.dumps(d, indent=1)
    return "\n".join(deviation_text(r, scan, b))
