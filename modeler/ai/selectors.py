"""Selectors instead of raw IDs: find a SEL criterion that picks exactly one entity,
and try SEL lines without touching the real selection.

A script that says ``SEL, S, FACE, NORMAL, 0,0,1`` then ``SEL, R, FACE, LOC,
Z, 12`` keeps working when an earlier step changes and IDs move; one that
says ``PICK, FACE, 31`` may not. ``selector_for`` gives the first kind of
line for anything a person (or the AI) pointed at.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..commands.processor import REGISTRY, CommandError
from ..core.model import ModelError, check_kind
from ..lang.expr import ExprError, fmt_num
from ..lang.script import ScriptError, parse
from ..lang.script import Cmd as _Cmd
from ..geometry import recognize as rc
from ..commands import queries

if TYPE_CHECKING:
    from ..commands.processor import Processor


class SelectorError(Exception):
    pass


def _n(v: float) -> str:
    return fmt_num(round(v, 6) + 0.0)


def _body_word(p: "Processor", bid: int) -> str:
    """How a script should name a body: its own name, or its ID."""
    b = p.model.bodies[bid]
    if b.name and b.name.lower() != f"body{bid}":
        return b.name
    return str(bid)


def _candidates(p: "Processor", kind: str, gid: int) -> list[tuple[str, list[str]]]:
    """Criteria true of this entity, most meaningful first."""
    m = p.model
    shape = m.entity_shape(kind, gid)
    out: list[tuple[str, list[str]]] = []
    if kind in ("FACE", "EDGE"):
        t = (rc.surface_type(shape) if kind == "FACE" else rc.curve_type(shape)).upper()
        from ..commands.handlers import _CURVE, _SURF

        if t in (_SURF if kind == "FACE" else _CURVE):
            out.append(("TYPE", [t]))
    if kind == "FACE":
        from ..commands.handlers import _normal

        n = _normal(shape)
        if n:
            out.append(("NORMAL", [_n(c) for c in n]))
    if kind in ("FACE", "EDGE"):
        from ..commands.handlers import _radius

        r = _radius(kind, shape)
        if r is not None:
            out.append(("RADIUS", ["EQ", _n(r)]))
    if kind != "BODY":
        c = queries.centre(kind, shape)
        for axis, v in zip("XYZ", c):
            out.append(("LOC", [axis, _n(v)]))
    if kind == "EDGE":
        out.append(("SIZE", ["EQ", _n(queries.props("EDGE", shape).Mass())]))
    if kind == "FACE":
        out.append(("SIZE", ["EQ", _n(queries.props("FACE", shape).Mass())]))
    if kind != "BODY":
        bid = m.entity_owner(kind, gid)[0]
        if len(m.bodies) > 1:
            out.append(("BODY", [_body_word(p, bid)]))
    return out


def _line(mode: str, kind: str, crit: str, vals: list[str]) -> str:
    return ", ".join(["SEL", mode, kind, crit, *vals])


def selector_for(p: "Processor", kind: str, gid: int) -> dict[str, Any]:
    """The shortest run of SEL lines (most meaningful criteria first) that
    selects exactly this entity, checked against the model."""
    try:
        kind = check_kind(kind)
        p.model.entity_shape(kind, gid)
    except ModelError as exc:
        raise SelectorError(str(exc)) from None
    if kind == "BODY":
        word = _body_word(p, gid)
        named = word != str(gid)
        return {"kind": kind, "id": gid, "unique": True, "robust": named,
                "lines": [_line("S", kind, "ID", [word])]}
    remaining: set[int] | None = None
    chosen: list[tuple[str, list[str]]] = []
    cands = _candidates(p, kind, gid)
    while cands:
        best = None
        for crit, vals in cands:
            got = set(_match(p, kind, crit, vals))
            if gid not in got:  # rounding put it outside; never use such a line
                continue
            left = got if remaining is None else remaining & got
            if best is None or len(left) < len(best[2]):
                best = (crit, vals, left)
        if best is None or (remaining is not None and len(best[2]) >= len(remaining)):
            break
        chosen.append((best[0], best[1]))
        remaining = best[2]
        cands = [c for c in cands if c[0] != best[0] or c[1] != best[1]]
        if len(remaining) == 1:
            break
    out: dict[str, Any] = {"kind": kind, "id": gid}
    if remaining is not None and len(remaining) == 1:
        out["unique"] = True
        out["robust"] = True
        out["lines"] = [_line("S" if i == 0 else "R", kind, c, v) for i, (c, v) in enumerate(chosen)]
        return out
    out["unique"] = False
    out["robust"] = False
    out["look_alikes"] = sorted((remaining or set()) - {gid})[:20]
    out["lines"] = [_line("S", kind, "ID", [str(gid)])]
    out["note"] = "no criterion tells it apart from its look-alikes; only the ID picks it"
    return out


def _match(p: "Processor", kind: str, crit: str, vals: list[str]) -> list[int]:
    from ..commands.handlers import _match as match

    return match(p, kind, crit, (vals + [""] * 6)[:6])


def preview_selection(p: "Processor", lines: list[str] | str) -> dict[str, Any]:
    """Run SEL lines on a copy of the selection: what they would select, and
    whether look-alikes make the result fragile. The model's own selection is
    left as it was."""
    if isinstance(lines, str):
        lines = [ln for ln in lines.splitlines() if ln.strip()]
    m = p.model
    saved = (m.selection_kind, list(m.selection), m.revision, m._listeners)
    m._listeners = []  # nobody hears about the trial selections
    steps = []
    try:
        for text in lines:
            try:
                stmts = parse(text)
            except ScriptError as exc:
                raise SelectorError(f"{text}: {exc}") from None
            if len(stmts) != 1 or not isinstance(stmts[0], _Cmd) or stmts[0].name not in ("SEL", "CMSEL"):
                raise SelectorError(f"only SEL and CMSEL lines can be previewed, not {text.strip()!r}")
            cmd = REGISTRY[stmts[0].name]
            try:
                values, _ = p._bind(cmd, stmts[0].args)
                cmd.fn(p, **values)
            except (CommandError, ModelError, ExprError) as exc:
                raise SelectorError(f"{text.strip()}: {exc}") from None
            steps.append(len(m.selection))
        result = {"kind": m.selection_kind, "count": len(m.selection), "ids": list(m.selection)[:200],
                  "after_each_line": steps}
    finally:
        m.selection_kind, m.selection, m.revision, m._listeners = saved
    return result
