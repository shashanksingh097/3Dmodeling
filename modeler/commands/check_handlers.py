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


# ---- PROBE, PROFILE, THICK --------------------------------------------------------------


def _nums(p: Processor, raws: list[str], n: int, what: str) -> tuple[list[float], int]:
    """n numbers from the raw arguments (a point fills three), and how many arguments they took."""
    out: list[float] = []
    used = 0
    for r in raws:
        if len(out) >= n:
            break
        used += 1
        if r.strip() == "":
            raise CommandError(f"{what}: needs {n} numbers")
        try:
            v = p.evaluate(r)
        except ExprError as exc:
            raise CommandError(f"{what}: {exc}") from None
        if isinstance(v, tuple):
            out.extend(float(c) for c in v)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out.append(float(v))
        else:
            raise CommandError(f"{what}: give numbers or points")
    if len(out) < n:
        raise CommandError(f"{what}: needs {n} numbers")
    return out[:n], used


@command(
    "PROBE",
    Arg("how", str, help="RAY or POINT"),
    *[Arg(f"v{i}", Raw, "") for i in range(1, 8)],
    logged=False,
    help=(
        "Find material without looking: PROBE, RAY, x,y,z, dx,dy,dz [, body] lists every face the ray "
        "crosses and how much material it passes through (wall thickness along a line, does a hole go "
        "through) · PROBE, POINT, x,y,z [, body] says whether the point is inside, on or outside, and the "
        "nearest face"
    ),
)
def probe(p: Processor, how, v1, v2, v3, v4, v5, v6, v7):
    from ..ai import describe as ds
    from ..ai import probe as pb

    raws = [v1, v2, v3, v4, v5, v6, v7]
    try:
        if how == "RAY":
            vals, used = _nums(p, raws, 6, "PROBE, RAY")
            body = raws[used].strip() if used < len(raws) and raws[used].strip() else None
            out = pb.probe_ray(p, vals[:3], vals[3:], body)
            lines = [f"ray from {_short(out['from'])} along {_short(out['dir'])}:"]
            for h in out["hits"]:
                lines.append(f"  {h['t']:g}: {'enters' if h.get('enters') else 'leaves'} body {h['body']} "
                             f"at face {h['face']} {_short(h['at'])}")
            for s in out["material"]:
                lines.append(f"  material of body {s['body']} from {s['from']:g} to {s['to']:g} ({s['length']:g})")
            if not out["hits"]:
                lines.append("  meets nothing")
            return "\n".join(lines)
        if how == "POINT":
            vals, used = _nums(p, raws, 3, "PROBE, POINT")
            body = raws[used].strip() if used < len(raws) and raws[used].strip() else None
            row = pb.probe_point(p, [vals], body)["points"][0]
            if "body" not in row:
                return f"{_short(row['at'])}: {row['state']}"
            where = f"face {row['face']}" if "face" in row else "the body"
            return (f"{_short(row['at'])}: {row['state']} body {row['body']}; nearest {where} at "
                    f"{_short(row['nearest'])}, distance {row['distance']:g}")
    except ds.DescribeError as exc:
        raise CommandError(f"PROBE: {exc}") from None
    raise CommandError("PROBE: use RAY or POINT")


@command(
    "PROFILE",
    Arg("b", Raw, help="the body"),
    Arg("plane", Raw, "XY", help="XY, YZ, ZX or a datum plane"),
    Arg("offset", float, 0.0, help="move the plane this far along its normal"),
    Arg("step", float, 0.0, help="for a stack of cuts: the distance between them"),
    Arg("count", int, 1, help="for a stack of cuts: how many"),
    Arg("fmt", str, "TEXT", help="TEXT or JSON"),
    logged=False,
    help=(
        "A cut through a body as text: each loop with its lines, arcs and circles, the area and centre. "
        "PROFILE, flange, XY, 6 (the cut 6 above XY) · PROFILE, flange, XY, 0, 5, 8 (a cut every 5, eight "
        "of them: reads like a scan) · PROFILE, part, mid (a datum plane)"
    ),
)
def profile(p: Processor, b, plane, offset, step, count, fmt):
    from ..ai import describe as ds
    from ..ai import probe as pb
    from .feature_handlers import plane_ref

    d = plane_ref(p, plane, "PROFILE")
    if count < 1:
        raise CommandError("PROFILE: count is at least 1")
    offsets = [offset + i * step for i in range(count)] if count > 1 or offset else None
    if count > 1 and step == 0:
        raise CommandError("PROFILE: a stack of cuts needs a step")
    try:
        out = pb.section_profile(p, b, d, offsets, plane.strip().upper())
    except ds.DescribeError as exc:
        raise CommandError(f"PROFILE: {exc}") from None
    if fmt == "JSON":
        return json.dumps(out, separators=(",", ":"))
    head = (f"body {out['body']} cut by {out['plane']['name']} (u along {_short(out['plane']['u'])}, "
            f"v along {_short(out['plane']['v'])}):")
    cuts = out.get("cuts") or [out]
    lines = [head]
    for c in cuts:
        pre = f"  at {c['offset']:g}: " if "offset" in c else "  "
        if "loops" not in c:
            lines.append(pre + "nothing (the plane misses the body)")
            continue
        if "note" in c:
            lines.append(pre + c["note"])
            pre = " " * len(pre)
        lines.append(pre + f"area {c['area']:g}, centre {_short(c['centre'])}")
        for lp in c["loops"]:
            kind = "outside" if lp["outer"] else "hole"
            body_txt = {k: v for k, v in lp.items() if k != "outer"}
            if "segments" in body_txt:
                lines.append(f"    {kind}: {len(body_txt['segments'])} segments")
                for s in body_txt["segments"]:
                    lines.append("      " + _short(s))
            else:
                lines.append(f"    {kind}: " + _short(body_txt))
    return "\n".join(lines)


@command(
    "THICK",
    Arg("b", Raw, help="the body"),
    Arg("below", float, 0.0, help="list every face whose wall is thinner than this (0: the five thinnest)"),
    logged=False,
    help=(
        "Wall thickness, measured straight into the material from points spread over every face: "
        "THICK, housing (the five thinnest places) · THICK, housing, 2 (everywhere thinner than 2). "
        "MINWALL(b) gives the thinnest in an expression: ASSERT, MINWALL(housing), GE, 2"
    ),
)
def thick(p: Processor, b, below):
    from ..ai import describe as ds
    from ..ai import probe as pb

    try:
        out = pb.wall_thickness(p, b, below)
    except ds.DescribeError as exc:
        raise CommandError(f"THICK: {exc}") from None
    if not out["thinnest"]:
        return f"body {out['body']}: " + ("no wall thinner than " + f"{below:g}" if below > 0 else "no walls found")
    lines = [f"body {out['body']}: thinnest wall {out['min']:g}"]
    for r in out["thinnest"]:
        lines.append(f"  {r['t']:g} from face {r['face']} at {_short(r['at'])} to face {r['to_face']} "
                     f"at {_short(r['to'])}")
    return "\n".join(lines)
