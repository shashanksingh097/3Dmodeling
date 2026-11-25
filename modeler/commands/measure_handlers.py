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
         Arg("density", float, 0.0, "density in kg/m3 (e.g. 7850 for steel); default: each body's MATERIAL"),
         logged=False,
         help="Volume, area, centre of mass, and principal moments of inertia: MASSPROP [, body [, density]]. "
              "With a density, or when every body has a MATERIAL, mass is in kg and inertia in kg.mm2 (or the model's unit).")
def massprop(p: Processor, b, density):
    m = p.model
    if density < 0:
        raise CommandError("MASSPROP: the density cannot be negative")
    if b:
        ids = [b]
    elif m.selection_kind == "BODY" and m.selection:
        ids = list(m.selection)
    else:
        ids = m.shown_ids()
    from ..geometry import meshbody

    ids = [i for i in ids if robust.solids(m.body(i).shape)
           or (meshbody.is_mesh(m.body(i).shape) and meshbody.info(m.body(i).shape).closed)]
    if not ids:
        raise CommandError("MASSPROP: no solid bodies to measure")
    u = m.units.lower()
    scale = UNITS[m.units] / 1000.0  # model unit in metres
    # density per body: the one given, else the body's material
    dens = {i: density or m.density(i) for i in ids}
    by_material = not density and all(dens.values())
    missing = [] if density or by_material else [i for i in ids if not dens[i]]
    weighted = bool(density) or by_material
    g = GProp_GProps()
    vol = area = 0.0
    for i in ids:
        gi = GProp_GProps()
        BRepGProp.VolumeProperties_s(m.body(i).shape, gi)
        vol += gi.Mass()
        # weighted by kg per cubic model unit: the sum is then mass, mass centre and inertia
        g.Add(gi, dens[i] * scale ** 3 if weighted else 1.0)
        ga = GProp_GProps()
        BRepGProp.SurfaceProperties_s(m.body(i).shape, ga)
        area += ga.Mass()
    c = g.CentreOfMass()
    what = f"body {ids[0]}" if len(ids) == 1 else f"{len(ids)} bodies ({', '.join(map(str, ids[:10]))}{'...' if len(ids) > 10 else ''})"
    lines = [f"{what}:",
             f"  volume {_n(vol)} {u}3, surface area {_n(area)} {u}2",
             f"  centre of mass ({_n(c.X())}, {_n(c.Y())}, {_n(c.Z())})"]
    pp = g.PrincipalProperties()
    i1, i2, i3 = pp.Moments()
    axes = [pp.FirstAxisOfInertia(), pp.SecondAxisOfInertia(), pp.ThirdAxisOfInertia()]
    if density:
        lines.insert(2, f"  mass {_n(g.Mass())} kg (density {fmt_num(density)} kg/m3)")
        unit = f"kg.{u}2"
    elif by_material:
        mats = sorted({m.body(i).material.lower() for i in ids})
        lines.insert(2, f"  mass {_n(g.Mass())} kg ({', '.join(mats)})")
        unit = f"kg.{u}2"
    else:
        unit = f"{u}5 (per unit density; give a density or a MATERIAL for kg.{u}2)"
        if len(missing) < len(ids):
            lines.insert(2, "  no mass: bodies " + ", ".join(map(str, missing[:10])) + " have no material")
    k = 1.0
    lines.append("  principal moments of inertia about the centre: " + ", ".join(_n(v * k) for v in (i1, i2, i3)) + f" {unit}")
    lines.append("  along " + ", ".join(_fmt((a.X(), a.Y(), a.Z())) for a in axes))
    p.give_report("MASSPROP", {
        "bodies": ids, "unit": u, "volume": round(vol, 6), "area": round(area, 6),
        "mass_kg": round(g.Mass(), 9) if weighted else None,
        "centre": [round(v, 6) for v in (c.X(), c.Y(), c.Z())],
        "inertia": [round(v, 6) for v in (i1, i2, i3)], "inertia_unit": unit.split(" ")[0],
        "no_material": missing})
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
        from ..geometry import meshbody

        ids = [i for i in m.shown_ids() if robust.solids(m.bodies[i].shape)
               or (meshbody.is_mesh(m.bodies[i].shape) and meshbody.info(m.bodies[i].shape).closed)]
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
        from ..geometry import meshbody

        if not apart and (meshbody.is_mesh(sx) or meshbody.is_mesh(sy)):
            # a mesh body: the common volume is found on triangles
            from .mesh_handlers import default_deflection

            try:
                overlap = meshbody.overlap_volume(sx, sy, default_deflection(p, sx if not meshbody.is_mesh(sx) else sy))
            except meshbody.MeshError as exc:
                raise CommandError(f"CLASH: bodies {x} and {y}: {exc}") from None
        elif not apart:
            common = BRepAlgoAPI_Common(sx, sy)
            if common.IsDone() and not robust.is_empty(common.Shape()):
                overlap = robust.volume(common.Shape())
        if overlap > 1e-9 * max(1.0, robust.volume(sx)):
            hits += 1
            lines.append(f"bodies {x} and {y} OVERLAP: {_n(overlap)} {m.units.lower()}3 in common")
        elif len(pairs) == 1 or not apart:
            try:
                d, _, _ = ft.distance(sx, sy)
            except ft.FeatureError as exc:
                raise CommandError(f"CLASH: bodies {x} and {y}: {exc}") from None
            lines.append(f"bodies {x} and {y} " + ("touch (no overlap)" if d < 1e-7 else f"are clear: gap {_n(d)}"))
    if len(pairs) > 1:
        lines.append(f"{len(pairs)} pairs checked: " + (f"{hits} overlap" if hits else "no overlaps"))
    if hits:
        lines.append("CLASHFIX, a, b, CUT (or MOVE) [, clearance [, direction [, PREVIEW]]] fixes one: cuts b's shape "
                     "out of a, or moves a clear of b")
    return "\n".join(lines)


MAX_SECTIONS = 3


def cut_faces(shape, d: dt.Datum):
    """The faces where a plane cuts a solid (an empty list when it misses), with area and centre."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.gp import gp_Ax3, gp_Dir, gp_Pln, gp_Pnt

    if not robust.solids(shape):
        return []
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    lo_c, hi_c = box.CornerMin(), box.CornerMax()  # (Get() does not convert in OCP 8)
    x0, y0, z0, x1, y1, z1 = lo_c.X(), lo_c.Y(), lo_c.Z(), hi_c.X(), hi_c.Y(), hi_c.Z()
    far = max(abs(c - o) for c, o in zip(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), d.origin))
    size = robust.diagonal(shape) * 2 + 2 * far + 1.0  # the sheet reaches past the part, wherever it is
    pln = gp_Pln(gp_Ax3(gp_Pnt(*d.origin), gp_Dir(*d.z), gp_Dir(*d.x)))
    sheet = BRepBuilderAPI_MakeFace(pln, -size, size, -size, size).Face()
    com = BRepAlgoAPI_Common(shape, sheet)
    if not com.IsDone():
        return []
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer

    out = []
    ex = TopExp_Explorer(com.Shape(), TopAbs_FACE)
    while ex.More():
        f = ex.Current()
        ex.Next()
        g = GProp_GProps()
        BRepGProp.SurfaceProperties_s(f, g)
        if g.Mass() > 1e-12:
            c = g.CentreOfMass()
            out.append((g.Mass(), (c.X(), c.Y(), c.Z())))
    return out


def _cut_report(p: Processor, planes) -> list[str]:
    lines = []
    for k, (d, _side) in enumerate(planes, 1):
        hits = []
        for bid in p.model.shown_ids():
            faces = cut_faces(p.model.bodies[bid].shape, d)
            if faces:
                area = sum(a for a, _c in faces)
                cx = [round(sum(a * c[i] for a, c in faces) / area, 9) + 0.0 for i in range(3)]
                hits.append(f"body {bid}: area {_n(area)}, centre ({', '.join(_n(v) for v in cx)})"
                            + (f", {len(faces)} pieces" if len(faces) > 1 else ""))
        tag = f"plane {k}" if len(planes) > 1 else "the plane"
        lines.append(f"  {tag} cuts " + ("; ".join(hits) if hits else "no solid"))
    return lines


@command("SECTION", Arg("plane", Raw, "OFF", "a datum plane, XY/YZ/ZX, or OFF"),
         Arg("side", str, "BELOW", "BELOW (default: keep the part under the plane) or ABOVE"),
         Arg("offset", float, 0.0, "move the plane this far along its normal"),
         Arg("mode", str, "NEW", "NEW (this plane only) or ADD (one more plane, up to three)"),
         logged=False,
         help="Cut the view open along a plane to look inside (the model is not changed): SECTION, mid · "
              "SECTION, XY, ABOVE · SECTION, XY, BELOW, 12.5 (moved 12.5 along the plane's normal) · "
              "SECTION, YZ, ABOVE, 0, ADD (up to three planes at once) · SECTION, OFF. The cut faces are capped "
              "and hatched, and the area and centre of each cut are printed. The Section window moves the "
              "plane with a slider.")
def section(p: Processor, plane, side, offset, mode):
    word = plane.strip()
    if mode not in ("NEW", "ADD"):
        raise CommandError("SECTION: mode is NEW or ADD")
    adding, shift = mode == "ADD", offset
    side = side.upper()
    if not word or word.upper() == "OFF":
        p.section = None
        msg = "section view off"
    else:
        if side not in ("ABOVE", "BELOW"):
            raise CommandError("SECTION: side must be ABOVE or BELOW")
        d = plane_ref(p, word, "SECTION")
        if shift:
            d = dt.Datum("PLANE", d.name, dt.add(d.origin, dt.mul(d.z, shift)), d.z, d.x)
        planes = list(p.section or []) if adding else []
        if len(planes) >= MAX_SECTIONS:
            raise CommandError(f"SECTION: at most {MAX_SECTIONS} planes at once; SECTION, OFF starts again")
        planes.append((d, side))
        p.section = planes
        where = f"plane {d.name}" + (f" moved {_n(shift)}" if shift else "")
        msg = (f"section view at {where}, showing what is {side.lower()} it" +
               (f" ({len(planes)} planes)" if len(planes) > 1 else ""))
        msg = "\n".join([msg, *_cut_report(p, planes)])
    hook = getattr(p.view, "set_section", None) if p.view else None
    if hook:
        hook(p.section)
    return msg
