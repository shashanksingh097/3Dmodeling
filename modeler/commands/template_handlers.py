"""Project templates (PLAN item 88): NEW, template and TEMPLATE.

A template is a command script whose steps a new project starts with: the
units, layers, materials, parameters, the title block's properties, a first
sketch. Its first comment lines say what it is::

    ! template: sheet_metal
    ! title: New sheet metal part
    ! about: A bent sheet part in millimetres: ...
    ! order: 3

The built-in ones live in ``modeler/templates``; the user's own are saved by
``TEMPLATE, SAVE, name`` into the per-user app data folder (``MODELER_TEMPLATES``
overrides it). A user template with the name of a built-in one is used
instead of it. ``NEW, part`` starts a new project from one: the session is
cleared and the template's steps become the first history entries, so each
can be changed later like any step.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any

from .processor import Arg, CommandError, Processor, Text, command

BUILTIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
EXT = ".cmd"
_HEAD = re.compile(r"^\s*!\s*(template|title|about|order)\s*:\s*(.*?)\s*$", re.I)
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]{0,39}$")


def user_dir() -> str:
    """The user's template folder (not created here); ``MODELER_TEMPLATES`` overrides it."""
    if os.environ.get("MODELER_TEMPLATES"):
        return os.environ["MODELER_TEMPLATES"]
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "3Dmodeling", "templates")


@dataclass
class Template:
    name: str
    title: str
    about: str
    path: str
    source: str  # "built-in" or "user"
    order: int = 100
    steps: list[str] = field(default_factory=list)  # the script, without the header lines

    def text(self) -> str:
        return "\n".join(self.steps)

    def sets(self) -> dict[str, Any]:
        """What the template sets, read from its steps."""
        return summarize(self.steps)

    def data(self) -> dict[str, Any]:
        return {"name": self.name, "title": self.title, "about": self.about, "source": self.source,
                "path": self.path, "sets": self.sets(), "steps": len([s for s in self.steps if _code(s)])}


def _code(line: str) -> str:
    """A line without its comment (a ! outside quotes)."""
    out, q = [], False
    for ch in line:
        if ch == '"':
            q = not q
        if ch == "!" and not q:
            break
        out.append(ch)
    return "".join(out).strip()


def summarize(steps: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {"units": "MM", "layers": [], "materials": [], "parameters": {}, "properties": {},
                           "sketches": [], "other": 0}
    for raw in steps:
        line = _code(raw)
        if not line:
            continue
        head, _, rest = line.partition(",")
        word = head.strip().upper()
        args = [a.strip().strip('"') for a in _split(rest)] if rest else []
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$", line)
        if m and "," not in m.group(1):
            out["parameters"][m.group(1).upper()] = m.group(2).strip()
        elif word == "/UNITS" and args:
            out["units"] = args[0].upper()
        elif word == "LAYER" and args:
            if args[0].upper() not in [x.upper() for x in out["layers"]] and args[0].upper() != "DEFAULT":
                out["layers"].append(args[0])
        elif word == "MATERIAL" and len(args) >= 2:
            out["materials"].append(args[1])
        elif word == "PROPERTY" and len(args) >= 2:
            out["properties"][args[0].upper()] = args[1]
        elif word == "SKETCH" and args:
            out["sketches"].append(args[0])
        else:
            out["other"] += 1
    return out


def _split(text: str) -> list[str]:
    out, cur, q = [], [], False
    for ch in text:
        if ch == '"':
            q = not q
        if ch == "," and not q:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return out


def read(path: str, source: str) -> Template:
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    meta: dict[str, str] = {}
    body: list[str] = []
    for ln in lines:
        m = _HEAD.match(ln)
        if m and not body:
            meta[m.group(1).lower()] = m.group(2)
            continue
        body.append(ln)
    while body and not body[0].strip():
        body.pop(0)
    name = meta.get("template") or os.path.splitext(os.path.basename(path))[0]
    try:
        order = int(meta.get("order", "100"))
    except ValueError:
        order = 100
    title = meta.get("title") or ("New " + name.replace("_", " "))
    return Template(name.lower(), title, meta.get("about", ""), path, source, order, body)


def all_templates() -> list[Template]:
    """Built-in templates, then the user's (a user one with a built-in name replaces it)."""
    found: dict[str, Template] = {}
    for d, source in ((BUILTIN, "built-in"), (user_dir(), "user")):
        if not os.path.isdir(d):
            continue
        for n in sorted(os.listdir(d)):
            if not n.lower().endswith(EXT):
                continue
            try:
                t = read(os.path.join(d, n), source)
            except (OSError, UnicodeDecodeError):
                continue
            found[t.name] = t
    return sorted(found.values(), key=lambda t: (t.source != "built-in", t.order, t.name))


def find(name: str) -> Template:
    key = name.strip().strip('"').lower()
    for t in all_templates():
        if t.name == key or t.title.lower() == key or t.title.lower() == "new " + key:
            return t
    names = ", ".join(t.name for t in all_templates()) or "none"
    raise CommandError(f"no template called {name!r} (there are: {names})")


def start_from(p: Processor, t: Template) -> list:
    """Clear the session and run the template's steps as the first history entries."""
    p.reset()
    p.project_path = None
    results = p.run_script(t.text()) if t.text().strip() else []
    bad = [r for r in results if not r.ok]
    if bad:
        raise CommandError(f"the template {t.name} stopped at '{bad[0].line.strip()}': {bad[0].message}")
    return results


def _setup_text(s: dict[str, Any]) -> str:
    bits = [f"units {s['units'].lower()}"]
    if s["layers"]:
        bits.append("layers " + ", ".join(s["layers"]))
    if s["parameters"]:
        bits.append("parameters " + ", ".join(f"{k} = {v}" for k, v in s["parameters"].items()))
    if s["materials"]:
        bits.append("materials " + ", ".join(s["materials"]))
    if s["properties"]:
        bits.append("title block " + ", ".join(f"{k.lower()} {v}" for k, v in s["properties"].items()))
    if s["sketches"]:
        bits.append("a sketch " + ", ".join(s["sketches"]))
    if s["other"]:
        bits.append(f"{s['other']} other step{'s' if s['other'] != 1 else ''}")
    return "; ".join(bits)


def save_template(p: Processor, name: str, title: str = "", about: str = "") -> str:
    """Write the current history as the user's template ``name``; returns its path."""
    if not _NAME.match(name):
        raise CommandError("TEMPLATE, SAVE: the name is a word of letters, digits, _ or - (up to 40), e.g. "
                           "my_bracket")
    steps = [e.text for e in p.history[: p.cursor] if not getattr(e, "suppressed", False)]
    if not steps:
        raise CommandError("TEMPLATE, SAVE: the history is empty: set up the project first (units, layers, "
                           "parameters ...)")
    d = user_dir()
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name.lower() + EXT)
    title = title or ("New " + name.replace("_", " "))
    about = about or ("Made from " + (os.path.basename(p.project_path) if p.project_path else "a project")
                      + ": " + _setup_text(summarize(steps)))
    head = [f"! template: {name.lower()}", f"! title: {title}", f"! about: {about}", "! order: 100"]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(head + steps) + "\n")
    return path


@command(
    "TEMPLATE",
    Arg("action", str, "LIST", help="LIST, SHOW, SAVE or DELETE (or JSON for the list as data)"),
    Arg("name", Text, "", help="the template's name (SHOW, SAVE, DELETE)"),
    Arg("title", Text, "", help="SAVE: its title on the start page (default: New name)"),
    Arg("about", Text, "", help="SAVE: one line on what it is for"),
    logged=False,
    help="Project templates, the steps a new project starts with (units, layers, materials, parameters, "
         "title block, a first sketch): TEMPLATE lists them · TEMPLATE, SHOW, part prints its steps · "
         "TEMPLATE, SAVE, my_bracket [, title [, about]] saves this project's history as your own template · "
         "TEMPLATE, DELETE, my_bracket. NEW, part starts a project from one; the start page shows them all.",
)
def template(p: Processor, action, name, title, about):
    import json

    action = (action or "LIST").upper()
    name = (name or "").strip().strip('"')
    if action in ("LIST", "JSON"):
        ts = all_templates()
        if action == "JSON" or name.upper() == "JSON":
            return json.dumps({"templates": [t.data() for t in ts], "user_folder": user_dir()})
        if not ts:
            return "no templates"
        lines = ["templates (NEW, name starts a project from one):"]
        for t in ts:
            lines.append(f"  {t.name}: {t.title}" + (" (yours)" if t.source == "user" else "")
                         + f" - {_setup_text(t.sets())}")
        return "\n".join(lines)
    if not name:
        raise CommandError(f"TEMPLATE, {action}: give the template's name")
    if action == "SHOW":
        t = find(name)
        return f"{t.title} ({t.source}, {t.path}):\n{t.about}\n" + "\n".join("  " + s for s in t.steps)
    if action == "SAVE":
        path = save_template(p, name, title.strip().strip('"'), about.strip().strip('"'))
        return f"saved the template {name.lower()} ({p.cursor} steps) to {path}; NEW, {name.lower()} starts from it"
    if action == "DELETE":
        t = find(name)
        if t.source != "user":
            raise CommandError(f"TEMPLATE, DELETE: {t.name} is built in; only your own templates can be deleted")
        os.remove(t.path)
        back = [x for x in all_templates() if x.name == t.name]
        return f"deleted the template {t.name}" + (" (the built-in one is used again)" if back else "")
    raise CommandError("TEMPLATE: the action is LIST, SHOW, SAVE or DELETE")
