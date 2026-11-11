"""Reading command-language text: lines, arguments and blocks.

A script is a list of statements, one per line:

* ``NAME, arg, arg, , arg``  a command (or a macro call)
* ``W = 40``                 a parameter assignment
* ``*DO`` / ``*IF`` / ``*WHILE`` / ``*MACRO`` ... their closing line: a block
* ``! text``                 a comment (``!=`` is "not equal", not a comment)

:func:`parse` turns text into a tree of statements. :func:`split_entries`
cuts text into *top-level units* (one plain line, or a whole block with its
leading comments), which is what the history stores and edits.
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*$")
_ASSIGN = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(?!=)(.*)$", re.S)

OPENERS = {"*DO": "*ENDDO", "*IF": "*ENDIF", "*WHILE": "*ENDWHILE", "*MACRO": "*END"}
CLOSERS = {"*ENDDO", "*ENDIF", "*ENDWHILE", "*END", "*ENDMACRO"}
MIDDLES = {"*ELSEIF", "*ELSE"}
SIMPLE = {"*EXIT", "*CYCLE", "*RETURN", "*MSG", "*DEL"}

COMPARE_WORDS = {"EQ": "==", "NE": "!=", "LT": "<", "GT": ">", "LE": "<=", "GE": ">="}


class ScriptError(Exception):
    def __init__(self, message: str, line: int | None = None) -> None:
        super().__init__(message)
        self.line = line

    def __str__(self) -> str:
        msg = super().__str__()
        return f"line {self.line}: {msg}" if self.line else msg


class Incomplete(ScriptError):
    """The text ends inside an open block (more lines are needed)."""


# ---- low-level text helpers ----------------------------------------------------

def strip_comment(line: str) -> str:
    """Remove a ``!`` comment, ignoring ``!`` inside quotes and ``!=``."""
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == "\\":
                continue
            if ch == quote and (i == 0 or line[i - 1] != "\\"):
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "!" and not line.startswith("=", i + 1):
            return line[:i]
    return line


def split_args(text: str) -> list[str]:
    """Split on commas that are not inside (), [] or quotes. Parts are stripped."""
    parts, depth, quote, cur = [], 0, None, []
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            cur.append(ch)
            if ch == "\\" and i + 1 < len(text):
                cur.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            cur.append(ch)
        elif ch in "([":
            depth += 1
            cur.append(ch)
        elif ch in ")]":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        i += 1
    if quote:
        raise ScriptError("a quoted string is not closed")
    if depth != 0:
        raise ScriptError("parentheses do not match")
    parts.append("".join(cur).strip())
    return parts


def is_ident(text: str) -> bool:
    return bool(_IDENT.match(text))


# ---- statements ----------------------------------------------------------------

@dataclass
class Stmt:
    line: int  # 1-based line number in the text it came from


@dataclass
class Cmd(Stmt):
    name: str  # upper case
    args: list[str]  # raw argument text, evaluated when run
    text: str  # the line without comment, for messages


@dataclass
class Assign(Stmt):
    name: str
    expr: str


@dataclass
class Do(Stmt):
    var: str
    start: str
    end: str
    step: str
    body: list[Stmt] = field(default_factory=list)


@dataclass
class If(Stmt):
    branches: list[tuple[str, list[Stmt]]] = field(default_factory=list)  # (condition expr, body)
    orelse: list[Stmt] = field(default_factory=list)


@dataclass
class While(Stmt):
    cond: str
    body: list[Stmt] = field(default_factory=list)


@dataclass
class MacroDef(Stmt):
    name: str
    params: list[tuple[str, str | None]]  # (NAME, default expr or None)
    body: list[Stmt] = field(default_factory=list)
    source: str = ""


@dataclass
class Simple(Stmt):
    """*EXIT, *CYCLE, *RETURN, *MSG, *DEL"""

    word: str
    args: list[str]


def condition(args: list[str], word: str, line: int) -> str:
    """Build a condition expression from ``*IF``/``*WHILE`` arguments.

    Accepts ``a, GT, b [, THEN]`` or one expression ``a > b``.
    """
    args = list(args)
    if args and args[-1].upper() == "THEN":
        args.pop()
    if len(args) == 1 and args[0]:
        return args[0]
    if len(args) == 3 and args[1].upper() in COMPARE_WORDS:
        return f"({args[0]}) {COMPARE_WORDS[args[1].upper()]} ({args[2]})"
    raise ScriptError(f"{word}: write '{word}, a, GT, b' (EQ NE LT GT LE GE) or '{word}, a > b'", line)


def _lines(text: str) -> list[tuple[int, str]]:
    return [(i + 1, line) for i, line in enumerate(text.splitlines())]


def parse(text: str, first_line: int = 1) -> list[Stmt]:
    """Parse text into statements. Raises Incomplete if a block is left open."""
    lines = [(n + first_line - 1, line) for n, line in _lines(text)]
    pos = 0

    def block(closers: set[str], opener_line: int, opener: str) -> tuple[list[Stmt], str, list[str], int]:
        """Read statements until one of closers; return (body, closer word, closer args, line)."""
        nonlocal pos
        body: list[Stmt] = []
        while pos < len(lines):
            n, raw = lines[pos]
            code = strip_comment(raw).strip()
            if code.startswith("*"):
                parts = split_args_at(code, n)
                word = parts[0].upper()
                if word in closers or (word in CLOSERS | MIDDLES and closers):
                    if word not in closers:
                        raise ScriptError(f"{word} does not close {opener} (opened on line {opener_line})", n)
                    pos += 1
                    return body, word, parts[1:], n
            st = statement()
            if st is not None:
                body.append(st)
        if closers:
            raise Incomplete(f"{opener} opened on line {opener_line} is not closed", opener_line)
        return body, "", [], 0

    def statement() -> Stmt | None:
        nonlocal pos
        n, raw = lines[pos]
        code = strip_comment(raw).strip()
        pos += 1
        if not code:
            return None
        if code.startswith("*"):
            parts = split_args_at(code, n)
            word, args = parts[0].upper(), parts[1:]
            if word == "*DO":
                if len(args) not in (3, 4) or not is_ident(args[0]):
                    raise ScriptError("*DO: write '*DO, i, start, end [, step]'", n)
                body, _, _, _ = block({"*ENDDO"}, n, word)
                return Do(n, args[0].upper(), args[1], args[2], args[3] if len(args) == 4 else "1", body)
            if word == "*IF":
                node = If(n)
                cond = condition(args, word, n)
                while True:
                    body, closer, cargs, cn = block({"*ELSEIF", "*ELSE", "*ENDIF"}, n, word)
                    node.branches.append((cond, body))
                    if closer == "*ELSEIF":
                        cond = condition(cargs, closer, cn)
                        continue
                    if closer == "*ELSE":
                        node.orelse, _, _, _ = block({"*ENDIF"}, n, word)
                    return node
            if word == "*WHILE":
                cond = condition(args, word, n)
                body, _, _, _ = block({"*ENDWHILE"}, n, word)
                return While(n, cond, body)
            if word == "*MACRO":
                if not args or not is_ident(args[0]):
                    raise ScriptError("*MACRO: write '*MACRO, name, arg1, arg2=default, ...'", n)
                params = []
                for a in args[1:]:
                    name, _, default = a.partition("=")
                    name = name.strip()
                    if not is_ident(name):
                        raise ScriptError(f"*MACRO: {a!r} is not a valid argument name", n)
                    params.append((name.upper(), default.strip() or None))
                start = pos - 1
                body, _, _, end_line = block({"*END", "*ENDMACRO"}, n, word)
                src = "\n".join(line for _, line in lines[start:pos])
                return MacroDef(n, args[0].upper(), params, body, src)
            if word in SIMPLE:
                return Simple(n, word, args)
            if word in CLOSERS | MIDDLES:
                raise ScriptError(f"{word} without a matching block", n)
            raise ScriptError(f"unknown block word {parts[0]!r}", n)
        m = _ASSIGN.match(code)
        if m and not _looks_like_command(code):
            expr = m.group(2).strip()
            if not expr:
                raise ScriptError(f"{m.group(1)} = ... needs a value", n)
            return Assign(n, m.group(1).upper(), expr)
        parts = split_args_at(code, n)
        name = parts[0]
        if not is_ident(name.lstrip("/")) or name.count("/") > 1 or ("/" in name and not name.startswith("/")):
            raise ScriptError(f"{name!r} is not a command name", n)
        args = parts[1:]
        while args and args[-1] == "":  # trailing empty args take defaults anyway
            args.pop()
        return Cmd(n, name.upper(), args, code)

    body, _, _, _ = block(set(), 0, "")
    return body


def _looks_like_command(code: str) -> bool:
    """``NAME, x=1`` is a command with an odd argument, not an assignment."""
    eq = code.find("=")
    comma = code.find(",")
    return 0 <= comma < eq


def split_args_at(code: str, line: int) -> list[str]:
    try:
        return split_args(code)
    except ScriptError as exc:
        raise ScriptError(str(exc), line) from None


# ---- top-level units --------------------------------------------------------------

def split_entries(text: str) -> list[str]:
    """Cut text into top-level units: one statement each, with the comment
    lines just above it. Blocks (``*DO`` ... ``*ENDDO``) stay one unit.

    Raises Incomplete if the text ends inside a block.
    """
    out: list[str] = []
    pending: list[str] = []  # comments waiting for their statement
    depth = 0
    cur: list[str] = []
    opened_at = 0
    for n, raw in _lines(text):
        code = strip_comment(raw).strip()
        if depth == 0 and not code:
            if raw.strip():
                pending.append(raw.rstrip())
            elif pending:  # a blank line ends a comment paragraph
                pending = []
            continue
        cur.append(raw.rstrip())
        word = split_args_at(code, n)[0].upper() if code.startswith("*") else ""
        if word in OPENERS:
            if depth == 0:
                opened_at = n
            depth += 1
        elif word in CLOSERS:
            depth -= 1
            if depth < 0:
                raise ScriptError(f"{word} without a matching block", n)
        if depth == 0:
            out.append(textwrap.dedent("\n".join(pending + cur)))
            pending, cur = [], []
    if depth:
        raise Incomplete(f"block opened on line {opened_at} is not closed", opened_at)
    return out


def needs_more(text: str) -> bool:
    """True if text is an unfinished block (interactive input continues)."""
    try:
        split_entries(text)
    except Incomplete:
        return True
    except ScriptError:
        return False
    return False


def first_code_line(text: str) -> str:
    """The first line that is not a comment: how an entry is labelled."""
    for raw in text.splitlines():
        code = strip_comment(raw).strip()
        if code:
            return code
    return text.strip()


def code_key(text: str) -> str:
    """The statements of a unit without comments, blank lines or indentation:
    equal for two texts that run the same commands."""
    lines = (strip_comment(raw).strip() for raw in text.splitlines())
    return "\n".join(line for line in lines if line)


def leading_comment(text: str) -> str:
    out = []
    for raw in text.splitlines():
        s = raw.strip()
        if s.startswith("!"):
            out.append(s[1:].strip())
        elif s:
            break
    return " ".join(out)
