"""The assistant's modelling tools as an MCP server, for any MCP client (PLAN item 22).

    python -m modeler mcp [--script part.cmd]

speaks the Model Context Protocol over stdin/stdout (JSON-RPC 2.0, one message per line) and
serves the same tools the app's assistant uses (ai/tools.py): find and read commands, run
lines, look at the model (DESCRIBE, PROBE, sections, wall thickness, contacts), check
expectations, a sandbox to try things in, undo. The model lives in this process, headless;
``--script`` runs a script first. Files are read and written where the commands say (EXPORT,
SAVE, RUN ...), as in the app.

The skills (ai/skills.py) are served as prompts (prompts/list, prompts/get) and resources
(resources/list, resources/read with ``skill://name`` and ``skill://name/example.cmd``).

The protocol needs no package: initialize, tools/list, tools/call, prompts, resources and ping are answered,
notifications are taken quietly, and anything else gets "method not found". Only answers go
to stdout; whatever the model or the kernel prints goes to stderr.
"""

from __future__ import annotations

import contextlib
import json
import sys
from typing import Any, TextIO

PROTOCOL = "2025-06-18"
KNOWN_PROTOCOLS = ("2024-11-05", "2025-03-26", "2025-06-18")

INSTRUCTIONS = (
    "A command-driven 3D CAD modeller (OCCT kernel). Build parts by running command lines "
    "(BLOCK, CYL, SKETCH ... EXTRUDE, FILLET, SUBTRACT ...) with the run tool; find commands with "
    "find_commands and read their arguments with command_help before using one. run works on a working "
    "copy (the sandbox, opened by the first run); the reading tools look at that copy while it is open. "
    "Look at the result with model_summary and describe_body, measure with probe_ray, section_profile, "
    "wall_thickness and contact, and state what must hold with check. Every command line is one history "
    "step; undo takes steps back. apply makes the working copy the model; save_project and export write "
    "the model to files. For a whole workflow (sheet metal, enclosures, gears, assemblies, fixing a failed "
    "step ...) read the matching skill first: list_skills and load_skill, or the server's prompts."
)

# tools only this server has: the app's assistant hands its script to the person instead
EXTRA_TOOLS = [
    {"name": "apply", "description": "Make the working copy the model: its new history steps are run on the "
                                     "model and the working copy is closed. Then save_project or export.",
     "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "save_project", "description": "Save the model (after apply) as a project file (.m3d).",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string", "description": "file path"}},
                     "required": ["path"]}},
    {"name": "export", "description": "Write the model's bodies (after apply) to a file; the type comes from the "
                                      "ending: .step .stp .iges .igs .brep .stl .obj .3mf .glb .gltf",
     "inputSchema": {"type": "object", "properties": {
         "path": {"type": "string", "description": "file path"},
         "body": {"type": "string", "description": "one body, by ID or name (default: all)"}},
         "required": ["path"]}},
]


class Server:
    def __init__(self, toolbox, out: TextIO, version: str = "") -> None:
        self.box = toolbox
        self.out = out
        self.version = version
        self.initialized = False

    # ---- one message ---------------------------------------------------------------
    def handle(self, line: str) -> dict | None:
        """The answer to one line from the client, or None (a notification, or nothing)."""
        line = line.strip()
        if not line:
            return None
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            return _error(None, -32700, f"not JSON: {exc}")
        if isinstance(msg, list):  # a batch (2025-03-26)
            answers = [a for a in (self._one(m) for m in msg) if a is not None]
            return answers or None  # type: ignore[return-value]
        return self._one(msg)

    def _one(self, msg: Any) -> dict | None:
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or "method" not in msg:
            if isinstance(msg, dict) and ("result" in msg or "error" in msg):
                return None  # an answer to something we never ask
            return _error(msg.get("id") if isinstance(msg, dict) else None, -32600, "not a JSON-RPC 2.0 request")
        method, mid, params = msg["method"], msg.get("id"), msg.get("params") or {}
        if mid is None:  # a notification: notifications/initialized, cancelled ...
            if method == "notifications/initialized":
                self.initialized = True
            return None
        try:
            if method == "initialize":
                return _result(mid, self._initialize(params))
            if method == "ping":
                return _result(mid, {})
            if method == "tools/list":
                return _result(mid, {"tools": self._tool_list()})
            if method == "tools/call":
                return _result(mid, self._call(params))
            if method == "prompts/list":
                return _result(mid, {"prompts": self._prompts()})
            if method == "prompts/get":
                return _result(mid, self._prompt(params))
            if method == "resources/list":
                return _result(mid, {"resources": self._resources()})
            if method == "resources/templates/list":
                return _result(mid, {"resourceTemplates": []})
            if method == "resources/read":
                return _result(mid, self._read(params))
        except _BadParams as exc:
            return _error(mid, -32602, str(exc))
        return _error(mid, -32601, f"no method {method!r}")

    def _initialize(self, params: dict) -> dict:
        asked = params.get("protocolVersion", PROTOCOL)
        return {
            "protocolVersion": asked if asked in KNOWN_PROTOCOLS else PROTOCOL,
            "capabilities": {"tools": {"listChanged": False}, "prompts": {"listChanged": False},
                             "resources": {"listChanged": False, "subscribe": False}},
            "serverInfo": {"name": "3dmodeling", "title": "3Dmodeling CAD", "version": self.version},
            "instructions": INSTRUCTIONS,
        }

    # ---- skills as prompts and resources ---------------------------------------------
    def _skills(self):
        from . import skills as sk

        return sk.discover(self.box.real.project_dir)

    def _prompts(self) -> list[dict]:
        return [{"name": s.name, "title": s.title, "description": s.description,
                 "arguments": [{"name": "request", "description": "what to make (optional)", "required": False}]}
                for s in self._skills().values()]

    def _prompt(self, params: dict) -> dict:
        s = self._skills().get(str(params.get("name", "")))
        if s is None:
            raise _BadParams(f"no prompt {params.get('name')!r}")
        text = s.body
        if s.example:
            with open(s.example, encoding="utf-8") as f:
                text += "\n\nExample script (it passes its own checks):\n```\n" + f.read().rstrip() + "\n```\n"
        request = (params.get("arguments") or {}).get("request")
        if request:
            text += f"\n\nThe request: {request}\n"
        return {"description": s.description, "messages": [{"role": "user", "content": {"type": "text", "text": text}}]}

    def _resources(self) -> list[dict]:
        out = []
        for s in self._skills().values():
            out.append({"uri": f"skill://{s.name}", "name": s.name, "title": s.title, "description": s.description,
                        "mimeType": "text/markdown"})
            if s.example:
                out.append({"uri": f"skill://{s.name}/example.cmd", "name": f"{s.name} example",
                            "description": f"example script for {s.name}", "mimeType": "text/plain"})
        return out

    def _read(self, params: dict) -> dict:
        uri = str(params.get("uri", ""))
        if not uri.startswith("skill://"):
            raise _BadParams(f"no resource {uri!r}")
        name, _, rest = uri[len("skill://"):].partition("/")
        s = self._skills().get(name)
        if s is None or rest not in ("", "example.cmd") or (rest and not s.example):
            raise _BadParams(f"no resource {uri!r}")
        if rest:
            with open(s.example, encoding="utf-8") as f:
                return {"contents": [{"uri": uri, "mimeType": "text/plain", "text": f.read()}]}
        return {"contents": [{"uri": uri, "mimeType": "text/markdown", "text": s.text()}]}

    def _tool_list(self) -> list[dict]:
        out = [dict(t) for t in EXTRA_TOOLS]
        for d in self.box.definitions():
            out.append({"name": d["name"], "description": d["description"], "inputSchema": d["input_schema"]})
        return out

    def _call(self, params: dict) -> dict:
        name = params.get("name")
        if not isinstance(name, str):
            raise _BadParams("tools/call needs a tool name")
        extra = {t["name"] for t in EXTRA_TOOLS}
        if name not in self.box.tools and name not in extra:
            raise _BadParams(f"no tool {name!r}")
        args = params.get("arguments") or {}
        if not isinstance(args, dict):
            raise _BadParams("arguments must be an object")
        with contextlib.redirect_stdout(sys.stderr):  # nothing but answers on stdout
            if name in extra:
                answer = self._extra(name, args)
            else:
                tool = self.box.tools[name]
                if "where" in tool.params and "where" not in args and self.box.box is not None:
                    args = {**args, "where": "sandbox"}  # look at the working copy while it is open
                answer = self.box.call(name, args)
        text = json.dumps(answer, separators=(",", ":"), default=str)
        res = {"content": [{"type": "text", "text": text}], "isError": "error" in answer}
        if isinstance(answer, dict):
            res["structuredContent"] = json.loads(text)
        return res

    def _extra(self, name: str, args: dict) -> dict:
        p = self.box.real
        if name == "apply":
            if self.box.box is None:
                return {"applied": 0, "msg": "no working copy open: the model is as it is"}
            script = self.box.box.script()
            self.box.box = None
            if not script.strip():
                return {"applied": 0, "msg": "the working copy added nothing"}
            results = p.run_script(script)
            bad = [r for r in results if not r.ok]
            if bad:
                return {"error": f"{bad[0].line}: {bad[0].message}", "applied": len(results) - len(bad)}
            return {"applied": len(results), "history": p.cursor, "bodies": len(p.model.bodies)}
        path = args.get("path")
        if not isinstance(path, str) or not path.strip():
            return {"error": f"{name} needs a path"}
        unknown = set(args) - {"path", "body"}
        if unknown:
            return {"error": f"{name} has no argument {', '.join(sorted(unknown))}"}
        quoted = '"' + path.replace('"', "") + '"'
        if name == "save_project":
            line = f"SAVE, {quoted}"
        else:
            ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
            fmt = {"step": "STEP", "stp": "STEP", "iges": "IGES", "igs": "IGES", "brep": "BREP", "stl": "STL",
                   "obj": "OBJ", "3mf": "3MF", "glb": "GLTF", "gltf": "GLTF"}.get(ext)
            if fmt is None:
                return {"error": f"export: cannot tell the file type from {path!r}",
                        "hint": "end the path with .step .iges .brep .stl .obj .3mf or .glb"}
            line = f"EXPORT, {fmt}, {quoted}" + (f", {args['body']}" if args.get("body") else "")
        note = {"note": "the working copy is still open: call apply first to include its steps"} \
            if self.box.box is not None else {}
        r = p.run(line)
        if r.ok:
            return {"ok": True, "msg": r.message, **note}
        return {"error": r.message, **({"hint": note["note"]} if note else {})}

    # ---- the loop ------------------------------------------------------------------
    def serve(self, inp: TextIO) -> None:
        for line in inp:
            answer = self.handle(line)
            if answer is not None:
                self.out.write(json.dumps(answer, separators=(",", ":")) + "\n")
                self.out.flush()


class _BadParams(Exception):
    pass


def _result(mid, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _error(mid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def main(args: list[str]) -> int:
    from .. import __version__
    from ..commands import Processor
    from .tools import Toolbox

    out = sys.stdout
    sys.stdout = sys.stderr  # stray prints from anywhere must not break the protocol
    p = Processor()
    if args[:1] == ["--script"] and len(args) >= 2:
        with open(args[1], encoding="utf-8") as f:
            bad = [r for r in p.run_script(f.read()) if not r.ok]
        if bad:
            print(f"the script failed: {bad[0].line}: {bad[0].message}", file=sys.stderr)
            return 1
        args = args[2:]
    if args:
        print("usage: python -m modeler mcp [--script part.cmd]", file=sys.stderr)
        return 2
    Server(Toolbox(p), out, __version__).serve(sys.stdin)
    return 0
