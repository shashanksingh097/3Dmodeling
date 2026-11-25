"""Numbers with units (PLAN item 92).

Any number in a command, a form field or a parameter may carry a unit:
``25 mm``, ``1/4 in``, ``0.5 m``, ``2 ft``, ``30 deg``, ``1.2 rad``. ``expand``
turns them into ordinary expressions before they are read: a length becomes
``(value * INCH)``, where INCH, MM, CM and METER are the processor's unit
constants (how long one of them is in the project's units), so ``1 in`` in a
millimetre project is 25.4. Angles are in degrees, so ``deg`` is 1 and ``rad``
is 180/pi. Text inside quotes is left alone.

``/UNITS, IN, SHOW`` sets the units numbers are shown in (the status bar, the
Properties panel, SELINFO) without changing the model; ``scale_info`` converts
a selinfo answer to them.
"""

from __future__ import annotations

import math
import re
from typing import Any

# unit word -> the expression it multiplies by
LENGTH_WORDS = {"mm": "MM", "cm": "CM", "m": "METER", "in": "INCH", "inch": "INCH", "inches": "INCH",
                "ft": "(12*INCH)", "feet": "(12*INCH)", "foot": "(12*INCH)"}
ANGLE_WORDS = {"deg": "1", "degree": "1", "degrees": "1", "°": "1", "rad": f"({180 / math.pi!r})"}
WORDS = {**LENGTH_WORDS, **ANGLE_WORDS}

# millimetres in one of each project unit (core/model.py UNITS) and in each shown unit
MM_PER = {"MM": 1.0, "CM": 10.0, "M": 1000.0, "IN": 25.4, "FT": 304.8}

_NUM = r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
_UNIT_RE = re.compile(
    rf"(?<![\w.])({_NUM}(?:\s*/\s*{_NUM})?)\s*(°|(?:inches|inch|in|feet|foot|ft|mm|cm|m|degrees|degree|deg|rad)(?![\w]))",
    re.I)


def has_unit(text: str) -> bool:
    return any(_UNIT_RE.search(seg) for seg in _outside_quotes(text or ""))


def _outside_quotes(text: str) -> list[str]:
    return [seg for i, seg in enumerate(re.split(r'("[^"]*"|\'[^\']*\')', text)) if i % 2 == 0]


_PAREN_RE = re.compile(r"\)\s*(°|(?:inches|inch|in|feet|foot|ft|mm|cm|m|degrees|degree|deg|rad)(?![\w]))", re.I)


def expand(text: str) -> str:
    """``25 mm + 2`` -> ``(25*MM) + 2``; ``1/4 in`` -> ``((1/4)*INCH)``; ``(W/4) in`` ->
    ``((W/4)*INCH)``; text in quotes is kept."""
    if not text or not (_UNIT_RE.search(text) or _PAREN_RE.search(text)):
        return text
    parts = re.split(r'("[^"]*"|\'[^\']*\')', text)
    out = []
    for i, seg in enumerate(parts):
        if i % 2 == 0:
            seg = _parens(_UNIT_RE.sub(lambda m, s=seg: _one(m, s), seg))
        out.append(seg)
    return "".join(out)


def _parens(seg: str) -> str:
    """``(expr) unit`` -> ``((expr)*UNIT)``."""
    while True:
        m = _PAREN_RE.search(seg)
        if not m:
            return seg
        depth, j = 0, m.start()
        while j >= 0:
            depth += {")": 1, "(": -1}.get(seg[j], 0)
            if depth == 0:
                break
            j -= 1
        if j < 0:
            return seg  # unbalanced: leave it to fail
        while j > 0 and (seg[j - 1].isalnum() or seg[j - 1] in "_."):
            j -= 1  # MAX(a, b) in: the call, not only its brackets
        seg = seg[:j] + "(" + seg[j:m.start() + 1] + "*" + WORDS[m.group(1).lower()] + ")" + seg[m.end():]


def _one(m: re.Match, seg: str) -> str:
    before = seg[: m.start()].rstrip()
    if before.endswith("/"):
        return m.group(0)  # W/4 in: unclear, leave it to fail
    num, word = m.group(1), m.group(2).lower()
    if "/" in num:
        num = f"({num.replace(' ', '')})"
    return f"({num}*{WORDS[word]})"


def unit_name(units: str) -> str:
    return {"MM": "millimetres", "CM": "centimetres", "M": "metres", "IN": "inches", "FT": "feet"}.get(
        units.upper(), units.lower())


def unit_label(units: str) -> str:
    return {"MM": "mm", "CM": "cm", "M": "m", "IN": "in", "FT": "ft"}.get(units.upper(), units.lower())


def factor(model_units: str, shown: str) -> float:
    """Multiply a length in the model's units by this to get it in the shown units."""
    return MM_PER[model_units.upper()] / MM_PER[shown.upper()]


_LEN = {"size", "centre", "length", "r", "d", "distance", "from", "to", "dx", "dy", "dz", "at", "ends",
        "cdx", "cdy", "cdz", "centres", "centre_distance", "cdistance", "x", "y", "z"}
_AREA = {"area"}
_VOL = {"volume"}


def _scale(v: Any, k: float) -> Any:
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return round(v * k, 6) + 0.0
    if isinstance(v, (list, tuple)):
        return [_scale(x, k) for x in v]
    return v


def scale_info(d: Any, k: float) -> Any:
    """A selinfo answer (dict/list) with lengths times k, areas k², volumes k³."""
    if k == 1.0:
        return d
    if isinstance(d, list):
        return [scale_info(x, k) for x in d]
    if not isinstance(d, dict):
        return d
    out = {}
    for key, v in d.items():
        if key in _LEN:
            out[key] = _scale(v, k)
        elif key in _AREA:
            out[key] = _scale(v, k * k)
        elif key in _VOL:
            out[key] = _scale(v, k ** 3)
        elif isinstance(v, (dict, list)):
            out[key] = scale_info(v, k)
        else:
            out[key] = v
    return out
