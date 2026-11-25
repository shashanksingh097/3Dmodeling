"""View directions by name (PLAN item 93): the words VIEW takes and the view cube writes.

A view is named by the sides the eye looks from: ``TOP``, ``TOP FRONT`` (an edge
of the view cube), ``TOP FRONT RIGHT`` (a corner, the same as ``ISO``). ``turned``
turns a view by 90 degrees, as the arrows beside the cube do.
"""

from __future__ import annotations

import math

# where the eye is, as a direction from the model
WORDS = {"TOP": (0, 0, 1), "BOTTOM": (0, 0, -1), "FRONT": (0, -1, 0), "BACK": (0, 1, 0),
         "LEFT": (-1, 0, 0), "RIGHT": (1, 0, 0)}
ORDER = ("TOP", "BOTTOM", "FRONT", "BACK", "LEFT", "RIGHT")
NAMED = {"ISO": "TOP FRONT RIGHT"}
TURNS = ("LEFT", "RIGHT", "UP", "DOWN", "CW", "CCW")
_AXIS = {"X": ("RIGHT", "LEFT"), "Y": ("BACK", "FRONT"), "Z": ("TOP", "BOTTOM")}


def canonical(name: str) -> str:
    """ "front-top" -> "TOP FRONT"; "" when it is not a view."""
    n = name.strip().upper().replace("-", " ").replace("_", " ")
    n = NAMED.get(n, n)
    words = n.split()
    if direction(" ".join(words)) is None:
        return ""
    return " ".join(sorted(words, key=ORDER.index))


def direction(name: str) -> tuple[float, float, float] | None:
    """ "TOP FRONT RIGHT" -> (1, -1, 1); None when a word is not a side, or two are opposite."""
    words = NAMED.get(name.strip().upper(), name.strip().upper()).replace("-", " ").replace("_", " ").split()
    if not words or len(set(words)) != len(words):
        return None
    v = [0, 0, 0]
    for w in words:
        if w not in WORDS:
            return None
        for i, c in enumerate(WORDS[w]):
            if c and v[i]:
                return None
            v[i] += c
    return (float(v[0]), float(v[1]), float(v[2]))


def up_for(d: tuple[float, float, float]) -> tuple[float, float, float]:
    """Z up, except looking straight down or up, where Y (back) is up on the screen."""
    if abs(d[0]) < 1e-9 and abs(d[1]) < 1e-9:
        return (0.0, 1.0, 0.0) if d[2] > 0 else (0.0, -1.0, 0.0)
    return (0.0, 0.0, 1.0)


def name_of(orientation) -> str:
    """OCCT's V3d_XposYnegZpos -> "TOP FRONT RIGHT"."""
    text = str(getattr(orientation, "name", orientation)).split(".")[-1].replace("V3d_", "")
    words, i = [], 0
    while i < len(text):
        axis, sign = text[i], text[i + 1:i + 4]
        if axis in _AXIS and sign in ("pos", "neg"):
            words.append(_AXIS[axis][0 if sign == "pos" else 1])
            i += 4
        else:
            i += 1
    return " ".join(sorted(words, key=ORDER.index))


def _rot(v, axis, deg):
    """v turned by deg about the unit axis (right hand)."""
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    kx, ky, kz = axis
    x, y, z = v
    dot = kx * x + ky * y + kz * z
    cx, cy, cz = ky * z - kz * y, kz * x - kx * z, kx * y - ky * x
    return tuple(round(vi * c + ci * s + ki * dot * (1 - c), 12) + 0.0
                 for vi, ci, ki in zip((x, y, z), (cx, cy, cz), (kx, ky, kz)))


def _unit(v):
    n = math.sqrt(sum(c * c for c in v)) or 1.0
    return tuple(c / n for c in v)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def turned(eye, up, how: str):
    """(eye, up) after a 90 degree turn: LEFT/RIGHT about the screen's up, UP/DOWN about
    its horizontal, CW/CCW (a roll) about the line of sight. eye points from the model
    to the eye; LEFT brings what is on the left of the screen to the front."""
    eye, up = _unit(eye), _unit(up)
    right = _unit(_cross(up, eye))  # the screen's right, seen from the eye
    how = how.upper()
    if how == "LEFT":
        return _rot(eye, up, 90), up
    if how == "RIGHT":
        return _rot(eye, up, -90), up
    if how == "UP":  # look from further up: the top comes towards you
        return _rot(eye, right, -90), _rot(up, right, -90)
    if how == "DOWN":
        return _rot(eye, right, 90), _rot(up, right, 90)
    if how == "CW":
        return eye, _rot(up, eye, -90)
    if how == "CCW":
        return eye, _rot(up, eye, 90)
    raise ValueError(how)


def nearest_name(eye, tol: float = 1e-4) -> str:
    """The view's name when the eye looks from a face, edge or corner direction, else ""."""
    e = _unit(eye)
    best = ""
    for x in (-1, 0, 1):
        for y in (-1, 0, 1):
            for z in (-1, 0, 1):
                if (x, y, z) == (0, 0, 0):
                    continue
                u = _unit((x, y, z))
                if sum(a * b for a, b in zip(u, e)) > 1 - tol:
                    words = [w for w, d in WORDS.items() if any(c and c == dc for c, dc in zip((x, y, z), d))]
                    best = " ".join(sorted(words, key=ORDER.index))
    return best
