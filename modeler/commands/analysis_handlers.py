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
