"""Measuring: DIST, ANGLE, MASSPROP, CLASH, and the SECTION view.

All of these are queries: they print what they find and change nothing, so
they are not part of the history.
"""

from __future__ import annotations

import math

from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

from ..core import datum as dt
from ..core.model import UNITS, ModelError, check_kind
from ..geometry import features as ft
from ..geometry import robust
from ..lang.expr import fmt_num
from .feature_handlers import _Args, _fmt, plane_ref
from .processor import Arg, BodyRef, CommandError, Processor, Raw, command

_REFS = [Arg("k1", Raw, ""), Arg("i1", Raw, ""), Arg("k2", Raw, ""), Arg("i2", Raw, "")]


def _n(v: float) -> str:
    return f"{v:.6g}"


class _Thing:
    """Something to measure: an entity, a body or a datum."""

    def __init__(self, label: str, shape=None, datum: dt.Datum | None = None, kind: str = "") -> None:
        self.label, self.shape, self.datum, self.kind = label, shape, datum, kind

    def get_shape(self):
        return self.shape if self.shape is not None else ft.datum_shape(self.datum)

    def direction(self) -> tuple[dt.P3, str] | None:
        """(unit direction, "normal" or "line") for angles."""
        if self.datum is not None:
            if self.datum.kind == "POINT":
                return None
            return self.datum.z, ("normal" if self.datum.kind == "PLANE" else "line")
        if self.kind == "FACE":
            got = ft.face_plane(self.shape)
            if got:
                return got[1], "normal"
            ax = ft.face_axis(self.shape)
            return (ax[1], "line") if ax else None
        if self.kind == "EDGE":
            line = ft.edge_line(self.shape)
            if line:
                return line[1], "line"
            circ = ft.edge_circle(self.shape)
            return (circ[1], "normal") if circ else None
        return None


def _things(p: Processor, what: str, raws: list[str]) -> list[_Thing]:
    m = p.model
    raws = [r.strip() for r in raws]
    if not any(raws):  # the two selected things
        if len(m.selection) != 2:
            raise CommandError(f"{what}: select two things first (Ctrl+click), or give them: "
                               f"{what}, FACE, 6, EDGE, 3 · {what}, DATUM, mid, BODY, plate")
        k = m.selection_kind
        return [_entity(p, k, gid) for gid in m.selection]
    out = []
    a = _Args(p, what, raws)
    for _ in range(2):
        word = a.word("the kind").upper()
        if word == "DATUM":
            name = a.word("the datum name")
            try:
                out.append(_Thing(name, datum=m.datum(name)))
            except ModelError as exc:
                raise CommandError(f"{what}: {exc}") from None
            continue
        if word in dt.BASE_PLANES:
            out.append(_Thing(word, datum=plane_ref(p, word, what)))
            continue
        try:
            k = check_kind(word)
        except ModelError as exc:
            raise CommandError(f"{what}: {exc}, or DATUM") from None
        if k == "BODY":
            from .processor import REGISTRY

            out.append(_entity(p, k, p._body_arg(REGISTRY[what], a.word("the body"))))
        else:
            out.append(_entity(p, k, a.entity(k, f"the {k.lower()}")))
    a.done()
    return out


def _entity(p: Processor, kind: str, gid: int) -> _Thing:
    try:
        shape = p.model.entity_shape(kind, gid)
    except ModelError as exc:
        raise CommandError(str(exc)) from None
    return _Thing(f"{kind} {gid}", shape=shape, kind=kind)


@command("DIST", *_REFS, logged=False,
         help="Shortest distance between two things: DIST (the two selected) · DIST, FACE, 6, VERTEX, 3 · "
              "DIST, BODY, a, BODY, b · DIST, DATUM, mid, EDGE, 4. Also the gap along X, Y and Z.")
def dist(p: Processor, k1, i1, k2, i2):
    a, b = _things(p, "DIST", [k1, i1, k2, i2])
    try:
        d, pa, pb = ft.distance(a.get_shape(), b.get_shape())
    except ft.FeatureError as exc:
        raise CommandError(f"DIST: {exc}") from None
    delta = dt.sub(pb, pa)
    lines = [f"distance {_n(d)} between {a.label} and {b.label}"]
    if d > 0:
        lines.append(f"  from {_fmt(pa)} to {_fmt(pb)}; dx {_n(delta[0])}, dy {_n(delta[1])}, dz {_n(delta[2])}")
    else:
        lines.append(f"  they touch or overlap (at {_fmt(pa)})")
    return "\n".join(lines)


@command("ANGLE", *_REFS, logged=False,
         help="Angle between two flat faces, straight edges, axes or planes: ANGLE (the two selected) · "
              "ANGLE, FACE, 3, FACE, 5 · ANGLE, EDGE, 4, DATUM, top.")
def angle(p: Processor, k1, i1, k2, i2):
    a, b = _things(p, "ANGLE", [k1, i1, k2, i2])
    da, db = a.direction(), b.direction()
    for t, dd in ((a, da), (b, db)):
        if dd is None:
            raise CommandError(f"ANGLE: {t.label} has no direction (use flat faces, straight or round edges, axes or planes)")
    (va, ka), (vb, kb) = da, db
    c = max(-1.0, min(1.0, dt.dot(va, vb)))
    between = math.degrees(math.acos(c))
    if ka == kb == "normal":
        text = f"angle {_n(between)} deg between {a.label} and {b.label} (between their normals"
        if a.kind == b.kind == "FACE" and 1e-6 < between < 180 - 1e-6:
            text += f"; as faces of one body they meet at {_n(180 - between)} deg inside"
        text += ")"
    elif ka == kb == "line":
        acute = min(between, 180 - between)
        text = f"angle {_n(acute)} deg between {a.label} and {b.label} (lines; {_n(between)} deg between their directions)"
    else:
        acute = abs(90 - between)
        text = f"angle {_n(acute)} deg between {a.label} and {b.label} (line to plane)"
    return text


@command("MASSPROP", Arg("b", BodyRef, 0, "body (default: the selected bodies, or all)"),
         Arg("density", float, 0.0, "density in kg/m3 (e.g. 7850 for steel) to get mass and inertia"),
         logged=False,
         help="Volume, area, centre of mass, and principal moments of inertia: MASSPROP [, body [, density]]. "
              "With a density, mass is in kg and inertia in kg.mm2 (or the model's unit).")
def massprop(p: Processor, b, density):
    m = p.model
    if density < 0:
        raise CommandError("MASSPROP: the density cannot be negative")
    if b:
        ids = [b]
    elif m.selection_kind == "BODY" and m.selection:
        ids = list(m.selection)
    else:
        ids = [i for i in m.bodies if i not in m.hidden]
    ids = [i for i in ids if robust.solids(m.body(i).shape)]
    if not ids:
        raise CommandError("MASSPROP: no solid bodies to measure")
    u = m.units.lower()
    scale = UNITS[m.units] / 1000.0  # model unit in metres
    rho = density * scale ** 3  # kg per cubic model unit
    g = GProp_GProps()
    area = 0.0
    for i in ids:
        gi = GProp_GProps()
        BRepGProp.VolumeProperties_s(m.body(i).shape, gi)
        g.Add(gi)
        ga = GProp_GProps()
        BRepGProp.SurfaceProperties_s(m.body(i).shape, ga)
        area += ga.Mass()
    vol = g.Mass()
    c = g.CentreOfMass()
    what = f"body {ids[0]}" if len(ids) == 1 else f"{len(ids)} bodies ({', '.join(map(str, ids[:10]))}{'...' if len(ids) > 10 else ''})"
    lines = [f"{what}:",
             f"  volume {_n(vol)} {u}3, surface area {_n(area)} {u}2",
             f"  centre of mass ({_n(c.X())}, {_n(c.Y())}, {_n(c.Z())})"]
    pp = g.PrincipalProperties()
    i1, i2, i3 = pp.Moments()
    axes = [pp.FirstAxisOfInertia(), pp.SecondAxisOfInertia(), pp.ThirdAxisOfInertia()]
    if density:
        lines.insert(2, f"  mass {_n(vol * rho)} kg (density {fmt_num(density)} kg/m3)")
        k, unit = rho, f"kg.{u}2"
    else:
        k, unit = 1.0, f"{u}5 (per unit density; give a density for kg.{u}2)"
    lines.append("  principal moments of inertia about the centre: " + ", ".join(_n(v * k) for v in (i1, i2, i3)) + f" {unit}")
    lines.append("  along " + ", ".join(_fmt((a.X(), a.Y(), a.Z())) for a in axes))
    return "\n".join(lines)


@command("CLASH", Arg("a", BodyRef, 0), Arg("b", BodyRef, 0), logged=False,
         help="Do bodies overlap? CLASH, a, b reports the overlap volume, or the clearance between them. "
              "CLASH alone checks every pair of shown solid bodies.")
def clash(p: Processor, a, b):
    m = p.model
    if a and b:
        pairs = [(a, b)]
        if a == b:
            raise CommandError("CLASH: give two different bodies")
    elif a or b:
        raise CommandError("CLASH: give two bodies, or none to check every pair")
    else:
        ids = [i for i in m.bodies if i not in m.hidden and robust.solids(m.bodies[i].shape)]
        if len(ids) > 200:
            raise CommandError("CLASH: more than 200 bodies; name the two to check")
        pairs = [(x, y) for k, x in enumerate(ids) for y in ids[k + 1:]]
    if not pairs:
        return "fewer than two solid bodies, nothing to check"
    from .queries import bbox

    lines, hits = [], 0
    for x, y in pairs:
        sx, sy = m.body(x).shape, m.body(y).shape
        bx, by = bbox(sx), bbox(sy)
        apart = any(bx[i + 3] < by[i] or by[i + 3] < bx[i] for i in range(3))
        overlap = 0.0
        if not apart:
            common = BRepAlgoAPI_Common(sx, sy)
            if common.IsDone() and not robust.is_empty(common.Shape()):
                overlap = robust.volume(common.Shape())
        if overlap > 1e-9 * max(1.0, robust.volume(sx)):
            hits += 1
            lines.append(f"bodies {x} and {y} OVERLAP: {_n(overlap)} {m.units.lower()}3 in common")
        elif len(pairs) == 1 or not apart:
            d, _, _ = ft.distance(sx, sy)
            lines.append(f"bodies {x} and {y} " + (f"touch (no overlap)" if d < 1e-7 else f"are clear: gap {_n(d)}"))
    if len(pairs) > 1:
        lines.append(f"{len(pairs)} pairs checked: " + (f"{hits} overlap" if hits else "no overlaps"))
    return "\n".join(lines)


@command("SECTION", Arg("plane", Raw, "OFF", "a datum plane, XY/YZ/ZX, or OFF"),
         Arg("side", str, "BELOW", "BELOW (default: keep the part under the plane) or ABOVE"),
         logged=False,
         help="Cut the view open along a plane to look inside (the model is not changed): SECTION, mid · "
              "SECTION, XY, ABOVE · SECTION, OFF.")
def section(p: Processor, plane, side):
    word = plane.strip()
    if side not in ("ABOVE", "BELOW"):
        raise CommandError("SECTION: side must be ABOVE or BELOW")
    if not word or word.upper() == "OFF":
        p.section = None
        msg = "section view off"
    else:
        d = plane_ref(p, word, "SECTION")
        p.section = (d, side)
        msg = f"section view at plane {d.name}, showing what is {side.lower()} it"
    hook = getattr(p.view, "set_section", None) if p.view else None
    if hook:
        hook(p.section)
    return msg
