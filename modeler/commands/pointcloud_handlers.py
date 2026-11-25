"""Point clouds (PLAN item 77, geometry/pointcloud.py): TOPOINTS samples a body as a made-up scan,
FITPOINTS fits a plane, cylinder, sphere, cone or freeform face to a patch of a point body and
says how far the points are from it, the way DEVIATION does. IMPORT reads .xyz, .pts, .ply and
.e57 points (project_handlers.py)."""

from __future__ import annotations

import json

import numpy as np

from ..geometry import pointcloud as pc
from ..geometry import robust
from .processor import Arg, BodyRef, CommandError, Processor, command


def need_points(p: Processor, b: int, what: str) -> np.ndarray:
    shape = p.model.body(b).shape
    if not pc.is_points(shape):
        raise CommandError(f"{what}: body {b} is not a point body (IMPORT a .xyz, .pts, .ply or .e57 file, or "
                           "TOPOINTS a body)")
    return pc.arrays(shape)


@command(
    "TOPOINTS",
    Arg("b", BodyRef, help="the body to sample"),
    Arg("count", int, 20000, "how many points, spread evenly over its surface"),
    Arg("noise", float, 0.0, "move each point up to ± this along the surface (like a scanner's noise)"),
    help="A point body from a body's surface: TOPOINTS, part, 20000, 0.02 makes a made-up scan to try point "
         "cloud work on, or to hand points to another program (new body; the body stays)",
)
def topoints(p: Processor, b, count, noise):
    from .handlers import _added

    if not 10 <= count <= pc.MOST_POINTS:
        raise CommandError(f"TOPOINTS: the count is 10 to {pc.MOST_POINTS:,}")
    if noise < 0:
        raise CommandError("TOPOINTS: the noise cannot be negative")
    shape = p.model.body(b).shape
    if pc.is_points(shape) or not robust.count(shape, robust.TopAbs_FACE):
        raise CommandError(f"TOPOINTS: body {b} has no faces to sample")
    pts = pc.sample(shape, count, noise)
    body = p.model.add_body(pc.make_shape(pts))
    return _added(p, body, f"TOPOINTS body {b}")


def fit_text(f: pc.Fit, r, b: int, n: int) -> list[str]:
    lines = [f"FITPOINTS {n:,} points of body {b}: {f.words()}"]
    if f.extra.get("tried"):
        tried = ", ".join(f"{k.lower()} {v:.3g}" for k, v in f.extra["tried"].items())
        lines.append(f"  RMS of each shape tried: {tried} (the simplest that fits nearly as well as the best wins)")
    lines.append(f"  the points to the face (tolerance ±{r.tol:.4g}): {100 * r.within:.1f}% within; largest "
                 f"{r.largest_out:+.4g} / {r.largest_in:+.4g}, RMS {r.rms:.4g}"
                 + ("; tolerance met" if r.as_dict()["met"] else ""))
    return lines


@command(
    "FITPOINTS",
    Arg("b", BodyRef, help="a point body"),
    Arg("kind", str, "AUTO", "PLANE, CYLINDER, SPHERE, CONE, FREEFORM, or AUTO (the simplest shape that fits)"),
    Arg("x", float, 0.0, "the patch's centre: pick a point of the cloud"),
    Arg("y", float, 0.0),
    Arg("z", float, 0.0),
    Arg("r", float, 0.0, "the patch: points within this distance of the centre (0: every point)"),
    Arg("tol", float, 0.0, "the tolerance band, ± (0: 0.1% of the patch's size)"),
    Arg("fmt", str, "TEXT", "TEXT or JSON"),
    help="Fit an exact face to a patch of a point cloud: FITPOINTS, scan, CYLINDER, x, y, z, 15 fits a "
         "cylinder to the points within 15 of (x, y, z) and makes it a face trimmed to the patch (new body). "
         "It says the fitted sizes (a radius, an axis, a cone's angle) and how far the points are from the face "
         "like DEVIATION: the share within ±tolerance, the largest distance out and in, the RMS",
)
def fitpoints(p: Processor, b, kind, x, y, z, r, tol, fmt):
    from ..geometry import deviation as dv
    from .handlers import _added

    if kind not in pc.KINDS:
        raise CommandError(f"FITPOINTS: kind is one of {', '.join(pc.KINDS)}")
    if fmt not in ("TEXT", "JSON"):
        raise CommandError("FITPOINTS: the format is TEXT or JSON")
    if r < 0 or tol < 0:
        raise CommandError("FITPOINTS: the radius and the tolerance cannot be negative")
    pts = pc.patch(need_points(p, b, "FITPOINTS"), (x, y, z), r)
    if len(pts) < 6:
        raise CommandError(f"FITPOINTS: only {len(pts)} points within {r:g} of ({x:g}, {y:g}, {z:g}); pick a point "
                           "of the cloud as the centre, or a larger radius")
    size = float(np.linalg.norm(np.ptp(pts, axis=0)))
    tol = tol or 1e-3 * size
    try:
        f = pc.fit(pts, kind, tol)
    except pc.CloudError as exc:
        raise CommandError(f"FITPOINTS: {exc}") from None
    try:
        res = dv.deviation(pts, None, f.face, tol)
    except ValueError as exc:
        raise CommandError(f"FITPOINTS: {exc}") from None
    body = p.model.add_body(f.face)
    d = {"body": b, "points": int(len(pts)), "kind": f.kind, "fit": _jsonable(f.params), "new_body": body.id,
         "tolerance": tol, "within": res.within, "largest_out": res.largest_out, "largest_in": res.largest_in,
         "rms": res.rms, "met": res.as_dict()["met"]}
    if f.extra.get("tried"):
        d["tried_rms"] = f.extra["tried"]
    p.give_report("FITPOINTS", d)
    added = _added(p, body, "FITPOINTS")
    if fmt == "JSON":
        return json.dumps(d, indent=1)
    return "\n".join(fit_text(f, res, b, len(pts)) + [added])


def _jsonable(params: dict) -> dict:
    out = {}
    for k, v in params.items():
        if isinstance(v, np.ndarray):
            out[k] = [round(float(x), 6) for x in v]
        elif isinstance(v, float):
            out[k] = round(v, 6)
        else:
            out[k] = v
    return out
