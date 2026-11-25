"""Plug-ins: people's own commands, written in Python (PLAN item 74).

A plug-in is one ``.py`` file in the plug-in folder (``<app data>/3Dmodeling/plugins``, or
``MODELER_PLUGINS_HOME``). It adds commands with :func:`plugin_command`, named and typed like the
built-in ones, so each gets a fill-in form, a HELP page and a skill for the assistant made from its
arguments, with nothing more to write::

    from modeler.plugins import Arg, BodyRef, plugin_command

    @plugin_command("BOLTRING", Arg("b", BodyRef, help="the body to drill"),
                    Arg("n", int, 6, "how many holes"), Arg("d", float, 6.0, "hole diameter"),
                    Arg("r", float, 30.0, "radius of the ring"),
                    help="A ring of n holes round the body's middle: BOLTRING, plate, 6, 6, 30")
    def boltring(api, b, n, d, r):
        box = api.value(f"BBOX({b})")
        for i in range(n):
            ...
            api.run(f"HOLE, {b}, {x}, {y}, {top}, {d}")
        return f"{n} holes"

The function gets an ``api`` object, not the model, and each body argument as text to put in
commands: the body's name, which stays with it when a command remakes it, or its number for a
body with no name of its own (then use ``LAST`` for it after a command that remakes it). ``api.run(line)`` runs a command (its reply
comes back, a failure raises), ``api.query(name, ...)`` runs a query and gives its data, and
``api.value(expr)`` works out an expression (``BBOX(plate).zmax``, parameters ...). A plug-in command is one history step, like a
macro: undo takes all of it back, and a rebuild runs it again.

The check: the model is compared before and after each part of the plug-in that is not a
command. If a plug-in changed the model itself (reaching round the api), the step is undone and
refused with the plug-in named, so a project always comes from its commands.

Plug-ins are Python and run with the app's rights, like add-ons in any program: only put files
you trust in the folder. Turned-off plug-ins (Preferences > Plug-ins) are not read at all.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import traceback
from dataclasses import dataclass, field

from .commands.processor import REGISTRY, Arg, BodyRef, CommandError, Command, Path, Processor, Text

__all__ = ["Arg", "BodyRef", "Path", "Text", "CommandError", "plugin_command", "PluginApi"]

_ARG_TYPES = (float, int, str, Text, BodyRef, Path)


@dataclass
class Plugin:
    name: str  # the file's name without .py
    path: str
    enabled: bool = True
    commands: list[str] = field(default_factory=list)
    problem: str = ""  # why it did not load (shown in Preferences and PLUGINS)
    about: str = ""  # the file's first docstring line


_plugins: dict[str, Plugin] = {}
_disabled: set[str] = set()
_loading: Plugin | None = None  # the plug-in whose file is being read


def folder() -> str:
    """The plug-in folder (not created here)."""
    if os.environ.get("MODELER_PLUGINS_HOME"):
        return os.environ["MODELER_PLUGINS_HOME"]
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "3Dmodeling", "plugins")


EXAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugin_examples", "bolt_ring.py")


# ---- writing a plug-in -------------------------------------------------------------------------

class PluginApi:
    """What a plug-in command is given: commands in, data out."""

    def __init__(self, p: Processor, plugin: str, command: str) -> None:
        self._p = p
        self._plugin = plugin
        self._command = command
        self.units = p.model.units

    def run(self, line: str) -> str:
        """Run one command line (or a few, joined with new lines); its reply, or CommandError."""
        from .lang.script import ScriptError, parse

        _guard_check(self)
        try:
            stmts = parse(line)
        except ScriptError as exc:
            raise CommandError(str(exc)) from None
        trace = self._p._trace
        start = len(trace)
        self._p._exec_block(stmts)
        _guard_mark(self)
        return "\n".join(self._p._trace[start:])

    def query(self, name: str, *args) -> object:
        """Run a query command (CENTER, BBOX, PROBE, FEATURES, SHEETDATA ...) and give its data: the
        report it makes, or its reply text when it makes none."""
        cmd = REGISTRY.get(name.upper())
        if cmd is None:
            raise CommandError(f"unknown command {name!r}")
        if cmd.logged and not cmd.queries:
            raise CommandError(f"{name.upper()} changes the model: use api.run for it")
        _guard_check(self)
        values, _shown = self._p._bind(cmd, [str(a) for a in args])
        self._p.reports.pop(cmd.name, None)
        msg = self._p._call(cmd, values)
        _guard_mark(self)
        return self._p.reports.get(cmd.name, msg)

    def value(self, expr: str):
        """An expression's value, with the model's parameters (W * 2, BBOX(plate).dx ...)."""
        return self._p.evaluate(str(expr))


def plugin_command(name: str, *args: Arg, help: str = "", logged: bool = True):
    """Add a command from a plug-in file. The function gets (api, **arguments)."""
    key = name.strip().upper()
    if not key.isidentifier() or not key[0].isalpha():
        raise CommandError(f"{name!r} is not a command name (letters, digits, _)")
    for a in args:
        if not isinstance(a, Arg) or a.type not in _ARG_TYPES:
            raise CommandError(f"{key}: every argument is an Arg of float, int, str, Text, BodyRef or Path")
    owner = _loading
    if owner is None:
        raise CommandError("plugin_command is used in plug-in files in the plug-in folder")

    def deco(fn):
        old = REGISTRY.get(key)
        if old is not None and getattr(old, "plugin", "") != owner.name:
            raise CommandError(f"{key} is already a command" + (f" (from plug-in {old.plugin})"
                                                                 if getattr(old, "plugin", "") else ""))

        def handler(p: Processor, **values):
            return _run(p, owner.name, key, fn, values)

        text = help or (fn.__doc__ or "").strip() or f"The {key} command."
        cmd = Command(key, handler, list(args), f"{text} [plug-in {owner.name}]", logged)
        cmd.plugin = owner.name  # type: ignore[attr-defined]
        REGISTRY[key] = cmd
        owner.commands.append(key)
        return fn

    return deco


# ---- running one, with the check -------------------------------------------------------------

def _fingerprint(m) -> tuple:
    """What the model is: enough to see a change made behind the commands' back."""
    bodies = tuple(sorted((bid, id(b), _shape_key(b.shape), b.name) for bid, b in m.bodies.items()))
    return (m.revision, bodies, len(m.notes), len(getattr(m, "drawsheets", {})))


def _shape_key(s) -> int:
    try:
        return hash(s)
    except TypeError:
        return id(s)


def _guard_check(api: PluginApi) -> None:
    want = getattr(api, "_fp", None)
    if want is not None and _fingerprint(api._p.model) != want:
        raise _Bypass()


def _guard_mark(api: PluginApi) -> None:
    api._fp = _fingerprint(api._p.model)


class _Bypass(Exception):
    pass


def _run(p: Processor, plugin: str, key: str, fn, values: dict):
    cmd = REGISTRY[key]
    for a in cmd.args:
        # a body is handed over as the name to use in commands: its number changes when a command
        # remakes it (HOLE, FILLET ...), its name does not
        if a.type is BodyRef and values.get(a.name):
            from .core.model import _is_default_name

            body = p.model.body(values[a.name])
            values[a.name] = str(body.id) if _is_default_name(body) else body.name
    snap = p.model.snapshot()
    api = PluginApi(p, plugin, key)
    _guard_mark(api)
    try:
        out = fn(api, **values)
        _guard_check(api)
    except _Bypass:
        p.model.restore(snap)
        raise CommandError(f"{key}: plug-in {plugin} changed the model without using commands, so the step "
                           f"was undone (a plug-in may only change the model with api.run)") from None
    except CommandError as exc:
        raise CommandError(f"{key}: {exc}") from None
    except Exception as exc:  # noqa: BLE001 - a plug-in's own bug: name it, keep the app going
        tb = traceback.extract_tb(exc.__traceback__)
        where = next((f"{os.path.basename(f.filename)} line {f.lineno}" for f in reversed(tb)
                      if f.filename.endswith(".py") and plugin in os.path.basename(f.filename)), "")
        raise CommandError(f"{key}: plug-in {plugin} failed: {type(exc).__name__}: {exc}"
                           + (f" ({where})" if where else "")) from None
    return "" if out is None else str(out)


# ---- finding and loading --------------------------------------------------------------------------

def configure(disabled) -> None:
    """The plug-ins switched off (by file name), from the settings."""
    global _disabled
    _disabled = {str(d) for d in (disabled or [])}


def unload() -> None:
    """Take every plug-in command out of the registry."""
    for key in [k for k, c in REGISTRY.items() if getattr(c, "plugin", "")]:
        del REGISTRY[key]
    _plugins.clear()


def load_all(where: str = "") -> list[Plugin]:
    """Read every turned-on plug-in in the folder (again). Returns all plug-ins found."""
    global _loading
    unload()
    root = where or folder()
    if not os.path.isdir(root):
        return []
    for entry in sorted(os.listdir(root)):
        if not entry.endswith(".py") or entry.startswith(("_", ".")):
            continue
        name = entry[:-3]
        pl = Plugin(name, os.path.join(root, entry), name not in _disabled)
        _plugins[name] = pl
        pl.about = _about(pl.path)
        if not pl.enabled:
            continue
        _loading = pl
        try:
            spec = importlib.util.spec_from_file_location(f"modeler_plugin_{name}", pl.path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            if not pl.commands:
                pl.problem = "it adds no commands (use @plugin_command)"
        except CommandError as exc:
            pl.problem = str(exc)
        except Exception as exc:  # noqa: BLE001 - a broken file must not stop the app
            line = ""
            tb = traceback.extract_tb(exc.__traceback__)
            hit = [f for f in tb if f.filename == pl.path]
            if hit:
                line = f" (line {hit[-1].lineno})"
            pl.problem = f"{type(exc).__name__}: {exc}{line}"
        finally:
            _loading = None
        if pl.problem:
            for key in pl.commands:
                REGISTRY.pop(key, None)
            pl.commands = []
    return list(_plugins.values())


def _about(path: str) -> str:
    import ast

    try:
        with open(path, encoding="utf-8") as fh:
            doc = ast.get_docstring(ast.parse(fh.read()))
    except (OSError, SyntaxError, ValueError, UnicodeDecodeError):
        return ""
    return (doc or "").strip().splitlines()[0] if doc else ""


def plugins() -> list[Plugin]:
    return list(_plugins.values())


def commands() -> list[str]:
    return sorted(k for k, c in REGISTRY.items() if getattr(c, "plugin", ""))


def add_example(where: str = "") -> str:
    """Copy the example plug-in into the folder (made if needed). Returns the new file."""
    import shutil

    root = where or folder()
    os.makedirs(root, exist_ok=True)
    dest = os.path.join(root, os.path.basename(EXAMPLE))
    if not os.path.exists(dest):
        shutil.copyfile(EXAMPLE, dest)
    return dest


# ---- skills for the assistant ---------------------------------------------------------------------

def _arg_line(a: Arg) -> str:
    kind = {float: "a number", int: "a whole number", str: "a word", Text: "text", BodyRef: "a body",
            Path: "a file"}.get(a.type, "a value")
    need = "required" if a.default is None else f"default {a.default!r}"
    return f"* `{a.name}`: {kind}, {need}" + (f". {a.help}" if a.help else "")


def skills() -> list:
    """A skill per loaded plug-in, made from its commands' help and arguments."""
    from .ai.skills import Skill

    out = []
    for pl in _plugins.values():
        if not pl.enabled or pl.problem or not pl.commands:
            continue
        lines = [f"# Plug-in {pl.name}", "", pl.about or "Commands added by a plug-in.", "", "## Commands", ""]
        for key in pl.commands:
            cmd = REGISTRY.get(key)
            if cmd is None:
                continue
            lines += [f"### {key}", "", cmd.help, "", f"`{key}, " + ", ".join(a.name for a in cmd.args) + "`",
                      "", *[_arg_line(a) for a in cmd.args], ""]
        lines += ["## Check the result", "", "Look at the bodies it made or changed (LIST, PROBE) before going "
                  "on; it is one history step, so UNDO takes all of it back."]
        slug = "plugin-" + "".join(c if c.isalnum() else "-" for c in pl.name.lower()).strip("-")
        desc = (pl.about or f"The {', '.join(pl.commands)} command(s) from the {pl.name} plug-in.").replace("<", "")
        out.append(Skill(slug, desc[:300], "\n".join(lines), pl.path, "plug-in", list(pl.commands),
                         f"Plug-in: {pl.name}"))
    return out
