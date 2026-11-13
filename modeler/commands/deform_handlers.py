"""Deformers: BEND, TWIST, TAPER, STRETCH and FLOW change a body in place
(it keeps its ID and its faces keep theirs); SWEEPVOL makes the volume a
tool sweeps along a path (see geometry/deform.py and geometry/sweptvol.py)."""

from __future__ import annotations

import numpy as np

from ..core.model import ModelError
from ..geometry import deform as dfm
from ..geometry import nurbs as nb
from ..geometry import robust
from ..geometry import sweep as sw
from ..geometry import sweptvol as sv
from ..lang.expr import fmt_num
from ..lang.script import is_ident
from .curve_handlers import _Law, _new, _wire
from .processor import Arg, BodyRef, CommandError, Processor, Raw, command


def _axis(p: Processor, bid: int, word: str, what: str) -> str:
    w = word.strip().upper()
    if not w:  # the body's longest side
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib

        box = Bnd_Box()
        BRepBndLib.AddOptimal_s(p.model.body(bid).shape, box, False, False)
        lo, hi = box.CornerMin(), box.CornerMax()
        d = [hi.X() - lo.X(), hi.Y() - lo.Y(), hi.Z() - lo.Z()]
        return "XYZ"[int(np.argmax(d))]
    if w not in dfm.AXES:
        raise CommandError(f"{what}: the axis is X, Y or Z, got {word}")
    return w


def _law(p: Processor, text: str, what: str):
    """A law in t (0 at the start of the body, 1 at the end) as a numpy function; None for the plain t."""
    src = text.strip()
    if not src or src.upper() == "T":
        return None
    law = _Law(p, src, what, 0.0)

    def fn(t):
        t = np.asarray(t, float)
        return np.array([law(float(x)) for x in t.ravel()]).reshape(t.shape)

    # the same t is asked for again and again: evaluate the law once on a fine table
    ts = np.linspace(0.0, 1.0, 801)
    table = fn(ts)
    return lambda t: np.interp(np.asarray(t, float), ts, table)


def _apply(p: Processor, bid: int, fn, what: str, how: str) -> str:
    from .handlers import _added

    m = p.model
    old = m.body(bid).shape
    try:
        new, err, faceted = dfm.deform(old, fn)
    except dfm.DeformError as exc:
        raise CommandError(f"{what}: {exc}") from None
    except Exception as exc:  # noqa: BLE001  (a kernel failure on an odd shape)
        raise CommandError(f"{what}: the kernel could not deform body {bid} ({exc})") from None
    maker = nb.SameTopology(old, new)
    try:
        body = m.replace([bid], new, maker, same_id=True)
    except ModelError as exc:
        raise CommandError(f"{what}: {exc}") from None
    note = "as a mesh: its corner points moved" if faceted else f"fitted within {err:.2g}"
    return _added(p, body, f"{what} body {bid} {how} ({note})")


@command(
    "BEND",
    Arg("body", BodyRef),
    Arg("angle", help="degrees the body turns from one end to the other"),
    Arg("axis", str, "", "X, Y or Z: the length that bends (default: the body's longest side)"),
    Arg("toward", str, "", "the side it bends towards: X, Y, Z, -X, -Y or -Z (default Z, or X for an axis Z)"),
    Arg("law", Raw, "", "how much of the bend is done by t (0 to 1 along the body); default even, t"),
    help="Bend a body into an arc: its centre line keeps its length and turns by the angle: BEND, bar, 90 · "
         "BEND, bar, 90, X, -Z (downwards) · BEND, bar, 120, X, Z, t**2 (more bend at the far end). The body "
         "keeps its ID and its faces theirs.",
)
def bend(p: Processor, body, angle, axis, toward, law):
    ax = _axis(p, body, axis, "BEND")
    try:
        f = dfm.frame_of(p.model.body(body).shape, ax, toward or None)
        fn = dfm.bend(f, angle, _law(p, law, "BEND law"))
    except dfm.DeformError as exc:
        raise CommandError(str(exc) if str(exc).startswith("BEND") else f"BEND: {exc}") from None
    up = "+" + (toward or ("Z" if ax != "Z" else "X")) if not (toward or "").startswith("-") else toward
    return _apply(p, body, fn, "BEND", f"by {fmt_num(angle)} degrees along {ax} towards {up}")


@command(
    "TWIST",
    Arg("body", BodyRef), Arg("angle", help="degrees the far end turns"),
    Arg("axis", str, "", "X, Y or Z (default: the body's longest side)"),
    Arg("law", Raw, "", "how much of the turn is done by t (default t: evenly)"),
    help="Twist a body about an axis through its middle: one end stays, the other turns by the angle: TWIST, "
         "bar, 90 · TWIST, bar, 180, Z, t**2 · TWIST, bar, 45, X, sin(180*t) (out and back).",
)
def twist(p: Processor, body, angle, axis, law):
    ax = _axis(p, body, axis, "TWIST")
    f = dfm.frame_of(p.model.body(body).shape, ax)
    return _apply(p, body, dfm.twist(f, angle, _law(p, law, "TWIST law")), "TWIST",
                  f"by {fmt_num(angle)} degrees about {ax}")


@command(
    "TAPER",
    Arg("body", BodyRef), Arg("scale", help="the size of the far end's cross-section (1 = unchanged)"),
    Arg("axis", str, "", "X, Y or Z (default: the body's longest side)"),
    Arg("law", Raw, "", "how much of the change is done by t (default t: evenly)"),
    help="Taper a body: its cross-section grows or shrinks along an axis, about the axis through its middle: "
         "TAPER, column, 0.5 · TAPER, vase, 1.4, Z, sin(180*t) (wider in the middle).",
)
def taper(p: Processor, body, scale, axis, law):
    ax = _axis(p, body, axis, "TAPER")
    f = dfm.frame_of(p.model.body(body).shape, ax)
    try:
        fn = dfm.taper(f, scale, _law(p, law, "TAPER law"))
        fn(np.array([f.o, f.o + f.a * f.L]))  # (a scale at or below 0 is reported now)
    except dfm.DeformError as exc:
        raise CommandError(str(exc)) from None
    return _apply(p, body, fn, "TAPER", f"to {fmt_num(scale)} along {ax}")


@command(
    "STRETCH",
    Arg("body", BodyRef), Arg("factor", help="how much longer (2 = twice as long, 0.5 = half)"),
    Arg("axis", str, "", "X, Y or Z (default: the body's longest side)"),
    Arg("mode", str, "KEEP", "KEEP the volume (the sides grow thinner) or FREE (only the length changes)"),
    help="Stretch a body along an axis from its start; the sides shrink to keep its volume: STRETCH, bar, 1.5 · "
         "STRETCH, bar, 1.5, X, FREE.",
)
def stretch(p: Processor, body, factor, axis, mode):
    if mode not in ("KEEP", "FREE"):
        raise CommandError("STRETCH: the mode is KEEP or FREE")
    ax = _axis(p, body, axis, "STRETCH")
    f = dfm.frame_of(p.model.body(body).shape, ax)
    try:
        fn = dfm.stretch(f, factor, mode == "KEEP")
    except dfm.DeformError as exc:
        raise CommandError(str(exc)) from None
    return _apply(p, body, fn, "STRETCH", f"by {fmt_num(factor)} along {ax}"
                  + (", volume kept" if mode == "KEEP" else ""))


@command(
    "FLOW",
    Arg("body", BodyRef, help="the body to lay along the curve (text, a pattern, a strip)"),
    Arg("curve", BodyRef, help="the curve it follows"),
    *[Arg(f"a{i}", Raw, "") for i in range(1, 5)],
    help="Lay a body along a curve: its length (along an axis, default its longest side) runs along the curve "
         "from the curve's start, and its cross-section turns with the curve: FLOW, label, arc · FLOW, label, "
         "arc, FIT (stretched to the curve's length) · FLOW, label, arc, X, 12 (start 12 along the curve) · "
         "add FRENET to follow the curve's bend (default MINTWIST). The body's up side (+Z, or +X for an axis "
         "Z) stays on the curve's up side, as for a SWEEP profile.",
)
def flow(p: Processor, body, curve, **raws):
    if body == curve:
        raise CommandError("FLOW: the body cannot follow itself")
    fit, mode, axis, start = False, "MINTWIST", "", 0.0
    for raw in (r.strip() for r in raws.values()):
        if not raw:
            continue
        up = raw.upper()
        if is_ident(raw) and up == "FIT":
            fit = True
        elif is_ident(raw) and up in sw.MODES:
            mode = up
        elif is_ident(raw) and up in dfm.AXES:
            axis = up
        else:
            v = p.evaluate(raw)
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise CommandError(f"FLOW: {raw} is not FIT, a mode, an axis or a start distance")
            start = float(v)
    ax = _axis(p, body, axis, "FLOW")
    path = _wire(p, curve, "the FLOW curve")
    f = dfm.frame_of(p.model.body(body).shape, ax)
    try:
        fn = dfm.flow(f, path, fit, mode, start)
    except (dfm.DeformError, sw.CurveError) as exc:
        raise CommandError(str(exc) if str(exc).startswith("FLOW") else f"FLOW: {exc}") from None
    how = f"along curve {curve}" + (", fitted to its length" if fit else "") + \
          (f", from {fmt_num(start)}" if start else "")
    return _apply(p, body, fn, "FLOW", how)


@command(
    "SWEEPVOL",
    Arg("tool", BodyRef, help="the moving body (a cutter), placed where the path starts"),
    Arg("path", BodyRef, help="the curve it moves along; it does not turn on the way"),
    help="The volume a tool sweeps through as it moves along a path without turning, as a new body to cut "
         "away: SWEEPVOL, cutter, track then SUBTRACT, part, LAST. Exact for a ball, and for a cylinder (an end "
         "mill) moving square to its axis; other tools are copied closely along the path (the message says how "
         "high the ridges between copies can be).",
)
def sweepvol(p: Processor, tool, path):
    m = p.model
    if tool == path:
        raise CommandError("SWEEPVOL: the tool cannot be its own path")
    if not robust.solids(m.body(tool).shape):
        raise CommandError(f"SWEEPVOL: body {tool} is not a solid")
    pw = _wire(p, path, "the SWEEPVOL path")
    try:
        shape, how, ridge = sv.swept_volume(m.body(tool).shape, pw)
    except (sv.SweptVolumeError, sw.CurveError) as exc:
        raise CommandError(f"SWEEPVOL: {exc}") from None
    extra = "" if ridge == 0 else f"; ridges between them up to {ridge:.2g} high"
    return _new(p, shape, f"SWEEPVOL of body {tool} along curve {path} ({how}{extra})", solid=True)


