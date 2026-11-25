"""The command processor: registry, interpreter, history and undo.

Every change to the model goes through the processor, whether the text was
typed, read from a script, or built by a GUI action.

Language (see docs/LANGUAGE.md for the full reference)
------------------------------------------------------
* Commands: ``NAME, arg, arg, , arg``. Every numeric argument is an
  expression of parameters (``BLOCK, 0,0,0, W, W/2, T``). A point value such
  as ``P = (10, 0, 5)`` fills three numeric arguments at once.
* Parameters: ``W = 40``. Names are case-insensitive.
* Blocks: ``*DO``/``*ENDDO``, ``*IF``/``*ELSEIF``/``*ELSE``/``*ENDIF``,
  ``*WHILE``/``*ENDWHILE``, ``*MACRO``/``*END``, with ``*EXIT``, ``*CYCLE``,
  ``*RETURN``, ``*MSG`` and ``*DEL``.

History
-------
The history is a list of *entries*: each is one top-level statement as it
was written (a command, an assignment or a whole block). An entry runs
atomically: if any part of it fails, the model goes back to how it was
before the entry. A state snapshot is kept after every entry, so undo/redo
are instant and editing entry *k* only re-runs entries *k* onwards.
"""

from __future__ import annotations

import contextlib
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..core.model import ID_KINDS, IdPins, Lineage, Model, ModelError
from ..core.refs import RefLog
from ..lang.expr import Evaluator, ExprError, Vec, fmt_num, format_value
from ..lang.script import (
    Assign,
    Cmd,
    Do,
    If,
    Incomplete,
    MacroDef,
    PartDef,
    ScriptError,
    Simple,
    Stmt,
    While,
    code_key,
    first_code_line,
    is_ident,
    needs_more,
    parse,
    split_entries,
)

MAX_LOOP = 100_000  # iterations of one *DO or *WHILE
MAX_STEPS = 2_000_000  # statements in one entry
MAX_DEPTH = 64  # nested macro calls
MAX_TRACE = 300  # lines of output kept for one entry


class CommandError(Exception):
    pass


class ViewHooks(Protocol):
    """What the viewport offers to view commands. Absent when headless."""

    def set_view(self, name: str) -> None: ...
    def fit(self) -> None: ...
    def fit_bodies(self, ids: list[int]) -> None: ...
    def set_pick_mode(self, kind: str) -> None: ...


class Text:
    """Argument type: a string that keeps its case (file names, labels)."""


class Path(Text):
    """Argument type: a file name. A plain quoted name is taken exactly as
    written, so Windows paths need no doubled backslashes: RUN, "C:\\work\\a.cmd"."""


class Raw:
    """Argument type: the argument text as written; the handler evaluates it."""


# commands that keep an exploded view (XSHOW) shown; any other command puts the model back first
SHOWN_EXPLODED = {"XSHOW", "FIT", "VIEW", "RENDER", "LIST", "DESCRIBE", "MSG", "*MSG"}

class BodyRef:
    """Argument type: a body, given by ID, by name, or by a parameter holding either."""


@dataclass
class Arg:
    name: str
    type: type = float  # float, int, str (keyword, upper-cased), Text or BodyRef
    default: Any = None  # None means required
    help: str = ""


@dataclass
class Command:
    name: str
    fn: Callable[..., str | None]
    args: list[Arg]
    help: str
    logged: bool = True  # False: queries/view commands, never in the history
    session: bool = False  # acts on the history itself (UNDO, HIST ...): top level only
    # first words that make the command a query, run but not kept (TAKE, LIST, part);
    # "" makes the bare command (no arguments) a query (/UNITS alone says what is set)
    queries: tuple[str, ...] = ()
    # the most an argument may be (counts and sizes that would take hours or all the memory)
    limits: dict[str, float] = field(default_factory=dict)
    # a word anywhere in the arguments that makes the command a query (CLASHFIX, ..., PREVIEW)
    query_word: str = ""

    def is_query(self, args: list[str]) -> bool:
        if self.query_word and any(a.strip().upper() == self.query_word for a in args):
            return True
        if not self.logged:
            return True
        if not self.queries:
            return False
        first = args[0].strip().upper() if args else ""
        return first in self.queries and (first or all(not a.strip() for a in args))


REGISTRY: dict[str, Command] = {}


def command(name: str, *args: Arg, help: str = "", logged: bool = True, session: bool = False):
    """Register a handler. The handler gets (processor, **parsed_args)."""

    def deco(fn):
        REGISTRY[name.upper()] = Command(name.upper(), fn, list(args), help, logged and not session, session)
        return fn

    return deco


@dataclass
class Result:
    line: str
    ok: bool
    message: str = ""
    pending: bool = False  # interactive input is inside an open block
    warning: str = ""  # the command ran, but something needs the user's attention
    report: dict | None = None  # the same answer as data, from checks such as STRESS or PRINTCHECK


@dataclass
class Entry:
    """One top-level unit of the history."""

    text: str
    ok: bool = True
    message: str = ""
    suppressed: bool = False
    pins: dict[str, list[int]] = field(default_factory=dict)
    # fingerprints of the picks this entry made (see core/refs.py)
    refs: list = field(default_factory=list)
    # set when the entry ran but needs attention (a repaired pick, say)
    warning: str = ""
    uid: int = 0  # stays with the entry for good; says which step made an entity
    # what the entry did to bodies the last time it ran (core/model.py Lineage);
    # not saved: every replay records it again
    lineage: object = None
    # for skipping it when it need not run again (see Processor.rebuild): the
    # state it last started from and ended with, and what it looked at
    # (None: it cannot be skipped); not saved
    before: object = field(default=None, repr=False, compare=False)
    after: object = field(default=None, repr=False, compare=False)
    reads: object = field(default=None, repr=False, compare=False)
    seconds: float = field(default=0.0, repr=False, compare=False)  # how long its last run took; not saved

    def __deepcopy__(self, memo):
        import copy as _copy
        from dataclasses import fields

        new = _copy.copy(self)
        for f in fields(self):
            if f.name not in ("before", "after", "reads"):  # saved states share their (immutable) bodies
                setattr(new, f.name, _copy.deepcopy(getattr(self, f.name), memo))
        return new

    @property
    def label(self) -> str:
        return first_code_line(self.text)


class RebuildCancelled(Exception):
    """The person pressed Cancel while the history was being re-run."""


class _Exit(Exception):
    pass


class _Cycle(Exception):
    pass


class _Return(Exception):
    pass


# commands that read something besides the model and parameters (an older
# state, the history): an entry that runs one is never skipped on a rebuild.
# Commands that take a file name (IMPORT, LIB, ...) count too.
VOLATILE = {"PATTERN", "RUN", "STEPS", "RELOAD"}

SELECTED = -1  # what the word SEL gives where bodies are expected
SEL_AS_BODIES = {"UNION", "SUBTRACT", "INTERSECT"}

UNIT_NAMES = {"MM": "MM", "CM": "CM", "METER": "M", "INCH": "IN"}
RESERVED = {"LAST"} | set(UNIT_NAMES)


class Processor:
    def __init__(
        self,
        model: Model | None = None,
        view: ViewHooks | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> None:
        self.model = model or Model()
        self.view = view
        self.listeners: list[Callable[[Result], None]] = []
        self.history_listeners: list[Callable[[], None]] = []
        self.params: dict[str, Any] = {}
        self.macros: dict[str, MacroDef] = {}
        # configurations: named sets of parameter values (CONFIG), by upper-case name; the one in use
        # (USECONFIG) fixes those parameters the way -D does, until another is chosen
        self.configs: dict[str, dict[str, Any]] = {}
        self.config = ""
        self.config_values: dict[str, Any] = {}
        # steps turned off in a configuration (CONFIGOFF, DESIGNTABLE): name -> entry uids
        self.config_off: dict[str, set[int]] = {}
        self.backups_keep = 5  # earlier saves kept (BACKUPS, n)
        self.saved_script = ""  # the history as last saved or opened: anything else is not saved yet
        self.note_ends: dict = {}  # NOTE, SIZE: what each end was on when first made, by (step uid, note)
        self.drawings_auto = ""  # DRAWINGS, file, AUTO: the file written again after every rebuild and save
        # DRIVE: parameters held at a value for a moment (a slider moving an assembly); not history
        self.drive: dict[str, Any] = {}
        self.exploded: dict | None = None  # XSHOW: the model as it was, put back before the next command
        self.parts: dict[str, PartDef] = {}  # *PART definitions, by upper-case name
        # built part shapes by (definition text, parameter values); not undo state,
        # because a key never changes meaning
        self.part_cache: dict = {}
        self.lib_files: dict[str, str] = {}  # LIB, LOAD names as written -> the file read
        # sculpt strokes by name (S1, S2 ...): points the brush went through, kept with the project
        # (strokes.npz) because a stroke is too long to write into a history line
        self.strokes: dict = {}
        # geometry taken from other parts (TAKE), by name: what was asked, a fingerprint to find it
        # again, and for COPY the geometry itself (BREP text); kept with the project
        self.taken: dict = {}
        # the assistant conversation: [{"who": "you"/"assistant", "text": ...}], saved with the project
        self.chat: list[dict] = []
        # LIB, LINK names as written -> what the last run read (part_handlers.Link);
        # not undo state: it says what the file held, which RELOAD compares
        self.links: dict = {}
        # where a project last found each linked file ({name: {"abs": .., "rel": ..}}),
        # so a reopened project reads the live part file, not its saved copy
        self.link_paths: dict[str, dict] = {}
        self.project_dir: str = ""  # the folder of the opened project (linked files may sit next to it)
        # part name -> (file, "linked" | "copy" | "loaded") for parts read from a part file
        self.part_files: dict[str, tuple[str, str]] = {}
        # parameters fixed from outside (batch runner -D): assignments keep these values
        self.overrides = {k.upper(): v for k, v in (overrides or {}).items()}
        # IMPORT file names as written in the script -> the file to read
        # (set when a project is opened, so imports come from the project)
        self.file_map: dict[str, str] = {}
        self.autosave_path: str | None = None  # where the GUI autosaves (OPEN, AUTOSAVE)
        self.project_path: str | None = None  # the last SAVE/OPEN file
        self.last_failure: dict | None = None  # the last typed step that failed
        self.last_tool = ""  # the last typed step that changed the model (REPEAT runs it again)
        self.last_report: dict | None = None  # give_report: the data of the line being run
        self.reports: dict[str, dict] = {}  # the newest report of each check (STRESS, GRAVITY ...)
        self.part_doc = None  # a part document (commands/partdoc_handlers.py PartDoc), or None for a project
        self.section = None  # SECTION view: (datum plane, "ABOVE"/"BELOW") or None; a view setting only
        self.control_points: int | None = None  # CPOINTS: the body whose control points the view shows
        self.analysis = None  # ANALYZE: what the view colours (analysis_handlers.Analysis), a view setting only
        self.toolpath = None  # MILL: the milling path the view shows (a compound of polylines), a view setting only
        self.tutorial = None  # TUTORIAL: the lesson being followed (tutorial_handlers.Lesson), or None
        # the window (gui/main_window.py MainWindow) when there is one: LAYOUT and TUTORIAL tell it
        # what to show; headless runs leave it None and the commands still work
        self.ui = None

        self.history: list[Entry] = []
        self._uid = 0  # the last entry uid handed out
        self.cursor = 0  # entries[:cursor] are applied; the rest can be redone
        self._snaps: list[dict] = [self._state()]
        self._buffer: list[str] = []
        # what UNDO and REDO step through: {"kind": "cursor", "from", "to"} for
        # a new entry or a roll back, {"kind": "hist", "label", "before",
        # "after"} (history_backup()s) for a history edit (HIST, EDIT/INSERT/...)
        self._undo: list[dict] = []
        self._redo: list[dict] = []
        # skip entries whose inputs did not change when the history is re-run
        self.skip_unchanged = True
        self.skipped = 0  # entries the last rebuild reused instead of re-running

        self._scopes: list[dict[str, Any]] = []  # macro locals
        self._loops = 0
        self._steps = 0
        self._trace: list[str] = []
        self._warnings: list[str] = []
        self.refs: RefLog | None = None  # the running entry's pick fingerprints
        self.entry_uid = 0  # uid of the running history entry
        self.entry_index = 0  # 0-based place of the running entry in the history
        # called before each entry a rebuild re-runs, with (done, total, label);
        # returning False cancels the rebuild (the GUI's progress dialog)
        self.progress: Callable[[int, int, str], bool] | None = None
        self._quiet = True
        # time.monotonic() after which a running entry stops (sandbox runs); None: no limit
        self.deadline: float | None = None

        from . import queries  # registers the model query functions

        self.evaluator = Evaluator(self._lookup, queries.functions(self))

    # =====================================================================
    # Public API
    # =====================================================================
    def run(self, line: str) -> Result:
        """Run one line of interactive input. Never raises.

        A line that opens a block (``*DO, i, 1, 3``) is buffered until the
        block is closed; the result then has ``pending=True``.
        """
        if self._buffer or needs_more(line):
            self._buffer.append(line)
            text = "\n".join(self._buffer)
            if needs_more(text):
                return self._finish(Result(line.strip(), True, pending=True))
            self._buffer = []
            return self._finish(self._note_tool(self.run_unit(text)))
        return self._finish(self._note_tool(self.run_unit(line)))

    # commands REPEAT never runs again: picking, undo, history edits and itself
    NOT_REPEATED = frozenset({"PICK", "SEL", "CMSEL", "PICKMODE", "PICKREGION", "REPEAT", "UNDO", "REDO", "HIST",
                              "NEW", "OPEN", "SAVE", "RESUME", "PARAM", "NAME", "/UNITS", "TUTORIAL",
                              "LAYOUT"})

    def _note_tool(self, res: Result) -> Result:
        """Remember the last typed or clicked step that changed the model, for REPEAT (PLAN item 90)."""
        if res.ok and res.line and not res.pending:
            line = first_code_line(res.line).strip()
            word = line.split(",", 1)[0].strip().upper()
            cmd = REGISTRY.get(word)
            if cmd is not None and cmd.logged and word not in self.NOT_REPEATED and "\n" not in res.line.strip():
                self.last_tool = res.line.strip()
        return res

    def unexplode(self) -> bool:
        """Put the model back as it was before XSHOW (True if it was exploded)."""
        if self.exploded is None:
            return False
        snap, self.exploded = self.exploded, None
        self.model.restore(snap)
        return True

    def cancel_pending(self) -> None:
        self._buffer = []

    @property
    def pending(self) -> bool:
        return bool(self._buffer)

    def run_script(self, text: str, saved: list[dict] | None = None) -> list[Result]:
        """Run a whole script, one history entry per top-level unit.

        Stops at the first failing unit (which is not added to the history).

        saved: what a project file remembers about each entry (its text, the
        IDs it handed out and its pick fingerprints). An entry whose text
        matches gets its IDs back, so the model is numbered exactly as it
        was when the project was saved.
        """
        try:
            units = split_entries(text)
        except ScriptError as exc:
            return [self._finish(Result(first_code_line(text), False, str(exc)))]
        saved = list(saved or [])
        floor: dict[str, int] = {}
        for item in saved:
            for kind, ids in (item.get("pins") or {}).items():
                if ids and kind in ID_KINDS:
                    floor[kind] = max(floor.get(kind, 1), max(ids) + 1)
        self.model.id_floor.update(floor)
        results = []
        k = 0
        typed_tool = self.last_tool  # a script's own steps are repeated only inside it
        try:
            for unit in units:
                seed = None
                if k < len(saved) and code_key(saved[k].get("text", "")) == code_key(unit):
                    seed, k = saved[k], k + 1
                r = self._finish(self._note_tool(self.run_unit(unit, seed)))  # REPEAT inside the script
                if r.line:
                    results.append(r)
                    if not r.ok:
                        break
        finally:
            for kind in floor:
                self.model.id_floor[kind] = 1
            self.last_tool = typed_tool
        return results

    def run_unit(self, text: str, seed: dict | None = None) -> Result:
        """Run one top-level unit and, if it changes the model, add it to the history."""
        text = text.strip("\n").rstrip()
        label = text.strip()
        if not first_code_line(text) or first_code_line(text).startswith("!"):
            return Result("", True)
        try:
            stmts = parse(text)
        except ScriptError as exc:
            return Result(label, False, str(exc))
        if not stmts:
            return Result("", True)
        if self.exploded is not None and not (len(stmts) == 1 and isinstance(stmts[0], Cmd)
                                              and stmts[0].name in SHOWN_EXPLODED):
            self.unexplode()
        if len(stmts) == 1 and isinstance(stmts[0], Cmd):
            cmd = REGISTRY.get(stmts[0].name)
            if cmd is not None and cmd.is_query(stmts[0].args):
                return self._run_unlogged(cmd, stmts[0], label)
        entry = Entry(text)
        if seed:
            entry.pins = {k: [int(i) for i in v] for k, v in (seed.get("pins") or {}).items() if k in ID_KINDS}
            entry.refs = list(seed.get("refs") or [])
            uid = int(seed.get("uid") or 0)
            if uid > 0 and all(e.uid != uid for e in self.history):
                entry.uid = uid
                self._uid = max(self._uid, uid)
        self.entry_index = self.cursor
        if self.is_off(entry):
            ok, message = True, f"off in configuration {self.config}"
        else:
            ok, message = self._run_entry(entry, stmts)
        if not ok:
            message = self.did_you_mean(message)
        entry.ok, entry.message = ok, message
        if not ok:
            self.last_failure = {"line": label, "message": message}  # for diagnose (ai/diagnose.py)
            return Result(label, False, message)
        del self.history[self.cursor :]
        del self._snaps[self.cursor + 1 :]
        self.history.append(entry)
        self.cursor += 1
        self._snaps.append(self._state())
        entry.after = self._snaps[-1]
        self._push_undo({"kind": "cursor", "from": self.cursor - 1, "to": self.cursor})
        self._history_changed()
        return Result(label, True, message, warning=entry.warning)

    def reset(self) -> None:
        """Start a new, empty session (history, parameters, macros and model)."""
        self._buffer = []
        self.last_tool = ""
        self._scopes = []
        self.params = {}
        self.macros = {}
        self.configs = {}
        self.config = ""
        self.config_values = {}
        self.config_off = {}
        self.drawings_auto = ""
        self.note_ends = {}
        self.saved_script = ""
        self.backups_keep = 5
        self.drive = {}
        self.exploded = None
        self.parts = {}
        self.part_files = {}
        self.file_map = {}
        self.strokes = {}
        self.taken = {}
        self.chat = []
        self.links = {}
        self.link_paths = {}
        self.project_dir = ""
        self.part_doc = None
        self.model.clear()
        self.history = []
        self._uid = 0
        self.cursor = 0
        self._snaps = [self._state()]
        self._undo, self._redo = [], []
        self._history_changed()

    def is_off(self, e: Entry) -> bool:
        """Is the entry turned off in the configuration in use?"""
        return bool(self.config and e.uid and e.uid in self.config_off.get(self.config, ()))

    @property
    def log(self) -> list[str]:
        """The applied history as text, one entry per item."""
        return [e.text for e in self.history[: self.cursor] if not e.suppressed]

    def script(self, standalone: bool = False) -> str:
        """The applied history as a script that rebuilds the model. ``standalone``
        also writes the points of the sculpt strokes first (STROKE lines), which a
        project keeps in its own file, so the script works on its own."""
        out = []
        if standalone and self.strokes:
            from .sculpt_handlers import format_points

            out.append("! the sculpt strokes the SCULPT steps use")
            out += [f'STROKE, {k}, "{format_points(v)}"' for k, v in self.strokes.items()]
        for e in self.history[: self.cursor]:
            if e.suppressed:
                out.extend("! [suppressed] " + line for line in e.text.splitlines())
            else:
                out.append(e.text)
        return "\n".join(out) + ("\n" if out else "")

    def evaluate(self, expr: str) -> Any:
        """Evaluate an expression against the current parameters and model."""
        return self.evaluator.eval(expr)

    # ---- undo / redo / history editing ------------------------------------
    @property
    def can_undo(self) -> bool:
        return bool(self._undo) or self.cursor > 0

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self, n: int = 1) -> str:
        """Take back the last n actions: new entries, roll backs and history edits."""
        self.unexplode()
        if not self.can_undo:
            raise CommandError("nothing to undo")
        done: list[str] = []
        for _ in range(max(1, n)):
            if not self.can_undo:
                break
            act = self._undo.pop() if self._undo else {"kind": "cursor", "from": self.cursor - 1, "to": self.cursor}
            if act["kind"] == "cursor" and act["to"] != self.cursor:  # out of step: just go back one entry
                act = {"kind": "cursor", "from": self.cursor - 1, "to": self.cursor}
            if act["kind"] == "cursor":
                if act["from"] < act["to"]:  # going back over entries: keep them for REDO
                    f, t = act["from"], act["to"]
                    act["tail"] = (f, self.history[f:t], self._snaps[f + 1:t + 1])
                self._move_cursor(act["from"], act.get("tail"))
                done.append("step")
            else:
                self.history_restore(act["before"], emit=False)
                done.append(act["label"])
            self._redo.append(act)
        self.model.restore(self.model.snapshot())  # one refresh for listeners
        self._history_changed()
        return "undid " + self._undo_words(done) + f"; {self.cursor} in history"

    def redo(self, n: int = 1) -> str:
        self.unexplode()
        if not self._redo:
            raise CommandError("nothing to redo")
        done: list[str] = []
        for _ in range(max(1, n)):
            if not self._redo:
                break
            act = self._redo.pop()
            if act["kind"] == "cursor":
                self._move_cursor(act["to"], act.get("tail"))
                done.append("step")
            else:
                self.history_restore(act["after"], emit=False)
                done.append(act["label"])
            self._undo.append(act)
        self.model.restore(self.model.snapshot())
        self._history_changed()
        return "redid " + self._undo_words(done) + f"; {self.cursor} in history"

    def _move_cursor(self, to: int, tail: tuple | None) -> None:
        """Set the cursor for UNDO/REDO. Going back, the entries passed over
        are kept with the action (``tail``): a history edit undone in between
        can have taken them out of the history, and going forward puts them back."""
        lo = min(to, self.cursor)
        if to > self.cursor and tail is not None and tail[0] == lo:
            _, entries, snaps = tail
            self.history = self.history[:lo] + list(entries)
            self._snaps = self._snaps[:lo + 1] + list(snaps)
        to = max(0, min(to, len(self.history)))
        self.cursor = to
        self._restore(self._snaps[to], emit=False)

    @staticmethod
    def _undo_words(done: list[str]) -> str:
        steps = done.count("step")
        edits = [d for d in done if d != "step"]
        parts = []
        if steps:
            parts.append(f"{steps} step{'s' if steps > 1 else ''}")
        if edits:
            parts.append(", ".join(edits))
        return " and ".join(parts)

    MAX_HIST_UNDO = 100  # history edits UNDO can take back (each keeps a copy of the history)

    def _push_undo(self, act: tuple) -> None:
        self._undo.append(act)
        self._redo = []
        hist = [i for i, a in enumerate(self._undo) if a["kind"] == "hist"]
        if len(hist) > self.MAX_HIST_UNDO:
            del self._undo[: hist[0] + 1]

    @contextlib.contextmanager
    def undo_group(self, label: str):
        """Everything run inside is one UNDO step (and one REDO): an assistant proposal of many
        lines or history edits is taken back at once. Nothing changed: nothing is recorded."""
        before = self.history_backup()
        texts = [(e.uid, e.text) for e in self.history]
        mark = len(self._undo)
        try:
            yield
        finally:
            if len(self._undo) > mark or self.cursor != before["cursor"] \
                    or [(e.uid, e.text) for e in self.history] != texts:
                del self._undo[mark:]
                self._push_undo({"kind": "hist", "label": label, "before": before, "after": self.history_backup()})

    def record_hist_edit(self, label: str, before: dict) -> None:
        """Make a history edit undoable: ``before`` is history_backup() from before it."""
        self._push_undo({"kind": "hist", "label": label, "before": before, "after": self.history_backup()})

    def roll_to(self, n: int) -> str:
        """Apply entries 1..n only (later ones stay, for REDO or HIST, ROLLBACK). One UNDO step."""
        if not 0 <= n <= len(self.history):
            raise CommandError(f"HIST, ROLLBACK: give 0 to {len(self.history)}")
        if n == self.cursor:
            return f"already at entry {n}"
        before = self.cursor
        act = {"kind": "cursor", "from": before, "to": n}
        if n < before:  # the entries rolled back over, for when UNDO goes forward again
            act["tail"] = (n, self.history[n:before], self._snaps[n + 1:before + 1])
        self.cursor = n
        self._restore(self._snaps[n])
        self._push_undo(act)
        self._history_changed()
        return f"the model is now as after entry {n}; {len(self.history) - n} later entr" \
               f"{'y' if len(self.history) - n == 1 else 'ies'} can be redone"

    def edit_entry(self, index: int, text: str) -> str:
        """Replace entry ``index`` (1-based) and re-run from there."""
        i = self._index(index)
        new = self._check_unit(text)
        if code_key(new) != code_key(self.history[i].text):
            self.history[i].refs = []  # new picks: the old fingerprints no longer apply
        self.history[i].text = new
        self.history[i].suppressed = False
        return self.rebuild(i)

    def insert_entry(self, index: int, text: str) -> str:
        """Insert a new entry before ``index`` (1-based; one past the end appends)."""
        self._drop_redo_tail()
        if not 1 <= index <= self.cursor + 1:
            raise CommandError(f"insert position must be 1 to {self.cursor + 1}")
        new = self._check_unit(text)
        self.history.insert(index - 1, Entry(new))
        self.cursor += 1
        self._snaps.insert(index, self._snaps[index - 1])  # placeholder, rebuilt below
        return self.rebuild(index - 1)

    def delete_entry(self, index: int) -> str:
        i = self._index(index)
        del self.history[i]
        del self._snaps[i + 1]
        self.cursor -= 1
        return self.rebuild(i)

    def suppress_entry(self, index: int, on: bool = True) -> str:
        i = self._index(index)
        self.history[i].suppressed = on
        return self.rebuild(i)

    def move_entry(self, index: int, to: int) -> str:
        i, j = self._index(index), self._index(to)
        e = self.history.pop(i)
        self.history.insert(j, e)
        return self.rebuild(min(i, j))

    def wrap_entries(self, first: int, last: int, name: str) -> str:
        """Turn entries first..last (1-based) into a part, placed once where it
        was: ``*PART`` + ``INST`` (+ ``NAME`` when the steps made one named body).

        Parameters set inside the range become the part's own parameters;
        parameters from before it that the steps use become part parameters
        too, passed in by the ``INST`` (``W=W``), so the model still follows
        them. The part is built first; if it fails, nothing changes.
        """
        import re

        from .part_handlers import build

        self._drop_redo_tail()
        i0, i1 = self._index(first), self._index(last)
        if i1 < i0:
            raise CommandError("HIST, PART: the last entry comes before the first")
        if not is_ident(name):
            raise CommandError(f"HIST, PART: {name!r} is not a valid part name")
        entries = [e for e in self.history[i0:i1 + 1] if not e.suppressed]
        outer = self._snaps[i0]["params"]
        inner: list[tuple[str, str]] = []
        body: list[str] = []
        for e in entries:
            stmts = parse(e.text)
            if len(stmts) == 1 and isinstance(stmts[0], Assign):
                inner.append((stmts[0].name, stmts[0].expr))
                continue
            body.append(e.text)
        used = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", "\n".join(body + [x for _, x in inner])))
        inner_names = {n for n, _ in inner}
        passed = [k for k in outer if k in {u.upper() for u in used} and k not in inner_names]
        params = [f"{k}={format_value(outer[k])}" for k in passed] + [f"{n}={x}" for n, x in inner]
        head = f"*PART, {name}" + (", " + ", ".join(params) if params else "")
        block = "\n".join(["  " + ln for t in body for ln in t.splitlines()])
        part_text = f"{head}\n{block}\n*ENDPART"
        stmts = parse(part_text)
        part = stmts[0]
        trial = dict(self.parts)
        saved_parts, self.parts = self.parts, trial
        try:
            build(self, part, {k: outer[k] for k in passed})
        finally:
            self.parts = saved_parts
        # the name the steps gave their one body, so later steps still find it
        snap_after = self._snaps[i1 + 1]["model"]
        before = self._snaps[i0]["model"]["bodies"]
        made = [b for bid, b in snap_after["bodies"].items() if bid not in before]
        new = [part_text, f"INST, {name}" + "".join(f", {k}={k}" for k in passed)]
        if len(made) == 1 and not made[0].name.lower().startswith("body"):
            new.append(f"NAME, LAST, {made[0].name}")
        n = i1 - i0 + 1
        self.history[i0:i1 + 1] = [Entry(t) for t in new]
        del self._snaps[i0 + 1:i1 + 2]
        for _ in new:
            self._snaps.insert(i0 + 1, self._snaps[i0])  # placeholders, rebuilt below
        self.cursor += len(new) - n
        msg = self.rebuild(i0)
        return f"steps {first} to {last} are now part {name.lower()}, placed once\n{msg}"

    def rebuild(self, start: int = 0, skip: bool = True) -> str:
        """Re-run entries ``start`` (0-based) .. cursor-1 from the snapshot before ``start``.

        Entries that now fail are kept and marked; the model skips them.
        Each entry asks for the same IDs it handed out last time.

        An entry after ``start`` whose inputs (the parameters, bodies, faces
        and other model state it read last time) are all unchanged is not run
        again: what it did last time is copied over (``skip``; see
        core/track.py). Entries that read files or older states always run.
        """
        self.unexplode()
        self._drop_redo_tail()
        m = self.model
        # the view's own changes are not history: keep them through the re-run
        # (a CLEAR or HIDE step that runs again must not wipe them)
        view = (set(m.view_hidden), set(m.view_shown), dict(m.faded))
        self._restore(self._snaps[start], emit=False)
        floor: dict[str, int] = {}
        for e in self.history[start:]:
            for kind, ids in e.pins.items():
                if ids:
                    floor[kind] = max(floor.get(kind, 1), max(ids) + 1)
        self.model.id_floor.update(floor)
        errors: list[str] = []
        warnings: list[str] = []
        skipped = 0
        try:
            for j in range(start, self.cursor):
                e = self.history[j]
                if self.progress is not None and not self.progress(j - start, self.cursor - start, e.label):
                    raise RebuildCancelled()
                if e.suppressed:
                    e.ok, e.message, e.warning = True, "suppressed", ""
                elif self.is_off(e):
                    e.ok, e.message, e.warning = True, f"off in configuration {self.config}", ""
                elif skip and j > start and self._can_skip(e, now := self._shared_state(j)):
                    # nothing it reads changed: take over what it did last time
                    after = self._skipped_state(e, now)
                    self._restore(after, emit=False)
                    e.before = now
                    skipped += 1
                    if e.warning:
                        warnings.append(f"entry {j + 1}: {e.warning}")
                else:
                    try:
                        stmts = parse(e.text)
                    except ScriptError as exc:
                        e.ok, e.message, e.warning = False, self.did_you_mean(str(exc)), ""
                    else:
                        self.entry_index = j
                        e.ok, e.message = self._run_entry(e, stmts)
                        if not e.ok:
                            e.message = self.did_you_mean(e.message)
                    if not e.ok:
                        errors.append(f"entry {j + 1}: {e.message}")
                    elif e.warning:
                        warnings.append(f"entry {j + 1}: {e.warning}")
                self._snaps[j + 1] = e.after = self._state()
        finally:
            for kind in floor:
                self.model.id_floor[kind] = 1
            m.view_hidden, m.view_shown, m.faded = view
        self.model.restore(self.model.snapshot())  # one refresh for listeners
        self._history_changed()
        n = self.cursor - start
        self.skipped = skipped
        msg = f"re-ran {n - skipped} entr{'y' if n - skipped == 1 else 'ies'} from {start + 1}"
        if skipped:
            msg += f" ({skipped} unchanged, reused)"
        if errors:
            msg += f"; {len(errors)} failed:\n  " + "\n  ".join(errors)
        if warnings:
            msg += f"\n{len(warnings)} warning{'s' if len(warnings) > 1 else ''}:\n  " + "\n  ".join(warnings)
        if self.drawings_auto:  # drawings kept up to date (DRAWINGS, file, AUTO)
            from .drawsheet_handlers import refresh

            refresh(self)
        return msg

    def history_backup(self) -> dict:
        """Everything a history edit can change, to put back if it is cancelled."""
        import copy as _copy

        return {"history": [_copy.copy(e) for e in self.history], "snaps": list(self._snaps),
                "cursor": self.cursor, "uid": self._uid, "state": self._state()}

    def history_restore(self, saved: dict, emit: bool = True) -> None:
        import copy as _copy

        # copies again, so the backup stays as it was for a later REDO/UNDO
        self.history = [_copy.copy(e) for e in saved["history"]]
        self._snaps = list(saved["snaps"])
        self.cursor = saved["cursor"]
        self._uid = saved["uid"]
        self._restore(saved["state"], emit=emit)
        if emit:
            self._history_changed()

    def state_before(self, steps: int) -> dict:
        """The saved state from before the last ``steps`` entries (as seen by
        the running entry)."""
        k = self.entry_index - steps
        if steps < 1 or k < 0:
            raise CommandError(f"there are only {self.entry_index} steps before this one")
        return self._snaps[k]

    def entry_for_param(self, name: str) -> int | None:
        """1-based index of the top-level entry that last assigns ``name``, if it is a plain ``NAME = expr``."""
        key = name.upper()
        for i in range(self.cursor - 1, -1, -1):
            try:
                stmts = parse(self.history[i].text)
            except ScriptError:
                continue
            if len(stmts) == 1 and isinstance(stmts[0], Assign) and stmts[0].name == key:
                return i + 1
        return None

    # =====================================================================
    # Internals
    # =====================================================================
    def _finish(self, res: Result) -> Result:
        for fn in list(self.listeners):
            fn(res)
        return res

    def _history_changed(self) -> None:
        for fn in list(self.history_listeners):
            fn()

    def _state(self) -> dict:
        return {"model": self.model.snapshot(), "params": dict(self.params), "macros": dict(self.macros),
                "parts": dict(self.parts), "part_files": dict(self.part_files),
                "configs": {k: dict(v) for k, v in self.configs.items()}}

    def _shared_state(self, i: int | None = None) -> dict:
        """The state now; the snapshot taken after the step before (step ``i`` starts from
        ``_snaps[i]``) when nothing has changed since, the usual case, so a long history keeps
        one copy of each state, not two."""
        from ..core.track import same

        now = self._state()
        i = self.entry_index if i is None else i
        if 0 <= i < len(self._snaps) and same(now, self._snaps[i]):
            return self._snaps[i]
        return now

    def _restore(self, state: dict, emit: bool = True) -> None:
        self.params = dict(state["params"])
        self.macros = dict(state["macros"])
        self.parts = dict(state.get("parts", {}))
        self.part_files = dict(state.get("part_files", {}))
        self.configs = {k: dict(v) for k, v in state.get("configs", {}).items()}
        if emit:
            self.model.restore(state["model"])
        else:
            listeners, self.model._listeners = self.model._listeners, []
            try:
                self.model.restore(state["model"])
            finally:
                self.model._listeners = listeners

    def _drop_redo_tail(self) -> None:
        if self.cursor < len(self.history):
            del self.history[self.cursor :]
            del self._snaps[self.cursor + 1 :]

    def _index(self, index: int) -> int:
        if not 1 <= index <= self.cursor:
            raise CommandError(f"no history entry {index} (there are {self.cursor})")
        return index - 1

    def _check_unit(self, text: str) -> str:
        text = text.strip("\n").rstrip()
        try:
            units = split_entries(text)
            stmts = parse(text)
        except Incomplete as exc:
            raise CommandError(f"the new text is not complete: {exc}") from None
        except ScriptError as exc:
            raise CommandError(str(exc)) from None
        if len(units) != 1 or not stmts:
            raise CommandError("an entry must be exactly one statement or one block")
        if len(stmts) == 1 and isinstance(stmts[0], Cmd):
            cmd = REGISTRY.get(stmts[0].name)
            if cmd is not None and cmd.is_query(stmts[0].args):
                raise CommandError(f"{cmd.name} does not belong in the history")
        return text

    def _call(self, cmd: Command, values: dict) -> str:
        """Run a handler. Commands that cannot work on mesh bodies cannot reach
        a mesh body's face through a pick either (see mesh_handlers.MESH_OK)."""
        from .mesh_handlers import MESH_OK

        m = self.model
        before = m.mesh_entities_ok
        m.mesh_entities_ok = cmd.name in MESH_OK
        try:
            return cmd.fn(self, **values) or ""
        except (CommandError, ModelError, ExprError, ScriptError, RebuildCancelled, _Exit, _Cycle, _Return,
                RecursionError):
            raise
        except Exception as exc:  # the kernel refused, or a bug: say so in plain words (core/kernel_errors.py)
            from ..core.kernel_errors import explain

            if (type(exc).__module__ or "").startswith("modeler.gui"):
                raise  # the window's own requests (NeedInput, NeedSelection ...)
            raise CommandError(explain(cmd.name, exc)) from exc
        finally:
            m.mesh_entities_ok = before

    def give_report(self, name: str, data: dict) -> None:
        """A check hands its answer over as data too: the Result of the line gets it
        (the assistant's tools pass it on as JSON), and ``reports[name]`` keeps the newest."""
        self.last_report = data
        self.reports[name] = data

    _NEAR_RE = re.compile(r"(unknown command|unknown name|no body or parameter named|no body named|"
                          r"no sketch named|no part named) '([^']+)'")

    def did_you_mean(self, message: str) -> str:
        """A misspelt command or name: add "did you mean ..." with the nearest real ones
        (PLAN item 89). The message is returned unchanged when nothing is near."""
        import difflib

        if not message or "did you mean" in message:
            return message
        m = self._NEAR_RE.search(message)
        if not m:
            return message
        what, bad = m.group(1), m.group(2)
        if what == "unknown command":
            pool = list(REGISTRY) + list(self.macros)
            near = difflib.get_close_matches(bad.upper(), pool, n=3, cutoff=0.6)
        else:
            names: dict[str, str] = {}
            if what in ("unknown name", "no body or parameter named"):
                for k in self.params:
                    names[str(k).lower()] = str(k)
            if what != "no sketch named" and what != "no part named":
                for b in self.model.bodies.values():
                    if b.name:
                        names[b.name.lower()] = b.name
            if what in ("no sketch named", "unknown name", "no body or parameter named"):
                for k in self.model.sketches:
                    names.setdefault(str(k).lower(), str(k))
            if what == "no part named":
                for k in self.parts:
                    names[str(k).lower()] = str(k)
            near = [names[n] for n in difflib.get_close_matches(bad.lower(), list(names), n=3, cutoff=0.6)]
        if not near:
            return message
        lines = message.split("\n")
        lines[0] = lines[0].rstrip(".") + "; did you mean " + " or ".join(near) + "?"
        return "\n".join(lines)

    def _run_unlogged(self, cmd: Command, st: Cmd, label: str) -> Result:
        self._trace = []
        self.last_report = None
        try:
            values, _ = self._bind(cmd, st.args)
            msg = self._call(cmd, values)
            return Result(label, True, msg, report=self.last_report)
        except (CommandError, ModelError, ExprError, ScriptError) as exc:
            return Result(label, False, self.did_you_mean(str(exc)))
        except Exception as exc:  # kernel failures should not kill the app
            return Result(label, False, f"{type(exc).__name__}: {exc}")

    def _run_entry(self, entry: Entry, stmts: list[Stmt]) -> tuple[bool, str]:
        """Run an entry atomically. Returns (ok, message)."""
        t0 = time.perf_counter()
        try:
            return self._run_entry_timed(entry, stmts)
        finally:
            entry.seconds = time.perf_counter() - t0

    def _run_entry_timed(self, entry: Entry, stmts: list[Stmt]) -> tuple[bool, str]:
        before = self._shared_state()
        revision = self.model_revision()
        self._trace, self._steps, self._loops, self._scopes = [], 0, 0, []
        self._warnings = []
        entry.warning = ""
        if not entry.uid:
            self._uid += 1
            entry.uid = self._uid
        pins = IdPins(entry.pins, entry.uid)
        self.model.pins = pins
        self.entry_uid = entry.uid  # which step is running (sketch constraints remember it)
        self.refs = refs = RefLog(entry.refs)
        outer = self.model.lineage  # (a HIST entry can run entries inside it)
        self.model.lineage = lineage = Lineage()
        single = len(stmts) == 1 and isinstance(stmts[0], (Cmd, Assign))
        self._quiet = single
        entry.before, entry.after, entry.reads = before, None, None
        tracks = self._track_start()
        try:
            self._exec_block(stmts)
        except (_Exit, _Cycle):
            return self._fail(before, revision, "*EXIT/*CYCLE outside a loop")
        except _Return:
            return self._fail(before, revision, "*RETURN outside a macro")
        except (CommandError, ModelError, ExprError, ScriptError) as exc:
            return self._fail(before, revision, str(exc))
        except RecursionError:
            return self._fail(before, revision, "too deeply nested")
        except Exception as exc:  # kernel failures should not kill the app
            return self._fail(before, revision, f"{type(exc).__name__}: {exc}")
        finally:
            self.model.pins = None
            self.refs = None
            self.model.lineage = outer
            reads = self._track_stop(tracks)
        entry.reads = reads
        entry.lineage = lineage
        entry.pins = pins.merged()
        entry.refs = refs.merged()
        entry.warning = "\n".join(dict.fromkeys(self._warnings))
        text = self._trace_text()
        if entry.warning:
            text = (text + "\n" if text else "") + "\n".join("warning: " + w for w in entry.warning.splitlines())
        return True, text

    # ---- read tracking (skipping unchanged entries on a rebuild) ---------
    def _track_start(self):
        """Swap the tables an entry reads for Track dicts (core/track.py)."""
        from ..core.track import Track

        if getattr(self, "_tracking", False):
            return None  # an entry inside an entry: the outer one keeps track
        m = self.model
        t = {"params": Track(self.params), "bodies": Track(m.bodies),
             "entities": {k: Track(v) for k, v in m._entities.items()},
             "origin": {k: Track(v) for k, v in m._origin.items()}}
        self.params, m.bodies = t["params"], t["bodies"]
        m._entities = dict(t["entities"])
        m._origin = dict(t["origin"])
        self._tracking, self._volatile = True, False
        return t

    def _track_stop(self, t):
        """Put plain dicts back; return what was read (core/track.Reads), or
        None when the entry cannot be skipped next time."""
        from ..core.track import Reads, Track

        if t is None:
            return None
        m = self.model
        self._tracking = False
        intact = self.params is t["params"] and m.bodies is t["bodies"] and all(
            m._entities.get(k) is v for k, v in t["entities"].items()) and all(
            m._origin.get(k) is v for k, v in t["origin"].items())
        # put plain dicts back wherever a Track is still in place
        if isinstance(self.params, Track):
            self.params = self.params.plain()
        if isinstance(m.bodies, Track):
            m.bodies = m.bodies.plain()
        for table in (m._entities, m._origin):
            for k, v in list(table.items()):
                if isinstance(v, Track):
                    table[k] = v.plain()
        if not intact or self._volatile:
            return None
        r = Reads()
        r.params = Reads.of(t["params"])
        r.bodies = Reads.of(t["bodies"])
        r.names = t["bodies"].names
        r.entities = {k: Reads.of(v) for k, v in t["entities"].items()}
        r.origin = {k: Reads.of(v) for k, v in t["origin"].items()}
        return r

    def _note_volatile(self, cmd: Command) -> None:
        """Commands that read files or older states are always run again."""
        if cmd.name in VOLATILE or any(a.type is Path for a in cmd.args):
            self._volatile = True

    def _can_skip(self, e: Entry, now: dict) -> bool:
        """Would entry ``e`` do exactly what it did last time, starting from ``now``?"""
        from ..core.track import same, same_keys

        r, old = e.reads, e.before
        if not self.skip_unchanged or r is None or old is None or e.after is None or not e.ok or e.suppressed:
            return False
        om, nm = old["model"], now["model"]
        for k in om.keys() | nm.keys():
            if k not in ("bodies", "entities", "origin") and not same(om.get(k), nm.get(k)):
                return False
        for k in ("macros", "parts", "part_files"):
            if not same_keys(old.get(k, {}), now.get(k, {}), None, identity=True):
                return False
        if not same_keys(old["params"], now["params"], r.params):
            return False
        if not same_keys(om["bodies"], nm["bodies"], r.bodies, identity=True):
            return False
        if r.names and {i: b.name for i, b in om["bodies"].items()} != {i: b.name for i, b in nm["bodies"].items()}:
            return False
        for table in ("entities", "origin"):
            for kind, keys in getattr(r, table).items():
                if not same_keys(om[table].get(kind, {}), nm[table].get(kind, {}), keys):
                    return False
        return True

    def _skipped_state(self, e: Entry, now: dict) -> dict:
        """``now`` with what ``e`` changed the last time it ran."""
        from ..core.track import apply_delta

        old, after = e.before, e.after
        om, am, nm = old["model"], after["model"], now["model"]
        model = {k: v for k, v in am.items()}
        model["bodies"] = apply_delta(nm["bodies"], om["bodies"], am["bodies"], identity=True)
        for table in ("entities", "origin"):
            model[table] = {k: apply_delta(nm[table].get(k, {}), om[table].get(k, {}), am[table].get(k, {}))
                            for k in nm[table].keys() | am[table].keys()}
        state = dict(after)
        state["model"] = model
        state["params"] = apply_delta(now["params"], old["params"], after["params"])
        return state

    def warn(self, text: str) -> None:
        """Flag the running entry: it worked, but the user should look at it."""
        if text:
            self._warnings.append(text)

    def model_revision(self) -> int:
        return self.model.revision

    def _fail(self, before: dict, revision: int, message: str) -> tuple[bool, str]:
        self._restore(before, emit=self.model_revision() != revision)
        done = self._trace_text()
        return False, (done + "\n" if done and not self._quiet else "") + message

    def _trace_text(self) -> str:
        lines = self._trace
        if len(lines) > MAX_TRACE:
            lines = lines[: MAX_TRACE - 1] + [f"... ({len(self._trace) - MAX_TRACE + 1} more lines)"]
        return "\n".join(lines)

    def _say(self, text: str) -> None:
        if text:
            self._trace.append(text)

    # ---- statements --------------------------------------------------------
    def _exec_block(self, stmts: list[Stmt]) -> None:
        for st in stmts:
            self._exec(st)

    def _exec(self, st: Stmt) -> None:
        self._steps += 1
        if self._steps > MAX_STEPS:
            raise CommandError(f"stopped after {MAX_STEPS} steps (endless loop?)")
        if self.deadline is not None and time.monotonic() > self.deadline:
            raise CommandError("stopped: the time limit for this run is used up")
        try:
            getattr(self, "_exec_" + type(st).__name__)(st)
        except (CommandError, ModelError, ExprError) as exc:
            if self._quiet or str(exc).startswith("line "):
                raise
            raise CommandError(f"line {st.line}: {exc}") from None

    def _exec_Assign(self, st: Assign) -> None:
        name = st.name
        self._check_param_name(name)
        if not self._scopes and name in self.overrides:
            value = self.overrides[name]
            self._set(name, value)
            self._say(f"{name} = {format_value(value)} (fixed from outside)")
            return
        if not self._scopes and name in self.drive:
            value = self.drive[name]
            self._set(name, value)
            self._say(f"{name} = {format_value(value)} (driven)")
            return
        if not self._scopes and name in self.config_values:
            value = self.config_values[name]
            self._set(name, value)
            self._say(f"{name} = {format_value(value)} (configuration {self.config})")
            return
        value = self.evaluator.eval(st.expr)
        self._set(name, value)
        self._say(f"{name} = {format_value(value)}")

    def _exec_Cmd(self, st: Cmd) -> None:
        if st.name in self.macros:
            self._call_macro(self.macros[st.name], st.args)
            return
        cmd = REGISTRY.get(st.name)
        if cmd is None:
            raise CommandError(f"unknown command {st.name!r} (type HELP for a list)")
        if cmd.session:
            raise CommandError(f"{cmd.name} can only be used on its own line")
        values, shown = self._bind(cmd, st.args)
        if getattr(self, "_tracking", False):
            self._note_volatile(cmd)
        if self.model.lineage is not None:
            self.model.lineage.start_command()
        msg = self._call(cmd, values)
        if self._quiet:
            self._say(msg)
        else:
            self._say(f"{shown}: {msg}" if msg else shown)

    def _exec_Do(self, st: Do) -> None:
        start, end, step = (self._number(e, "*DO") for e in (st.start, st.end, st.step))
        if step == 0:
            raise CommandError("*DO: step cannot be 0")
        count = math.floor((end - start) / step + 1e-9) + 1
        if count > MAX_LOOP:
            raise CommandError(f"*DO would run {count} times (limit {MAX_LOOP})")
        self._loops += 1
        try:
            for k in range(max(0, count)):
                v = start + k * step
                self._set(st.var, int(v) if float(v).is_integer() else v)
                try:
                    self._exec_block(st.body)
                except _Cycle:
                    continue
                except _Exit:
                    break
        finally:
            self._loops -= 1

    def _exec_If(self, st: If) -> None:
        for cond, body in st.branches:
            if self._truth(cond):
                self._exec_block(body)
                return
        self._exec_block(st.orelse)

    def _exec_While(self, st: While) -> None:
        self._loops += 1
        try:
            n = 0
            while self._truth(st.cond):
                n += 1
                if n > MAX_LOOP:
                    raise CommandError(f"*WHILE ran {MAX_LOOP} times (endless loop?)")
                try:
                    self._exec_block(st.body)
                except _Cycle:
                    continue
                except _Exit:
                    break
        finally:
            self._loops -= 1

    def _exec_MacroDef(self, st: MacroDef) -> None:
        if st.name in REGISTRY:
            raise CommandError(f"*MACRO: {st.name} is a built-in command; pick another name")
        if self._scopes:
            raise CommandError("*MACRO: macros are defined at the top level, not inside another macro")
        self.macros[st.name] = st
        args = ", ".join(n if d is None else f"{n}={d}" for n, d in st.params)
        self._say(f"macro {st.name}({args}) defined")

    def _exec_PartDef(self, st: PartDef) -> None:
        from .part_handlers import define_part

        self._say(define_part(self, st))

    def _exec_Simple(self, st: Simple) -> None:
        w = st.word
        if w == "*EXIT":
            if not self._loops:
                raise CommandError("*EXIT outside a loop")
            raise _Exit
        if w == "*CYCLE":
            if not self._loops:
                raise CommandError("*CYCLE outside a loop")
            raise _Cycle
        if w == "*RETURN":
            if not self._scopes:
                raise CommandError("*RETURN outside a macro")
            raise _Return
        if w == "*MSG":
            parts = []
            for a in st.args:
                v = self.evaluator.eval(a)
                parts.append(v if isinstance(v, str) else format_value(v))
            self._trace.append("".join(parts))
            return
        if w == "*DEL":
            for a in st.args:
                key = a.strip().upper()
                scope = self._scopes[-1] if self._scopes else self.params
                if key in scope:
                    del scope[key]
                elif key in self.macros and not self._scopes:
                    del self.macros[key]
                else:
                    raise CommandError(f"*DEL: no parameter or macro {a!r}")
            self._say("deleted " + ", ".join(a.upper() for a in st.args))

    def _call_macro(self, md: MacroDef, raw: list[str]) -> None:
        if len(raw) > len(md.params):
            raise CommandError(f"{md.name} takes at most {len(md.params)} arguments, got {len(raw)}")
        if len(self._scopes) >= MAX_DEPTH:
            raise CommandError(f"macros nested more than {MAX_DEPTH} deep")
        local: dict[str, Any] = {}
        for i, (pname, default) in enumerate(md.params):
            s = raw[i] if i < len(raw) else ""
            if s:
                local[pname] = self._macro_arg(s)
            elif default is not None:
                local[pname] = self.evaluator.eval(default)
            else:
                raise CommandError(f"{md.name}: argument '{pname.lower()}' is required")
        self._scopes.append(local)
        quiet, self._quiet = self._quiet, False
        try:
            self._exec_block(md.body)
        except _Return:
            pass
        except (CommandError, ModelError, ExprError) as exc:
            raise CommandError(f"in macro {md.name.lower()}: {exc}") from None
        finally:
            self._scopes.pop()
            self._quiet = quiet

    def _macro_arg(self, s: str) -> Any:
        """Macro arguments are expressions; an unknown bare word is passed as text (FACE, base ...)."""
        if is_ident(s):
            try:
                return self._lookup(s.upper())
            except KeyError:
                if not self.evaluator.is_name(s):
                    return s
        return self.evaluator.eval(s)

    # ---- names -------------------------------------------------------------
    def _lookup(self, key: str) -> Any:
        if self._scopes and key in self._scopes[-1]:
            return self._scopes[-1][key]
        if key in self.params:
            return self.params[key]
        if key == "LAST":
            if not self.model.last_body:
                raise ExprError("LAST: no body has been made yet")
            return self.model.last_body
        if key in UNIT_NAMES:
            from ..core.model import UNITS

            return UNITS[UNIT_NAMES[key]] / UNITS[self.model.units]
        body = self.model.body_by_name(key)
        if body is not None:  # a body name stands for its ID: VOL(plate)
            return body.id
        raise KeyError(key)

    def _set(self, key: str, value: Any) -> None:
        (self._scopes[-1] if self._scopes else self.params)[key] = value

    def _check_param_name(self, key: str) -> None:
        if key in RESERVED or self.evaluator.is_name(key):
            raise CommandError(f"{key} is a built-in name and cannot be a parameter")
        if not self._scopes and key not in self.params and self.model.body_by_name(key) is not None:
            raise CommandError(f"{key} is the name of a body; a parameter with the same name would hide it "
                               f"in commands (pick another name, or rename the body with NAME)")

    def _number(self, expr: str, what: str) -> float:
        v = self.evaluator.eval(expr)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise CommandError(f"{what}: {expr!r} must be a number")
        return v

    def _truth(self, expr: str) -> bool:
        v = self.evaluator.eval(expr)
        if isinstance(v, (Vec, str)):
            raise CommandError(f"condition {expr!r} must be a number or comparison")
        return bool(v)

    # ---- arguments ---------------------------------------------------------
    def _bind(self, cmd: Command, raw_args: list[str]) -> tuple[dict[str, Any], str]:
        values: dict[str, Any] = {}
        shown: list[str] = [cmd.name]
        i = 0
        for raw in raw_args:
            if i >= len(cmd.args):
                raise CommandError(f"{cmd.name} takes at most {len(cmd.args)} arguments, got more")
            arg = cmd.args[i]
            if raw == "":
                values[arg.name] = self._default(cmd, arg)
                shown.append("")
                i += 1
                continue
            if arg.type in (float, int):
                try:
                    v = self.evaluator.eval(raw)
                except ExprError as exc:
                    raise CommandError(f"{cmd.name}: '{arg.name}': {exc}") from None
                if isinstance(v, Vec):  # a point fills several numeric arguments
                    for comp in v:
                        if i >= len(cmd.args) or cmd.args[i].type not in (float, int):
                            raise CommandError(f"{cmd.name}: the point {v!r} does not fit at argument '{arg.name}'")
                        values[cmd.args[i].name] = self._convert(cmd, cmd.args[i], comp)
                        shown.append(fmt_num(comp))
                        i += 1
                    continue
                values[arg.name] = self._convert(cmd, arg, v)
                shown.append(fmt_num(values[arg.name]))
            elif arg.type is Raw:
                values[arg.name] = raw.strip()
                shown.append(values[arg.name])
            elif arg.type is BodyRef:
                values[arg.name] = self._body_arg(cmd, raw)
                shown.append(str(values[arg.name]))
            else:
                values[arg.name] = self._word_arg(cmd, arg, raw)
                shown.append(values[arg.name] if arg.type is str else format_value(values[arg.name]))
            i += 1
        for arg in cmd.args[i:]:
            values[arg.name] = self._default(cmd, arg)
        for name, most in cmd.limits.items():
            v = values.get(name)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) > most:
                raise CommandError(f"{cmd.name}: {name} {format_value(v)} is more than this command can make "
                                   f"in a sensible time; at most {format_value(most)}")
        while shown and shown[-1] == "":
            shown.pop()
        return values, ", ".join(shown)

    @staticmethod
    def _default(cmd: Command, arg: Arg) -> Any:
        if arg.default is None:
            raise CommandError(f"{cmd.name}: argument '{arg.name}' is required")
        return arg.default

    @staticmethod
    def _convert(cmd: Command, arg: Arg, v: Any) -> Any:
        if isinstance(v, str) or not isinstance(v, (int, float)):
            raise CommandError(f"{cmd.name}: '{arg.name}' must be a number, got {format_value(v)}")
        if arg.type is int:
            if not float(v).is_integer():
                raise CommandError(f"{cmd.name}: '{arg.name}' must be a whole number, got {fmt_num(v)}")
            return int(v)
        return float(v)

    def _word_arg(self, cmd: Command, arg: Arg, raw: str) -> str:
        s = raw.strip()
        if arg.type is Path and len(s) >= 2 and s[0] in "\"'" and s[-1] == s[0] and s[0] not in s[1:-1]:
            return s[1:-1]
        if s[:1] in "\"'(":
            v = self.evaluator.eval(s)
            if not isinstance(v, str):
                raise CommandError(f"{cmd.name}: '{arg.name}' must be text, got {format_value(v)}")
        elif is_ident(s):
            try:
                v = self._lookup(s.upper())
                if not isinstance(v, str):
                    v = s
            except KeyError:
                v = s
        else:
            v = s
        return v.upper() if arg.type is str else v

    def _body_arg(self, cmd: Command, raw: str) -> int:
        bid = self._body_ref(cmd, raw)
        if bid != SELECTED:
            from .mesh_handlers import check_mesh_use

            check_mesh_use(self, cmd.name, bid)
        return bid

    def _body_ref(self, cmd: Command, raw: str) -> int:
        s = raw.strip()
        v: Any
        if s.upper() == "SEL" and cmd.name in SEL_AS_BODIES:
            return SELECTED  # "all the selected bodies"; the handler expands it
        if is_ident(s):
            try:
                v = self._lookup(s.upper())
            except KeyError:
                b = self.model.body_by_name(s)
                if b is None:
                    if self.evaluator.is_name(s):
                        v = self.evaluator.eval(s)
                    else:
                        raise CommandError(f"{cmd.name}: no body or parameter named {s!r}") from None
                else:
                    return b.id
        else:
            v = self.evaluator.eval(s)
        if isinstance(v, str):
            b = self.model.body_by_name(v)
            if b is None:
                raise CommandError(f"{cmd.name}: no body named {v!r}")
            return b.id
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not float(v).is_integer():
            raise CommandError(f"{cmd.name}: a body is an ID or a name, got {format_value(v)}")
        return int(v)
