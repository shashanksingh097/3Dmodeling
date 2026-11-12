"""A copy of the model to try things in.

The sandbox is a second processor that starts from the user's model (or
from an empty one, or from before history entry n) and shares nothing that
can change: bodies are immutable and the history is copied. Whatever runs
here never reaches the user's model; the only way back is to hand the
script to the user, who runs it themselves.
"""

from __future__ import annotations

import copy
import time
from typing import Any

from ..commands.processor import Processor
from ..core.model import Model
from ..lang.script import ScriptError, first_code_line, split_entries
from . import diff as df
from . import lint as ln

TIME_LIMIT = 60.0  # seconds for one run() call


class SandboxError(Exception):
    pass


class Sandbox:
    def __init__(self, source: Processor, start: str | int = "current") -> None:
        p = Processor(Model(), overrides=source.overrides)
        p.part_cache = source.part_cache  # keys never change meaning, so sharing is safe
        p.lib_files = dict(source.lib_files)
        p.file_map = dict(source.file_map)
        if start == "empty":
            self.start = "empty"
        else:
            if start == "current":
                n = source.cursor
            else:
                n = int(start) - 1  # "before entry n": the state after n-1 entries
                if not 0 <= n <= source.cursor:
                    raise SandboxError(f"there are {source.cursor} entries; give 1 to {source.cursor + 1}")
            p.history = copy.deepcopy(source.history[:n])
            p._snaps = list(source._snaps[: n + 1])
            p.cursor = n
            p._uid = source._uid
            p._restore(p._snaps[n] if start != "current" else source._state())
            self.start = "current" if start == "current" else f"before entry {n + 1}"
        self.p = p
        self.base = p.cursor  # entries up to here came from the user's model

    # ---- running ---------------------------------------------------------------
    def run(self, script: str, stop_on_error: bool = True, detail: bool = False,
            time_limit: float = TIME_LIMIT) -> dict[str, Any]:
        """Run a script entry by entry. Each entry reports ok or not, its
        message, and what it changed."""
        p = self.p
        checked = ln.lint(p, script, sandbox=True)
        refused = [i for i in checked["issues"] if i["level"] == "error" and "sandbox" in i["msg"]]
        if refused:
            return {"ok": False, "refused": refused, "entries": []}
        try:
            units = split_entries(script)
        except ScriptError as exc:
            return {"ok": False, "entries": [{"line": first_code_line(script), "ok": False, "msg": str(exc)}]}
        rows: list[dict[str, Any]] = []
        ok = True
        p.deadline = time.monotonic() + time_limit
        try:
            for unit in units:
                before, at = p._state(), p.cursor
                r = p.run_unit(unit)
                if not r.line:
                    continue
                row: dict[str, Any] = {"line": r.line.splitlines()[0], "ok": r.ok}
                if p.cursor > at:
                    row["entry"] = p.cursor
                msg = r.message.strip()
                if msg and (detail or not r.ok or len(msg) < 300):
                    # a long trace keeps its start and its end, where an error is
                    row["msg"] = msg if len(msg) < 2000 else msg[:600] + "\n...\n" + msg[-1200:]
                if r.warning:
                    row["warning"] = r.warning
                if r.ok:
                    changes = df.diff_states(before, p._state())
                    if not detail:
                        changes.pop("selection", None)
                    if changes:
                        row["changes"] = changes
                else:
                    ok = False
                    hint = _hint(r.message)
                    if hint:
                        row["hint"] = hint
                rows.append(row)
                if not r.ok and stop_on_error:
                    break
        finally:
            p.deadline = None
        return {"ok": ok, "entries": rows, "history": p.cursor, "rev": p.model.revision}

    def script(self) -> str:
        """The entries this sandbox added, as a script to hand to the user."""
        return "\n".join(e.text for e in self.p.history[self.base: self.p.cursor] if not e.suppressed)

    def undo(self, n: int = 1) -> str:
        if self.p.cursor - n < 0:
            raise SandboxError("nothing to undo")
        return self.p.undo(n)


def _hint(message: str) -> str:
    low = message.lower()
    if "unknown command" in low:
        return "find_commands lists the commands; command_help shows one"
    if "is required" in low or "takes at most" in low or "must be" in low:
        return "command_help shows the arguments"
    if "no body" in low or "no face" in low or "no edge" in low:
        return "model_summary lists the bodies; describe_body shows faces and edges"
    if "time limit" in low:
        return "the script ran too long; try fewer steps or a smaller loop"
    return ""
