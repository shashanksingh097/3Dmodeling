"""Safeguards for the assistant (PLAN item 66).

* Reading and changing are kept apart. Every tool the assistant (in the app, or through the
  MCP server) can call has a kind: ``read`` looks at the model, ``try`` works on a copy (the
  sandbox), ``view`` only changes what the 3D view shows or asks the user to click, ``propose``
  hands a change to the user, and ``change`` (only the MCP server's apply, save_project and
  export) changes the model or writes files. Toolbox.call checks after every read and try tool
  that the model is as it was, and puts it back if not.
* A plan before any change: a proposal is run on a copy first, and its expected effect (bodies
  added, removed and changed with their volumes, parameters, steps added, edited and re-run,
  files used) is shown with it, before the user presses Run.
* A confirm step for broad changes: a proposal that removes bodies, changes several existing
  ones, re-runs much of the history, changes a volume by more than half or uses files needs a
  second, deliberate yes.
* One undo for the whole proposal: Processor.undo_group.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .lint import FILE_COMMANDS

if TYPE_CHECKING:
    from ..commands.processor import Processor

# the toolbox's tools that run things on a copy of the model; every other toolbox tool reads
TRY_TOOLS = {"sandbox", "run", "undo", "check", "diagnose", "vary", "round_trip", "sandbox_script"}
# the app assistant's own tools
APP_TOOLS = {"propose_commands": "propose", "propose_edits": "propose", "ask_pick": "view", "highlight": "view",
             "render": "view", "render_detail": "view", "render_compare": "view", "list_files": "read",
             "read_file": "read"}
# the MCP server's own tools: the only ones that change the model or write files
MCP_TOOLS = {"apply": "change", "save_project": "change", "export": "change"}

KINDS = ("read", "try", "view", "propose", "change")

# a change is broad (and needs a confirm) beyond these
BROAD_CHANGED = 3  # existing bodies changed
BROAD_REBUILT = 10  # existing steps re-run by history edits
BROAD_EDITS = 3  # history steps edited, inserted or removed
BROAD_VOLUME = 0.5  # a body's volume changed by more than this fraction


def kind_of(name: str) -> str:
    if name in MCP_TOOLS:
        return MCP_TOOLS[name]
    if name in APP_TOOLS:
        return APP_TOOLS[name]
    return "try" if name in TRY_TOOLS else "read"


def fingerprint(p: "Processor") -> tuple:
    """What a reading tool must leave as it was: the model, the history, undo and the selection."""
    m = p.model
    return (m.revision, p.cursor, len(p.history), tuple((e.uid, e.text) for e in p.history[-3:]),
            len(p._undo), len(p._redo), tuple(m.selection), tuple(sorted(m.bodies)),
            tuple(sorted((k, repr(v)) for k, v in p.params.items())))


def _names(p: "Processor", rows: list[dict]) -> list[str]:
    return [str(r.get("name") or r.get("id")) for r in rows]


def effect(real: "Processor", after: "Processor", *, steps_added: int = 0, edits: list[dict] | None = None,
           files: list[str] | None = None) -> dict[str, Any]:
    """What a proposal will do to the model: ``after`` is a copy with the proposal run on it."""
    from .diff import _vol, diff_states

    ch = diff_states(real._state(), after._state(), limit=200)
    added, removed, changed = ch.get("added", []), ch.get("removed", []), list(ch.get("changed", []))
    # a boolean makes a new body under the old name: that is the body changed, not one removed and one added
    gone = {r["name"]: r for r in removed if r.get("name")}
    for r in list(added):
        old = gone.pop(r.get("name") or "", None) if r.get("name") else None
        if old is not None:
            added.remove(r)
            removed.remove(old)
            changed.append({"id": r["id"], "name": r["name"],
                            "volume": [_vol(real.model.bodies[old["id"]]), r.get("volume")]})
    out: dict[str, Any] = {"added": _names(after, added), "removed": _names(real, removed), "changed": []}
    big: list[str] = []
    for r in changed:
        row: dict[str, Any] = {"body": str(r.get("name") or r["id"])}
        if "volume" in r:
            va, vb = r["volume"]
            row["volume"] = [va, vb]
            if va and vb is not None and abs(vb - va) > BROAD_VOLUME * abs(va):
                big.append(row["body"])
        if "faces" in r:
            row["faces_added"] = len(r["faces"]["added"])
            row["faces_removed"] = len(r["faces"]["removed"])
        out["changed"].append(row)
    if ch.get("params"):
        out["params"] = ch["params"]
    edits = edits or []
    out["steps_added"] = steps_added + sum(1 for e in edits if e["action"] == "insert")
    out["steps_edited"] = sum(1 for e in edits if e["action"] == "edit")
    out["steps_removed"] = sum(1 for e in edits if e["action"] == "delete")
    first = min((int(e["entry"]) for e in edits), default=None)
    out["steps_rerun"] = max(0, real.cursor - first + 1) if first is not None else 0
    if files:
        out["files"] = files
    reasons = []
    if out["removed"]:
        reasons.append(f"removes {_count(len(out['removed']), 'body', 'bodies')}: {_list(out['removed'])}")
    if len(out["changed"]) >= BROAD_CHANGED:
        reasons.append(f"changes {len(out['changed'])} existing bodies")
    if big:
        reasons.append(f"changes the volume of {_list(big)} by more than half")
    if out["steps_rerun"] >= BROAD_REBUILT:
        reasons.append(f"re-runs {out['steps_rerun']} steps of the history")
    if len(edits) >= BROAD_EDITS or out["steps_removed"]:
        n = len(edits)
        reasons.append(f"edits {_count(n, 'history step', 'history steps')}"
                       + (f", removing {out['steps_removed']}" if out["steps_removed"] else ""))
    if files:
        reasons.append("reads or writes files: " + _list(files))
    out["broad"] = reasons
    out["text"] = describe(out)
    return out


def describe(e: dict[str, Any]) -> str:
    """The effect in a few plain lines, as shown above the Run button."""
    lines = []
    if e.get("added"):
        lines.append(f"Adds {_count(len(e['added']), 'body', 'bodies')}: {_list(e['added'])}")
    for r in e.get("changed", [])[:8]:
        what = f"Changes {r['body']}"
        if "volume" in r and None not in r["volume"]:
            what += f": volume {_g(r['volume'][0])} to {_g(r['volume'][1])}"
        lines.append(what)
    if len(e.get("changed", [])) > 8:
        lines.append(f"... and {len(e['changed']) - 8} more bodies")
    if e.get("removed"):
        lines.append(f"Removes {_list(e['removed'])}")
    for k, (a, b) in list(e.get("params", {}).items())[:6]:
        lines.append(f"Sets {k} = {_g(b)}" + (f" (was {_g(a)})" if a is not None else ""))
    steps = []
    if e.get("steps_added"):
        steps.append(f"{_count(e['steps_added'], 'new step', 'new steps')}")
    if e.get("steps_edited"):
        steps.append(f"{e['steps_edited']} edited")
    if e.get("steps_removed"):
        steps.append(f"{e['steps_removed']} removed")
    if e.get("steps_rerun"):
        steps.append(f"{e['steps_rerun']} re-run")
    if steps:
        lines.append("History: " + ", ".join(steps))
    if e.get("files"):
        lines.append("Uses files (not tried on the copy): " + _list(e["files"]))
    if not lines:
        lines.append("No change to the bodies")
    return "\n".join(lines)


def file_lines(script: str) -> list[str]:
    """The lines of a script that read or write files (the copy refuses them)."""
    out = []
    for ln in script.splitlines():
        word = ln.strip().split(",", 1)[0].strip().upper()
        if word in FILE_COMMANDS:
            out.append(ln.strip())
    return out


def plan_script(real: "Processor", script: str) -> dict[str, Any]:
    """Run new steps on a copy of the model; their effect, or the step that fails."""
    from .sandbox import Sandbox

    files = file_lines(script)
    box = Sandbox(real)
    tried = "\n".join(ln for ln in script.splitlines() if ln.strip() not in files) if files else script
    res = box.run(tried)
    if not res["ok"]:
        bad = next((r for r in res["entries"] if not r["ok"]), None)
        refused = res.get("refused")
        return {"error": (bad["line"] + ": " + bad.get("msg", "fails")) if bad else
                str(refused[0]["msg"] if refused else "the script fails on a copy of the model")}
    return effect(real, box.p, steps_added=box.p.cursor - box.base, files=files)


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _list(xs: list[str], most: int = 6) -> str:
    return ", ".join(xs[:most]) + (f" and {len(xs) - most} more" if len(xs) > most else "")


def _g(x) -> str:
    if isinstance(x, float):
        return f"{x:.6g}"
    return str(x)
