"""The tools the AI assistant calls: a fixed list, JSON in and JSON out.

Every tool is a thin layer over the command language (rule 1 of
docs/M9-ai-tools.md): it reads the model or runs commands in a sandbox
copy, and formats the answer. Read tools look at the user's model by
default, or at the sandbox with ``where: "sandbox"``. Nothing here changes
the user's model.

Use from Python::

    box = Toolbox(processor)
    box.call("describe_body", {"body": "flange"})

or from a shell (headless)::

    python -m modeler tool describe_body '{"body": "flange"}' --script scripts/flange.cmd
    python -m modeler tools          # the tool definitions, as JSON
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from ..commands.processor import REGISTRY, Processor
from . import describe as ds
from . import diff as df
from . import expect
from . import lint as ln
from . import selectors as sl
from .sandbox import Sandbox, SandboxError

KINDS = ["BODY", "FACE", "EDGE", "VERTEX"]
_WHERE = {"type": "string", "enum": ["model", "sandbox"],
          "description": "read the user's model (default) or the sandbox"}


@dataclass
class Tool:
    name: str
    description: str
    params: dict[str, Any]  # JSON schema properties
    required: tuple[str, ...]
    fn: Callable[..., Any]

    def definition(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description,
                "input_schema": {"type": "object", "properties": self.params, "required": list(self.required)}}


class ToolError(Exception):
    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


class Toolbox:
    def __init__(self, processor: Processor) -> None:
        self.real = processor
        self.box: Sandbox | None = None
        self.tools: dict[str, Tool] = {t.name: t for t in self._tools()}

    # ---- calling -------------------------------------------------------------------
    def definitions(self) -> list[dict[str, Any]]:
        return [t.definition() for t in self.tools.values()]

    def call(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run one tool. Never raises: a failure is an answer with ``error`` (and a ``hint``)."""
        tool = self.tools.get(name)
        if tool is None:
            return {"error": f"no tool {name!r}", "hint": "tools: " + ", ".join(self.tools)}
        args = dict(args or {})
        unknown = set(args) - set(tool.params)
        if unknown:
            return {"error": f"{name} has no argument {', '.join(sorted(unknown))}",
                    "hint": f"arguments: {', '.join(tool.params) or 'none'}"}
        missing = [k for k in tool.required if k not in args]
        if missing:
            return {"error": f"{name} needs {', '.join(missing)}"}
        try:
            return tool.fn(**args)
        except ToolError as exc:
            out = {"error": str(exc)}
            if exc.hint:
                out["hint"] = exc.hint
            return out
        except (ds.DescribeError, sl.SelectorError, SandboxError, expect.ExpectError, ValueError) as exc:
            return {"error": str(exc)}
        except Exception as exc:  # a kernel failure must not end the conversation
            return {"error": f"{type(exc).__name__}: {exc}"}

    def call_json(self, name: str, args_json: str) -> str:
        try:
            args = json.loads(args_json) if args_json.strip() else {}
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"arguments are not JSON: {exc}"})
        return json.dumps(self.call(name, args), separators=(",", ":"))

    def _p(self, where: str = "model") -> Processor:
        if where == "sandbox":
            if self.box is None:
                raise ToolError("no sandbox is open", "call sandbox first")
            return self.box.p
        if where != "model":
            raise ToolError("where is model or sandbox")
        return self.real

    # ---- the tools -----------------------------------------------------------------
    def _tools(self) -> list[Tool]:
        return [
            Tool("find_commands", "Commands whose name or help matches the words, one line each.",
                 {"query": {"type": "string"}, "limit": {"type": "integer"}}, ("query",), self.find_commands),
            Tool("command_help", "One command's arguments (type, default, help) and examples.",
                 {"name": {"type": "string"}}, ("name",), self.command_help),
            Tool("model_summary", "Units, every body (id, name, kind, volume, bounding box), parameters, datums, "
                 "sketches, named sets, the selection and the history length.",
                 {"where": _WHERE}, (), self.model_summary),
            Tool("describe_body", "One body: valid, volume, area, bounding box, centre, counts, faces by type, "
                 "flat faces by direction, holes (diameter, through or depth, axis, positions, patterns). "
                 "detail 'faces' or 'edges' lists every face or edge instead.",
                 {"body": {"type": ["string", "integer"], "description": "name or ID"},
                  "detail": {"type": "string", "enum": ["summary", "faces", "edges"]},
                  "limit": {"type": "integer"}, "where": _WHERE}, ("body",), self.describe_body),
            Tool("describe_entities", "One row per face, edge or vertex: type, size, centre, normal or axis, "
                 "radius, neighbours, the history entry that made it.",
                 {"kind": {"type": "string", "enum": KINDS}, "ids": {"type": "array", "items": {"type": "integer"}},
                  "where": _WHERE}, ("kind", "ids"), self.describe_entities),
            Tool("history", "History entries with number, text and status (ok, warning, suppressed, undone).",
                 {"first": {"type": "integer"}, "last": {"type": "integer"}, "where": _WHERE}, (), self.history),
            Tool("selector_for", "SEL lines that pick exactly this entity by what it is, not by ID, so scripts "
                 "survive history edits. Says when only the ID works.",
                 {"kind": {"type": "string", "enum": KINDS}, "id": {"type": "integer"}, "where": _WHERE},
                 ("kind", "id"), self.selector_for),
            Tool("preview_selection", "What SEL lines would select, without changing the selection.",
                 {"lines": {"type": "array", "items": {"type": "string"}}, "where": _WHERE}, ("lines",),
                 self.preview_selection),
            Tool("sandbox", "Start (or restart) the sandbox: a copy of the model to run scripts in. start is "
                 "'current' (default), 'empty', or an entry number n (the model before entry n).",
                 {"start": {"type": ["string", "integer"]}}, (), self.sandbox),
            Tool("lint", "Check a script without running it: syntax, unknown commands, argument counts, names "
                 "used before they are set, raw IDs, commands refused in the sandbox.",
                 {"script": {"type": "string"}}, ("script",), self.lint),
            Tool("run", "Run a script in the sandbox, entry by entry: ok or error with message and hint, and what "
                 "each entry changed (bodies made, removed, changed; parameters).",
                 {"script": {"type": "string"}, "stop_on_error": {"type": "boolean"},
                  "detail": {"type": "boolean"}}, ("script",), self.run),
            Tool("undo", "Take back the last n entries in the sandbox.", {"n": {"type": "integer"}}, (), self.undo),
            Tool("check", "Test expectations exactly; each is the arguments of ASSERT: 'VOL(b), BETWEEN, 1, 2', "
                 "'BBOX(b).dz, EQ, 12, 0.01', 'HOLES(b, 8), EQ, 6', 'VALID(b)', 'PIECES(b), EQ, 1', "
                 "'SYMMETRIC(b, \"YZ\")', 'GAP(a, b), EQ, 0'. Checks the sandbox when one is open.",
                 {"expectations": {"type": "array", "items": {"type": "string"}}, "where": _WHERE},
                 ("expectations",), self.check),
            Tool("diff", "What changed between two history positions (0 is the empty start; default: the "
                 "sandbox's own steps, or the last step of the model).",
                 {"first": {"type": "integer"}, "last": {"type": "integer"}, "where": _WHERE}, (), self.diff),
            Tool("sandbox_script", "The commands the sandbox added since it started, as one script.",
                 {}, (), self.sandbox_script),
        ]

    # learn the language
    def find_commands(self, query: str, limit: int = 15) -> dict[str, Any]:
        words = [w.lower() for w in query.split() if w]
        scored = []
        for c in REGISTRY.values():
            text = (c.name + " " + c.help).lower()
            score = sum((3 if w == c.name.lower() else 1) for w in words if w in text)
            if score:
                first = c.help.split(" · ")[0]
                scored.append((-score, c.name, first if len(first) <= 140 else first[:137] + "..."))
        scored.sort()
        rows = [f"{name}: {first}" for _, name, first in scored[:limit]]
        out: dict[str, Any] = {"commands": rows}
        if len(scored) > limit:
            out["more"] = len(scored) - limit
        return out

    def command_help(self, name: str) -> dict[str, Any]:
        c = REGISTRY.get(name.strip().upper())
        if c is None:
            close = self.find_commands(name, 5)["commands"]
            raise ToolError(f"no command {name!r}", "closest: " + "; ".join(close) if close else "")
        args = []
        for a in c.args:
            row = {"name": a.name, "type": _type_name(a.type)}
            if a.default is not None:
                row["default"] = a.default
            if a.help:
                row["help"] = a.help
            args.append(row)
        parts = c.help.split(" · ")
        return {"name": c.name, "help": parts[0], "examples": parts[1:], "args": args,
                "in_history": c.logged}

    # read the model
    def model_summary(self, where: str = "model") -> dict[str, Any]:
        return ds.model_summary(self._p(where))

    def describe_body(self, body, detail: str = "summary", limit: int = ds.LIMIT, where: str = "model"):
        return ds.describe_body(self._p(where), body, detail, limit)

    def describe_entities(self, kind: str, ids: list[int], where: str = "model"):
        return ds.describe_entities(self._p(where), kind, [int(i) for i in ids])

    def history(self, first: int = 1, last: int = 0, where: str = "model") -> dict[str, Any]:
        p = self._p(where)
        last = last or len(p.history)
        rows = []
        for i in range(max(1, first), min(last, len(p.history)) + 1):
            e = p.history[i - 1]
            status = "undone" if i > p.cursor else "suppressed" if e.suppressed else "warning" if e.warning else "ok"
            row: dict[str, Any] = {"n": i, "text": e.text, "status": status}
            if e.warning:
                row["warning"] = e.warning
            rows.append(row)
        return {"entries": rows, "applied": p.cursor}

    def selector_for(self, kind: str, id: int, where: str = "model"):
        return sl.selector_for(self._p(where), kind, int(id))

    def preview_selection(self, lines: list[str], where: str = "model"):
        return sl.preview_selection(self._p(where), lines)

    # sandbox
    def sandbox(self, start="current") -> dict[str, Any]:
        if isinstance(start, str) and start.strip().lstrip("-").isdigit():
            start = int(start)
        if isinstance(start, str) and start not in ("current", "empty"):
            raise ToolError("start is 'current', 'empty' or an entry number")
        self.box = Sandbox(self.real, start)
        p = self.box.p
        return {"sandbox": self.box.start, "history": p.cursor, "bodies": len(p.model.bodies)}

    def lint(self, script: str) -> dict[str, Any]:
        return ln.lint(self.box.p if self.box else self.real, script, sandbox=True)

    def run(self, script: str, stop_on_error: bool = True, detail: bool = False) -> dict[str, Any]:
        if self.box is None:
            self.sandbox("current")
        return self.box.run(script, stop_on_error, detail)  # type: ignore[union-attr]

    def undo(self, n: int = 1) -> dict[str, Any]:
        if self.box is None:
            raise ToolError("no sandbox is open", "call sandbox first")
        msg = self.box.undo(n)
        return {"msg": msg, "history": self.box.p.cursor}

    def check(self, expectations: list[str], where: str = "") -> dict[str, Any]:
        p = self._p(where or ("sandbox" if self.box else "model"))
        rows, passed = [], 0
        for text in expectations:
            try:
                out = expect.check(p, text)
            except expect.ExpectError as exc:
                rows.append({"check": text, "pass": False, "error": str(exc)})
                continue
            rows.append(out.as_dict())
            passed += out.passed
        return {"passed": passed, "failed": len(rows) - passed, "results": rows}

    def diff(self, first: int = -1, last: int = -1, where: str = "") -> dict[str, Any]:
        where = where or ("sandbox" if self.box else "model")
        p = self._p(where)
        last = p.cursor if last < 0 else last
        if first < 0:
            first = self.box.base if where == "sandbox" and self.box else max(0, last - 1)
        return df.diff_entries(p, first, last)

    def sandbox_script(self) -> dict[str, Any]:
        if self.box is None:
            raise ToolError("no sandbox is open", "call sandbox first")
        return {"script": self.box.script(), "entries": self.box.p.cursor - self.box.base}


def _type_name(t) -> str:
    from ..commands.processor import BodyRef, Path, Raw, Text

    return {float: "number", int: "integer", str: "keyword", Text: "text", Path: "file", Raw: "expression",
            BodyRef: "body"}.get(t, getattr(t, "__name__", str(t)))
