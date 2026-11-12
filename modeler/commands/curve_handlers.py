"""Shapes on curves: paths, profiles, LOFT, SWEEP, MORPH, PIPE.

Curves (paths and profiles) are ordinary bodies holding a wire. Lofts and
sweeps make new bodies and leave their curves in place, so a profile or a
path can be used again.

Laws are expressions in ``t``: 0 at the start of the path, 1 at the end.
They can use parameters and every math function: ``SWEEP, foil, span,
40 - 32*t, 1 - 0.5*t``.
"""

from __future__ import annotations

import ast
from typing import Callable

from ..geometry import curves as cv
from ..geometry import robust
from ..geometry import sweep as sw
from ..lang.expr import ExprError, Vec, format_value
from ..lang.script import is_ident
from .processor import REGISTRY, Arg, BodyRef, CommandError, Processor, Raw, Text, command

_PLANE = (
    Arg("nx", float, 0.0, "plane normal (default +Z)"),
    Arg("ny", float, 0.0),
    Arg("nz", float, 1.0),
    Arg("angle", float, 0.0, "turn the profile in its plane (degrees)"),
)
_MAX_POINTS = 32
_POINTS = [Arg(f"p{i}", Raw, "") for i in range(1, _MAX_POINTS + 1)]


def _new(p: Processor, shape, what: str, solid: bool | None = None) -> str:
    """Add a shape made from curves, after checking it (see robust.check_made).
    ``solid``: whether a closed solid was asked for (None: if the shape has one)."""
    from .handlers import _added

    name = what.split()[0]
    if solid is None:
        solid = bool(robust.solids(shape))
    try:
        shape, notes = robust.check_made(shape, name, solid)
    except robust.ShapeError as exc:
        raise CommandError(str(exc)) from None
    for note in notes:
        p.warn(note)
    return _added(p, p.model.add_body(shape), what)


def _curve(p: Processor, fn, *args, what: str, **kw) -> str:
    from .feature_handlers import place

    try:
        shape = fn(*args, **kw)
    except cv.CurveError as exc:
        raise CommandError(str(exc) if str(exc).startswith(what) else f"{what}: {exc}") from None
    shape = place(p, shape)  # onto the work plane, if one is set
    b = p.model.add_body(shape)
    kind = "closed" if shape.Closed() else "open"
    name = "" if b.name == f"body{b.id}" else f" '{b.name}'"
    return f"{what} -> curve {b.id}{name} ({kind}, length {_fmt(sw.PathSampler(shape).length)})"


def _fmt(x: float) -> str:
    return f"{x:.4g}"


def _wire(p: Processor, bid: int, what: str):
    try:
        return sw.as_wire(p.model.body(bid).shape, what)
    except cv.CurveError as exc:
        raise CommandError(f"{exc} (body {bid})") from None


# ---- points and laws -------------------------------------------------------------
def _points(p: Processor, raws: list[str], what: str, allow_close: bool = True) -> tuple[list[tuple], bool]:
    pts: list[tuple] = []
    closed = False
    items = [r for r in raws if r.strip()]
    for k, raw in enumerate(items):
        word = raw.strip().upper()
        if allow_close and word == "CLOSE" and k == len(items) - 1:
            closed = True
            continue
        try:
            v = p.evaluate(raw)
        except ExprError as exc:
            raise CommandError(f"{what}: point {k + 1}: {exc}") from None
        if not isinstance(v, Vec):
            raise CommandError(f"{what}: point {k + 1} must be a point like (10, 0, 5), got {format_value(v)}")
        pts.append((v[0], v[1], v[2] if len(v) > 2 else 0.0))
    return pts, closed


def _uses_t(text: str) -> bool:
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except SyntaxError:
        return True
    return any(isinstance(n, ast.Name) and n.id.upper() == "T" for n in ast.walk(tree))


def _string_literal(text: str) -> str | None:
    try:
        node = ast.parse(text.strip(), mode="eval").body
    except SyntaxError:
        return None
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


class _Law:
    """A law from expression text; ``value`` is set when it does not depend on t."""

    def __init__(self, p: Processor, text: str, what: str, default: float):
        src = text.strip() or format_value(default)
        quoted = _string_literal(src)
        if quoted is not None:  # a quoted law: "40 - 32*t"
            src = quoted
        self.p, self.src, self.what = p, src, what
        self.value: float | None = None
        if not _uses_t(src):
            self.value = self._num(p.evaluate(src), None)
        else:
            self(0.0)  # report mistakes now, not halfway along the path

    def _num(self, v, t) -> float:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            at = "" if t is None else f" at t = {t:g}"
            raise CommandError(f"{self.what}: {self.src!r} must give a number{at}, got {format_value(v)}")
        return float(v)

    def __call__(self, t: float) -> float:
        if self.value is not None:
            return self.value
        base = dict(self.p._scopes[-1]) if self.p._scopes else {}
        base["T"] = t
        self.p._scopes.append(base)
        try:
            return self._num(self.p.evaluate(self.src), t)
        except ExprError as exc:
            raise CommandError(f"{self.what}: {exc}") from None
        finally:
            self.p._scopes.pop()

    def is_(self, v: float) -> bool:
        return self.value is not None and abs(self.value - v) < 1e-12


def _mode(mode: str, what: str) -> str:
    m = mode.upper() or "MINTWIST"
    if m not in sw.MODES:
        raise CommandError(f"{what}: mode must be one of {', '.join(sw.MODES)}, got {mode!r}")
    return m


def _run(what: str, fn: Callable, *a, **kw):
    try:
        return fn(*a, **kw)
    except cv.CurveError as exc:
        msg = str(exc)
        for prefix in ("LOFT: ", "SWEEP: ", "MORPH: ", "SPINELOFT: ", "RAILSWEEP: ", "PIPE: "):
            if msg.startswith(prefix):
                msg = msg[len(prefix):]
        raise CommandError(f"{what}: {msg}") from None


# =============================================================================
# Paths
# =============================================================================


@command("LINE", Arg("x1"), Arg("y1"), Arg("z1"), Arg("x2"), Arg("y2"), Arg("z2"),
         help="Straight curve from (x1,y1,z1) to (x2,y2,z2).")
def line(p: Processor, x1, y1, z1, x2, y2, z2):
    return _curve(p, cv.line, (x1, y1, z1), (x2, y2, z2), what="LINE")


@command("ARC", Arg("x1"), Arg("y1"), Arg("z1"), Arg("x2"), Arg("y2"), Arg("z2"), Arg("x3"), Arg("y3"), Arg("z3"),
         help="Circular arc from point 1 through point 2 to point 3.")
def arc(p: Processor, x1, y1, z1, x2, y2, z2, x3, y3, z3):
    return _curve(p, cv.arc3, (x1, y1, z1), (x2, y2, z2), (x3, y3, z3), what="ARC")


@command("POLYLINE", *_POINTS,
         help="Straight segments through points: POLYLINE, (0,0,0), (10,0,0), (10,10,0). End with CLOSE to close it.")
def polyline(p: Processor, **pts):
    points, closed = _points(p, list(pts.values()), "POLYLINE")
    return _curve(p, cv.polyline, points, closed, what="POLYLINE")


@command("SPLINE", *_POINTS,
         help="Smooth curve through points: SPLINE, (0,0,0), (10,5,0), (20,0,4). End with CLOSE for a closed loop.")
def spline_(p: Processor, **pts):
    points, closed = _points(p, list(pts.values()), "SPLINE")
    return _curve(p, cv.spline, points, closed, what="SPLINE")


@command(
    "HELIX",
    Arg("x"), Arg("y"), Arg("z"), Arg("r"), Arg("pitch", help="rise per turn"), Arg("turns"),
    Arg("dx", float, 0.0, "axis direction (default +Z)"), Arg("dy", float, 0.0), Arg("dz", float, 1.0),
    Arg("taper", float, 0.0, "cone angle in degrees (radius grows with height)"),
    Arg("hand", str, "RIGHT", "RIGHT or LEFT"),
    Arg("plaw", Raw, "1", "pitch law in t (multiplies the pitch), e.g. 0.5 + t"),
    help="Helix around the axis through (x,y,z); it starts on the +X side (the profile X side for other axes).",
)
def helix(p: Processor, x, y, z, r, pitch, turns, dx, dy, dz, taper, hand, plaw):
    if hand not in ("RIGHT", "LEFT"):
        raise CommandError("HELIX: hand must be RIGHT or LEFT")
    law = _Law(p, plaw, "HELIX pitch law", 1.0)
    return _curve(p, cv.helix, (x, y, z), (dx, dy, dz), r, pitch, turns, taper, hand == "LEFT",
                  None if law.is_(1.0) else law, what="HELIX")


@command(
    "CURVE",
    Arg("kind", str, help="PARAM"), Arg("fx", Raw), Arg("fy", Raw), Arg("fz", Raw),
    Arg("t0", float, 0.0), Arg("t1", float, 1.0), Arg("n", int, 64, "samples (the curve is fitted through them)"),
    help="Equation curve: CURVE, PARAM, 20*cos(t), 20*sin(t), 3*t, 0, 4*pi. Closes itself when it ends where it starts.",
)
def curve(p: Processor, kind, fx, fy, fz, t0, t1, n):
    if kind != "PARAM":
        raise CommandError("CURVE: the only kind so far is PARAM")
    if not 4 <= n <= 2000:
        raise CommandError("CURVE: n must be from 4 to 2000")
    if t1 <= t0:
        raise CommandError("CURVE: t1 must be greater than t0")
    laws = [_Law(p, f, f"CURVE {a}", 0.0) for a, f in zip("xyz", (fx, fy, fz))]
    pts = [tuple(law(t0 + (t1 - t0) * i / n) for law in laws) for i in range(n + 1)]
    closed = cv.norm(cv.sub(pts[0], pts[-1])) < 1e-9 * max(1.0, max(cv.norm(q) for q in pts))
    return _curve(p, cv.spline, pts[:-1] if closed else pts, closed, what="CURVE")


# =============================================================================
# Profiles
# =============================================================================


@command("CIRCLE", Arg("x"), Arg("y"), Arg("z"), Arg("r"), *_PLANE,
         help="Circle profile centered at (x,y,z) in the plane with normal (nx,ny,nz).")
def circle(p: Processor, x, y, z, r, nx, ny, nz, angle):
    return _curve(p, cv.circle, (x, y, z), r, (nx, ny, nz), angle, what="CIRCLE")


@command("ELLIPSE", Arg("x"), Arg("y"), Arg("z"), Arg("a", help="half-width along profile X"),
         Arg("b", help="half-height along profile Y"), *_PLANE, help="Ellipse profile.")
def ellipse(p: Processor, x, y, z, a, b, nx, ny, nz, angle):
    return _curve(p, cv.ellipse, (x, y, z), a, b, (nx, ny, nz), angle, what="ELLIPSE")


@command("RECT", Arg("x"), Arg("y"), Arg("z"), Arg("w"), Arg("h"), Arg("r", float, 0.0, "corner radius"), *_PLANE,
         help="Rectangle profile w by h centered at (x,y,z), optional corner radius.")
def rect(p: Processor, x, y, z, w, h, r, nx, ny, nz, angle):
    return _curve(p, cv.rect, (x, y, z), w, h, r, (nx, ny, nz), angle, what="RECT")


@command("POLYGON", Arg("x"), Arg("y"), Arg("z"), Arg("r", help="corner circle radius"), Arg("sides", int), *_PLANE,
         Arg("corner", float, 0.0, "corner rounding radius"), help="Regular polygon profile.")
def polygon(p: Processor, x, y, z, r, sides, nx, ny, nz, angle, corner):
    return _curve(p, cv.polygon, (x, y, z), r, sides, (nx, ny, nz), angle, corner, what="POLYGON")


@command("STAR", Arg("x"), Arg("y"), Arg("z"), Arg("ro", help="outer radius"), Arg("ri", help="inner radius"),
         Arg("points", int), *_PLANE, help="Star profile.")
def star(p: Processor, x, y, z, ro, ri, points, nx, ny, nz, angle):
    return _curve(p, cv.star, (x, y, z), ro, ri, points, (nx, ny, nz), angle, what="STAR")


@command("SLOT", Arg("x"), Arg("y"), Arg("z"), Arg("length"), Arg("width"), *_PLANE,
         help="Slot (stadium) profile, length along profile X.")
def slot(p: Processor, x, y, z, length, width, nx, ny, nz, angle):
    return _curve(p, cv.slot, (x, y, z), length, width, (nx, ny, nz), angle, what="SLOT")


@command("AIRFOIL", Arg("x"), Arg("y"), Arg("z"), Arg("chord"), Arg("code", Text, "0012", "NACA 4-digit code"), *_PLANE,
         Arg("pivot", float, 0.25, "point of the chord placed at (x,y,z), as a fraction"),
         help="NACA 4-digit airfoil profile (e.g. 2412), chord along profile X.")
def airfoil(p: Processor, x, y, z, chord, code, nx, ny, nz, angle, pivot):
    return _curve(p, cv.airfoil, (x, y, z), chord, str(code), (nx, ny, nz), angle, pivot, what="AIRFOIL")


# =============================================================================
# Loft, sweep, morph, pipe
# =============================================================================

_LOFT_WORDS = ("RULED", "CLOSED", "SURFACE")


@command("LOFT", *[Arg(f"a{i}", Raw, "") for i in range(1, 25)],
         help="Smooth solid through section curves: LOFT, s1, s2, s3. Add RULED (straight between sections), "
              "CLOSED (loop back to the first) or SURFACE (no caps).")
def loft(p: Processor, **raws):
    words, ids = set(), []
    for raw in (r.strip() for r in raws.values()):
        if not raw:
            continue
        if is_ident(raw) and raw.upper() in _LOFT_WORDS:
            words.add(raw.upper())
            continue
        ids.append(p._body_arg(REGISTRY["LOFT"], raw))
    if len(ids) < 2:
        raise CommandError("LOFT: give at least 2 section curves")
    if len(set(ids)) != len(ids) and "CLOSED" not in words:
        raise CommandError("LOFT: a section is used twice")
    wires = [_wire(p, b, "a LOFT section") for b in ids]
    shape = _run("LOFT", sw.loft, wires, solid="SURFACE" not in words, ruled="RULED" in words, closed="CLOSED" in words)
    return _new(p, shape, f"LOFT through {len(ids)} sections")


_SPINE_WORDS = ("SURFACE",) + tuple(sw.MODES)


@command("SPINELOFT", Arg("spine", BodyRef, help="the centre line the sections follow"),
         *[Arg(f"a{i}", Raw, "") for i in range(1, 17)],
         help="Loft through sections placed along a curved centre line: SPINELOFT, spine, s1, s2, s3. Draw each "
              "section where it belongs, across the spine; between them the shape blends smoothly and stays square "
              "to the spine. Add FRENET or FIXED (how the sections turn, default MINTWIST) or SURFACE (no caps).")
def spineloft(p: Processor, spine, **raws):
    words, ids = set(), []
    for raw in (r.strip() for r in raws.values()):
        if not raw:
            continue
        if is_ident(raw) and raw.upper() in _SPINE_WORDS:
            words.add(raw.upper())
            continue
        ids.append(p._body_arg(REGISTRY["SPINELOFT"], raw))
    if len(ids) < 2:
        raise CommandError("SPINELOFT: give the spine and at least 2 section curves")
    if len(set(ids)) != len(ids):
        raise CommandError("SPINELOFT: a section is used twice")
    if spine in ids:
        raise CommandError("SPINELOFT: the spine cannot also be a section")
    modes = [w for w in words if w in sw.MODES]
    if len(modes) > 1:
        raise CommandError("SPINELOFT: give one of MINTWIST, FRENET or FIXED")
    sp = _wire(p, spine, "the SPINELOFT spine")
    wires = [_wire(p, b, "a SPINELOFT section") for b in ids]
    shape, used, ts = _run("SPINELOFT", sw.spine_loft, wires, sp, modes[0] if modes else "MINTWIST", 0,
                           "SURFACE" not in words)
    at = ", ".join(f"{t:.3g}" for t in ts)
    return _new(p, shape, f"SPINELOFT through {len(ids)} sections at t = {at} ({used} loft sections)")


_LAW_ARGS = (
    Arg("twist", Raw, "0", "twist law in degrees, e.g. 40 - 32*t"),
    Arg("scale", Raw, "1", "scale law, e.g. 1 - 0.5*t"),
)


def _do_sweep(p: Processor, what: str, profiles: list[int], path: int, twist, scale, mode, sx="1", sy="1",
              ox="0", oy="0", n=0, solid=1, stations=None) -> str:
    mode = _mode(mode, what)
    pw = _wire(p, path, f"the {what} path")
    prof = [_wire(p, b, f"a {what} profile") for b in profiles]
    laws = {
        "twist": _Law(p, twist, f"{what} twist", 0.0),
        "scale": _Law(p, scale, f"{what} scale", 1.0),
        "sx": _Law(p, sx, f"{what} sx", 1.0),
        "sy": _Law(p, sy, f"{what} sy", 1.0),
        "ox": _Law(p, ox, f"{what} ox", 0.0),
        "oy": _Law(p, oy, f"{what} oy", 0.0),
    }
    plain = {k: law.is_(1.0 if k in ("scale", "sx", "sy") else 0.0) for k, law in laws.items()}
    if n < 0:
        raise CommandError(f"{what}: n must be 0 (automatic) or more")
    if len(prof) == 1 and all(plain.values()) and n == 0:
        shape = _run(what, sw.exact_sweep, prof[0], pw, mode, bool(solid), what)
        how = "exact"
    elif len(prof) == 1 and n == 0 and all(v for k, v in plain.items() if k != "scale"):
        shape = _run(what, sw.law_sweep, prof[0], pw, laws["scale"], mode, bool(solid), what)
        how = "exact, scale law"
    else:
        shape, used = _run(what, sw.section_sweep, prof, pw, laws["twist"], laws["scale"], laws["sx"], laws["sy"],
                           laws["ox"], laws["oy"], mode, n, bool(solid), stations)
        how = f"{used} sections"
    return _new(p, shape, f"{what} ({how})")


@command(
    "SWEEP",
    Arg("profile", BodyRef), Arg("path", BodyRef), *_LAW_ARGS,
    Arg("mode", str, "MINTWIST", "MINTWIST, FRENET or FIXED"),
    Arg("sx", Raw, "1", "extra scale along the profile's X (side), law in t"),
    Arg("sy", Raw, "1", "extra scale along the profile's Y (up), law in t"),
    Arg("ox", Raw, "0", "offset along the side direction, law in t"),
    Arg("oy", Raw, "0", "offset along the up direction, law in t"),
    Arg("n", int, 0, "number of sections (0 = automatic)"),
    Arg("solid", int, 1, "1 = solid, 0 = surface only"),
    help="Move a profile along a path. Laws in t (0 at the start, 1 at the end) twist, scale, stretch or offset it.",
)
def sweep(p: Processor, profile, path, twist, scale, mode, sx, sy, ox, oy, n, solid):
    return _do_sweep(p, "SWEEP", [profile], path, twist, scale, mode, sx, sy, ox, oy, n, solid)


@command(
    "MORPH",
    Arg("path", BodyRef), *_LAW_ARGS, Arg("mode", str, "MINTWIST", "MINTWIST, FRENET or FIXED"),
    *[Arg(f"s{i}", BodyRef, 0) for i in range(1, 9)],
    help="Sweep that changes shape: the profiles s1, s2, ... (drawn at the start of the path) are reached at evenly "
         "spaced points along it. Repeat a profile to hold a shape longer.",
)
def morph(p: Processor, path, twist, scale, mode, **ss):
    profiles = [b for b in ss.values() if b]
    if len(profiles) < 2:
        raise CommandError("MORPH: give at least 2 profiles")
    return _do_sweep(p, "MORPH", profiles, path, twist, scale, mode)


@command(
    "RAILSWEEP",
    Arg("profile", BodyRef), Arg("rail1", BodyRef, help="the rail a point of the profile follows"),
    Arg("rail2", BodyRef, 0, "a second rail: the profile spans both (0 = one rail)"),
    Arg("path", BodyRef, 0, "the curve the sections stand square to (0 = rail 1)"),
    Arg("thick", Raw, "1", "two rails: thickness law in t, square to the line between the rails"),
    Arg("fit", str, "SCALE", "one rail: SCALE (turn and grow to reach the rail) or TURN (turn only)"),
    Arg("n", int, 0, "number of sections (0 = automatic)"),
    Arg("solid", int, 1, "1 = solid, 0 = surface only"),
    help="Sweep steered by rails. Draw the profile where the sweep starts, touching the rails. One rail: the "
         "profile turns about the path so its point on the rail stays on it. Two rails: it turns, moves and scales "
         "to span both (a wing between leading and trailing edges): RAILSWEEP, foil, le, te, spine · "
         "RAILSWEEP, foil, le, te, spine, 1 - 0.3*t (thinner towards the tip).",
)
def railsweep(p: Processor, profile, rail1, rail2, path, thick, fit, n, solid):
    if fit not in sw.RAIL_FITS:
        raise CommandError(f"RAILSWEEP: fit must be {' or '.join(sw.RAIL_FITS)}")
    if n < 0:
        raise CommandError("RAILSWEEP: n must be 0 (automatic) or more")
    law = _Law(p, thick, "RAILSWEEP thickness", 1.0)
    if rail2 == 0 and not law.is_(1.0):
        raise CommandError("RAILSWEEP: a thickness law needs two rails")
    if rail2 and fit != "SCALE":
        raise CommandError("RAILSWEEP: with two rails the rails set the size; leave fit out")
    prof = _wire(p, profile, "the RAILSWEEP profile")
    rails = [_wire(p, rail1, "rail 1")] + ([_wire(p, rail2, "rail 2")] if rail2 else [])
    pw = _wire(p, path, "the RAILSWEEP path") if path else rails[0]
    shape, used = _run("RAILSWEEP", sw.rail_sweep, prof, pw, rails, fit, None if law.is_(1.0) else law, n,
                       bool(solid))
    how = "two rails" if rail2 else "one rail" + (", turn only" if fit == "TURN" else "")
    return _new(p, shape, f"RAILSWEEP ({how}, {used} sections)")


@command(
    "PIPE",
    Arg("path", BodyRef), Arg("r"), Arg("ri", float, 0.0, "inner radius for a hollow pipe"),
    Arg("rlaw", Raw, "1", "radius law in t (multiplies both radii)"),
    Arg("mode", str, "MINTWIST"),
    help="Round pipe along a path, solid or hollow, with an optional radius law.",
)
def pipe(p: Processor, path, r, ri, rlaw, mode):
    if r <= 0 or ri < 0 or ri >= r:
        raise CommandError("PIPE: need r > ri >= 0")
    mode = _mode(mode, "PIPE")
    pw = _wire(p, path, "the PIPE path")
    ps = sw.PathSampler(pw)
    o, tan = ps.at(0)
    law = _Law(p, rlaw, "PIPE radius law", 1.0)

    def one(radius):
        prof = cv.circle(o, radius, tan)
        if law.is_(1.0):
            return _run("PIPE", sw.exact_sweep, prof, pw, mode, True, "PIPE")
        return _run("PIPE", sw.law_sweep, prof, pw, law, mode, True, "PIPE")

    shape = one(r)
    if ri > 0:
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut

        cut = BRepAlgoAPI_Cut(shape, one(ri))
        if not cut.IsDone():
            raise CommandError("PIPE: kernel failed hollowing the pipe")
        shape = robust.unwrap(cut.Shape())
    return _new(p, shape, "PIPE", solid=True)
