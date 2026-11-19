"""Every command under the headings of the command menu, with lines from the
example scripts. No Qt here, so the help browser and the user guide website
(modeler/docsite.py) share it, and headless tests can use it."""

from __future__ import annotations

import glob
import os
import re

OTHER = "Other"
# headings for commands that have no form, after the command menu's own;
# an empty tuple takes the sketch commands (S..., ENDSKETCH)
EXTRA: list[tuple[str, tuple[str, ...]]] = [
    ("Files and history", ("NEW", "OPEN", "SAVE", "RUN", "NEWPART", "OPENPART", "SAVEPART", "RELOAD",
                           "UNDO", "REDO", "HIST", "STEPS")),
    ("View and picking", ("VIEW", "FIT", "PICK", "PICKMODE", "CPOINTS", "HELP")),
    ("Inside a sketch", ()),
]
MAX_EXAMPLES = 4

_EXAMPLES: dict[str, list[tuple[str, str]]] | None = None


def _commands():
    from ..commands.processor import REGISTRY

    return REGISTRY


def groups() -> list[tuple[str, list[str]]]:
    """(heading, command names) in menu order; every registered command appears once."""
    from .forms import CATEGORIES

    reg = _commands()
    seen: set[str] = set()
    out = []
    for cat, names in CATEGORIES:
        got = [n for n in names if n in reg and n not in seen]
        seen.update(got)
        if got:
            out.append((cat, got))
    rest = sorted(n for n in reg if n not in seen)
    for cat, names in EXTRA:
        got = [n for n in rest if (n in names if names else n.startswith("S") or n == "ENDSKETCH")]
        rest = [n for n in rest if n not in got]
        if got:
            out.append((cat, got))
    if rest:
        out.append((OTHER, rest))
    return out


def heading_of(name: str) -> str:
    for cat, names in groups():
        if name in names:
            return cat
    return OTHER


def examples() -> dict[str, list[tuple[str, str]]]:
    """Command name -> [(script file, line)] from the bundled example scripts."""
    global _EXAMPLES
    if _EXAMPLES is not None:
        return _EXAMPLES

    reg = _commands()
    out: dict[str, list[tuple[str, str]]] = {}
    d = examples_dir()
    for path in sorted(glob.glob(os.path.join(d, "*.cmd"))) if d else []:
        try:
            with open(path, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        for line in lines:
            text = line.split("!")[0].rstrip()
            m = re.match(r"\s*([*/]?[A-Za-z][A-Za-z0-9_]*)\s*(,|$)", text)
            if not m:
                continue
            name = m.group(1).upper()
            if name not in reg:
                continue
            got = out.setdefault(name, [])
            if len(got) < MAX_EXAMPLES and all(t != text.strip() for _, t in got):
                got.append((os.path.basename(path), text.strip()))
    _EXAMPLES = out
    return out



def examples_dir() -> str | None:
    """Example scripts: bundled with the package, or the repository's scripts/."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for d in (os.path.join(here, "examples"), os.path.join(os.path.dirname(here), "scripts")):
        if os.path.isdir(d) and any(n.endswith(".cmd") for n in os.listdir(d)):
            return d
    return None


def signature(c) -> str:
    return ", ".join([c.name] + [x.name if x.default is None else f"[{x.name}]" for x in c.args])
