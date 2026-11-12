"""Trying a model with other values: vary a parameter, and edit the history and back.

Both run in sandbox copies, so the user's model never changes.

* ``vary``: re-runs the history with each value of a parameter and says
  which values break a step or an expectation. Shows whether the model is
  really parametric (does the bolt circle still work with 3 holes? 12?).
* ``round_trip``: makes history edits, then undoes them by editing back,
  and checks that every body, face and edge has its old ID again, the
  selection and named sets are as they were, and no step was left with a
  warning. This is the test of stable references (PLAN.md 3.2) for a script.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..commands.processor import CommandError, RebuildCancelled
from ..geometry import robust
from ..lang.expr import format_value
from . import expect
from .describe import num
from .sandbox import Sandbox, SandboxError

if TYPE_CHECKING:
    from ..commands.processor import Processor


def _problems(p: "Processor") -> tuple[list[dict], list[dict]]:
    failed, warned = [], []
    for i, e in enumerate(p.history[: p.cursor], 1):
        if not e.ok:
            failed.append({"entry": i, "text": e.label, "msg": e.message.splitlines()[-1] if e.message else ""})
        elif e.warning:
            warned.append({"entry": i, "text": e.label, "warning": e.warning})
    return failed, warned


def vary(source: "Processor", param: str, values: list, expectations: list[str] | None = None) -> dict[str, Any]:
    name = param.strip().upper()
    index = source.entry_for_param(name)
    if index is None:
        raise SandboxError(f"no history entry sets {name} as plain '{name} = value'")
    rows = []
    for value in values:
        sb = Sandbox(source)
        p = sb.p
        text = f"{name} = {format_value(value) if not isinstance(value, str) else value}"
        row: dict[str, Any] = {"value": value}
        try:
            p.edit_entry(index, text)
        except (CommandError, RebuildCancelled) as exc:
            row.update(ok=False, error=str(exc))
            rows.append(row)
            continue
        failed, warned = _problems(p)
        if failed:
            row["failed"] = failed[:5]
        if warned:
            row["warnings"] = warned[:5]
        bodies = {}
        for b in p.model.bodies.values():
            if robust.solids(b.shape):
                bodies[b.name] = num(robust.volume(b.shape))
        if len(bodies) <= 8:
            row["volumes"] = bodies
        if expectations:
            bad = []
            for e in expectations:
                try:
                    out = expect.check(p, e)
                except expect.ExpectError as exc:
                    bad.append({"check": e, "error": str(exc)})
                    continue
                if not out.passed:
                    bad.append(out.as_dict())
            row["checks_failed"] = bad
        row["ok"] = not failed and not row.get("checks_failed")
        rows.append(row)
    return {"param": name, "entry": index, "results": rows,
            "all_ok": all(r["ok"] for r in rows)}


def signature(p: "Processor") -> dict[str, Any]:
    """What must come back after an edit and its undo: IDs, sizes, selection, sets."""
    m = p.model
    bodies = {}
    for bid, b in sorted(m.bodies.items()):
        bodies[bid] = {"name": b.name, "faces": sorted(b.entity_ids["FACE"]), "edges": sorted(b.entity_ids["EDGE"]),
                       "vertices": sorted(b.entity_ids["VERTEX"]),
                       "volume": num(robust.volume(b.shape), 6) if robust.solids(b.shape) else None}
    return {"bodies": bodies, "selection": (m.selection_kind, list(m.selection)),
            "sets": {k: (kind, list(ids)) for k, (kind, ids) in m.named_sets.items()}}


def _compare(a: dict, b: dict) -> list[str]:
    out = []
    for bid in sorted(set(a["bodies"]) | set(b["bodies"])):
        x, y = a["bodies"].get(bid), b["bodies"].get(bid)
        if x is None:
            out.append(f"body {bid} ({y['name']}) is new")
            continue
        if y is None:
            out.append(f"body {bid} ({x['name']}) is gone")
            continue
        for k in ("name", "volume"):
            if x[k] != y[k]:
                out.append(f"body {bid}: {k} was {x[k]}, now {y[k]}")
        for k in ("faces", "edges", "vertices"):
            if x[k] != y[k]:
                gone = sorted(set(x[k]) - set(y[k]))[:10]
                new = sorted(set(y[k]) - set(x[k]))[:10]
                out.append(f"body {bid}: {k} IDs changed (lost {gone}, got {new})")
    if a["selection"] != b["selection"]:
        out.append(f"selection was {a['selection']}, now {b['selection']}")
    if a["sets"] != b["sets"]:
        out.append("named sets changed")
    return out


def round_trip(source: "Processor", edits: list[dict]) -> dict[str, Any]:
    """Apply history edits ({"entry": n, "text": "..."} or {"param": "N", "value": 8}),
    then edit every entry back, and compare."""
    sb = Sandbox(source)
    p = sb.p
    before = signature(p)
    _, warned0 = _problems(p)
    originals: list[tuple[int, str]] = []
    during = []
    for ed in edits:
        if "param" in ed:
            name = str(ed["param"]).upper()
            n = p.entry_for_param(name)
            if n is None:
                raise SandboxError(f"no history entry sets {name} as plain '{name} = value'")
            text = f"{name} = {ed['value']}"
        else:
            n, text = int(ed["entry"]), str(ed["text"])
        if not 1 <= n <= p.cursor:
            raise SandboxError(f"no history entry {n} (there are {p.cursor})")
        originals.append((n, p.history[n - 1].text))
        try:
            p.edit_entry(n, text)
        except (CommandError, RebuildCancelled) as exc:
            raise SandboxError(f"edit of entry {n} refused: {exc}") from None
        failed, warned = _problems(p)
        step: dict[str, Any] = {"entry": n, "text": text}
        if failed:
            step["failed"] = failed[:5]
        if warned:
            step["warnings"] = warned[:5]
        during.append(step)
    for n, text in reversed(originals):
        p.edit_entry(n, text)
    after = signature(p)
    failed, warned = _problems(p)
    diffs = _compare(before, after)
    new_warnings = [w for w in warned if w not in warned0]
    out: dict[str, Any] = {"ok": not diffs and not failed and not new_warnings, "during": during}
    if diffs:
        out["differences"] = diffs[:20]
    if failed:
        out["failed_after"] = failed[:5]
    if new_warnings:
        out["warnings_after"] = new_warnings[:5]
    return out
