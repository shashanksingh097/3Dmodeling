"""Standard parts: GEAR (involute gears and racks) and FASTENER (ISO screws, nuts, washers)."""

from __future__ import annotations

from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.gp import gp_Ax2, gp_Ax3, gp_Dir, gp_Pnt, gp_Trsf

from ..geometry import fasteners as fs
from ..geometry import gears as gr
from ..lang.expr import fmt_num
from .processor import Arg, CommandError, Processor, command

GEAR_KINDS = ("EXTERNAL", "INTERNAL", "RACK")


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
    Arg("kind", str, "EXTERNAL", "EXTERNAL (a gear), INTERNAL (a ring with the teeth inside) or RACK"),
    Arg("helix", float, 0.0, "helix angle in degrees (0: spur); a mating gear needs the opposite angle"),
    Arg("rim", float, 0.0, "EXTERNAL: bore diameter (0: none); INTERNAL: outside diameter (0: root + 6 "
                           "modules); RACK: thickness under the roots (0: 2 modules)"),
    Arg("pressure", float, 20.0, "pressure angle in degrees"),
    Arg("dx", float, 0.0, "axis direction (default +Z)"), Arg("dy", float, 0.0), Arg("dz", float, 1.0),
    help="An involute gear about the axis through (x,y,z): GEAR, 0,0,0, 2, 20, 10 (spur, module 2, 20 teeth, "
         "10 wide) · GEAR, 0,0,0, 2, 20, 10, , 15, 8 (helical, 15°, 8 bore) · GEAR, 0,0,0, 2, 60, 10, INTERNAL "
         "· GEAR, 0,0,0, 2, 12, 10, RACK (12 teeth along +X). A tooth points along the local X axis. Two gears "
         "of z1 and z2 teeth mesh at the centre distance module x (z1 + z2) / 2: put the second one along X and, "
         "if z2 is even, turn it by 180/z2 degrees so a tooth falls into a gap. A gear inside an INTERNAL one "
         "fits as made, along X at module x (z2 - z1) / 2. A rack has gaps at X = 0, 1, 2 ... pitches: a gear "
         "above a gap at module x z / 2, turned -90 degrees.",
)
def gear(p: Processor, x, y, z, module, teeth, width, kind, helix, rim, pressure, dx, dy, dz):
    from .handlers import _made

    k = kind.strip().upper() or "EXTERNAL"
    if k not in GEAR_KINDS:
        raise CommandError("GEAR: the kind must be EXTERNAL, INTERNAL or RACK")
    if rim < 0:
        raise CommandError("GEAR: the rim size cannot be negative")
    n = int(round(teeth))
    if abs(teeth - n) > 1e-9:
        raise CommandError("GEAR: the number of teeth must be a whole number")
    try:
        if k == "RACK":
            if helix:
                raise gr.GearError("a helical rack is not made yet; give helix 0")
            shape, pitch, length = gr.rack(module, n, width, rim, pressure)
            what = (f"GEAR rack, module {fmt_num(module)}, {n} teeth at pitch {fmt_num(round(pitch, 4))}, "
                    f"{fmt_num(round(length, 4))} long, {fmt_num(width)} wide; pitch line at its local Y = 0, gaps at X = 0, "
                    f"{fmt_num(round(pitch, 4))} ... (a gear of z teeth meshes with its centre module x z / 2 above a gap)")
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
    Arg("kind", str, help="CAP (ISO 4762 socket head cap screw), HEXBOLT (ISO 4017 hex head screw), NUT "
                          "(ISO 4032) or WASHER (ISO 7089)"),
    Arg("size", str, help="M3, M4, M5, M6, M8, M10, M12, M16, M20 or M24"),
    Arg("x", float, 0.0, "the seat: where the head, nut or washer sits"), Arg("y", float, 0.0),
    Arg("z", float, 0.0),
    Arg("length", float, 0.0, "a screw's length under the head"),
    Arg("thread", str, "PLAIN", "PLAIN (a smooth shank, quick) or REAL (cut helical threads, a few seconds)"),
    Arg("dx", float, 0.0, "the way the screw points, into the hole (default -Z: a head or washer sits on top "
                          "of the seat, a nut hangs under it)"),
    Arg("dy", float, 0.0), Arg("dz", float, -1.0),
    help="A standard fastener from the ISO tables, sitting at (x,y,z): FASTENER, CAP, M8, 0,0,10, 25 (an M8x25 "
         "cap screw whose head sits on z = 10) · FASTENER, NUT, M8, 0,0,-12 (a nut under a plate whose bottom is "
         "at z = -12) · FASTENER, WASHER, M8, 0,0,10 (under the head) · "
         "FASTENER, HEXBOLT, M6, 0,0,0, 20, REAL (real threads). The body is named (e.g. M8x25_CAP_1) and made "
         "of steel; GRAVITY, , \"M8x25_CAP_1\" counts it as holding what it touches.",
)
def fastener(p: Processor, kind, size, x, y, z, length, thread, dx, dy, dz):
    from .handlers import _made

    k = kind.strip().upper()
    if k in ("BOLT", "HEX"):
        k = "HEXBOLT"
    if k in ("SHCS", "SCREW"):
        k = "CAP"
    if k not in fs.KINDS:
        raise CommandError("FASTENER: the kind must be CAP, HEXBOLT, NUT or WASHER")
    thr = thread.strip().upper() or "PLAIN"
    if thr not in ("PLAIN", "REAL"):
        raise CommandError("FASTENER: thread must be PLAIN or REAL")
    if length < 0:
        raise CommandError("FASTENER: the length cannot be negative")
    try:
        d = fs.size_of(size)
        if k not in fs.SCREWS and length:
            raise fs.FastenerError(f"a {k.lower()} has no length; leave it empty")
        shape, label = fs.build(k, d, length, thr == "REAL")
    except fs.FastenerError as exc:
        raise CommandError(f"FASTENER: {exc}") from None
    except Exception as exc:  # a kernel failure while threading
        raise CommandError(f"FASTENER: building it failed ({exc}); try thread PLAIN") from None
    sign = 1 if k == "NUT" else -1  # a nut goes on the far side, along the screw; the rest stand up from the seat
    msg = _made(p, _placed(shape, x, y, z, sign * dx, sign * dy, sign * dz, "FASTENER"),
                f"FASTENER {label}" + (", threaded" if thr == "REAL" else ""))
    m = p.model
    bid = m.last_body
    base = f"M{d}x{fmt_num(length)}_{k}" if k in fs.SCREWS else f"M{d}_{k}"
    name = _free_name(p, base.replace(".", "_"))
    m.rename(bid, name)
    m.set_style(bid, material="STEEL")
    return msg.replace(f"-> body {bid} ", f"-> body {bid} '{name}' ", 1)
