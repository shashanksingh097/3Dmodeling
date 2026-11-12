"""Checking and describing: ASSERT, DESCRIBE, SELFOR, LINT, DIFF.

These are the commands under the AI assistant's tools (docs/M9-ai-tools.md),
and just as useful typed by hand. ASSERT goes in the history (a script can
carry its own checks); the others only read the model.

The modeler.ai modules are imported inside the handlers: they import the
command package themselves.
"""

from __future__ import annotations

import json
from typing import Any

from ..core.model import ENTITY_KINDS, ModelError, check_kind
from ..lang.expr import ExprError
from .processor import Arg, CommandError, Path, Processor, Raw, command


@command(
    "ASSERT",
    Arg("value", Raw, help="what to check: an expression, e.g. VOL(b), BBOX(b).dz, HOLES(b, 8), VALID(b)"),
    Arg("op", Raw, "", help="EQ NE LT GT LE GE or BETWEEN (left out: the value must be true)"),
    Arg("ref", Raw, "", help="the value to compare with (BETWEEN: the low end)"),
    Arg("tol", Raw, "", help="tolerance for EQ/NE/LT/GT/LE/GE (BETWEEN: the high end)"),
    help=(
        "Check the model; the step fails (and says why) when the check does not hold. "
        "ASSERT, VOL(flange), BETWEEN, 81500, 82200 · ASSERT, BBOX(flange).dz, EQ, 12, 0.01 · "
        "ASSERT, HOLES(flange, 8), EQ, 6 · ASSERT, VALID(flange) · ASSERT, VOL(a) > VOL(b)"
    ),
)
def assert_(p: Processor, value, op, ref, tol):
    from ..ai import expect

    parts = [value, op, ref, tol]
    while parts and parts[-1] == "":
        parts.pop()
    text = ", ".join(parts)
    try:
        out = expect.check(p, text)
    except expect.ExpectError as exc:
        raise CommandError(f"ASSERT: {exc}") from None
    if not out.passed:
        raise CommandError(f"ASSERT failed: {out.sentence()}")
    return out.sentence()


# ---- DESCRIBE -------------------------------------------------------------------------


@command(
    "DESCRIBE",
    Arg("what", Raw, "MODEL", help="MODEL, a body (name or ID), SEL, or FACE / EDGE / VERTEX"),
    Arg("detail", Raw, "", help="for a body: SUMMARY, FACES or EDGES; for FACE/EDGE/VERTEX: the ID"),
    Arg("fmt", str, "TEXT", help="TEXT or JSON"),
    logged=False,
    help=(
        "Describe the model in words and numbers: DESCRIBE (every body, parameter, datum) · "
        "DESCRIBE, flange (size, faces by type, holes) · DESCRIBE, flange, FACES · DESCRIBE, FACE, 12 · "
        "DESCRIBE, SEL (what is selected) · add JSON for the exact data the AI assistant reads"
    ),
)
def describe(p: Processor, what, detail, fmt):
    from ..ai import describe as ds

    if fmt not in ("TEXT", "JSON"):
        raise CommandError("DESCRIBE: the format is TEXT or JSON")
    word = what.strip().upper()
    if word in ("JSON", "TEXT") and detail == "":  # DESCRIBE, JSON
        word, fmt = "MODEL", word
    if detail.strip().upper() in ("JSON", "TEXT"):  # DESCRIBE, flange, JSON
        detail, fmt = "", detail.strip().upper()
    try:
        if word == "MODEL":
            data = ds.model_summary(p)
        elif word == "SEL":
            m = p.model
            if not m.selection:
                raise CommandError("DESCRIBE, SEL: nothing is selected")
            data = ds.describe_entities(p, m.selection_kind, list(m.selection))
        elif word in ENTITY_KINDS or word in ("FACES", "EDGES", "VERTICES"):
            kind = {"FACES": "FACE", "EDGES": "EDGE", "VERTICES": "VERTEX"}.get(word, word)
            if not detail.strip():
                raise CommandError(f"DESCRIBE, {kind}, id: give the ID")
            ids = [int(_whole(p, s)) for s in detail.split()]
            data = ds.describe_entities(p, kind, ids)
        else:
            level = (detail.strip() or "SUMMARY").lower()
            data = ds.describe_body(p, what.strip(), level)
    except ds.DescribeError as exc:
        raise CommandError(f"DESCRIBE: {exc}") from None
    if fmt == "JSON":
        return json.dumps(data, separators=(",", ":"))
    return as_text(data)


def _whole(p: Processor, s: str) -> int:
    try:
        v = p.evaluate(s)
    except ExprError as exc:
        raise CommandError(f"DESCRIBE: {exc}") from None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not float(v).is_integer():
        raise CommandError("DESCRIBE: an ID is a whole number")
    return int(v)


def _short(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:g}"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, list):
        if all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v):
            return "(" + ", ".join(_short(x) for x in v) + ")"
        return "[" + ", ".join(_short(x) for x in v) + "]"
    if isinstance(v, dict):
        return " ".join(f"{k} {_short(x)}" for k, x in v.items())
    return str(v)


def as_text(d: dict[str, Any], indent: str = "") -> str:
    """Readable lines for the command line: one key per line, one row per list item."""
    lines = []
    for k, v in d.items():
        if k in ("rev",):
            continue
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            lines.append(f"{indent}{k}:")
            for row in v:
                lines.append(f"{indent}  " + _short(row))
        elif isinstance(v, dict) and v and any(isinstance(x, dict) for x in v.values()):
            lines.append(f"{indent}{k}:")
            lines.append(as_text(v, indent + "  "))
        else:
            lines.append(f"{indent}{k}: {_short(v)}")
    return "\n".join(lines)


# ---- SELFOR ---------------------------------------------------------------------------


@command(
    "SELFOR",
    Arg("kind", str, "", help="BODY, FACE, EDGE or VERTEX (left out: the selection)"),
    Arg("id", int, 0, help="the entity's ID"),
    logged=False,
    help=(
        "The SEL lines that pick exactly this entity by what it is (normal, place, type, size) rather than by "
        "its ID, so a script keeps working when earlier steps change: SELFOR, FACE, 12 · SELFOR (the selection)"
    ),
)
def selfor(p: Processor, kind, id):
    from ..ai import selectors as sl

    m = p.model
    if not kind:
        if len(m.selection) != 1:
            raise CommandError("SELFOR: select one thing first, or give it: SELFOR, FACE, 12")
        kind, id = m.selection_kind, m.selection[0]
    try:
        out = sl.selector_for(p, check_kind(kind), id)
    except (sl.SelectorError, ModelError) as exc:
        raise CommandError(f"SELFOR: {exc}") from None
    lines = list(out["lines"])
    if not out["unique"]:
        lines.append(f"! {out['note']}: {', '.join(map(str, out['look_alikes']))}")
    return "\n".join(lines)


# ---- LINT -----------------------------------------------------------------------------


@command(
    "LINT",
    Arg("file", Path, "", help="a script file; left out: the current history"),
    logged=False,
    help=(
        "Check a script without running it: syntax, unknown commands, argument counts, names used before they "
        "are set, raw IDs that may move: LINT, \"bracket.cmd\" · LINT (the history as it is)"
    ),
)
def lint(p: Processor, file):
    from ..ai import lint as ln

    if file:
        try:
            with open(file, encoding="utf-8") as f:
                text = f.read()
        except OSError as exc:
            raise CommandError(f"LINT: cannot read {file}: {exc.strerror}") from None
        fresh = Processor()
        fresh.overrides = dict(p.overrides)
        out = ln.lint(fresh, text)
    else:
        out = ln.lint(Processor(), p.script())
    if not out["issues"]:
        return "no problems found"
    return "\n".join(f"line {i['line']}: {i['level']}: {i['msg']}" for i in out["issues"])


# ---- DIFF -----------------------------------------------------------------------------


@command(
    "DIFF",
    Arg("first", int, -1, help="history position to compare from (0 = the empty start); default: one step back"),
    Arg("last", int, -1, help="history position to compare to; default: now"),
    Arg("fmt", str, "TEXT", help="TEXT or JSON"),
    logged=False,
    help=(
        "What changed between two points of the history: bodies made, removed and changed (volume, faces), "
        "parameters, datums, sketches. DIFF (the last step) · DIFF, 3 (since entry 3) · DIFF, 0, 5 · DIFF, 3, 7, JSON"
    ),
)
def diff(p: Processor, first, last, fmt):
    from ..ai import diff as df

    last = p.cursor if last < 0 else last
    first = max(0, last - 1) if first < 0 else first
    try:
        d = df.diff_entries(p, first, last)
    except ValueError as exc:
        raise CommandError(f"DIFF: {exc}") from None
    if fmt == "JSON":
        return json.dumps(d, separators=(",", ":"))
    head = f"from {'the start' if first == 0 else f'entry {first}'} to {'now' if last == p.cursor else f'entry {last}'}:"
    return head + "\n" + df.diff_text(d)
