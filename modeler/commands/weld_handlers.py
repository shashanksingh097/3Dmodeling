"""WELD: weld beads where parts meet (geometry/welds.py); CUTLIST lists their lengths."""

from __future__ import annotations

from ..geometry import robust
from ..geometry import welds as wd
from ..lang.expr import fmt_num
from .processor import REGISTRY, Arg, CommandError, Processor, Raw, command


def _near(a, b, gap: float) -> bool:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    ba, bb = Bnd_Box(), Bnd_Box()
    BRepBndLib.Add_s(a, ba)
    BRepBndLib.Add_s(b, bb)
    ba.Enlarge(gap)
    return not ba.IsOut(bb)


@command(
    "WELD",
    Arg("a", Raw, help="a body, or ALL: every pair of frame members (MEMBER) that touch"),
    Arg("b", Raw, "", "the other body"),
    Arg("size", float, 0.0, "the weld size (0: a fifth of the thinner wall, at least 2)"),
    help="Weld beads along the joint where two parts meet: WELD, post, beam, 5 · WELD, ALL, 4 (every joint of a "
         "frame). Each bead is a new body (weld_1 ...), drawn as a round bead of the size across; CUTLIST adds "
         "the weld lengths.",
)
def weld(p: Processor, a, b, size):
    from .handlers import _added

    m = p.model
    if size < 0:
        raise CommandError("WELD: the size cannot be negative")
    pairs: list[tuple[int, int]] = []
    if a.strip().upper() == "ALL":
        if b.strip():
            try:
                size = float(p.evaluate(b))
            except Exception:
                raise CommandError("WELD: after ALL comes the size: WELD, ALL, 4") from None
        ids = [i for i in m.members if i in m.bodies and m.is_shown(i)]
        if len(ids) < 2:
            raise CommandError("WELD: ALL welds frame members (MEMBER); there are fewer than two shown")
        for i, x in enumerate(ids):
            for y in ids[i + 1:]:
                if _near(m.bodies[x].shape, m.bodies[y].shape, 1e-6):
                    pairs.append((x, y))
    else:
        if not b.strip():
            raise CommandError("WELD: give the two bodies: WELD, post, beam [, size]")
        cmd = REGISTRY["WELD"]
        pairs.append((p._body_ref(cmd, a.strip()), p._body_ref(cmd, b.strip())))
    msgs = []
    for x, y in pairs:
        if x == y:
            raise CommandError("WELD: give two different bodies")
        if x in m.welds or y in m.welds:
            raise CommandError(f"WELD: body {x if x in m.welds else y} is a weld bead; give the two parts to join")
        sx, sy = m.body(x).shape, m.body(y).shape
        if not robust.solids(sx) or not robust.solids(sy):
            raise CommandError(f"WELD: bodies {x} and {y} must both be solids")
        try:
            edges = wd.joint(sx, sy)
        except wd.WeldError as exc:
            raise CommandError(f"WELD: {exc}") from None
        if not edges:
            if len(pairs) == 1:
                raise CommandError(f"WELD: bodies {x} and {y} do not touch")
            continue
        s = size or max(2.0, min(robust.diagonal(sx), robust.diagonal(sy)) / 40)
        try:
            shape = wd.bead(edges, s)
        except wd.WeldError as exc:
            raise CommandError(f"WELD: {exc}") from None
        if not robust.report(shape)["ok"]:
            p.warn(f"WELD: the bead between {x} and {y} did not come out as a clean solid; CHECK it")
        ln = wd.length(edges)
        body = m.add_body(shape)
        k = 1
        while m.body_by_name(f"weld_{k}") is not None:
            k += 1
        m.rename(body.id, f"weld_{k}")
        mat = m.body(x).material
        if mat:
            m.set_style(body.id, material=mat)
        m.welds[body.id] = (ln, s, x, y)
        msgs.append(_added(p, m.body(body.id), f"WELD {fmt_num(round(s, 4))} along {len(edges)} edge"
                                                f"{'s' if len(edges) != 1 else ''} between {x} and {y}, "
                                                f"{fmt_num(round(ln, 2))} long"))
    if not msgs:
        raise CommandError("WELD: no members touch each other")
    if len(msgs) > 1:
        total = sum(m.welds[i][0] for i in m.welds if i in m.bodies)
        msgs.append(f"{len(msgs)} welds, {fmt_num(round(total, 1))} of weld in the model")
    return "\n".join(msgs)


def weld_lines(p: Processor) -> list[str]:
    """CUTLIST's weld part: the total length per weld size."""
    m = p.model
    by: dict[float, list] = {}
    for bid, (ln, s, _a, _b) in m.welds.items():
        if bid in m.bodies and bid not in m.hidden:
            by.setdefault(round(s, 4), []).append(ln)
    return [f"welds {fmt_num(s)}: {len(v)} bead{'s' if len(v) != 1 else ''}, {fmt_num(round(sum(v), 1))} long"
            for s, v in sorted(by.items())]
