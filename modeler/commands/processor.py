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

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from ..core.model import IdPins, Model, ModelError
from ..lang.expr import Evaluator, ExprError, Vec, fmt_num, format_value
from ..lang.script import (
    Assign,
    Cmd,
    Do,
    If,
    Incomplete,
    MacroDef,
    ScriptError,
    Simple,
    Stmt,
    While,
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
    def set_pick_mode(self, kind: str) -> None: ...


class Text:
    """Argument type: a string that keeps its case (file names, labels)."""


class Raw:
    """Argument type: the argument text as written; the handler evaluates it."""


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


@dataclass
class Entry:
    """One top-level unit of the history."""

    text: str
    ok: bool = True
    message: str = ""
    suppressed: bool = False
    pins: dict[str, list[int]] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return first_code_line(self.text)


class _Exit(Exception):
    pass


class _Cycle(Exception):
    pass


class _Return(Exception):
    pass


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
        # parameters fixed from outside (batch runner -D): assignments keep these values
        self.overrides = {k.upper(): v for k, v in (overrides or {}).items()}

        self.history: list[Entry] = []
        self.cursor = 0  # entries[:cursor] are applied; the rest can be redone
        self._snaps: list[dict] = [self._state()]
        self._buffer: list[str] = []

        self._scopes: list[dict[str, Any]] = []  # macro locals
        self._loops = 0
        self._steps = 0
        self._trace: list[str] = []
        self._quiet = True

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
            return self._finish(self.run_unit(text))
        return self._finish(self.run_unit(line))

    def cancel_pending(self) -> None:
        self._buffer = []

    @property
    def pending(self) -> bool:
        return bool(self._buffer)

    def run_script(self, text: str) -> list[Result]:
        """Run a whole script, one history entry per top-level unit.

        Stops at the first failing unit (which is not added to the history).
        """
        try:
            units = split_entries(text)
        except ScriptError as exc:
            return [self._finish(Result(first_code_line(text), False, str(exc)))]
        results = []
        for unit in units:
            r = self._finish(self.run_unit(unit))
            if r.line:
                results.append(r)
                if not r.ok:
                    break
        return results

    def run_unit(self, text: str) -> Result:
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
        if len(stmts) == 1 and isinstance(stmts[0], Cmd):
            cmd = REGISTRY.get(stmts[0].name)
            if cmd is not None and not cmd.logged:
                return self._run_unlogged(cmd, stmts[0], label)
        entry = Entry(text)
        ok, message = self._run_entry(entry, stmts)
        entry.ok, entry.message = ok, message
        if not ok:
            return Result(label, False, message)
        del self.history[self.cursor :]
        del self._snaps[self.cursor + 1 :]
        self.history.append(entry)
        self.cursor += 1
        self._snaps.append(self._state())
        self._history_changed()
        return Result(label, True, message)

    @property
    def log(self) -> list[str]:
        """The applied history as text, one entry per item."""
        return [e.text for e in self.history[: self.cursor] if not e.suppressed]

    def script(self) -> str:
        """The applied history as a script that rebuilds the model."""
        out = []
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
    def undo(self, n: int = 1) -> str:
        if self.cursor == 0:
            raise CommandError("nothing to undo")
        n = max(1, min(n, self.cursor))
        self.cursor -= n
        self._restore(self._snaps[self.cursor])
        self._history_changed()
        return f"undid {n} step{'s' if n > 1 else ''}; {self.cursor} in history"

    def redo(self, n: int = 1) -> str:
        avail = len(self.history) - self.cursor
        if avail == 0:
            raise CommandError("nothing to redo")
        n = max(1, min(n, avail))
        self.cursor += n
        self._restore(self._snaps[self.cursor])
        self._history_changed()
        return f"redid {n} step{'s' if n > 1 else ''}; {self.cursor} in history"

    def edit_entry(self, index: int, text: str) -> str:
        """Replace entry ``index`` (1-based) and re-run from there."""
        i = self._index(index)
        new = self._check_unit(text)
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

    def rebuild(self, start: int = 0) -> str:
        """Re-run entries ``start`` (0-based) .. cursor-1 from the snapshot before ``start``.

        Entries that now fail are kept and marked; the model skips them.
        Each entry asks for the same IDs it handed out last time.
        """
        self._drop_redo_tail()
        self._restore(self._snaps[start], emit=False)
        floor: dict[str, int] = {}
        for e in self.history[start:]:
            for kind, ids in e.pins.items():
                if ids:
                    floor[kind] = max(floor.get(kind, 1), max(ids) + 1)
        self.model.id_floor.update(floor)
        errors = []
        try:
            for j in range(start, self.cursor):
                e = self.history[j]
                if e.suppressed:
                    e.ok, e.message = True, "suppressed"
                else:
                    try:
                        stmts = parse(e.text)
                    except ScriptError as exc:
                        e.ok, e.message = False, str(exc)
                    else:
                        e.ok, e.message = self._run_entry(e, stmts)
                    if not e.ok:
                        errors.append(f"entry {j + 1}: {e.message}")
                self._snaps[j + 1] = self._state()
        finally:
            for kind in floor:
                self.model.id_floor[kind] = 1
        self.model.restore(self.model.snapshot())  # one refresh for listeners
        self._history_changed()
        n = self.cursor - start
        msg = f"re-ran {n} entr{'y' if n == 1 else 'ies'} from {start + 1}"
        if errors:
            msg += f"; {len(errors)} failed:\n  " + "\n  ".join(errors)
        return msg

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
        return {"model": self.model.snapshot(), "params": dict(self.params), "macros": dict(self.macros)}

    def _restore(self, state: dict, emit: bool = True) -> None:
        self.params = dict(state["params"])
        self.macros = dict(state["macros"])
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
            if cmd is not None and not cmd.logged:
                raise CommandError(f"{cmd.name} does not belong in the history")
        return text

    def _run_unlogged(self, cmd: Command, st: Cmd, label: str) -> Result:
        self._trace = []
        try:
            values, _ = self._bind(cmd, st.args)
            msg = cmd.fn(self, **values) or ""
            return Result(label, True, msg)
        except (CommandError, ModelError, ExprError, ScriptError) as exc:
            return Result(label, False, str(exc))
        except Exception as exc:  # kernel failures should not kill the app
            return Result(label, False, f"{type(exc).__name__}: {exc}")

    def _run_entry(self, entry: Entry, stmts: list[Stmt]) -> tuple[bool, str]:
        """Run an entry atomically. Returns (ok, message)."""
        before = self._state()
        revision = self.model_revision()
        self._trace, self._steps, self._loops, self._scopes = [], 0, 0, []
        pins = IdPins(entry.pins)
        self.model.pins = pins
        single = len(stmts) == 1 and isinstance(stmts[0], (Cmd, Assign))
        self._quiet = single
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
        entry.pins = pins.used
        return True, self._trace_text()

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
        msg = cmd.fn(self, **values) or ""
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
        s = raw.strip()
        v: Any
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
