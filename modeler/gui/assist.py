"""Typing help for the command line: completion lists and argument hints.

Pure functions over the processor, so they are tested without a window.
Everything comes from the command registry's metadata, the same data
``HELP`` uses, plus the session's macros, parameters and body names.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

from ..commands import REGISTRY, Processor

_BLOCK_WORDS = ("*DO", "*ENDDO", "*IF", "*ELSEIF", "*ELSE", "*ENDIF", "*WHILE", "*ENDWHILE",
                "*MACRO", "*END", "*EXIT", "*CYCLE", "*RETURN", "*MSG", "*DEL")
# keyword choices for arguments that take a word, by command and argument name
_CHOICES = {
    "kind": ("BODY", "FACE", "EDGE", "VERTEX"),
    "mode": ("MINTWIST", "FRENET", "FIXED"),
    "format": ("STEP", "BREP", "STL", "IGES"),
    "hand": ("RIGHT", "LEFT"),
    "unit": ("MM", "CM", "M", "IN"),
}
_COMMAND_CHOICES = {
    ("ARRAY", "kind"): ("LINEAR", "POLAR", "PATH"),
    ("CURVE", "kind"): ("PARAM",),
    ("KEEP", "mode"): ("ON", "OFF"),
    ("SEL", "mode"): ("S", "R", "A", "U", "ALL", "NONE", "INVE"),
    ("VIEW", "name"): ("ISO", "TOP", "BOTTOM", "FRONT", "BACK", "LEFT", "RIGHT"),
    ("HIST", "action"): ("LIST", "EDIT", "INSERT", "DELETE", "SUPPRESS", "RESUME", "MOVE", "REPLAY", "PART"),
    ("EXPORT", "format"): ("STEP", "BREP", "STL"),
    ("IMPORT", "format"): ("STEP", "IGES", "BREP", "STL"),
    ("LIST", "what"): ("BODIES", "PARAMS", "MACROS", "PARTS", "SETS", "DATUMS"),
    ("LIB", "action"): ("LOAD",),
    ("PLANE", "how"): ("XY", "YZ", "ZX", "PN", "3P", "FACE", "OFFSET", "ANGLE", "MID", "NORMAL"),
    ("AXIS", "how"): ("X", "Y", "Z", "PD", "2P", "EDGE", "FACE", "PLANES"),
    ("POINT", "how"): ("XYZ", "VERTEX", "CENTER", "ON"),
    ("DATUM", "action"): ("DELETE",),
    ("HOLE", "kind"): ("SIMPLE", "CBORE", "CSINK"),
    ("SPLIT", "keep"): ("BOTH", "ABOVE", "BELOW"),
    ("SHELL", "side"): ("IN", "OUT"),
    ("SPRING", "finish"): ("PLAIN", "GROUND"),
    ("RAILSWEEP", "fit"): ("SCALE", "TURN"),
    ("OFFSET", "corners"): ("ROUND", "SHARP"),
    ("SECTION", "side"): ("ABOVE", "BELOW"),
}
_TOKEN = re.compile(r"[A-Za-z_*/][A-Za-z0-9_]*$")


@dataclass
class Context:
    command: str  # upper-case command (or macro) name, "" if none yet
    arg_index: int  # -1 while typing the command name itself
    start: int  # where the word being typed starts
    prefix: str  # the word being typed


def context(text: str, cursor: int | None = None) -> Context:
    """Where the cursor is: which command, which argument, which word."""
    cursor = len(text) if cursor is None else cursor
    before = text[:cursor]
    if "!" in before:  # inside a comment
        return Context("", -2, cursor, "")
    m = _TOKEN.search(before)
    prefix = m.group(0) if m else ""
    start = cursor - len(prefix)
    # split on top-level commas (not inside parentheses or quotes)
    parts, depth, quote, cur = [], 0, "", ""
    for ch in before:
        if quote:
            quote = "" if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
            continue
        cur += ch
    parts.append(cur)
    head = parts[0].strip()
    if len(parts) == 1:
        if "=" in head:  # a parameter assignment: complete names in the expression
            return Context("", 0, start, prefix)
        return Context("", -1, start, prefix)
    return Context(head.upper(), len(parts) - 2, start, prefix)


def _names(p: Processor) -> list[str]:
    out = sorted(p.params)
    out += sorted(b.name for b in p.model.bodies.values() if not b.name.startswith("body"))
    out += sorted(d.name for d in p.model.datums.values())
    return out


def completions(p: Processor, text: str, cursor: int | None = None) -> list[str]:
    """Words that fit where the cursor is, best first."""
    ctx = context(text, cursor)
    pre = ctx.prefix.upper()
    if ctx.arg_index == -2:
        return []
    if ctx.arg_index == -1:
        pool = list(REGISTRY) + sorted(p.macros) + list(_BLOCK_WORDS)
    else:
        pool = []
        cmd = REGISTRY.get(ctx.command)
        if cmd is not None and ctx.arg_index < len(cmd.args):
            arg = cmd.args[ctx.arg_index]
            pool += list(_COMMAND_CHOICES.get((cmd.name, arg.name), ()))
            if arg.type is str and not pool:
                pool += list(_CHOICES.get(arg.name, ()))
        pool += _names(p) + ["LAST"]
    if not pre:
        return []
    seen, out = set(), []
    for w in pool:
        if w.upper().startswith(pre) and w.upper() != pre and w not in seen:
            seen.add(w)
            out.append(w)
    return out


def signature(p: Processor, text: str, cursor: int | None = None) -> str:
    """Rich-text hint for the command being typed, current argument in bold."""
    ctx = context(text, cursor)
    name = ctx.command or (text.strip().split(",")[0].strip().upper() if ctx.arg_index == -1 else "")
    if not name:
        return ""
    cmd = REGISTRY.get(name)
    if cmd is None:
        md = p.macros.get(name)
        if md is None:
            return ""
        parts = [html.escape(n.lower() if d is None else f"[{n.lower()}={d}]") for n, d in md.params]
        if 0 <= ctx.arg_index < len(parts):
            parts[ctx.arg_index] = f"<b>{parts[ctx.arg_index]}</b>"
        return f"<b>{html.escape(md.name)}</b>, " + ", ".join(parts) + " &nbsp;<i>(your macro)</i>"
    parts = []
    for a in cmd.args:
        label = a.name if a.default is None else f"[{a.name}]"
        parts.append(html.escape(label))
    shown = parts
    # long variadic lists (point lists, extra bodies): show the start and an ellipsis
    if len(parts) > 12:
        shown = parts[:6] + ["…"]
    if 0 <= ctx.arg_index < len(cmd.args):
        i = min(ctx.arg_index, len(shown) - 1)
        if shown[i] != "…":
            shown[i] = f"<b><u>{shown[i]}</u></b>"
        a = cmd.args[ctx.arg_index]
        detail = a.help or cmd.help
        if a.default not in (None, ""):
            detail = (detail + "; " if detail else "") + f"default {a.default}"
    else:
        detail = cmd.help.split(". ")[0]
    sig = f"<b>{html.escape(cmd.name)}</b>" + (", " + ", ".join(shown) if shown else "")
    return sig + (f" &nbsp;—&nbsp; {html.escape(detail)}" if detail else "")
