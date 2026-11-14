"""The view's own steps: DISPLAY, FADE and UNFADE.

These change only how bodies are drawn: hidden, shown or see-through. They
are not history entries (so clicking around in the right-click menu does
not fill the history, and undo does not take them back), but they are
saved with the project. HIDE, SHOW and ISOLATE stay history steps for
scripts; a view step wins over them until one of them names the body again.
"""

from __future__ import annotations

from .layer_handlers import _ids_text, target_bodies
from .processor import Arg, CommandError, Processor, Raw, command

DEFAULT_FADE = 0.8  # how see-through FADE draws a body when no amount is given
DISPLAY_ACTIONS = ("HIDE", "SHOW", "ONLY", "FADE", "UNFADE", "ALL", "MODEL")


def view_targets(p: Processor, what: str, raw: str) -> list[int]:
    """Bodies from a target: a body (ID, name, LAST), SEL, ALL, or several
    bodies separated by spaces (``3 5 7``), as the right-click menu writes them."""
    s = raw.strip()
    parts = s.split()
    if len(parts) > 1:
        out: list[int] = []
        for part in parts:
            for bid in target_bodies(p, what, part):
                if bid not in out:
                    out.append(bid)
        return out
    return target_bodies(p, what, s or "SEL")


def _amount(what: str, raw: str) -> float:
    s = str(raw).strip()
    if not s:
        return DEFAULT_FADE
    try:
        a = float(s)
    except ValueError:
        raise CommandError(f"{what}: the amount is a number from 0.05 to 0.95 (how see-through), not {s}") from None
    if not 0.05 <= a <= 0.95:
        raise CommandError(f"{what}: the amount is from 0.05 (nearly solid) to 0.95 (nearly invisible), not {s}")
    return a


def _fade(p: Processor, target: str, amount: str, keep: str) -> str:
    m = p.model
    a = _amount("FADE", amount)
    if target.strip().upper() == "OTHERS":
        solid = view_targets(p, "FADE", keep or "SEL")
        stay = set(solid)
        others = [b for b in sorted(m.bodies) if b not in stay]
        for bid in solid:
            m.set_fade(bid, 0.0)
        for bid in others:
            m.set_fade(bid, a)
        return f"faded {len(others)} other bod{'y' if len(others) == 1 else 'ies'}; {_ids_text(solid)} solid"
    ids = view_targets(p, "FADE", target)
    for bid in ids:
        m.set_fade(bid, a)
    return f"faded {_ids_text(ids)}"


def _unfade(p: Processor, target: str) -> str:
    m = p.model
    if target.strip().upper() in ("", "ALL"):
        ids = sorted(b for b in m.faded if b in m.bodies)
        for bid in ids:
            m.set_fade(bid, 0.0)
        m.faded.clear()
        return "nothing is faded" if not ids else f"{_ids_text(ids)} solid again"
    ids = view_targets(p, "UNFADE", target)
    for bid in ids:
        m.set_fade(bid, 0.0)
    return f"{_ids_text(ids)} solid again"


@command(
    "FADE",
    Arg("target", Raw, "SEL", "a body, SEL, ALL, several bodies (3 5 7), or OTHERS"),
    Arg("amount", Raw, "", f"how see-through, 0.05 .. 0.95 (default {DEFAULT_FADE})"),
    Arg("keep", Raw, "", "with OTHERS: the bodies that stay solid (default SEL)"),
    logged=False,
    help="Draw bodies see-through, for the view only (not a history step; saved with the project): "
         "FADE, bracket · FADE, SEL, 0.5 · FADE, OTHERS (all but the selection) · FADE, OTHERS, , 12 "
         "(all but body 12). UNFADE makes them solid again.",
)
def fade(p: Processor, target, amount, keep):
    return _fade(p, target, amount, keep)


@command(
    "UNFADE",
    Arg("target", Raw, "ALL", "a body, SEL, several bodies, or ALL"),
    logged=False,
    help="Draw faded bodies solid again: UNFADE, bracket · UNFADE (all of them).",
)
def unfade(p: Processor, target):
    return _unfade(p, target)


@command(
    "DISPLAY",
    Arg("action", str, help=", ".join(DISPLAY_ACTIONS)),
    Arg("target", Raw, "SEL", "a body, SEL, ALL or several bodies (3 5 7)"),
    Arg("amount", Raw, "", "for FADE: how see-through"),
    logged=False,
    help="Change what the view shows without adding history steps (saved with the project): "
         "DISPLAY, HIDE, bracket · DISPLAY, SHOW, 5 · DISPLAY, ONLY, SEL (show only these) · "
         "DISPLAY, FADE, SEL · DISPLAY, UNFADE, ALL · DISPLAY, ALL (every body shown and solid) · "
         "DISPLAY, MODEL (drop the view's changes: back to what the history shows).",
)
def display(p: Processor, action, target, amount):
    m = p.model
    if action not in DISPLAY_ACTIONS:
        raise CommandError(f"DISPLAY: use one of {', '.join(DISPLAY_ACTIONS)}")
    if action == "FADE":
        return _fade(p, target, amount, "")
    if action == "UNFADE":
        return _unfade(p, target)
    if action == "MODEL":
        had = m.has_view_changes()
        m.set_view_state(None)
        return "showing what the history shows" if had else "the view had no changes of its own"
    if action == "ALL":
        for bid in sorted(m.bodies):
            m.set_view_shown(bid, True)
            m.set_fade(bid, 0.0)
        off = [lay.name for lay in m.layers.values() if not lay.visible]
        msg = f"showing all {len(m.bodies)} bodies, solid"
        return msg + (f" (layer {', '.join(off)} is off: LAYER, ALL, ON shows it)" if off else "")
    ids = view_targets(p, "DISPLAY", target)
    if action == "HIDE":
        for bid in ids:
            m.set_view_shown(bid, False)
        return f"hid {_ids_text(ids)} (view only)"
    if action == "SHOW":
        for bid in ids:
            m.set_view_shown(bid, True)
        off = sorted({m.layer_of(b).name for b in ids if not m.layer_of(b).visible})
        msg = f"showing {_ids_text(ids)}"
        return msg + (f" (on hidden layer {', '.join(off)}: LAYER, name, ON to see them)" if off else "")
    keep = set(ids)  # ONLY
    for bid in sorted(m.bodies):
        m.set_view_shown(bid, bid in keep)
    return f"showing only {_ids_text(ids)} (view only; DISPLAY, ALL brings the others back)"

