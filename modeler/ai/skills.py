"""Skill files: one short Markdown file per modelling workflow.

A skill is a folder with a ``SKILL.md`` (the open Agent Skills layout: front
matter with ``name`` and ``description``, then the text) and, for the built-in
ones, an ``example.cmd`` that runs and checks itself with ``ASSERT`` lines::

    modeler/skills/sheet-metal/SKILL.md
    modeler/skills/sheet-metal/example.cmd

The same files are read by the in-app assistant (``list_skills``,
``load_skill`` and the index in its first prompt), served by the MCP server
as prompts and resources, written out for other agents by
``python -m modeler skills export``, and shown to people as Guides in the
help browser. See docs/M12-assistant-skills.md.

Skills come from three places, in this order (a later one with the same name
wins, so a user can replace a built-in skill):

1. built in: ``modeler/skills/``;
2. the user's own folder: ``<app data>/3Dmodeling/skills`` (``MODELER_SKILLS_HOME``) and every folder in
   ``MODELER_SKILLS`` (separated like ``PATH``), and folders added with
   :func:`configure`;
3. the open project: a ``skills`` folder next to the project file.

Skills are only text for the assistant: nothing in them runs by itself.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from typing import Any

BUILTIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")
MAX_BYTES = 6000  # a skill should stay short: steps, checks, mistakes
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# things that look like keys or tokens must never sit in a skill
SECRET_RE = re.compile(r"(sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY)")

_extra_dirs: list[str] = []
_disabled: set[str] = set()


@dataclass
class Skill:
    name: str
    description: str
    body: str  # the Markdown after the front matter
    path: str  # the SKILL.md file
    source: str = "built-in"  # built-in, user or project
    commands: list[str] = field(default_factory=list)
    title: str = ""

    @property
    def folder(self) -> str:
        return os.path.dirname(self.path)

    @property
    def example(self) -> str:
        """The example script's path, or ''."""
        f = os.path.join(self.folder, "example.cmd")
        return f if os.path.isfile(f) else ""

    @property
    def enabled(self) -> bool:
        return self.name not in _disabled

    def text(self) -> str:
        """The whole SKILL.md, front matter and all."""
        with open(self.path, encoding="utf-8") as f:
            return f.read()

    def row(self) -> dict[str, Any]:
        out: dict[str, Any] = {"name": self.name, "title": self.title, "description": self.description,
                               "source": self.source}
        if self.commands:
            out["commands"] = self.commands
        if not self.enabled:
            out["enabled"] = False
        return out


class SkillError(Exception):
    pass


# ---- reading ----------------------------------------------------------------------------
def parse(text: str, path: str = "", source: str = "built-in") -> Skill:
    """A SKILL.md's text as a Skill. The front matter is the small part of YAML
    these files use: ``key: value`` lines between two ``---`` lines."""
    text = text.lstrip("﻿")
    if not text.startswith("---"):
        raise SkillError(f"{path or 'skill'}: SKILL.md must start with a front matter block (---)")
    end = text.find("\n---", 3)
    if end < 0:
        raise SkillError(f"{path or 'skill'}: the front matter has no closing ---")
    meta: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise SkillError(f"{path or 'skill'}: front matter line {line.strip()!r} is not 'key: value'")
        meta[key.strip().lower()] = value.strip().strip('"').strip("'")
    body = text[end + 4:].lstrip("\n")
    name = meta.get("name", "")
    if not name:
        raise SkillError(f"{path or 'skill'}: the front matter needs a name")
    desc = meta.get("description", "")
    if not desc:
        raise SkillError(f"{path or 'skill'}: the front matter needs a description")
    cmds = [c.strip().upper() for c in meta.get("commands", "").split(",") if c.strip()]
    title = ""
    m = re.search(r"^# (.+)$", body, re.M)
    if m:
        title = m.group(1).strip()
    return Skill(name, desc, body, path, source, cmds, title or name.replace("-", " ").capitalize())


def user_dir() -> str:
    """The user's own skill folder in the per-user app data folder (not created here);
    ``MODELER_SKILLS_HOME`` overrides it."""
    if os.environ.get("MODELER_SKILLS_HOME"):
        return os.environ["MODELER_SKILLS_HOME"]
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "3Dmodeling", "skills")


def configure(extra_dirs: list[str] | None = None, disabled: list[str] | set[str] | None = None) -> None:
    """Set the extra folders (from Settings) and the names switched off."""
    global _extra_dirs, _disabled
    if extra_dirs is not None:
        _extra_dirs = [d for d in extra_dirs if d]
    if disabled is not None:
        _disabled = set(disabled)


def roots(project_dir: str = "") -> list[tuple[str, str]]:
    """(folder, source) pairs, searched in this order."""
    out = [(BUILTIN, "built-in"), (user_dir(), "user")]
    for d in os.environ.get("MODELER_SKILLS", "").split(os.pathsep):
        if d.strip():
            out.append((os.path.expanduser(d.strip()), "user"))
    out += [(os.path.expanduser(d), "user") for d in _extra_dirs]
    if project_dir:
        out.append((os.path.join(project_dir, "skills"), "project"))
    return out


def discover(project_dir: str = "", include_disabled: bool = False) -> dict[str, Skill]:
    """Every skill by name; a later folder replaces an earlier skill of the same name.
    Files that do not read as skills are left out (``check`` reports them)."""
    found: dict[str, Skill] = {}
    for root, source in roots(project_dir):
        if not os.path.isdir(root):
            continue
        for entry in sorted(os.listdir(root)):
            f = os.path.join(root, entry, "SKILL.md")
            if not os.path.isfile(f):
                continue
            try:
                with open(f, encoding="utf-8") as fh:
                    s = parse(fh.read(), f, source)
            except (OSError, UnicodeDecodeError, SkillError):
                continue
            found[s.name] = s
    try:  # a skill for each loaded plug-in, made from its commands (modeler/plugins.py)
        from .. import plugins

        for s in plugins.skills():
            found.setdefault(s.name, s)
    except Exception:  # noqa: BLE001 - a plug-in must never stop the skills from loading
        pass
    if not include_disabled:
        found = {k: v for k, v in found.items() if v.enabled}
    return dict(sorted(found.items()))


def get(name: str, project_dir: str = "") -> Skill:
    skills = discover(project_dir)
    key = name.strip().lower().replace(" ", "-")
    if key in skills:
        return skills[key]
    close = [n for n in skills if key and (key in n or n in key)]
    raise SkillError(f"no skill {name!r}" + (f"; did you mean {', '.join(close)}?" if close else
                                              f"; skills: {', '.join(skills)}"))


def for_command(command: str, project_dir: str = "") -> list[Skill]:
    """The skills that name this command (for 'Guides that use it' and the Why? link)."""
    c = command.strip().upper()
    return [s for s in discover(project_dir).values() if c in s.commands]


def index_text(project_dir: str = "") -> str:
    """One line per skill for the assistant's first prompt."""
    skills = discover(project_dir)
    if not skills:
        return ""
    lines = [f"- {s.name}: {s.description}" for s in skills.values()]
    return "\n".join(lines)


# ---- tools ------------------------------------------------------------------------------
def list_rows(project_dir: str = "") -> dict[str, Any]:
    return {"skills": [s.row() for s in discover(project_dir).values()],
            "hint": "load_skill(name) gives the steps, the checks and the example script"}


def load(name: str, project_dir: str = "", example: bool = True) -> dict[str, Any]:
    s = get(name, project_dir)
    out: dict[str, Any] = {"name": s.name, "source": s.source, "text": s.body}
    if example and s.example:
        with open(s.example, encoding="utf-8") as f:
            out["example"] = f.read()
    return out


# ---- checking ---------------------------------------------------------------------------
def check(skill: Skill, run_example: bool = True) -> list[str]:
    """Problems with one skill; [] when it is fine. Built-in skills must pass in CI."""
    from ..commands.processor import REGISTRY

    problems: list[str] = []
    folder = os.path.basename(skill.folder)
    if not NAME_RE.match(skill.name):
        problems.append(f"name {skill.name!r}: use lower case letters, digits and single hyphens")
    if folder != skill.name:
        problems.append(f"name {skill.name!r} differs from its folder {folder!r}")
    if len(skill.description) > 1024:
        problems.append("description is over 1024 characters")
    text = skill.text()
    if len(text.encode("utf-8")) > MAX_BYTES:
        problems.append(f"SKILL.md is {len(text.encode('utf-8'))} bytes; keep it under {MAX_BYTES}")
    if SECRET_RE.search(text):
        problems.append("something that looks like a key or token is in the file")
    for c in skill.commands:
        if c not in REGISTRY and not c.startswith("*"):  # *PART, *DO ... are blocks, not commands
            problems.append(f"front matter names {c}, which is not a command")
    # every command line in a ```cmd block must lint
    for block in re.findall(r"```cmd\n(.*?)```", skill.body, re.S):
        problems += [f"in a cmd block: {p}" for p in _lint(block)]
    if skill.source == "built-in" and not skill.example:
        problems.append("no example.cmd")
    if skill.example:
        with open(skill.example, encoding="utf-8") as f:
            script = f.read()
        if skill.source == "built-in" and "ASSERT" not in script.upper():
            problems.append("example.cmd has no ASSERT lines")
        if run_example:
            problems += [f"example.cmd: {p}" for p in run(script)]
    return problems


def _lint(script: str) -> list[str]:
    from ..commands.processor import Processor
    from .lint import lint

    out = lint(Processor(), script, sandbox=False)
    return [f"line {i.get('line', '?')}: {i.get('msg', i)}" for i in out.get("issues", [])
            if i.get("level", "error") == "error"]


def run(script: str) -> list[str]:
    """Run an example script in a fresh model; the failures as text."""
    from ..commands.processor import Processor

    p = Processor()
    out = [f"{r.line}: {r.message}" for r in p.run_script(script) if not r.ok]
    # a history edit can leave an earlier step failing while the edit itself is ok
    out += [f"step {i} now fails: {e.message}" for i, e in enumerate(p.history[:p.cursor], 1) if not e.ok]
    return out


def check_all(project_dir: str = "", run_example: bool = True) -> dict[str, list[str]]:
    """Problems per skill, also for folders whose SKILL.md does not read at all."""
    out: dict[str, list[str]] = {}
    for root, source in roots(project_dir):
        if not os.path.isdir(root):
            continue
        for entry in sorted(os.listdir(root)):
            f = os.path.join(root, entry, "SKILL.md")
            if not os.path.isfile(f):
                continue
            try:
                with open(f, encoding="utf-8") as fh:
                    s = parse(fh.read(), f, source)
            except (OSError, UnicodeDecodeError, SkillError) as exc:
                out[entry] = [str(exc)]
                continue
            out[s.name] = check(s, run_example)
    return out


# ---- writing out for other agents -------------------------------------------------------
EXPORT_NOTE = """
## Using this skill outside the app

The commands above run in 3Dmodeling. Start its tools as an MCP server
(`python -m modeler mcp`, or `3Dmodeling-cli mcp` in a built app) and use
`run`, `check` and `describe_body` on its working copy; `apply` then
`save_project` or `export` write the result.
"""


def export(dest: str, names: list[str] | None = None, project_dir: str = "") -> list[str]:
    """Write skill folders into ``dest`` (for example ``.claude/skills``); the folders written."""
    skills = discover(project_dir)
    if names:
        missing = [n for n in names if n not in skills]
        if missing:
            raise SkillError(f"no skill {', '.join(missing)}")
        skills = {n: skills[n] for n in names}
    os.makedirs(dest, exist_ok=True)
    written = []
    for s in skills.values():
        out = os.path.join(dest, s.name)
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(s.text().rstrip() + "\n" + EXPORT_NOTE)
        if s.example:
            shutil.copyfile(s.example, os.path.join(out, "example.cmd"))
        written.append(out)
    return written


# ---- command line -----------------------------------------------------------------------
USAGE = """usage: python -m modeler skills [list | show NAME | check [--no-run] | export --to FOLDER [NAME ...]]"""


def main(args: list[str]) -> int:
    cmd = args[0] if args else "list"
    if cmd == "list":
        for s in discover(include_disabled=True).values():
            flag = "" if s.enabled else " (off)"
            print(f"{s.name} [{s.source}]{flag}: {s.description}")
        return 0
    if cmd == "show" and len(args) == 2:
        try:
            s = get(args[1])
        except SkillError as exc:
            print(exc)
            return 1
        print(s.text())
        return 0
    if cmd == "check":
        bad = 0
        for name, problems in check_all(run_example="--no-run" not in args).items():
            print(f"{name}: " + ("ok" if not problems else "\n  " + "\n  ".join(problems)))
            bad += bool(problems)
        return 1 if bad else 0
    if cmd == "export" and "--to" in args:
        i = args.index("--to")
        if i + 1 >= len(args):
            print(USAGE)
            return 2
        dest = args[i + 1]
        names = args[1:i] + args[i + 2:]
        try:
            for f in export(dest, names or None):
                print(f)
        except SkillError as exc:
            print(exc)
            return 1
        return 0
    print(USAGE)
    return 2
