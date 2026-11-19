"""Tolerance stack-ups (STACKUP) and geometric tolerance frames (NOTE, GDT).

A stack-up is a chain of sizes, each added or taken away, that closes on a
gap. Each link has a nominal size and limits (plus/minus, upper/lower, or an
ISO 286 tolerance such as H7 or g6). The worst case adds the limits up; the
statistical range (root sum square) takes each link's band as centred and
adds the half-widths as squares, which is what many parts made in a steady
process give.

Frames: the kind of tolerance, its size (a diameter zone with a leading
``ø``) and up to three datum letters. The view shows the frame as text with
the usual symbols; drawings draw the boxes and the symbols as lines, since
the sheet fonts have no symbols.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from . import fits as ft


class ToleranceError(ValueError):
    pass


# ---- stack-ups -----------------------------------------------------------------------------

@dataclass
class Link:
    text: str  # as given
    sign: int  # +1 adds to the gap, -1 takes away
    nominal: float
    upper: float  # deviations, mm
    lower: float

    @property
    def half(self) -> float:
        return (self.upper - self.lower) / 2

    @property
    def middle(self) -> float:
        return self.nominal + (self.upper + self.lower) / 2


_LINK = re.compile(
    r"^\s*(?P<sign>[+-])?\s*(?P<size>.+?)\s*"
    r"(?:(?:±|\+/-|\+-)\s*(?P<pm>[0-9.eE+-]+)"
    r"|(?P<up>[+-][0-9.eE]+)\s*/\s*(?P<lo>[+-]?[0-9.eE]+)"
    r"|(?P<iso>(?:js|JS|[a-zA-Z])\d{1,2}))?\s*$"
)


def parse_link(text: str, evaluate) -> Link:
    """'+25 ±0.1', '-24.9 +0.1/-0.05', '+25 H7', '-25 g6', '+W ±0.1' (a parameter), '+(A1) ±0.1'."""
    m = _LINK.match(text)
    if not m or not m.group("size"):
        raise ToleranceError(f"{text!r} is not a size like +25 ±0.1, -24.9 +0.1/-0.05 or +25 H7")
    sign = -1 if m.group("sign") == "-" else 1
    try:
        nominal = float(evaluate(m.group("size")))
    except Exception:
        raise ToleranceError(f"{m.group('size')!r} in {text!r} is not a number or a parameter") from None
    if m.group("pm") is not None:
        t = abs(float(m.group("pm")))
        up, lo = t, -t
    elif m.group("up") is not None:
        up, lo = float(m.group("up")), float(m.group("lo"))
    elif m.group("iso") is not None:
        try:
            lim = ft.limits(m.group("iso"), abs(nominal))
        except ft.FitError as exc:
            raise ToleranceError(str(exc)) from None
        up, lo = lim.upper / 1000, lim.lower / 1000
    else:
        up = lo = 0.0
    if lo > up:
        up, lo = lo, up
    return Link(text.strip(), sign, nominal, up, lo)


@dataclass
class Stack:
    links: list[Link]

    @property
    def nominal(self) -> float:
        return sum(k.sign * k.nominal for k in self.links)

    @property
    def worst(self) -> tuple[float, float]:
        lo = sum(k.sign * k.nominal + (k.lower if k.sign > 0 else -k.upper) for k in self.links)
        hi = sum(k.sign * k.nominal + (k.upper if k.sign > 0 else -k.lower) for k in self.links)
        return lo, hi

    @property
    def middle(self) -> float:
        return sum(k.sign * k.middle for k in self.links)

    @property
    def rss(self) -> tuple[float, float]:
        h = math.sqrt(sum(k.half ** 2 for k in self.links))
        return self.middle - h, self.middle + h

    def shares(self) -> list[float]:
        """Each link's share of the statistical spread, in percent."""
        total = sum(k.half ** 2 for k in self.links)
        return [100.0 * k.half ** 2 / total if total else 0.0 for k in self.links]


# ---- geometric tolerance frames ------------------------------------------------------------

_ARC = [(0.4 * math.cos(math.pi * i / 12), 0.4 * math.sin(math.pi * i / 12) - 0.15) for i in range(13)]


def _circle(r: float, cx: float = 0.0, cy: float = 0.0, n: int = 24) -> list:
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n + 1)]


# name: (view text, needs a datum (True), may not have one (False) or either (None), strokes in a unit box)
GDT = {
    "STRAIGHTNESS": ("⏤", False, [[(-0.4, 0.0), (0.4, 0.0)]]),
    "FLATNESS": ("⏥", False, [[(-0.45, -0.2), (0.25, -0.2), (0.45, 0.2), (-0.25, 0.2), (-0.45, -0.2)]]),
    "CIRCULARITY": ("○", False, [_circle(0.35)]),
    "CYLINDRICITY": ("⌭", False, [_circle(0.25), [(-0.45, -0.4), (-0.1, 0.4)], [(0.1, -0.4), (0.45, 0.4)]]),
    "LINEPROFILE": ("⌒", None, [_ARC]),
    "PROFILE": ("⌓", None, [_ARC + [_ARC[0]]]),
    "PARALLELISM": ("∥", True, [[(-0.35, -0.4), (-0.05, 0.4)], [(0.05, -0.4), (0.35, 0.4)]]),
    "PERPENDICULARITY": ("⟂", True, [[(-0.4, -0.35), (0.4, -0.35)], [(0.0, -0.35), (0.0, 0.4)]]),
    "ANGULARITY": ("∠", True, [[(0.4, 0.35), (-0.4, -0.35), (0.45, -0.35)]]),
    "POSITION": ("⌖", None, [_circle(0.28), [(-0.45, 0.0), (0.45, 0.0)], [(0.0, -0.45), (0.0, 0.45)]]),
    "CONCENTRICITY": ("◎", True, [_circle(0.2), _circle(0.38)]),
    "SYMMETRY": ("⌯", True, [[(-0.45, 0.0), (0.45, 0.0)], [(-0.28, 0.25), (0.28, 0.25)],
                                  [(-0.28, -0.25), (0.28, -0.25)]]),
    "RUNOUT": ("↗", True, [[(-0.3, -0.4), (0.3, 0.4)], [(0.02, 0.33), (0.3, 0.4), (0.28, 0.12)]]),
    "TOTALRUNOUT": ("⌰", True, [[(-0.45, -0.4), (0.25, -0.4)], [(-0.4, -0.4), (0.0, 0.4)],
                                     [(-0.12, 0.3), (0.0, 0.4), (0.02, 0.24)], [(-0.05, -0.4), (0.35, 0.4)],
                                     [(0.23, 0.3), (0.35, 0.4), (0.37, 0.24)]]),
}
ALIASES = {"POS": "POSITION", "PERP": "PERPENDICULARITY", "PARALLEL": "PARALLELISM", "FLAT": "FLATNESS",
           "ROUND": "CIRCULARITY", "ROUNDNESS": "CIRCULARITY", "CYL": "CYLINDRICITY", "ANGLE": "ANGULARITY",
           "STRAIGHT": "STRAIGHTNESS", "SURFACEPROFILE": "PROFILE", "CONCENTRIC": "CONCENTRICITY",
           "TOTAL": "TOTALRUNOUT"}
DIA = "ø"


@dataclass(frozen=True)
class Frame:
    kind: str  # a GDT name, or DATUM
    tol: str = ""  # e.g. "ø0.1" (DATUM: the letter)
    datums: tuple[str, ...] = ()

    def cells(self) -> list[str]:
        """The texts of the boxes after the symbol box."""
        return [self.tol] if self.kind == "DATUM" else [self.tol, *self.datums]

    def text(self) -> str:
        if self.kind == "DATUM":
            return f"[{self.tol}]"
        return " | ".join([GDT[self.kind][0], *self.cells()])


def frame(kind: str, tol: str, datums: list[str]) -> tuple[Frame, list[str]]:
    """A checked frame, and warnings about it."""
    key = ALIASES.get(kind.strip().upper(), kind.strip().upper())
    if key not in GDT:
        raise ToleranceError(f"{kind!r} is not a geometric tolerance; use one of {', '.join(GDT)}")
    t = tol.strip().replace(" ", "")
    dia = t[:1].upper() == "D" or t[:1] in ("ø", "⌀", "Ø")
    num = t[1:] if dia else t
    try:
        v = float(num)
    except ValueError:
        raise ToleranceError(f"the tolerance must be a number (ø0.1 or D0.1 for a round zone), got {tol!r}") \
            from None
    if v <= 0:
        raise ToleranceError("the tolerance must be more than 0")
    letters = [d.strip().upper() for d in datums if d.strip()]
    if len(letters) > 3:
        raise ToleranceError("a frame has at most three datums")
    bad = [d for d in letters if not re.fullmatch(r"[A-Z]{1,2}", d) or d in ("I", "O", "Q")]
    if bad:
        raise ToleranceError(f"datum letters are A to Z (not I, O or Q): {bad[0]!r}")
    warn = []
    needs = GDT[key][1]
    if needs is True and not letters:
        warn.append(f"{key.lower()} is measured from a datum: give one (A)")
    if needs is False and letters:
        raise ToleranceError(f"{key.lower()} is a form tolerance and takes no datum")
    zone = (DIA if dia else "") + f"{v:g}"
    return Frame(key, zone, tuple(letters)), warn


def datum(letter: str) -> Frame:
    d = letter.strip().upper()
    if not re.fullmatch(r"[A-Z]{1,2}", d) or d in ("I", "O", "Q"):
        raise ToleranceError(f"a datum letter is A to Z (not I, O or Q), got {letter!r}")
    return Frame("DATUM", d)


def _widths(fr: Frame, h: float) -> list[float]:
    tall = 1.7 * h
    widths = [] if fr.kind == "DATUM" else [tall]
    return widths + [max(tall, 0.62 * h * len(c) + 0.8 * h) for c in fr.cells()]


def frame_size(fr: Frame, h: float) -> tuple[float, float]:
    """The width and height of a frame drawn with text height h."""
    return sum(_widths(fr, h)), 1.7 * h


def frame_lines(fr: Frame, x: float, y: float, h: float) -> tuple[list, list]:
    """A frame drawn at (x, y) (its middle) with text height h: (polylines, [(x, y, text), ...])."""
    tall = 1.7 * h
    widths = _widths(fr, h)
    total = sum(widths)
    left, bottom, top = x - total / 2, y - tall / 2, y + tall / 2
    lines = [[(left, bottom), (left + total, bottom), (left + total, top), (left, top), (left, bottom)]]
    texts = []
    cx = left
    for i, w in enumerate(widths):
        if i:
            lines.append([(cx, bottom), (cx, top)])
        mid = cx + w / 2
        if i == 0 and fr.kind != "DATUM":
            s = 0.7 * tall
            for stroke in GDT[fr.kind][2]:
                lines.append([(mid + s * u, y + s * v) for u, v in stroke])
        else:
            texts.append((mid, y, fr.cells()[i - (0 if fr.kind == "DATUM" else 1)]))
        cx += w
    return lines, texts
