"""Standard parts: GEAR (involute gears and racks) and FASTENER (ISO screws, nuts, washers)."""

from __future__ import annotations

import math

from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.gp import gp_Ax2, gp_Ax3, gp_Dir, gp_Pnt, gp_Trsf

from ..geometry import fasteners as fs
from ..geometry import gears as gr
from ..lang.expr import fmt_num
from .processor import Arg, BodyRef, CommandError, Processor, Text, command

GEAR_KINDS = ("EXTERNAL", "INTERNAL", "RACK", "BEVEL", "WORM", "WORMWHEEL")


def _placed(shape, x, y, z, dx, dy, dz, what: str):
    """A part built about +Z at the origin, put at (x,y,z) with its +Z along (dx,dy,dz)."""
    if dx == dy == dz == 0:
        raise CommandError(f"{what}: the direction cannot be (0, 0, 0)")
    t = gp_Trsf()
    t.SetTransformation(gp_Ax3(gp_Ax2(gp_Pnt(x, y, z), gp_Dir(dx, dy, dz))), gp_Ax3())
    return BRepBuilderAPI_Transform(shape, t, True).Shape()


def _free_name(p: Processor, base: str) -> str:
    m = p.model
    k = 1
    while True:
        name = f"{base}_{k}"
        if m.body_by_name(name) is None and name.upper() not in m.datums and name.upper() not in m.sketches \
                and name.upper() not in p.params:
            return name
        k += 1


@command(
    "GEAR",
    Arg("x", float, 0.0), Arg("y", float, 0.0), Arg("z", float, 0.0),
    Arg("module", help="tooth size: the pitch diameter is module x teeth (normal module for a helical gear)"),
    Arg("teeth", help="number of teeth"),
    Arg("width", help="face width (along the axis)"),
    Arg("kind", str, "EXTERNAL", "EXTERNAL (a gear), INTERNAL (a ring with the teeth inside), RACK, BEVEL "
                                 "(straight bevel), WORM (teeth: its starts, width: its length) or WORMWHEEL"),
    Arg("helix", float, 0.0, "helix angle in degrees (0: spur); a mating gear needs the opposite angle, a "
                             "helical rack the same · WORMWHEEL: the worm's lead angle (0: from its starts and "
                             "a worm 10 modules across)"),
    Arg("rim", float, 0.0, "EXTERNAL, BEVEL, WORMWHEEL: bore diameter (0: none); INTERNAL: outside diameter (0: "
                           "root + 6 modules); RACK: thickness under the roots (0: 2 modules); WORM: its pitch "
                           "diameter (0: 10 modules)"),
    Arg("pressure", float, 20.0, "pressure angle in degrees"),
    Arg("dx", float, 0.0, "axis direction (default +Z)"), Arg("dy", float, 0.0), Arg("dz", float, 1.0),
    Arg("mate", float, 0.0, "BEVEL: the mating bevel gear's teeth (0: the same, a mitre pair) · WORMWHEEL: "
                            "the worm's starts (0: 1)"),
    help="An involute gear about the axis through (x,y,z): GEAR, 0,0,0, 2, 20, 10 (spur, module 2, 20 teeth, "
         "10 wide) · GEAR, 0,0,0, 2, 20, 10, , 15, 8 (helical, 15°, 8 bore) · GEAR, 0,0,0, 2, 60, 10, INTERNAL "
         "· GEAR, 0,0,0, 2, 12, 10, RACK (12 teeth along +X) · GEAR, 0,0,0, 2, 20, 8, BEVEL, , , , , , , 30 (a "
         "bevel gear for a 30-tooth mate at right angles) · GEAR, 0,0,0, 2, 1, 60, WORM · GEAR, 0,0,0, 2, 30, "
         "16, WORMWHEEL. A tooth points along the local X axis. Two gears "
         "of z1 and z2 teeth mesh at the centre distance module x (z1 + z2) / 2: put the second one along X and, "
         "if z2 is even, turn it by 180/z2 degrees so a tooth falls into a gap. A gear inside an INTERNAL one "
         "fits as made, along X at module x (z2 - z1) / 2. A rack has gaps at X = 0, 1, 2 ... pitches: a gear "
         "above a gap at module x z / 2, turned -90 degrees.",
)
def gear(p: Processor, x, y, z, module, teeth, width, kind, helix, rim, pressure, dx, dy, dz, mate):
    from .handlers import _made

    k = kind.strip().upper() or "EXTERNAL"
    if k not in GEAR_KINDS:
        raise CommandError("GEAR: the kind must be EXTERNAL, INTERNAL, RACK, BEVEL, WORM or WORMWHEEL")
    if rim < 0:
        raise CommandError("GEAR: the rim size cannot be negative")
    n = int(round(teeth))
    if abs(teeth - n) > 1e-9:
        raise CommandError("GEAR: the number of teeth must be a whole number")
    try:
        if k == "RACK":
            shape, pitch, length = gr.rack(module, n, width, rim, pressure, helix)
            what = (f"GEAR {'helical ' if helix else ''}rack, module {fmt_num(module)}, {n} teeth at pitch "
                    f"{fmt_num(round(pitch, 4))}, {fmt_num(round(length, 4))} long, {fmt_num(width)} wide"
                    + (f", helix {fmt_num(helix)}°" if helix else "") + "; pitch line at its local Y = 0, gaps at "
                    f"X = 0, {fmt_num(round(pitch, 4))} ... (a gear of z teeth meshes with its centre "
                    f"{'module / cos(helix)' if helix else 'module'} x z / 2 above a gap"
                    + (", with the same helix angle)" if helix else ")"))
        elif k == "BEVEL":
            z2 = int(round(mate)) if mate else n
            shape, g, cone, apex = gr.bevel(module, n, z2, width, rim, pressure)
            what = (f"GEAR bevel, module {fmt_num(module)}, {n} teeth, pitch diameter {fmt_num(round(2 * g.pitch_r, 4))}"
                    f" at the back face, pitch cone {fmt_num(round(cone, 4))}°, {fmt_num(width)} wide"
                    + (f", bore {fmt_num(rim)}" if rim else "")
                    + f"; the cone's apex is {fmt_num(round(apex, 4))} up the axis: its {z2}-tooth mate, on an axis at "
                      f"right angles through that apex, has its back face {fmt_num(round(g.pitch_r, 4))} from it")
        elif k == "WORM":
            shape, d1, lead = gr.worm(module, n, width, rim, pressure)
            what = (f"GEAR worm, module {fmt_num(module)}, {n} start{'s' if n != 1 else ''}, pitch diameter "
                    f"{fmt_num(round(d1, 4))}, {fmt_num(width)} long, lead angle {fmt_num(round(lead, 4))}°; a wheel "
                    f"of z teeth (WORMWHEEL{', mate ' + str(n) if n != 1 else ''}) meshes on an axis at right angles, "
                    f"{fmt_num(round(d1 / 2, 4))} + {fmt_num(round(module / 2, 4))} x z away")
        elif k == "WORMWHEEL":
            starts = int(round(mate)) if mate else 1
            lead = helix or math.degrees(math.atan(starts / 10))
            shape, g = gr.external(module * math.cos(math.radians(lead)), n, width, lead, rim, pressure)
            what = (f"GEAR worm wheel, module {fmt_num(module)}, {n} teeth, pitch diameter "
                    f"{fmt_num(round(2 * g.pitch_r, 4))}, {fmt_num(width)} wide, teeth at the worm's lead angle "
                    f"{fmt_num(round(lead, 4))}° (helical teeth, not throated)" + (f", bore {fmt_num(rim)}" if rim else "")
                    + f"; ratio {n}:{starts}")
        elif k == "INTERNAL":
            shape, g, od = gr.internal(module, n, width, helix, rim, pressure)
            what = (f"GEAR internal, module {fmt_num(module)}, {n} teeth, pitch diameter "
                    f"{fmt_num(round(2 * g.pitch_r, 4))}, outside {fmt_num(round(od, 4))}, {fmt_num(width)} wide"
                    + (f", helix {fmt_num(helix)}°" if helix else "")
                    + f"; a gear of z teeth inside meshes at centre distance {fmt_num(round(g.module * n / 2, 4))}"
                      f" - {fmt_num(round(g.module / 2, 4))} x z")
        else:
            shape, g = gr.external(module, n, width, helix, rim, pressure)
            half = g.module / 2
            what = (f"GEAR {'helical' if helix else 'spur'}, module {fmt_num(module)}, {n} teeth, pitch "
                    f"diameter {fmt_num(round(2 * g.pitch_r, 4))}, tip {fmt_num(round(2 * g.tip_r, 4))}, root "
                    f"{fmt_num(round(2 * g.root_r, 4))}, {fmt_num(width)} wide"
                    + (f", helix {fmt_num(helix)}°" if helix else "") + (f", bore {fmt_num(rim)}" if rim else "")
                    + f"; meshes with a gear of z teeth at centre distance {fmt_num(round(g.module * n / 2, 4))}"
                      f" + {fmt_num(round(half, 4))} x z")
    except gr.GearError as exc:
        raise CommandError(f"GEAR: {exc}") from None
    return _made(p, _placed(shape, x, y, z, dx, dy, dz, "GEAR"), what)


@command(
    "FASTENER",
    Arg("kind", str, help="CAP, HEXBOLT, CSK (countersunk), BUTTON, SET (set screw), NUT, WASHER, DOWEL, SPRINGPIN, "
                          "INSERT (heat-set threaded insert), BEARING, CIRCLIP or KEY"),
    Arg("size", str, help="M3 ... M24, an inch size (1/4-20, #10-24: CAP, HEXBOLT, NUT, WASHER, SET), a pin's "
                          "diameter (6), a bearing (608, 6201), a circlip's shaft (20), a key (6x6 or the shaft, 20)"),
    Arg("x", float, 0.0, "the seat: where the head, nut or washer sits (a pin, insert or bearing goes in from it)"),
    Arg("y", float, 0.0), Arg("z", float, 0.0),
    Arg("length", float, 0.0, "a screw's length under the head, a pin's or a key's length"),
    Arg("thread", str, "PLAIN", "PLAIN (a smooth shank, quick) or REAL (cut helical threads, a few seconds)"),
    Arg("dx", float, 0.0, "the way the screw points, into the hole (default -Z: a head or washer sits on top "
                          "of the seat, a nut hangs under it)"),
    Arg("dy", float, 0.0), Arg("dz", float, -1.0),
    Arg("hole", BodyRef, 0, "also make the matching hole in this body (the part it goes into)"),
    Arg("fit", str, "", "the hole: CLEAR (clearance; a countersunk screw also gets its countersink), TAP (a tap "
                        "drill as deep as the screw), CBORE (a counterbore: the head sinks in) or FIT (the hole a "
                        "pin, insert or bearing is pressed into; their default)"),
    help="A standard part from the tables, sitting at (x,y,z): FASTENER, CAP, M8, 0,0,10, 25 (an M8x25 cap screw "
         "whose head sits on z = 10) · FASTENER, NUT, M8, 0,0,-12 (under a plate whose bottom is at z = -12) · "
         "FASTENER, WASHER, M8, 0,0,10 · FASTENER, HEXBOLT, M6, 0,0,0, 20, REAL (real threads) · FASTENER, CSK, "
         "M5, 20,10,8, 16, , , , , plate (a countersunk screw and its countersunk hole in plate) · FASTENER, CAP, "
         "M6, 20,10,8, 20, , , , , plate, CBORE · FASTENER, DOWEL, 6, 0,0,10, 20, , , , , base (a dowel pin and "
         "its hole) · FASTENER, BEARING, 608, 0,0,10, , , , , , housing · FASTENER, CAP, 1/4-20, 0,0,0, 25.4. "
         "The body is named (e.g. M8x25_CAP_1), made of steel, and the BOM counts the same parts together.",
)
def fastener(p: Processor, kind, size, x, y, z, length, thread, dx, dy, dz, hole, fit):
    from .feature_handlers import hole as drill
    from .handlers import _made

    thr = thread.strip().upper() or "PLAIN"
    if thr not in ("PLAIN", "REAL"):
        raise CommandError("FASTENER: thread must be PLAIN or REAL")
    if length < 0:
        raise CommandError("FASTENER: the length cannot be negative")
    try:
        k = fs.kind_of(kind)
        if k not in fs.LENGTHED and length:
            raise fs.FastenerError(f"a {k.lower()} has no length; leave it empty")
        made = fs.make(k, size, length, thr == "REAL")
        cut = fs.hole_for(made, fit) if hole else None
        if fit and not hole:
            raise fs.FastenerError("give the body to make the hole in (after dx, dy, dz)")
    except fs.FastenerError as exc:
        raise CommandError(f"FASTENER: {exc}") from None
    except Exception as exc:  # a kernel failure while threading
        raise CommandError(f"FASTENER: building it failed ({exc}); try thread PLAIN") from None
    if dx == dy == dz == 0:
        raise CommandError("FASTENER: the direction cannot be (0, 0, 0)")
    hole_note = ""
    sx, sy, sz = x, y, z
    if cut is not None:
        n = math.sqrt(dx * dx + dy * dy + dz * dz)
        u = (dx / n, dy / n, dz / n)
        try:
            drill(p, hole, x, y, z, cut["d"], cut["depth"], cut["kind"], cut["d2"], cut["h2"], 0.0, *u)
        except CommandError as exc:
            raise CommandError(f"FASTENER: the hole: {str(exc).removeprefix('HOLE: ')}") from None
        sx, sy, sz = (c + cut["sink"] * ui for c, ui in zip((x, y, z), u))  # the head sits in its counterbore
        what = {"SIMPLE": "", "CBORE": f", counterbore {fmt_num(cut['d2'])} x {fmt_num(cut['h2'])}",
                "CSINK": f", countersink {fmt_num(cut['d2'])}"}[cut["kind"]]
        hole_note = (f"; hole {fmt_num(cut['d'])} " + ("through" if not cut["depth"] else f"x {fmt_num(cut['depth'])} deep")
                     + what + f" in body {p.model.last_body}")
        hole = p.model.last_body
    sign = 1 if made.kind in ("NUT",) else -1  # a nut goes on the far side, along the screw
    msg = _made(p, _placed(made.shape, sx, sy, sz, sign * dx, sign * dy, sign * dz, "FASTENER"),
                f"FASTENER {made.label}" + (", threaded" if thr == "REAL" else "") + hole_note)
    m = p.model
    bid = m.last_body
    name = _free_name(p, made.name.replace(".", "_"))
    m.rename(bid, name)
    m.set_style(bid, material="STEEL" if made.kind != "INSERT" else "BRASS")
    p.give_report("FASTENER", {"body": bid, "name": name, "kind": made.kind, "label": made.label,
                               "d": made.d, "pitch": round(made.pitch, 6), "length": made.length,
                               "hole": ({"body": hole, **{k2: v for k2, v in cut.items() if k2 != "sink"}}
                                        if cut is not None else None)})
    return msg.replace(f"-> body {bid} ", f"-> body {bid} '{name}' ", 1)


# ---- cams ------------------------------------------------------------------------------
CAM_KINDS = ("DISC", "BARREL")


@command(
    "CAM",
    Arg("x", float, 0.0), Arg("y", float, 0.0), Arg("z", float, 0.0),
    Arg("law", Text, help="the lift round the turn: R10/120 (rise 10 over 120°), D60 (dwell), F10/120 (fall); a "
                          "letter after a rise or fall picks the motion: C cycloidal (default), H harmonic, P 3-4-5 "
                          "polynomial, V constant speed"),
    Arg("base", help="DISC: the base circle's radius (where the roller is at the bottom) · BARREL: the "
                     "cylinder's radius"),
    Arg("roller", help="the follower's roller radius (DISC: 0 for a knife edge)"),
    Arg("width", help="DISC: the plate's thickness · BARREL: the cylinder's length"),
    Arg("kind", str, "DISC", "DISC (a plate cam pushing a follower along +X) or BARREL (a groove round a "
                             "cylinder, the follower sliding along the axis)"),
    Arg("bore", float, 0.0, "a bore through the middle (0: none)"),
    Arg("depth", float, 0.0, "BARREL: the groove's depth (0: the roller radius)"),
    help="A cam and its roller follower, the cam turning about Z through (x,y,z): CAM, 0,0,0, \"R10/120 D60 "
         "F10/120 D60\", 30, 8, 12 (a disc cam, base radius 30, roller 8, 12 thick) · CAM, 0,0,0, \"R30/180H "
         "F30/180H\", 40, 6, 80, BARREL. Turned A degrees (ROTATE, cam_1, A, x,y,z, 0,0,1), the roller rises by "
         "CAMLIFT(law, A): MOVE the follower by it to make them work together. It checks the pressure angle and "
         "that the roller fits the cam's tightest bend.",
)
def cam(p: Processor, x, y, z, law, base, roller, width, kind, bore, depth):
    from ..geometry import cams as cm
    from .handlers import _added

    k = kind.strip().upper() or "DISC"
    if k not in CAM_KINDS:
        raise CommandError("CAM: the kind is DISC or BARREL")
    try:
        pieces = cm.parse(law)
        lift = cm.stroke(pieces)
        if k == "DISC":
            disc = cm.disc(pieces, base, roller)
            if disc.undercut:
                raise cm.CamError(f"the roller ({fmt_num(roller)}) is bigger than the tightest bend of the cam's "
                                  f"path: the outline would cross itself; use a smaller roller, a bigger base "
                                  f"circle or a gentler law")
            shape = cm.disc_solid(disc, width, bore)
            info = (f"pressure angle up to {disc.pressure:.1f}° (at {disc.pressure_at:.0f}°)"
                    + (f", tightest bend radius {disc.sharpest:.3g}" if math.isfinite(disc.sharpest) else ""))
            if disc.pressure > 30:
                p.warn(f"CAM: the pressure angle reaches {disc.pressure:.1f}° (over 30° the follower tends to jam): "
                       "use a bigger base circle or spread the rise over more of the turn")
            from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder

            rr = roller if roller > 0 else max(1.0, 0.1 * base)
            follower = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(base + roller, 0, 0), gp_Dir(0, 0, 1)), rr,
                                                width).Shape()
        else:
            d = depth or roller
            z0 = (width - lift) / 2
            if z0 - roller <= 0:
                raise cm.CamError(f"the cylinder ({fmt_num(width)} long) is too short for a lift of "
                                  f"{fmt_num(lift)} and a roller of {fmt_num(roller)}")
            from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
            from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder

            body = BRepPrimAPI_MakeCylinder(base, width).Shape()
            if bore > 0:
                if bore / 2 >= base - d:
                    raise cm.CamError(f"a bore of {fmt_num(bore)} leaves no wall under the groove")
                body = BRepAlgoAPI_Cut(body, BRepPrimAPI_MakeCylinder(bore / 2, width).Shape()).Shape()
            cut = BRepAlgoAPI_Cut(body, cm.barrel_groove(pieces, base, roller, d, z0))
            if not cut.IsDone():
                raise cm.CamError("the groove could not be cut")
            shape = cut.Shape()
            info = f"groove {fmt_num(d)} deep, its lowest point {fmt_num(round(z0, 4))} up the cylinder"
            follower = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(base - d, 0, z0), gp_Dir(1, 0, 0)), roller,
                                                d + 2 * roller).Shape()
    except cm.CamError as exc:
        raise CommandError(f"CAM: {exc}") from None
    m = p.model
    name = _free_name(p, "cam")
    cam_body = m.add_body(_placed(shape, x, y, z, 0, 0, 1, "CAM"), name=name)
    roller_body = m.add_body(_placed(follower, x, y, z, 0, 0, 1, "CAM"), name=f"{name}_roller")
    head = (f"CAM {k.lower()}, stroke {fmt_num(round(lift, 6))}, {info}; the roller rises by "
            f"CAMLIFT(\"{law.strip().strip(chr(34))}\", A) when the cam has turned A degrees"
            + (" (along +X)" if k == "DISC" else " (along +Z)"))
    return "\n".join([head, _added(p, cam_body, "the cam"), _added(p, roller_body, "its roller, at A = 0")])
