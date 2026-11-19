"""ISO 286 limits and fits for holes and shafts (FITS): the standard
tolerance grades IT5 to IT13 and the fundamental deviations of the common
hole and shaft letters, from the tables of ISO 286, for sizes over 0 up to
500 mm (the main size ranges; for the letters here the intermediate ranges
give the same values).

Letters: holes D E F G H JS K M N P, shafts d e f g h js k m n p. A hole's
deviations mirror the shaft letter's, with the delta rule (add
IT(n) - IT(n-1)) for K, M and N up to IT8 and P up to IT7.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

RANGES = (0, 3, 6, 10, 18, 30, 50, 80, 120, 180, 250, 315, 400, 500)
IT = {  # micrometres, by size range
    5: (4, 5, 6, 8, 9, 11, 13, 15, 18, 20, 23, 25, 27),
    6: (6, 8, 9, 11, 13, 16, 19, 22, 25, 29, 32, 36, 40),
    7: (10, 12, 15, 18, 21, 25, 30, 35, 40, 46, 52, 57, 63),
    8: (14, 18, 22, 27, 33, 39, 46, 54, 63, 72, 81, 89, 97),
    9: (25, 30, 36, 43, 52, 62, 74, 87, 100, 115, 130, 140, 155),
    10: (40, 48, 58, 70, 84, 100, 120, 140, 160, 185, 210, 230, 250),
    11: (60, 75, 90, 110, 130, 160, 190, 220, 250, 290, 320, 360, 400),
    12: (100, 120, 150, 180, 210, 250, 300, 350, 400, 460, 520, 570, 630),
    13: (140, 180, 220, 270, 330, 390, 460, 540, 630, 720, 810, 890, 970),
}
# shaft fundamental deviations, micrometres: es for d to h, ei for k to p
FD = {
    "d": ("es", (-20, -30, -40, -50, -65, -80, -100, -120, -145, -170, -190, -210, -230)),
    "e": ("es", (-14, -20, -25, -32, -40, -50, -60, -72, -85, -100, -110, -125, -135)),
    "f": ("es", (-6, -10, -13, -16, -20, -25, -30, -36, -43, -50, -56, -62, -68)),
    "g": ("es", (-2, -4, -5, -6, -7, -9, -10, -12, -14, -15, -17, -18, -20)),
    "h": ("es", (0,) * 13),
    "k": ("ei", (0, 1, 1, 1, 2, 2, 2, 3, 3, 4, 4, 4, 5)),  # IT4 to IT7; 0 for the other grades
    "m": ("ei", (2, 4, 6, 7, 8, 9, 11, 13, 15, 17, 20, 21, 23)),
    "n": ("ei", (4, 8, 10, 12, 15, 17, 20, 23, 27, 31, 34, 37, 40)),
    "p": ("ei", (6, 12, 15, 18, 22, 26, 32, 37, 43, 50, 56, 62, 68)),
}
SHAFTS = ("d", "e", "f", "g", "h", "js", "k", "m", "n", "p")
HOLES = tuple(x.upper() for x in SHAFTS)


class FitError(ValueError):
    pass


def _range(size: float) -> int:
    if not 0 < size <= 500:
        raise FitError("ISO 286 fits here cover sizes over 0 up to 500 mm")
    for k in range(len(RANGES) - 1):
        if size <= RANGES[k + 1]:
            return k
    raise FitError("size out of range")


def it(size: float, grade: int) -> float:
    """The tolerance of an IT grade, in micrometres."""
    if grade not in IT:
        raise FitError(f"IT{grade} is not covered; grades are IT5 to IT13")
    return float(IT[grade][_range(size)])


def _shaft_fd(letter: str, size: float, grade: int) -> tuple[str, float]:
    """A shaft's fundamental deviation: ("es" or "ei", micrometres)."""
    if letter not in FD:
        raise FitError(f"shaft letter {letter} is not covered; use one of {' '.join(SHAFTS)}")
    which, row = FD[letter]
    v = float(row[_range(size)])
    if letter == "k" and not 4 <= grade <= 7:
        v = 0.0
    return which, v


@dataclass
class Limits:
    name: str  # e.g. "H7"
    hole: bool
    upper: float  # deviations in micrometres
    lower: float

    def text(self) -> str:
        def f(v):
            return "0" if v == 0 else f"{v / 1000:+.3f}"

        return f"{f(self.upper)}/{f(self.lower)}"


def _split(spec: str) -> tuple[str, int]:
    m = re.fullmatch(r"\s*(js|JS|[a-zA-Z])\s*(\d{1,2})\s*", spec)
    if not m:
        raise FitError(f"{spec!r} is not a tolerance like H7 or g6")
    return m.group(1), int(m.group(2))


def limits(spec: str, size: float) -> Limits:
    """The limits of one tolerance (H7 for a hole, g6 for a shaft: capitals are holes)."""
    letter, grade = _split(spec)
    t = it(size, grade)
    hole = letter[0].isupper()
    low = letter.lower()
    if low == "js":
        return Limits(f"{letter}{grade}", hole, t / 2, -t / 2)
    if low not in SHAFTS:
        raise FitError(f"{letter} is not covered; holes {' '.join(HOLES)}, shafts {' '.join(SHAFTS)}")
    if not hole:
        which, v = _shaft_fd(low, size, grade)
        return Limits(f"{letter}{grade}", False, v, v - t) if which == "es" else Limits(f"{letter}{grade}",
                                                                                       False, v + t, v)
    # holes: the mirror of the shaft letter, with the delta rule for K to P in the fine grades
    if low in ("d", "e", "f", "g", "h"):
        _w, es = _shaft_fd(low, size, grade)
        return Limits(f"{letter}{grade}", True, -es + t, -es)
    _w, ei = _shaft_fd(low, size, grade)
    delta = it(size, grade) - it(size, grade - 1) if grade - 1 in IT else 0.0
    if low in ("k", "m", "n") and grade <= 8 or low == "p" and grade <= 7:
        es = -ei + delta
    elif low == "k" or low == "n":
        es = 0.0
    else:
        es = -ei
    return Limits(f"{letter}{grade}", True, es, es - t)


@dataclass
class Fit:
    hole: Limits
    shaft: Limits
    size: float

    @property
    def most(self) -> float:  # the largest clearance (negative: interference), micrometres
        return self.hole.upper - self.shaft.lower

    @property
    def least(self) -> float:
        return self.hole.lower - self.shaft.upper

    def kind(self) -> str:
        if self.least >= 0:
            return "clearance"
        if self.most <= 0:
            return "interference"
        return "transition"


def fit(spec: str, size: float) -> Fit | Limits:
    """'H7/g6' gives a Fit; 'H7' or 'g6' alone gives that part's Limits."""
    if "/" in spec:
        a, b = (q.strip() for q in spec.split("/", 1))
        ha, sb = limits(a, size), limits(b, size)
        if not ha.hole or sb.hole:
            raise FitError("write the hole first, in capitals, then the shaft: H7/g6")
        return Fit(ha, sb, size)
    return limits(spec, size)


def mm(v: float) -> str:
    return f"{v / 1000:.3f}"
