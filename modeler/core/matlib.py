"""The material library: materials every project on this computer shares.

It is one JSON file, ``materials.json`` in the app's data folder (``MODELER_MATERIALS``
names another file). Each entry is a material with its density and, where known, its
stiffness, strength, heat values and how it looks::

    {"version": 1, "materials": [
        {"name": "AL6061", "density": 2700, "E_MPa": 68900, "poisson": 0.33, "yield_MPa": 276,
         "conductivity": 167, "expansion": 23.6, "color": [0.84, 0.85, 0.88], "look": "ALUMINIUM",
         "shiny": true, "note": "6061-T6"}]}

An entry with a built-in name (STEEL ...) changes that material for every project. MATLIB
and the Materials window write the file; MATERIAL, MASSPROP, STRESS, RENDER and the drawing
read it through ``Model.materials``. A saved project keeps a copy of the library materials
its bodies use, so it opens the same on a computer without them.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import replace

from .model import MATERIALS, Material

VERSION = 1
# the JSON field names, in the order the file and the window show them, and the Material field
FIELDS = (("density", "density"), ("E_MPa", "E"), ("poisson", "nu"), ("yield_MPa", "yield_"),
          ("conductivity", "k"), ("expansion", "cte"), ("specific_heat", "cp"), ("max_temp_C", "tmax"))
# short names MATLIB, SET takes (E=70000 ...), to the JSON field
SHORT = {"DENSITY": "density", "RHO": "density", "E": "E_MPa", "YOUNG": "E_MPa", "NU": "poisson",
         "POISSON": "poisson", "YIELD": "yield_MPa", "STRENGTH": "yield_MPa", "K": "conductivity",
         "CONDUCTIVITY": "conductivity", "CTE": "expansion", "EXPANSION": "expansion", "CP": "specific_heat",
         "HEAT": "specific_heat", "TMAX": "max_temp_C", "COLOR": "color", "COLOUR": "color",
         "TRANSPARENCY": "transparency", "LOOK": "look", "SHINY": "shiny", "NOTE": "note"}
# what RENDER can draw a material as (OCCT's named materials)
LOOKS = ("STEEL", "CHROME", "ALUMINIUM", "PEWTER", "COPPER", "BRASS", "BRONZE", "GOLD", "SILVER", "PLASTIC",
         "SHINY_PLASTIC", "SATIN", "PLASTER", "STONE", "GLASS", "OBSIDIAN", "JADE", "CHARCOAL")
LIMITS = {"density": (1e-3, 1e5), "E_MPa": (1e-3, 2e6), "poisson": (0.0, 0.4999), "yield_MPa": (1e-3, 1e5),
          "conductivity": (0.0, 1e4), "expansion": (-50.0, 1e3), "specific_heat": (1.0, 1e5),
          "max_temp_C": (-273.0, 4000.0), "transparency": (0.0, 0.95)}


class LibraryError(ValueError):
    pass


def path() -> str:
    """The library file (it may not exist yet)."""
    if os.environ.get("MODELER_MATERIALS"):
        return os.environ["MODELER_MATERIALS"]
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "3Dmodeling", "materials.json")


_cache: dict = {"key": None, "mats": {}, "error": ""}


def from_dict(d: dict) -> Material:
    """One library entry to a Material; LibraryError if it does not make sense."""
    if not isinstance(d, dict):
        raise LibraryError("an entry is not an object")
    name = str(d.get("name", "")).strip().upper()
    if not name or not all(c.isalnum() or c == "_" for c in name) or name[0].isdigit():
        raise LibraryError(f"{d.get('name')!r} is not a material name (letters, digits, _)")
    vals = {}
    for key, attr in FIELDS:
        v = d.get(key)
        if v is None:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise LibraryError(f"{name}: {key} is not a number ({v!r})") from None
        lo, hi = LIMITS[key]
        if not lo <= v <= hi:
            raise LibraryError(f"{name}: {key} {v:g} is outside {lo:g} ... {hi:g}")
        vals[attr] = v
    if "density" not in vals:
        raise LibraryError(f"{name}: a density (kg/m3) is needed")
    col = d.get("color")
    if col is not None:
        try:
            col = tuple(float(c) for c in col)
        except (TypeError, ValueError):
            raise LibraryError(f"{name}: color is three numbers 0..1") from None
        if len(col) != 3 or not all(0 <= c <= 1 for c in col):
            raise LibraryError(f"{name}: color is three numbers 0..1")
    tr = float(d.get("transparency", 0) or 0)
    if not 0 <= tr <= 0.95:
        raise LibraryError(f"{name}: transparency is 0 ... 0.95")
    look = str(d.get("look", "") or "").strip().upper()
    if look and look not in LOOKS:
        raise LibraryError(f"{name}: look {look} is not one of {', '.join(LOOKS)}")
    base = MATERIALS.get(name)
    if base is not None:  # a built-in one changed: what the entry leaves out stays as built in
        return replace(base, **vals, **({"color": col} if col is not None else {}),
                       **({"transparency": tr} if "transparency" in d else {}),
                       **({"look": look, "shiny": bool(d.get("shiny", base.shiny))} if look else {}),
                       note=str(d.get("note", "") or ""))
    return Material(name, color=col, transparency=tr, look=look, shiny=bool(d.get("shiny", False)),
                    note=str(d.get("note", "") or ""), **vals)


def to_dict(mat: Material) -> dict:
    return mat.props()


def read(file: str | None = None) -> dict[str, Material]:
    """Every material in the library file, by upper-case name (empty if there is no file).
    LibraryError names what is wrong with a file that cannot be read."""
    file = file or path()
    if not os.path.isfile(file):
        return {}
    try:
        with open(file, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise LibraryError(f"the material library {file} cannot be read ({exc})") from None
    entries = data.get("materials", []) if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise LibraryError(f"the material library {file} has no list of materials")
    out: dict[str, Material] = {}
    for d in entries:
        mat = from_dict(d)
        out[mat.name] = mat
    return out


def library() -> dict[str, Material]:
    """The library as the model starts from it (cached while the file is unchanged). A broken
    file gives nothing here; :func:`problem` says why."""
    file = path()
    try:
        st = os.stat(file)
        key = (file, st.st_mtime_ns, st.st_size)
    except OSError:
        key = (file, None, None)
    if key != _cache["key"]:
        try:
            mats, err = read(file), ""
        except LibraryError as exc:
            mats, err = {}, str(exc)
        _cache.update(key=key, mats=mats, error=err)
    return dict(_cache["mats"])


def problem() -> str:
    library()
    return _cache["error"]


def write(mats: dict[str, Material], file: str | None = None) -> str:
    """Write the library (every material given, by name order); returns the file."""
    file = file or path()
    os.makedirs(os.path.dirname(os.path.abspath(file)), exist_ok=True)
    data = {"version": VERSION, "materials": [to_dict(m) for _, m in sorted(mats.items())]}
    tmp = file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, file)
    _cache["key"] = None
    return file


def put(mat: Material, file: str | None = None) -> str:
    mats = read(file)
    mats[mat.name.upper()] = mat
    return write(mats, file)


def remove(name: str, file: str | None = None) -> bool:
    mats = read(file)
    if mats.pop(name.strip().upper(), None) is None:
        return False
    write(mats, file)
    return True


def parse_values(text: str) -> dict:
    """``E=70000 yield=300 color=0.2,0.2,0.2 look=steel note="T6 bar"`` to library fields."""
    import shlex

    out: dict = {}
    try:
        words = shlex.split(text)
    except ValueError as exc:
        raise LibraryError(f"cannot read {text!r} ({exc})") from None
    for w in words:
        if "=" not in w:
            raise LibraryError(f"{w!r}: write each value as name=value (E=70000)")
        k, v = w.split("=", 1)
        key = SHORT.get(k.strip().upper()) or next((f for f, _ in FIELDS if f.upper() == k.strip().upper()), None)
        if key is None:
            raise LibraryError(f"{k!r} is not a material value; use {', '.join(sorted(set(SHORT)))}")
        v = v.strip()
        if key == "color":
            out[key] = v  # the command turns a colour name into numbers
        elif key in ("look", "note"):
            out[key] = v
        elif key == "shiny":
            out[key] = v.upper() in ("1", "YES", "TRUE", "ON", "Y")
        elif v.upper() in ("", "NONE", "-"):
            out[key] = None
        else:
            try:
                out[key] = float(v)
            except ValueError:
                raise LibraryError(f"{k}: {v!r} is not a number") from None
    return out
