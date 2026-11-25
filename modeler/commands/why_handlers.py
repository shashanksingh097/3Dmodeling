"""Errors that point at the problem (PLAN item 89): WHY and the faces at fault.

``fault_for`` finds what a failure is about: the faces, edges or vertices its
message names, else the bodies the step names, else (for a line just typed)
what was picked. The window lights those up in red, the error bar offers the
usual fixes, and ``WHY, n`` prints the reason, the fixes tried on a copy of
the model (ai/diagnose.py) and the IDs at fault. ``WHY, OFF`` clears the red.
"""

from __future__ import annotations

import re
from typing import Any

from .processor import Arg, CommandError, Processor, Raw, command

_ENTITY_RE = re.compile(r"\b(face|edge|vertex|vertice|vertices)s?\s+((?:\d+)(?:\s*(?:,|and|to|&)\s*\d+)*)", re.I)
_BODY_RE = re.compile(r"\bbod(?:y|ies)\s+((?:\d+)(?:\s*(?:,|and)\s*\d+)*)", re.I)
_KIND = {"face": "FACE", "edge": "EDGE", "vertex": "VERTEX", "vertice": "VERTEX", "vertices": "VERTEX"}


def _entities(p: Processor, message: str) -> dict[str, list[int]]:
    m = p.model
    named: dict[str, list[int]] = {}
    for word, nums in _ENTITY_RE.findall(message or ""):
        k = _KIND[word.lower()]
        for n in re.findall(r"\d+", nums):
            gid = int(n)
            try:
                m.entity_owner(k, gid)
            except Exception:  # noqa: BLE001 - a number that is not an entity (now)
                continue
            named.setdefault(k, []).append(gid)
    return named


def _bodies_named(p: Processor, text: str, message: str) -> list[int]:
    m = p.model
    out: list[int] = []
    for grp in _BODY_RE.findall(message or ""):
        out += [int(n) for n in re.findall(r"\d+", grp) if int(n) in m.bodies]
    from ..ai.diagnose import _split_cmd

    split = _split_cmd(text or "")
    if split:
        for a in split[2]:
            a = a.strip().strip('"')
            b = m.body_by_name(a) if a and a[0].isalpha() else None
            bid = getattr(b, "id", b) if b is not None else None
            if isinstance(bid, int) and bid in m.bodies:
                out.append(bid)
    return list(dict.fromkeys(out))


def fault_for(p: Processor, text: str = "", message: str = "", typed: bool = False,
              picked: tuple[str, list[int]] | None = None) -> dict[str, Any] | None:
    """What a failure is about: {"kind": FACE|EDGE|VERTEX|BODY, "ids": [...], "from": why}.

    picked: the pick the step was given (kind, ids); a typed line uses the pick now."""
    if "unknown command" in (message or ""):
        return None  # nothing in the model is at fault
    named = _entities(p, message)
    if named:
        k = max(named, key=lambda kk: len(named[kk]))
        return {"kind": k, "ids": sorted(dict.fromkeys(named[k])), "from": "the message"}
    bodies = _bodies_named(p, text, message)
    m = p.model
    if picked is None and typed and m.selection:
        picked = (m.selection_kind, list(m.selection))
    if picked and picked[1] and picked[0] != "BODY":
        # the picked faces or edges say more than their whole body, when they are on it
        owners, ids = set(), []
        for gid in picked[1]:
            try:
                owners.add(m.entity_owner(picked[0], gid)[0])
                ids.append(gid)
            except Exception:  # noqa: BLE001 - gone
                pass
        if ids and (not bodies or owners <= set(bodies)):
            return {"kind": picked[0], "ids": ids, "from": "the pick it used"}
    if bodies:
        return {"kind": "BODY", "ids": bodies, "from": "the bodies the step names"}
    if picked and picked[1] and picked[0] == "BODY":
        ids = [b for b in picked[1] if b in m.bodies]
        if ids:
            return {"kind": "BODY", "ids": ids, "from": "the pick it used"}
    return None


def step_fault(p: Processor, n: int) -> dict[str, Any] | None:
    """What history step n's failure (or warning) is about, using the pick it was given."""
    e = p.history[n - 1]
    picked = None
    try:
        snap = p._snaps[n - 1]["model"]
        picked = (snap.get("selection_kind", "FACE"), list(snap.get("selection") or []))
    except (IndexError, KeyError, TypeError):
        pass
    return fault_for(p, e.text, e.message if not e.ok else (e.warning or ""), picked=picked)


def failed_steps(p: Processor) -> list[int]:
    return [i for i, e in enumerate(p.history[: p.cursor], 1) if not e.suppressed and not e.ok]


def show_fault(p: Processor, fault: dict[str, Any] | None) -> int:
    """Light up the entities at fault in red in the view (none: clear). How many shapes."""
    from .preview_handlers import _fault_shapes

    ghosts = _fault_shapes(p.model, fault)
    p.model.set_preview(ghosts)
    return len(ghosts)


def fault_text(fault: dict[str, Any] | None) -> str:
    if not fault:
        return ""
    k = fault["kind"].lower()
    ids = fault["ids"]
    word = {"vertex": "vertices", "body": "bodies"}.get(k, k + "s") if len(ids) != 1 else k
    return f"at fault: {word} {', '.join(map(str, ids[:20]))}" + (" ..." if len(ids) > 20 else "")


@command(
    "WHY",
    Arg("n", Raw, "", help="the history step (default: the first failed one, or the last line that failed); "
                           "OFF clears the red"),
    Arg("fmt", str, "TEXT", help="TEXT or JSON"),
    logged=False,
    help="Why did a step fail? WHY, 5 prints the reason, the usual fixes (each tried on a copy of the model, "
         "with the line that runs it) and the faces, edges or bodies at fault, and lights those up in red in "
         "the 3D view. WHY alone takes the first failed step, or the last line that failed. WHY, OFF clears "
         "the red. WHY, 5, JSON gives it as data.",
)
def why(p: Processor, n, fmt):
    import json

    from ..ai import diagnose as dg

    raw = (n or "").strip().upper()
    fmt = (fmt or "TEXT").upper()
    if raw == "JSON":
        raw, fmt = "", "JSON"
    if raw == "OFF":
        show_fault(p, None)
        return "the red marks are cleared"
    step = None
    if raw:
        try:
            step = int(raw)
        except ValueError:
            raise CommandError("WHY: give a history step number, or OFF") from None
    if step is not None and 1 <= step <= p.cursor:
        e = p.history[step - 1]
        if e.ok and not e.warning:
            show_fault(p, None)
            return f"step {step} ({e.label}) runs without a problem" + (" (it is suppressed)" if e.suppressed else "")
    try:
        d = dg.diagnose(p, step)
    except dg.DiagnoseError as exc:
        raise CommandError(f"WHY: {exc}") from None
    fault = d.get("fault")
    if fault:
        show_fault(p, fault)
    p.give_report("WHY", d)
    if fmt == "JSON":
        return json.dumps(d)
    text = dg.why_text(d)
    if fault:
        text += "\n\n" + fault_text(fault).capitalize() + " (red in the 3D view; WHY, OFF clears it)"
    return text


_NEAR = re.compile(r"'([^']+)'[^;\n]*; did you mean ([^?]+)\?")


def near_fixes(line: str, message: str) -> list[tuple[str, str]]:
    """The "did you mean" fixes of a failed line, as (button text, the line with it used)."""
    m = _NEAR.search(message or "")
    if not m or not line:
        return []
    bad = m.group(1)
    out = []
    for good in [g.strip() for g in m.group(2).split(" or ") if g.strip()]:
        fixed, n = re.subn(r"(?<![A-Za-z0-9_])" + re.escape(bad) + r"(?![A-Za-z0-9_])", good, line,
                           count=1, flags=re.I)
        if n and fixed != line:
            out.append((f"Use {good}", fixed))
    return out
