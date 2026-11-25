"""PREVIEW: what a step would make, worked out on a copy of the model (PLAN item 83).

The fill-in forms call :func:`preview_step` each time a field changes, and
the 3D view draws the result as a see-through ghost: new and changed bodies
in blue, bodies the step would remove in red, and when the step would fail,
the faces or edges it was given in red with the reason. Nothing reaches the
user's model or history until OK. The same answer is the ``PREVIEW``
command (for scripts and the command line) and the assistant's
``preview_step`` tool (as data).

The ghosts live on ``model.preview`` (not saved, not part of undo) and a
``preview`` event tells the view to redraw them.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from ..lang.script import first_code_line
from .processor import Arg, CommandError, Processor, Raw, command

TIME_LIMIT = 8.0  # seconds a preview may take before it gives up
SLOW = 1.5  # a preview slower than this: the forms switch to "Update preview" by hand

# ghost kinds the view draws: "solid" (see-through blue: what the step makes),
# "removed" (see-through red: bodies the step takes away), "fault" (red, on top:
# what a failing step was given), "curve" (bright: wires and sketches)
GHOST_KINDS = ("solid", "removed", "fault", "curve")

# words of a step that never change bodies, or touch files or the session: no preview
_NO_PREVIEW = {"PREVIEW", "SAVE", "OPEN", "EXPORT", "IMPORT", "NEW", "HIST", "UNDO", "REDO", "FIT", "VIEW",
               "HELP", "DRAWING", "RENDER", "AUTOSAVE", "/UNITS", "LIB", "LINK", "RELOAD", "SAVEPART",
               "OPENPART", "NEWPART", "TUTORIAL", "LAYOUT", "TEMPLATE"}

_ENTITY_RE = re.compile(r"\b(face|edge|vertex|vertice)s?\s+((?:\d+)(?:\s*(?:,|and|to)\s*\d+)*)", re.I)


@dataclass
class Preview:
    ok: bool
    message: str = ""
    added: list[dict] = field(default_factory=list)  # {"id", "name", "volume"}
    changed: list[dict] = field(default_factory=list)  # {"id", "name", "volume": [before, after]}
    removed: list[dict] = field(default_factory=list)  # {"id", "name"}
    fault: dict | None = None  # {"kind": FACE|EDGE|VERTEX|BODY, "ids": [...]} when it would fail
    seconds: float = 0.0
    skipped: str = ""  # why there is no preview (a file command, an empty line ...)
    ghosts: list = field(default_factory=list, repr=False)  # (shape, kind) for the view

    def data(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": self.ok, "message": self.message, "added": self.added,
                               "changed": self.changed, "removed": self.removed,
                               "seconds": round(self.seconds, 3)}
        if self.fault:
            out["fault"] = self.fault
        if self.skipped:
            out["skipped"] = self.skipped
        out["text"] = self.text()
        return out

    def text(self) -> str:
        """One or two plain lines: what the step would do, or why it would fail."""
        if self.skipped:
            return f"No preview: {self.skipped}"
        if not self.ok:
            where = ""
            if self.fault and self.fault["ids"]:
                k = self.fault["kind"].lower()
                ids = self.fault["ids"]
                where = f" (shown in red: {k} {_ids(ids)})" if len(ids) == 1 else f" (shown in red: {k}s {_ids(ids)})"
            return f"Would fail: {_reason(self.message)}{where}"
        bits = []
        for r in self.added:
            bits.append(f"adds {_label(r)}" + (f", volume {_g(r['volume'])}" if r.get("volume") is not None else ""))
        for r in self.changed:
            va, vb = r.get("volume", [None, None])
            named = bool(r.get("name")) and r["name"] != f"body{r['id']}"
            what = _label(r) if ("was" not in r or named) else f"body {r['was']} (becomes body {r['id']})"
            if va is not None and vb is not None:
                d = vb - va
                bits.append(f"changes {what}, volume {_g(va)} -> {_g(vb)} ({'+' if d >= 0 else ''}{_g(d)})")
            else:
                bits.append(f"changes {what}")
        for r in self.removed:
            if not r.get("replaced"):
                bits.append(f"removes {_label(r)}")
        if not bits:
            return "Changes no bodies" + (f": {_reason(self.message)}" if self.message else "")
        return "; ".join(bits)


def _g(x: float) -> str:
    return f"{x:,.6g}"


def _ids(ids: list[int]) -> str:
    return ", ".join(map(str, ids[:8])) + (f" and {len(ids) - 8} more" if len(ids) > 8 else "")


def _label(r: dict) -> str:
    name = r.get("name") or ""
    return name if name and name != f"body{r['id']}" else f"body {r['id']}"


def _reason(msg: str) -> str:
    line = (msg or "").strip().splitlines()[0] if (msg or "").strip() else "the step fails"
    return line


def _volume(body) -> float | None:
    try:
        from .queries import props

        if getattr(body, "mesh", None) is not None and getattr(body, "shape", None) is None:
            return None
        return float(props("BODY", body.shape).Mass())
    except Exception:  # noqa: BLE001 - a body without a volume (a wire, a mesh) has none
        return None


def _command_word(text: str) -> str:
    line = first_code_line(text or "").strip()
    return line.split(",", 1)[0].strip().upper() if line else ""


def _fault_of(box_p: Processor, real: Processor, message: str) -> dict | None:
    """What to show in red when a step fails: the entities its message names, or
    the faces, edges or bodies it was given (the selection, or the bodies it names)."""
    m = box_p.model
    named: dict[str, list[int]] = {}
    for word, nums in _ENTITY_RE.findall(message or ""):
        k = {"face": "FACE", "edge": "EDGE", "vertex": "VERTEX", "vertice": "VERTEX"}[word.lower()]
        for n in re.findall(r"\d+", nums):
            gid = int(n)
            try:
                m.entity_owner(k, gid)
            except Exception:  # noqa: BLE001 - a number in the message that is not an entity
                continue
            named.setdefault(k, []).append(gid)
    if named:
        k = max(named, key=lambda kk: len(named[kk]))
        return {"kind": k, "ids": sorted(dict.fromkeys(named[k]))}
    if m.selection:
        return {"kind": m.selection_kind, "ids": list(m.selection)}
    body_re = re.compile(r"\bbody (\d+)\b", re.I)
    ids = [int(b) for b in body_re.findall(message or "") if int(b) in m.bodies]
    if ids:
        return {"kind": "BODY", "ids": sorted(dict.fromkeys(ids))}
    return None


def _fault_shapes(model, fault: dict | None) -> list:
    if not fault:
        return []
    out = []
    for gid in fault["ids"][:200]:
        try:
            shape = model.bodies[gid].shape if fault["kind"] == "BODY" else model.entity_shape(fault["kind"], gid)
        except Exception:  # noqa: BLE001 - gone
            continue
        if shape is not None:
            out.append((shape, "fault"))
    return out


def preview_step(p: Processor, text: str, edit_row: int | None = None,
                 time_limit: float = TIME_LIMIT) -> Preview:
    """Run ``text`` on a copy of the model and say what it would do.

    ``edit_row`` (0-based) previews a changed history entry instead: the copy
    runs ``HIST, EDIT`` on that row, so later steps follow as they would."""
    from ..ai.sandbox import Sandbox
    from ..ai.lint import lint

    t0 = time.monotonic()
    word = _command_word(text)
    if not word:
        return Preview(ok=True, skipped="nothing to run yet")
    if word in _NO_PREVIEW and edit_row is None:
        return Preview(ok=True, skipped=f"{word} does not change the shapes")
    checked = lint(p, text, sandbox=True)
    files = [i for i in checked["issues"] if i["level"] == "error" and "sandbox" in i["msg"]]
    if files:
        return Preview(ok=True, skipped="it reads or writes files")
    box = Sandbox(p)
    run = text
    if edit_row is not None:
        from ..lang.expr import format_value

        run = f"HIST, EDIT, {edit_row + 1}, {format_value(text)}"
    res = box.run(run, time_limit=time_limit)
    seconds = time.monotonic() - t0
    if res.get("refused"):
        return Preview(ok=True, skipped="it reads or writes files", seconds=seconds)
    bad = next((e for e in res["entries"] if not e["ok"]), None)
    if bad is not None or not res["ok"]:
        msg = (bad or {}).get("msg") or "the step fails"
        fault = _fault_of(box.p, p, msg)
        pv = Preview(ok=False, message=msg, fault=fault, seconds=seconds)
        pv.ghosts = _fault_shapes(box.p.model, fault)
        return pv
    real, after = p.model, box.p.model
    pv = Preview(ok=True, message=(res["entries"][-1].get("msg", "") if res["entries"] else ""), seconds=seconds)
    for bid, body in after.bodies.items():
        old = real.bodies.get(bid)
        if old is body:
            continue
        name = body.name or ""
        if old is None:
            pv.added.append({"id": bid, "name": name, "volume": _volume(body)})
        else:
            pv.changed.append({"id": bid, "name": name, "volume": [_volume(old), _volume(body)]})
        if body.shape is not None and not body.shape.IsNull():
            pv.ghosts.append((body.shape, "solid"))
    for bid, body in real.bodies.items():
        if bid not in after.bodies:
            pv.removed.append({"id": bid, "name": body.name or ""})
            if body.shape is not None:
                pv.ghosts.append((body.shape, "removed"))
    # a boolean makes a new body under the old name: call it the body changed, as people see it
    gone = {r["name"]: r for r in pv.removed if r["name"]}
    for r in list(pv.added):
        old = gone.pop(r["name"], None) if r["name"] else None
        if old is not None:
            pv.added.remove(r)
            pv.removed.remove(old)
            pv.changed.append({"id": r["id"], "name": r["name"], "was": old["id"],
                               "volume": [_volume(real.bodies[old["id"]]), r["volume"]]})
            pv.ghosts = [(s, k) for s, k in pv.ghosts
                         if not (k == "removed" and s is real.bodies[old["id"]].shape)]
    # one body in, one body out (FILLET, HOLE, SHELL on an unnamed body): that body changed
    if len(pv.added) == 1 and len(pv.removed) == 1 and not pv.changed:
        a, r = pv.added[0], pv.removed[0]
        pv.changed.append({"id": a["id"], "name": a["name"] or r["name"], "was": r["id"],
                           "volume": [_volume(real.bodies[r["id"]]), a["volume"]]})
        pv.added, pv.removed = [], [r]
        pv.removed[0]["replaced"] = True
    return pv


def show(p: Processor, pv: Preview | None) -> None:
    """Hand a preview's ghosts to the view (None clears them)."""
    if pv is None:
        p.model.set_preview([])
        return
    ids = [r.get("was", r["id"]) for r in pv.changed] + [r["id"] for r in pv.removed]
    p.model.set_preview(pv.ghosts, list(dict.fromkeys(ids)))


@command(
    "PREVIEW",
    Arg("step", Raw, help='the step to try, in quotes: PREVIEW, "FILLET, 2" · PREVIEW, OFF clears the ghost'),
    logged=False,
    help='Show what a step would make without running it: PREVIEW, "FILLET, 2" draws the result see-through '
         "in the 3D view (new and changed bodies blue, removed ones red) and says what it would change, or "
         "why it would fail with the faces or edges at fault in red. Nothing is added to the history. "
         "PREVIEW, OFF clears the ghost. The fill-in forms do this as you type.",
)
def preview_cmd(p: Processor, step):
    s = str(step or "").strip()
    if len(s) >= 2 and s[0] == s[-1] == '"':
        s = s[1:-1].replace('""', '"')
    if s.upper() in ("", "OFF", "NONE", "CLEAR"):
        had = bool(p.model.preview)
        p.model.set_preview([])
        return "preview cleared" if had else "no preview was shown"
    if _command_word(s) == "PREVIEW":
        raise CommandError("PREVIEW: give the step to try, not another PREVIEW")
    pv = preview_step(p, s)
    show(p, pv)
    return pv.text()
