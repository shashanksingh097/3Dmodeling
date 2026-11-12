"""THREAD (real helical screw threads) and SPRING (coil springs)."""

from __future__ import annotations

from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut

from ..geometry import robust
from ..geometry import threads as th
from ..lang.expr import fmt_num
from .processor import Arg, CommandError, Processor, command

HANDS = ("RIGHT", "LEFT")


def _thread_size(rf: th.RoundFace, pitch: float) -> tuple[float, float]:
    """(major diameter, pitch) for a face, from the face and the pitch given (0 = ISO coarse)."""
    d = 2 * rf.radius
    if rf.outside:
        if pitch == 0:
            c = th.coarse_for_shaft(d)
            if c is None:
                raise CommandError(f"THREAD: a shaft of diameter {fmt_num(d)} is not an ISO metric size; "
                                   "give the pitch: THREAD, 1.5")
            return c
        return d, pitch
    c = th.coarse_for_hole(d)
    if pitch == 0:
        if c is None:
            raise CommandError(f"THREAD: a hole of diameter {fmt_num(d)} is not drilled for an ISO metric size "
                               "(an M8 hole is drilled 6.8, an M10 hole 8.5); give the pitch: THREAD, 1.25")
        return c
    if c is not None and abs(c[1] - pitch) < 1e-9:
        return c
    return d + 2 * th.INT_DEPTH * pitch, pitch  # the hole is the minor diameter


@command(
    "THREAD",
    Arg("pitch", float, 0.0, "distance between turns (default: ISO metric coarse for the diameter)"),
    Arg("length", float, 0.0, "threaded length from the free end (default: the whole face)"),
    Arg("hand", str, "RIGHT", "RIGHT or LEFT"),
    help="Cut a real helical ISO metric thread into the selected round faces: the side of a shaft gets an "
         "outside thread, the wall of a hole an inside thread. PICK, FACE, 7 then THREAD (M8 on an 8 mm shaft, "
         "or in a 6.8 mm hole) · THREAD, 1 (fine pitch) · THREAD, , 12 (12 long from the free end) · "
         "THREAD, , , LEFT.",
)
def thread(p: Processor, pitch, length, hand):
    from .handlers import _added, combine

    m = p.model
    if hand not in HANDS:
        raise CommandError("THREAD: hand must be RIGHT or LEFT")
    if pitch < 0 or length < 0:
        raise CommandError("THREAD: the pitch and the length cannot be negative")
    if m.selection_kind != "FACE" or not m.selection:
        raise CommandError("THREAD: select the round face to thread first, e.g. SEL, S, FACE, TYPE, CYLINDER "
                           "or PICK, FACE, 7")
    groups: dict[int, list[int]] = {}
    for gid in m.selection:
        groups.setdefault(m.entity_owner("FACE", gid)[0], []).append(gid)
    msgs = []
    for bid, fids in groups.items():
        body = m.body(bid)
        if not robust.solids(body.shape):
            raise CommandError(f"THREAD: body {bid} is not a solid")
        tools, notes = [], []
        for gid in fids:
            try:
                rf = th.round_face(m.entity_shape("FACE", gid))
                major, pt = _thread_size(rf, pitch)
                if length and length < pt:
                    raise th.ThreadError(f"a length of {fmt_num(length)} is shorter than one pitch ({fmt_num(pt)})")
                ends = th.free_ends(body.shape, rf, m.tolerance)
                origin, axis, a, b, where = th.thread_span(rf, ends, pt, length)
                tools.append(th.groove_tool(origin, axis, major, pt, a, b, rf.outside, rf.radius, hand == "LEFT"))
            except th.ThreadError as exc:
                raise CommandError(f"THREAD: face {gid}: {exc}") from None
            notes.append(f"{th.describe(major, pt, rf.outside, hand == 'LEFT')} on face {gid}, {where}")
        before = robust.volume(body.shape)
        shape, maker = combine(p, "SUBTRACT", BRepAlgoAPI_Cut, body.shape, tools, bid)
        if before - robust.volume(shape) < 1e-9 * max(1.0, before):
            raise CommandError(f"THREAD: nothing was cut from body {bid}")
        new = m.replace([bid], shape, maker, same_id=True)
        msgs.append(_added(p, new, "THREAD " + "; ".join(notes)))
    return "\n".join(msgs)


@command(
    "SPRING",
    Arg("x"), Arg("y"), Arg("z"),
    Arg("r", help="coil radius (axis to the middle of the wire)"),
    Arg("pitch", help="rise per turn of the active coils"),
    Arg("turns", help="number of turns, end coils included"),
    Arg("d", help="wire diameter"),
    Arg("dx", float, 0.0, "axis direction (default +Z)"), Arg("dy", float, 0.0), Arg("dz", float, 1.0),
    Arg("hand", str, "RIGHT", "RIGHT or LEFT"),
    Arg("closed", float, 0.0, "turns wound tight at each end (closed ends), e.g. 1"),
    Arg("finish", str, "PLAIN", "PLAIN, or GROUND (ends ground flat)"),
    help="Coil spring of round wire, its axis through (x,y,z): SPRING, 0,0,0, 10, 6, 8, 1.5 · "
         "SPRING, 0,0,0, 10, 6, 8, 1.5, , , , , 1, GROUND (compression spring with closed, ground ends).",
)
def spring(p: Processor, x, y, z, r, pitch, turns, d, dx, dy, dz, hand, closed, finish):
    from .handlers import _made

    if hand not in HANDS:
        raise CommandError("SPRING: hand must be RIGHT or LEFT")
    if finish not in ("PLAIN", "GROUND"):
        raise CommandError("SPRING: finish must be PLAIN or GROUND")
    if dx == dy == dz == 0:
        raise CommandError("SPRING: the axis direction cannot be 0, 0, 0")
    try:
        shape, height = th.spring((x, y, z), (dx, dy, dz), r, pitch, turns, d, hand == "LEFT", closed,
                                  finish == "GROUND")
    except th.ThreadError as exc:
        raise CommandError(f"SPRING: {exc}") from None
    ends = f", {fmt_num(closed)} closed turn{'s' if closed != 1 else ''} at each end" if closed else ""
    ground = ", ends ground" if finish == "GROUND" else ""
    what = (f"SPRING radius {fmt_num(r)}, wire {fmt_num(d)}, {fmt_num(turns)} turns at pitch {fmt_num(pitch)}"
            f"{ends}{ground}, {'left' if hand == 'LEFT' else 'right'}-hand, free height {fmt_num(round(height, 4))}")
    return _made(p, shape, what)
