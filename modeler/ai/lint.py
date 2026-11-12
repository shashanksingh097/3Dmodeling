"""Checking a script without running it.

Finds what would stop it or make it fragile before any geometry is made:
syntax, unknown commands, too many arguments, missing required ones,
names used before they are set, raw IDs where a selector would survive
history edits, and (for the sandbox) commands that touch files.
"""

from __future__ import annotations

import ast
import difflib
from typing import TYPE_CHECKING, Any

from ..commands.processor import REGISTRY, BodyRef
from ..lang.script import (
    Assign,
    Cmd,
    Do,
    If,
    MacroDef,
    PartDef,
    ScriptError,
    Simple,
    While,
    parse,
)

if TYPE_CHECKING:
    from ..commands.processor import Processor

# commands that read or write files, or replace the session: refused in the sandbox
FILE_COMMANDS = {"SAVE", "OPEN", "NEW", "RUN", "EXPORT", "IMPORT", "LIB", "LIBSAVE"}
# loop variables, macro arguments ... are only known while running; these
# words are never parameters
_WORDS = {"SEL", "ALL", "LAST", "NONE"}


def _issue(line: int, level: str, msg: str, **extra) -> dict[str, Any]:
    return {"line": line, "level": level, "msg": msg, **extra}


def lint(p: "Processor", text: str, sandbox: bool = False) -> dict[str, Any]:
    """Issues in the script, each with its line, level (error, warning) and message."""
    issues: list[dict[str, Any]] = []
    try:
        stmts = parse(text)
    except ScriptError as exc:
        return {"ok": False, "issues": [_issue(exc.line or 0, "error", str(exc).split(": ", 1)[-1]
                                               if exc.line else str(exc))]}
    known = {k.upper() for k in p.params} | {b.name.upper() for b in p.model.bodies.values()}
    macros = {k.upper() for k in p.macros}
    # every assignment anywhere counts as known after its line; a first pass
    # collects macros and names made by NAME, so order inside blocks is lenient
    _collect(stmts, macros)
    _walk(p, stmts, known, macros, issues, sandbox, scope=set())
    issues.sort(key=lambda i: i["line"])
    return {"ok": not any(i["level"] == "error" for i in issues), "issues": issues}


def _collect(stmts, macros: set[str]) -> None:
    for st in stmts:
        if isinstance(st, MacroDef):
            macros.add(st.name.upper())


def _walk(p, stmts, known: set[str], macros: set[str], issues, sandbox: bool, scope: set[str]) -> None:
    for st in stmts:
        if isinstance(st, Assign):
            _names(p, st.expr, st.line, known | scope, issues)
            known.add(st.name.upper())
        elif isinstance(st, Cmd):
            _command(p, st, known | scope, macros, issues, sandbox)
            if st.name == "NAME" and len(st.args) >= 2:
                known.add(st.args[1].strip().strip("\"'").upper())
        elif isinstance(st, Do):
            for e in (st.start, st.end, st.step):
                if e:
                    _names(p, e, st.line, known | scope, issues)
            _walk(p, st.body, known, macros, issues, sandbox, scope | {st.var.upper()})
        elif isinstance(st, If):
            for cond, body in st.branches:
                _names(p, cond, st.line, known | scope, issues)
                _walk(p, body, known, macros, issues, sandbox, scope)
            _walk(p, st.orelse, known, macros, issues, sandbox, scope)
        elif isinstance(st, While):
            _names(p, st.cond, st.line, known | scope, issues)
            _walk(p, st.body, known, macros, issues, sandbox, scope)
        elif isinstance(st, MacroDef):
            inner = {n.upper() for n, _ in st.params}
            _walk(p, st.body, set(known), macros, issues, sandbox, scope | inner)
        elif isinstance(st, PartDef):
            continue  # a part runs in a model of its own; it is checked when placed
        elif isinstance(st, Simple):
            continue


def _command(p, st: Cmd, known: set[str], macros: set[str], issues, sandbox: bool) -> None:
    if st.name in macros:
        return
    cmd = REGISTRY.get(st.name)
    if cmd is None:
        close = difflib.get_close_matches(st.name, list(REGISTRY) + sorted(macros), n=3, cutoff=0.6)
        hint = f"; did you mean {' or '.join(close)}?" if close else "; find_commands lists what there is"
        issues.append(_issue(st.line, "error", f"unknown command {st.name}{hint}"))
        return
    if sandbox and st.name in FILE_COMMANDS:
        issues.append(_issue(st.line, "error", f"{st.name} works on files and is not run in the sandbox; "
                                               "propose it to the user instead"))
    elif cmd.session and sandbox:
        issues.append(_issue(st.line, "warning", f"{st.name} changes the history itself"))
    args = list(st.args)
    while args and args[-1] == "":
        args.pop()
    if len(args) > len(cmd.args):
        issues.append(_issue(st.line, "error", f"{st.name} takes at most {len(cmd.args)} arguments, got {len(args)}"))
    required = sum(1 for a in cmd.args if a.default is None)
    if len(args) < required and not any(_maybe_point(a) for a in args):
        missing = [a.name for a in cmd.args if a.default is None][len(args):]
        issues.append(_issue(st.line, "error", f"{st.name} is missing {', '.join(missing)}"))
    for raw, arg in zip(args, cmd.args):
        if raw and arg.type in (float, int):
            _names(p, raw, st.line, known, issues)
        elif raw and arg.type is BodyRef:
            word = raw.strip()
            if word.isidentifier() and word.upper() not in known and word.upper() not in _WORDS \
                    and not p.evaluator.is_name(word):
                issues.append(_issue(st.line, "warning", f"{st.name}: no body or parameter named {word} yet"))
    if st.name == "PICK":
        issues.append(_issue(st.line, "warning", "PICK uses a raw ID; selector_for gives SEL lines that "
                                                 "survive history edits", fix="selector_for"))
    if st.name == "SEL" and len(args) >= 4:
        crit = args[2].upper()
        if crit == "ID" or _is_number(args[2]):
            issues.append(_issue(st.line, "warning", "SEL by ID: IDs can move when earlier steps change; "
                                                     "a criterion (NORMAL, LOC, TYPE ...) is safer",
                                 fix="selector_for"))


def _maybe_point(raw: str) -> bool:
    """An argument that may hold a point and so fill three arguments."""
    s = raw.strip()
    return bool(s) and not _is_number(s) and not s.startswith(("\"", "'"))


def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def _names(p, expr: str, line: int, known: set[str], issues) -> None:
    """Warn about names in an expression that are not set (yet)."""
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as exc:
        issues.append(_issue(line, "error", f"cannot read {expr.strip()!r}: {exc.msg}"))
        return
    calls = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            name = n.func.id.upper()
            if name not in p.evaluator.functions:
                issues.append(_issue(line, "error", f"unknown function {name}()"))
        elif isinstance(n, ast.Name) and id(n) not in calls:
            key = n.id.upper()
            if key in known or key in _WORDS or key in p.evaluator.constants or key in p.evaluator.functions \
                    or key in ("MM", "CM", "METER", "INCH"):
                continue
            if p.model.body_by_name(key) is not None:
                continue
            issues.append(_issue(line, "warning", f"{n.id} is not set before this line"))
