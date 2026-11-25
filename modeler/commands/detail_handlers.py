"""DETAIL: how much the 3D view draws, so big assemblies stay quick to turn (PLAN item 112)."""

from __future__ import annotations

from .processor import Arg, CommandError, Processor, command

MODES = ("AUTO", "FINE", "FAST")


@command(
    "DETAIL",
    Arg("mode", str, "", "AUTO (fast once 300 bodies are shown), FINE (everything) or FAST; empty: how it is now"),
    Arg("px", float, 0.0, "FAST: bodies smaller than this many pixels on screen are left out while it draws "
                          "(0: keep it as it is; the start is 3)"),
    logged=False,
    help="How much the 3D view draws: DETAIL, FAST draws new bodies with coarser meshes and leaves out bodies "
         "smaller than a few pixels (DETAIL, FAST, 6 leaves out more); DETAIL, FINE draws everything; DETAIL, AUTO "
         "(the start) is FINE until 300 bodies are shown, then FAST. Copies of a part (INST) always share one "
         "mesh, so a thousand bolts cost about as much to draw as their shapes. DETAIL alone says how it is.",
)
def detail(p: Processor, mode, px):
    mode = mode.strip().upper()
    if mode and mode not in MODES:
        raise CommandError(f"DETAIL: use AUTO, FINE or FAST, not {mode.lower()}")
    if px < 0:
        raise CommandError("DETAIL: the size in pixels cannot be negative")
    v = p.view if p.view is not None and hasattr(p.view, "set_detail") else None
    if v is None:
        st = {"mode": mode or "AUTO", "fast": False, "cull_px": px or 3.0, "shown": len(p.model.bodies),
              "big_after": 300, "note": "no 3D view: only the window uses this"}
    else:
        if mode:
            v.set_detail(mode, px or None)
        st = v.detail_state()
    p.give_report("detail", st)
    how = "fast" if st["fast"] else "fine"
    head = f"detail {st['mode'].lower()}: drawing {how}"
    if st["mode"] == "AUTO":
        head += f" ({st['shown']} bodies shown; fast from {st['big_after']})"
    if st["fast"]:
        head += f", bodies under {st['cull_px']:g} px left out"
    return head
