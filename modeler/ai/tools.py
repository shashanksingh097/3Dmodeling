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
from . import experiments as ex
from . import probe as pb
from . import contact as cx
from . import relate as rl
from . import selectors as sl
from .sandbox import Sandbox, SandboxError

KINDS = ["BODY", "FACE", "EDGE", "VERTEX"]
_POINT = {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3}
_BODIES = {"type": "array", "items": {"type": ["string", "integer"]},
           "description": "bodies to look at (default: every shown body)"}
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
        from . import safeguards as sg

        real = self.real
        mark = sg.fingerprint(real)
        backup, undo, redo = real.history_backup(), list(real._undo), list(real._redo)
        try:
            answer = self._call(tool, args)
        finally:
            if sg.fingerprint(real) != mark:  # a tool that reads or tries must never change the model
                real.history_restore(backup)
                real._undo, real._redo = undo, redo
                real.model.selection = list(backup["state"]["model"]["selection"])
                answer = {"error": f"{name} changed the user's model, which tools may not do; it was put back. "
                                   "This is a bug: please report it."}
        return answer

    def _call(self, tool: Tool, args: dict[str, Any]) -> dict[str, Any]:
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
            Tool("list_skills", "The skills: one short guide per workflow (sheet metal, enclosures, assemblies, "
                 "fixing failed steps ...), name and when to use it. Load the one that matches before writing a "
                 "script for it.", {}, (), self.list_skills),
            Tool("load_skill", "One skill's text: the steps in order, the commands, the checks that prove the "
                 "result, the usual mistakes, and an example script that passes its own checks.",
                 {"name": {"type": "string"}}, ("name",), self.load_skill),
            Tool("search_docs", "The parts of the language guide, the user guide, the skills and the example "
                 "scripts that match some words, trimmed to the matching part. For how something works that "
                 "command_help does not say (blocks, history editing, sketches, imports ...).",
                 {"query": {"type": "string"}, "limit": {"type": "integer"},
                  "sources": {"type": "array", "items": {"type": "string",
                                                         "enum": ["docs", "skill", "example"]}}},
                 ("query",), self.search_docs),
            Tool("parameters", "Every parameter: its value, the history step that sets it (with the HIST, EDIT "
                 "line to change it) and the steps that read it. Use it to turn 'make it wider' into one edit.",
                 {"where": _WHERE}, (), self.parameters),
            Tool("sketch_state", "A sketch: each curve (free or held), the constraints and sizes, degrees of "
                 "freedom left, repeated constraints and the closed profiles found. No name: every sketch's status.",
                 {"name": {"type": "string"}, "where": _WHERE}, (), self.sketch_state),
            Tool("diagnose", "Why a step failed and which usual fixes work: tries them on a copy of the model "
                 "(a size under the limit the message gives, smaller numbers, a fillet moved before the shell, HEAL "
                 "before a boolean, the nearest name) and gives the exact line to run for each one that passes. "
                 "No step and no line: the first failed history step, else the last failed line typed. fault: the "
                 "faces, edges or bodies at fault (kind + ids), the ones the user sees in red.",
                 {"step": {"type": "integer", "description": "history step number"},
                  "line": {"type": "string", "description": "a command line to look at instead"},
                  "where": _WHERE}, (), self.diagnose),
            Tool("model_summary", "Units, every body (id, name, kind, volume, bounding box), parameters, datums, "
                 "sketches, named sets, the selection and the history length.",
                 {"where": _WHERE}, (), self.model_summary),
            Tool("describe_body", "One body: valid, volume, area, bounding box, centre, counts, faces by type, "
                 "flat faces by direction, holes (diameter, through or depth, axis, positions, patterns), "
                 "features (fillets and rounds by radius, chamfers, bosses, pockets and slots with depth). "
                 "detail 'faces' or 'edges' lists every face or edge instead.",
                 {"body": {"type": ["string", "integer"], "description": "name or ID"},
                  "detail": {"type": "string", "enum": ["summary", "faces", "edges"]},
                  "limit": {"type": "integer"}, "where": _WHERE}, ("body",), self.describe_body),
            Tool("describe_entities", "One row per face, edge or vertex: type, size, centre, normal or axis, "
                 "radius, neighbours, the history entry that made it.",
                 {"kind": {"type": "string", "enum": KINDS}, "ids": {"type": "array", "items": {"type": "integer"}},
                  "where": _WHERE}, ("kind", "ids"), self.describe_entities),
            Tool("around", "What touches a face, edge or vertex: the faces next to it ring by ring (depth 1 to 3), "
                 "each with type, size, the way it faces and the feature it belongs to (hole, fillet, pocket ...).",
                 {"kind": {"type": "string", "enum": ["FACE", "EDGE", "VERTEX"]}, "id": {"type": "integer"},
                  "depth": {"type": "integer"}, "where": _WHERE}, ("kind", "id"), self.around),
            Tool("outline", "A body seen from a view (FRONT, TOP, RIGHT, LEFT, BACK, BOTTOM, ISO) as numbers: its "
                 "visible edges flattened, joined and simplified to a few hundred points, whole circles apart, "
                 "the size, and an SVG path. A picture in text; hidden=true adds hidden edges.",
                 {"body": {"type": ["string", "integer"]}, "view": {"type": "string"}, "hidden": {"type": "boolean"},
                  "where": _WHERE}, ("body",), self.outline),
            Tool("history", "History entries with number, text and status (ok, warning, suppressed, undone).",
                 {"first": {"type": "integer"}, "last": {"type": "integer"}, "where": _WHERE}, (), self.history),
            Tool("user_context", "What the user is pointing at now: the selection (each entity described, and SEL "
                 "lines for it), what a click picks, the open sketch, the work plane and the view direction. "
                 "Call it for 'this face', 'these edges', 'here'.", {}, (), self.user_context),
            Tool("selector_for", "SEL lines that pick exactly this entity by what it is, not by ID, so scripts "
                 "survive history edits. Says when only the ID works.",
                 {"kind": {"type": "string", "enum": KINDS}, "id": {"type": "integer"}, "where": _WHERE},
                 ("kind", "id"), self.selector_for),
            Tool("preview_step", "What one step would do, worked out on a copy of the model (the same as the "
                 "see-through preview the user's forms show): bodies added, changed (volume before and after) or "
                 "removed; or why it would fail, with the faces or edges at fault. entry (1-based) previews a "
                 "changed history entry instead (HIST, EDIT on a copy). Nothing changes.",
                 {"step": {"type": "string"}, "entry": {"type": "integer"}, "where": _WHERE}, ("step",),
                 self.preview_step),
            Tool("suggest_tools", "The modelling tools that fit the user's pick (or the sandbox's), best first, "
                 "each with what it runs: the list their right-click menu and the small toolbar beside a pick "
                 "show (Sketch on this face, Pull, Hole, Fillet, Loop, Tangent chain, Mate ...).",
                 {"where": _WHERE}, (), self.suggest_tools),
            Tool("templates", "The project templates the user can start from (start page, File > New, NEW, name): "
                 "each with its title, what it is for and what it sets (units, layers, parameters, materials, "
                 "title block, a first sketch). Starting one clears the model, so suggest it to the user (or "
                 "use it in the sandbox: sandbox then run NEW, name) rather than running it on their model.",
                 {}, (), self.templates),
            Tool("selection_numbers", "The numbers of the user's pick (or of kind + ids): a face's type, area and "
                 "radius; an edge's length, radius and arc angle; a vertex's position; a body's volume, area, size "
                 "and mass; totals for several, and the distance and angle between two. The same line their "
                 "status bar shows (status_line). Use it for 'how big is this', 'how far apart are these'.",
                 {"kind": {"type": "string", "enum": KINDS}, "ids": {"type": "array", "items": {"type": "integer"}},
                  "where": _WHERE}, (), self.selection_numbers),
            Tool("properties", "One table of a body's properties (default: the user's pick), or of a history step's "
                 "values (step): name, where (x, y, z of its centre), colour, layer, material, size, volume, area, "
                 "mass, and the values of the steps that made it (key 5.dx: argument dx of step 5; a part copy's "
                 "values too). Rows with edit set can be changed with PROPS, b, key, value, which writes the "
                 "ordinary step (MOVE, COLOR, HIST, EDIT ...): the same table as the user's Properties panel.",
                 {"body": {"type": "string", "description": "a body name or ID (default: the pick)"},
                  "step": {"type": "integer", "description": "a history step instead of a body"},
                  "where": _WHERE}, (), self.properties),
            Tool("view_state", "How the user's 3D view looks now: the direction it looks from (looking_from, "
                 "from the model towards the eye), which way is up, its name when it is a view cube side, edge "
                 "or corner (TOP, TOP FRONT, TOP FRONT RIGHT = iso), the bodies in sight, out of sight and "
                 "hidden. VIEW, name / VIEW, TURN, LEFT / VIEW, HOME change it (the view cube writes these).",
                 {}, (), self.view_state),
            Tool("tutorial", "The lesson the user is following (Help > Tutorials), if any: its step, the "
                 "step's text, what 'Show me' would run (hints) and each check with pass and what was found; "
                 "with no lesson, the tutorials there are. Help the user do the step themselves (say which "
                 "button, or the command); TUTORIAL, NEXT goes on once every check passes.",
                 {}, (), self.tutorial),
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
                 "'SYMMETRIC(b, \"YZ\")', 'GAP(a, b), EQ, 0', 'TOUCH(a, b)', 'OVERLAP(a, b), EQ, 0', "
                 "'GROUPS(), EQ, 1', 'CLEARANCE(pin, plate), GE, 0.05', 'PROBLEMS(b), EQ, 0', 'SAMESHAPE(a, b)'. Checks the sandbox when one is open.",
                 {"expectations": {"type": "array", "items": {"type": "string"}}, "where": _WHERE},
                 ("expectations",), self.check),
            Tool("diff", "What changed between two history positions (0 is the empty start; default: the "
                 "sandbox's own steps, or the last step of the model).",
                 {"first": {"type": "integer"}, "last": {"type": "integer"}, "where": _WHERE}, (), self.diff),
            Tool("sandbox_script", "The commands the sandbox added since it started, as one script.",
                 {}, (), self.sandbox_script),
            Tool("probe_ray", "Every face a ray crosses (body, face ID, point, distance, enters or leaves) and the "
                 "stretches of material along it: wall thickness on a line, does a hole go through, how far above "
                 "the plate a boss sits.",
                 {"origin": _POINT, "dir": _POINT, "bodies": _BODIES, "where": _WHERE}, ("origin", "dir"),
                 self.probe_ray),
            Tool("probe_point", "For each point: inside, on or outside which body, the nearest face and the "
                 "distance to it.",
                 {"points": {"type": "array", "items": _POINT}, "bodies": _BODIES, "where": _WHERE}, ("points",),
                 self.probe_point),
            Tool("section_profile", "The cut through a body as text: loops (outside or hole) of lines, arcs, "
                 "circles and rectangles in the plane's u, v coordinates, area and centre. Give offsets for a "
                 "stack of parallel cuts, which reads like a scan.",
                 {"body": {"type": ["string", "integer"]},
                  "plane": {"type": "string", "description": "XY, YZ, ZX or a datum plane name"},
                  "offsets": {"type": "array", "items": {"type": "number"}}, "where": _WHERE},
                 ("body", "plane"), self.section_profile),
            Tool("wall_thickness", "The thinnest walls of a body, measured straight into the material from points "
                 "over every face: thickness, the two faces and points. With below, every wall thinner than that.",
                 {"body": {"type": ["string", "integer"]}, "below": {"type": "number"}, "limit": {"type": "integer"},
                  "where": _WHERE}, ("body",), self.wall_thickness),
            Tool("contact", "Do two bodies touch? state 'apart' (gap, nearest points and faces), 'touch' (on "
                 "faces with the area, along a line with its length, or at a point; the faces in contact) or "
                 "'overlap' (volume in common, its box, the faces that dig in). tol: closer than this counts "
                 "as touching (default a millionth of the size).",
                 {"a": {"type": ["string", "integer"]}, "b": {"type": ["string", "integer"]},
                  "tol": {"type": "number"}, "where": _WHERE}, ("a", "b"), self.contact),
            Tool("assembly_check", "Check how all the parts sit together: every pair of solid bodies, with "
                 "the overlaps (clashes), the touching pairs and how, pairs closer than near, the groups of "
                 "bodies held together through contacts and the bodies touching nothing (floating). against "
                 "checks only those bodies against the rest.",
                 {"bodies": _BODIES, "against": {"type": ["string", "integer", "array"]},
                  "tol": {"type": "number"}, "near": {"type": "number", "description": "also list gaps up to this"},
                  "where": _WHERE}, (), self.assembly_check),
            Tool("fit_check", "Shafts in holes between two bodies (a bolt in a plate, a pin in a bush): both "
                 "diameters, clearance (negative: interference), state clearance / line to line / interference, "
                 "axis offset, tightest gap and engaged length.",
                 {"a": {"type": ["string", "integer"]}, "b": {"type": ["string", "integer"]},
                  "where": _WHERE}, ("a", "b"), self.fit_check),
            Tool("placement", "Where body a sits relative to body b: per axis X, Y, Z on which side and the gap, "
                 "or within / around / overlapping; the centre offset and the axes they are centred on; contact; "
                 "which face of a rests on b; flush flat faces; round faces on the same axis. Checks 'the lid "
                 "sits centred on the box' without a picture.",
                 {"a": {"type": ["string", "integer"]}, "b": {"type": ["string", "integer"]},
                  "where": _WHERE}, ("a", "b"), self.placement),
            Tool("check_design", "Rule checks on one body, each problem with IDs: not valid, open edges, not a "
                 "solid, loose pieces, inside out, edges shorter than min_edge, sliver faces, faces cutting "
                 "through each other, and walls thinner than min_wall when given. ok is true when none.",
                 {"body": {"type": ["string", "integer"]}, "min_wall": {"type": "number"},
                  "min_edge": {"type": "number", "description": "default: a thousandth of the body's size"},
                  "where": _WHERE}, ("body",), self.check_design),
            Tool("compare_bodies", "Are two bodies the same shape? Compares volume, area, faces by type and "
                 "inertia; when they match, says whether b is a moved copy (with the move) or a mirror image "
                 "of a; otherwise lists what differs.",
                 {"a": {"type": ["string", "integer"]}, "b": {"type": ["string", "integer"]},
                  "where": _WHERE}, ("a", "b"), self.compare_bodies),
            Tool("vary", "Re-run the history with each value of a parameter (set by a plain 'NAME = value' "
                 "entry) and report which values make a step fail or an expectation fail. Checks that the model "
                 "is really parametric. Uses the sandbox when one is open.",
                 {"param": {"type": "string"}, "values": {"type": "array"},
                  "expectations": {"type": "array", "items": {"type": "string"}}}, ("param", "values"), self.vary),
            Tool("round_trip", "Make history edits ({entry, text} or {param, value}), edit them back, and check "
                 "that every ID, volume, the selection and named sets came back and no step has a new warning. "
                 "Tests that a script's picks survive history edits. Uses the sandbox when one is open.",
                 {"edits": {"type": "array", "items": {"type": "object"}}}, ("edits",), self.round_trip),
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

    # skills
    def list_skills(self) -> dict[str, Any]:
        from . import skills as sk

        return sk.list_rows(self.real.project_dir)

    def load_skill(self, name: str) -> dict[str, Any]:
        from . import skills as sk

        try:
            return sk.load(name, self.real.project_dir)
        except sk.SkillError as exc:
            raise ToolError(str(exc), "list_skills gives the names") from None

    def search_docs(self, query: str, limit: int = 4, sources: list[str] | None = None):
        from . import knowledge as kn

        if sources:
            sources = ["LANGUAGE.md", "USER-GUIDE.md"] + [s for s in sources if s != "docs"] \
                if "docs" in sources else sources
        return kn.search_docs(query, int(limit), sources, self.real.project_dir)

    def parameters(self, where: str = "model"):
        from . import knowledge as kn

        return kn.parameters(self._p(where))

    def sketch_state(self, name: str = "", where: str = "model"):
        from . import knowledge as kn

        return kn.sketch_state(self._p(where), name)

    def diagnose(self, step: int | None = None, line: str = "", where: str = "model"):
        from . import diagnose as dg

        return dg.diagnose(self._p(where), int(step) if step else None, line or None)

    # read the model
    def model_summary(self, where: str = "model") -> dict[str, Any]:
        return ds.model_summary(self._p(where))

    def describe_body(self, body, detail: str = "summary", limit: int = ds.LIMIT, where: str = "model"):
        return ds.describe_body(self._p(where), body, detail, limit)

    def describe_entities(self, kind: str, ids: list[int], where: str = "model"):
        return ds.describe_entities(self._p(where), kind, [int(i) for i in ids])

    def around(self, kind: str, id: int, depth: int = 1, where: str = "model"):  # noqa: A002 - the tool's word
        return ds.around(self._p(where), kind, int(id), int(depth or 1))

    def outline(self, body, view: str = "FRONT", hidden: bool = False, where: str = "model"):
        return ds.outline(self._p(where), body, view or "FRONT", bool(hidden))

    def history(self, first: int = 1, last: int = 0, where: str = "model") -> dict[str, Any]:
        p = self._p(where)
        last = last or len(p.history)
        rows = []
        for i in range(max(1, first), min(last, len(p.history)) + 1):
            e = p.history[i - 1]
            status = ("undone" if i > p.cursor else "suppressed" if e.suppressed else "failed" if not e.ok
                      else "warning" if e.warning else "ok")
            row: dict[str, Any] = {"n": i, "text": e.text, "status": status}
            if not e.ok and i <= p.cursor:
                row["error"] = (e.message or "").splitlines()[0]
            if e.warning:
                row["warning"] = e.warning
            rows.append(row)
        return {"entries": rows, "applied": p.cursor}

    def user_context(self) -> dict[str, Any]:
        p = self.real
        m = p.model
        out: dict[str, Any] = {"selection": {"kind": m.selection_kind, "ids": list(m.selection)}}
        if m.selection:
            ids = list(m.selection)[:20]
            if m.selection_kind == "BODY":
                out["selection"]["bodies"] = [{"id": b, "name": getattr(m.bodies[b], "name", "") or ""}
                                              for b in ids if b in m.bodies]
            else:
                out["selection"]["described"] = ds.describe_entities(p, m.selection_kind, ids)
            if len(m.selection) == 1:
                try:
                    out["selection"]["selector"] = sl.selector_for(p, m.selection_kind, m.selection[0])
                except sl.SelectorError as exc:
                    out["selection"]["selector"] = {"error": str(exc)}
            if len(m.selection) > 20:
                out["selection"]["note"] = f"first 20 of {len(m.selection)} described"
            try:  # the numbers the user sees in the status bar: totals, distance and angle of two picks
                from ..commands import selinfo as si

                info = si.selection_info(p, limit=0)
                out["selection"]["numbers"] = {k: info[k] for k in ("total", "pair") if k in info}
                out["selection"]["numbers"]["status_line"] = si.line(info, pretty=False) if len(m.selection) > 1 \
                    else si.line(si.selection_info(p), pretty=False)
            except Exception:  # noqa: BLE001 - numbers are a help, never a failure
                pass
        else:
            out["selection"]["note"] = "nothing is selected; ask_pick asks the user to click"
        view = getattr(p, "view", None)
        if view is not None:
            out["click_picks"] = getattr(view, "pick_mode", "")
            try:
                d = view.view.Camera().Direction()
                out["looking_along"] = [round(d.X(), 3), round(d.Y(), 3), round(d.Z(), 3)]
            except Exception:  # noqa: BLE001 - no camera yet
                pass
        out["active_sketch"] = m.active_sketch or ""
        wp = getattr(m, "workplane", None)
        out["workplane"] = getattr(wp, "name", "") if wp is not None else "XY (default)"
        return out

    def selector_for(self, kind: str, id: int, where: str = "model"):
        return sl.selector_for(self._p(where), kind, int(id))

    def preview_step(self, step: str, entry: int | None = None, where: str = "model") -> dict[str, Any]:
        from ..commands import preview_handlers as ph

        p = self._p(where)
        if entry is not None and not 1 <= int(entry) <= p.cursor:
            raise ToolError(f"entry is 1 to {p.cursor}")
        return ph.preview_step(p, step, int(entry) - 1 if entry is not None else None).data()

    def suggest_tools(self, where: str = "model") -> dict[str, Any]:
        from ..gui import body_menu as bm

        p = self._p(where)
        return {"selection": {"kind": p.model.selection_kind, "ids": list(p.model.selection)},
                "tools": bm.tools_rows(p)}

    def templates(self) -> dict[str, Any]:
        from ..commands import template_handlers as th

        return {"templates": [t.data() for t in th.all_templates()], "user_folder": th.user_dir(),
                "start": "NEW, name (clears the model: the template's steps become the first history entries)",
                "save_own": "TEMPLATE, SAVE, name [, title [, about]]"}

    def selection_numbers(self, kind: str | None = None, ids: list[int] | None = None,
                          where: str = "model") -> dict[str, Any]:
        from ..commands import selinfo as si

        p = self._p(where)
        if ids is not None and not kind:
            raise ToolError("give the kind with the ids")
        if kind and kind.upper() not in KINDS:
            raise ToolError("kind is BODY, FACE, EDGE or VERTEX")
        try:
            info = si.selection_info(p, kind, [int(i) for i in ids] if ids is not None else (None if not kind or
                                     kind.upper() == p.model.selection_kind else []))
        except KeyError:
            raise ToolError("kind is BODY, FACE, EDGE or VERTEX") from None
        info["status_line"] = si.line(info, pretty=False)
        return info

    def properties(self, body: str | None = None, step: int | None = None, where: str = "model") -> dict[str, Any]:
        from ..commands import props_handlers as ph
        from ..commands.processor import CommandError

        p = self._p(where)
        try:
            if step is not None:
                if not 1 <= int(step) <= p.cursor:
                    raise ToolError(f"there are {p.cursor} history steps; give 1 to {p.cursor}")
                d = ph.step_properties(p, int(step))
            else:
                d = ph.properties(p, ph.body_of(p, str(body) if body not in (None, "") else "SEL"))
        except CommandError as exc:
            raise ToolError(str(exc)) from None
        d["change"] = "PROPS, b, key, value (b: the body, or STEP n): one ordinary step, Undo takes it back"
        return d

    def view_state(self) -> dict[str, Any]:
        p = self.real
        view = getattr(p, "view", None)
        if view is None or not hasattr(view, "view_state"):
            return {"note": "no 3D view is open (scripts and tests run without one)",
                    "hidden": sorted(p.model.hidden)}
        return view.view_state()

    def tutorial(self) -> dict[str, Any]:
        from ..commands import tutorial_handlers as th

        p = self.real
        if p.tutorial is not None:
            th.check_step(p, p.tutorial)
        return th.state(p)

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

    # probe space
    def probe_ray(self, origin, dir, bodies=None, where: str = "model"):
        return pb.probe_ray(self._p(where), origin, dir, bodies)

    def probe_point(self, points, bodies=None, where: str = "model"):
        return pb.probe_point(self._p(where), points, bodies)

    def section_profile(self, body, plane: str, offsets: list[float] | None = None, where: str = "model"):
        p = self._p(where)
        return pb.section_profile(p, body, _plane(p, plane), [float(o) for o in offsets] if offsets else None,
                                  plane.strip().upper())

    def wall_thickness(self, body, below: float = 0.0, limit: int = 5, where: str = "model"):
        return pb.wall_thickness(self._p(where), body, float(below), int(limit))

    # contact
    def contact(self, a, b, tol: float = 0.0, where: str = "model"):
        return cx.contact(self._p(where), a, b, float(tol or 0))

    def assembly_check(self, bodies=None, against=None, tol: float = 0.0, near: float = 0.0, where: str = "model"):
        return cx.assembly(self._p(where), bodies, against, float(tol or 0), float(near or 0))

    def fit_check(self, a, b, where: str = "model"):
        return cx.fit(self._p(where), a, b)

    def placement(self, a, b, where: str = "model"):
        return rl.placement(self._p(where), a, b)

    def check_design(self, body, min_wall: float = 0.0, min_edge: float = 0.0, where: str = "model"):
        return rl.design_check(self._p(where), body, float(min_wall or 0), float(min_edge or 0))

    def compare_bodies(self, a, b, where: str = "model"):
        return rl.compare(self._p(where), a, b)

    # experiments
    def vary(self, param: str, values: list, expectations: list[str] | None = None):
        return ex.vary(self.box.p if self.box else self.real, param, values, expectations)

    def round_trip(self, edits: list[dict]):
        return ex.round_trip(self.box.p if self.box else self.real, edits)

    def sandbox_script(self) -> dict[str, Any]:
        if self.box is None:
            raise ToolError("no sandbox is open", "call sandbox first")
        return {"script": self.box.script(), "entries": self.box.p.cursor - self.box.base}


def _plane(p: Processor, name: str):
    from ..commands.feature_handlers import plane_ref
    from ..commands.processor import CommandError

    try:
        return plane_ref(p, name, "plane")
    except CommandError as exc:
        raise ToolError(str(exc)) from None


def _type_name(t) -> str:
    from ..commands.processor import BodyRef, Path, Raw, Text

    return {float: "number", int: "integer", str: "keyword", Text: "text", Path: "file", Raw: "expression",
            BodyRef: "body"}.get(t, getattr(t, "__name__", str(t)))


LANGUAGE_BASICS = """\
The language in short:
- One command per line: NAME, arg, arg, ... (`BLOCK, 0,0,0, 40,20,10`). Arguments are numbers, expressions
  (`W/2 + 3`), keywords or quoted text. `!` starts a comment.
- Parameters: `W = 40` makes a named number; change it and everything that uses it rebuilds. Expressions
  use + - * / ^, functions (sin cos ... in degrees, sqrt, min, max) and queries such as VOL(b), BBOX(b).dz.
- Bodies have IDs (1, 2, ...) and names (NAME); LAST is the newest body.
- Selection: SEL, S/R/A/U, kind (FACE, EDGE, VERTEX, BODY), criterion... picks entities by a rule that
  survives edits (LOC, NORMAL, RADIUS, TYPE ...); features such as FILLET and HOLE work on the selection.
- Blocks: *DO, i, 1, 5 ... *ENDDO; *IF ... *ENDIF; *PART ... *ENDPART for reusable parts; *MACRO.
- Sketches: SKETCH, name, plane ... S-commands (SLINE, SCIRCLE, SCON, SDIM ...) ... ENDSKETCH, then
  EXTRUDE or REVOLVE.
- History: every top-level line is a step. HIST, EDIT/INSERT/DELETE changes old steps; the model rebuilds.
  Commands marked (not kept) run without being stored (queries, views, export).
"""


def command_families() -> str:
    """Every command name, grouped by family (the command menu's headings), for the small first prompt."""
    try:
        from ..gui.forms import categories  # no Qt: plain data

        CATEGORIES = categories()
    except Exception:  # noqa: BLE001
        CATEGORIES = []
    seen: set[str] = set()
    lines = []
    for cat, names in CATEGORIES:
        got = [n for n in names if n in REGISTRY and n not in seen]
        seen.update(got)
        if got:
            lines.append(f"{cat}: {', '.join(got)}")
    rest = sorted(n for n in REGISTRY if n not in seen)
    files = {"NEW", "OPEN", "SAVE", "RUN", "NEWPART", "OPENPART", "SAVEPART", "RELOAD", "UNDO", "REDO", "HIST",
             "STEPS", "VIEW", "FIT", "PICK", "PICKMODE", "CPOINTS", "HELP"}
    sketch = [n for n in rest if n not in files and (n.startswith("S") or n == "ENDSKETCH")]
    if sketch:
        lines.append("Inside a sketch: " + ", ".join(sketch))
    rest = [n for n in rest if n not in sketch]
    if rest:
        lines.append("Files, history, view: " + ", ".join(rest))
    return "\n".join(lines)


def command_catalogue() -> str:
    """Every command in one line each: its arguments (optional ones in brackets)
    and the first sentence of its help. Sent to the assistant once per chat."""
    lines = []
    for name in sorted(REGISTRY):
        c = REGISTRY[name]
        args = []
        for a in c.args:
            stem = a.name.rstrip("0123456789")
            if stem != a.name and args and args[-1].strip("[]").rstrip("0123456789.") == stem:
                if not args[-1].endswith("..."):
                    args[-1] = args[-1].strip("[]") + "..."
                continue  # v1, v2 ... v16: one entry
            args.append(f"[{a.name}]" if a.default is not None else a.name)
        head = name + (", " + ", ".join(args) if args else "")
        first = c.help.split(" · ")[0].split(": ")[0].strip()
        if ". " in first.replace("e.g. ", "e.g.\u00a0"):
            first = first.replace("e.g. ", "e.g.\u00a0").split(". ")[0].replace("\u00a0", " ")
        first = first.rstrip(".")
        if len(first) > 110:
            first = first[:107] + "..."
        lines.append(f"{head} - {first}" + ("" if c.logged else " (not kept)"))
    return "\n".join(lines)
