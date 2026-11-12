"""TEXT (letters from a font), SURFACE (equation surfaces), PUSHPULL and
DELFACE (direct face editing)."""

from __future__ import annotations

from ..geometry import curves as cv
from ..geometry import direct as de
from ..geometry import robust
from ..geometry import surfaces as sf
from ..geometry import text as tx
from ..lang.expr import ExprError, fmt_num, format_value
from .curve_handlers import _string_literal
from .processor import Arg, CommandError, Processor, Raw, Text, command

# =============================================================================
# TEXT
# =============================================================================


@command(
    "TEXT",
    Arg("text", Text, help="the letters, in quotes when they hold spaces or commas"),
    Arg("x"), Arg("y"), Arg("z"),
    Arg("size", help="font size (capital letters are about 0.7 of it)"),
    Arg("depth", float, 0.0, "0 = flat letters; else solid letters this thick along the normal"),
    Arg("nx", float, 0.0, "plane normal (default +Z)"), Arg("ny", float, 0.0), Arg("nz", float, 1.0),
    Arg("angle", float, 0.0, "turn the text in its plane (degrees)"),
    Arg("align", str, "LEFT", "LEFT, CENTER or RIGHT of (x,y,z)"),
    Arg("font", Text, "sans-serif", "font name (sans-serif, serif, monospace, DejaVu Sans ...) or a .ttf file"),
    Arg("style", str, "REGULAR", "REGULAR, BOLD, ITALIC or BOLDITALIC"),
    help="Letters from a font, standing on (x,y,z) with the baseline along the plane's X: "
         "TEXT, \"M8 BOLT\", 0,0,10, 6, 1 (raised letters 1 thick) · TEXT, ABC, 0,0,0, 10 (flat) · "
         "engrave: TEXT, \"No 5\", 5,5,9.5, 6, 1 then SUBTRACT, plate, LAST.",
)
def text_(p: Processor, text, x, y, z, size, depth, nx, ny, nz, angle, align, font, style):
    from .handlers import _made

    try:
        shape = tx.text_shape(str(text), (x, y, z), size, depth, str(font), (nx, ny, nz), angle, align, style)
    except cv.CurveError as exc:
        raise CommandError(f"TEXT: {exc}") from None
    kind = f"solid letters {fmt_num(depth)} thick" if depth else "flat letters"
    return _made(p, shape, f"TEXT {str(text)!r}, size {fmt_num(size)}, {kind}")


# =============================================================================
# SURFACE, PARAM
# =============================================================================


class _UVLaw:
    """An expression in u and v (degrees in sin and cos, as everywhere)."""

    def __init__(self, p: Processor, text: str, what: str):
        src = text.strip()
        quoted = _string_literal(src)
        self.p, self.src, self.what = p, quoted if quoted is not None else src, what
        if not self.src:
            raise CommandError(f"{what}: the expression is empty")

    def __call__(self, u: float, v: float) -> float:
        base = dict(self.p._scopes[-1]) if self.p._scopes else {}
        base["U"], base["V"] = u, v
        self.p._scopes.append(base)
        try:
            val = self.p.evaluate(self.src)
        except ExprError as exc:
            raise CommandError(f"{self.what}: {exc}") from None
        finally:
            self.p._scopes.pop()
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise CommandError(f"{self.what}: {self.src!r} must give a number at u = {u:g}, v = {v:g}, "
                               f"got {format_value(val)}")
        return float(val)


@command(
    "SURFACE",
    Arg("kind", str, help="PARAM"), Arg("fx", Raw), Arg("fy", Raw), Arg("fz", Raw),
    Arg("u0", float, 0.0), Arg("u1", float, 1.0), Arg("v0", float, 0.0), Arg("v1", float, 1.0),
    Arg("nu", int, 32, "grid points along u (the surface is fitted through them)"),
    Arg("nv", int, 32, "grid points along v"),
    Arg("thick", float, 0.0, "make a solid wall this thick (negative: to the other side)"),
    help="Equation surface x(u,v), y(u,v), z(u,v), fitted to one exact smooth surface: "
         "SURFACE, PARAM, u, v, 3*sin(6*u)*cos(6*v), 0, 60, 0, 40 · a closed one becomes a solid: "
         "SURFACE, PARAM, (20+6*cos(v))*cos(u), (20+6*cos(v))*sin(u), 6*sin(v), 0, 360, 0, 360 (a torus) · "
         "the last number thickens an open one into a wall.",
)
def surface(p: Processor, kind, fx, fy, fz, u0, u1, v0, v1, nu, nv, thick):
    from .handlers import _made

    if kind != "PARAM":
        raise CommandError("SURFACE: the only kind so far is PARAM")
    if not (2 <= nu <= 200 and 2 <= nv <= 200):
        raise CommandError("SURFACE: nu and nv must be from 2 to 200")
    if u1 <= u0 or v1 <= v0:
        raise CommandError("SURFACE: u1 must be greater than u0, and v1 greater than v0")
    laws = [_UVLaw(p, f, f"SURFACE {a}") for a, f in zip("xyz", (fx, fy, fz))]
    try:
        shape, what = sf.param_surface(lambda u, v: tuple(f(u, v) for f in laws), u0, u1, v0, v1, nu, nv, thick)
    except cv.CurveError as exc:
        raise CommandError(f"SURFACE: {exc}") from None
    return _made(p, shape, f"SURFACE ({what}, {nu + 1} x {nv + 1} points)")


# =============================================================================
# Direct face editing
# =============================================================================


def _faces(p: Processor, what: str) -> dict[int, list[int]]:
    from .feature_handlers import _faces_by_body

    groups = _faces_by_body(p, what)
    for bid in groups:
        if not robust.solids(p.model.body(bid).shape):
            raise CommandError(f"{what}: body {bid} is not a solid")
    return groups


@command(
    "PUSHPULL",
    Arg("d", help="distance along each face's outward normal: positive adds material, negative removes it"),
    help="Move the selected faces along their normals; the faces around them stretch to meet them. Works on any "
         "solid, imported ones too: a flat face moves flat, a hole's wall changes the hole (PICK, FACE, 7 then "
         "PUSHPULL, -1 makes a hole 1 bigger in radius), a fillet changes its radius.",
)
def pushpull(p: Processor, d):
    from .handlers import _added

    m = p.model
    if d == 0:
        raise CommandError("PUSHPULL: the distance cannot be 0")
    msgs = []
    for bid, fids in _faces(p, "PUSHPULL").items():
        body = m.body(bid)
        before = robust.volume(body.shape)
        try:
            shape, maker = de.push_pull(body.shape, [m.entity_shape("FACE", f) for f in fids], [d] * len(fids))
        except de.DirectError as exc:
            raise CommandError(f"PUSHPULL: body {bid}: {exc}") from None
        if robust.is_empty(shape) or not robust.is_valid(shape) or robust.volume(shape) <= 0:
            raise CommandError(f"PUSHPULL: moving face{'s' if len(fids) > 1 else ''} {', '.join(map(str, fids))} by "
                               f"{fmt_num(d)} gives an invalid body {bid} (a face would pass through another); "
                               "try a smaller distance")
        change = robust.volume(shape) - before
        if abs(change) < 1e-9 * max(1.0, before):
            raise CommandError(f"PUSHPULL: body {bid} did not change")
        new = m.replace([bid], robust.unwrap(shape), maker, same_id=True)
        sign = "+" if change > 0 else "-"
        msgs.append(_added(p, new, f"PUSHPULL {fmt_num(d)} on face{'s' if len(fids) > 1 else ''} "
                                   f"{', '.join(map(str, fids))} of body {bid} (volume {sign}{fmt_num(round(abs(change), 4))})"))
    return "\n".join(msgs)


@command(
    "DELFACE",
    help="Delete the selected faces and close the gap: the faces around them grow to fill it, so a hole, a boss, "
         "a pocket, a fillet or a chamfer disappears (select all of its faces). Good for simplifying imported parts.",
)
def delface(p: Processor):
    from .handlers import _added

    m = p.model
    msgs = []
    for bid, fids in _faces(p, "DELFACE").items():
        body = m.body(bid)
        n_before = len(body.entity_ids["FACE"])
        try:
            shape, maker = de.delete_faces(body.shape, [m.entity_shape("FACE", f) for f in fids])
        except de.DirectError as exc:
            raise CommandError(f"DELFACE: body {bid}: {exc} (select every face of the feature, for a "
                               "blind hole its wall and its bottom)") from None
        if robust.is_empty(shape) or not robust.is_valid(shape):
            raise CommandError(f"DELFACE: removing these faces leaves an invalid body {bid}")
        new = m.replace([bid], robust.unwrap(shape), maker, same_id=True)
        gone = n_before - len(new.entity_ids["FACE"])
        msgs.append(_added(p, new, f"DELFACE {', '.join(map(str, fids))} of body {bid} ({gone} fewer faces)"))
    return "\n".join(msgs)
