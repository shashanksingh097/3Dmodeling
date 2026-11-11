"""Command registry, a minimal parser and the processor.

Every change to the model goes through :meth:`Processor.run`, whether the text
was typed, read from a script, or built by a GUI action. Each successful
command is appended to the log, so the log replays the session.

The parser here is the M0 version: comma separated, case-insensitive names,
``!`` comments, numbers or words as arguments, empty arguments take defaults.
Parameters, expressions and control flow arrive in M1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from ..core.model import Model, ModelError


class CommandError(Exception):
    pass


class ViewHooks(Protocol):
    """What the viewport offers to view commands. Absent when headless."""

    def set_view(self, name: str) -> None: ...
    def fit(self) -> None: ...
    def set_pick_mode(self, kind: str) -> None: ...


@dataclass
class Arg:
    name: str
    type: type = float  # float, int or str
    default: Any = None  # None means required
    help: str = ""


@dataclass
class Command:
    name: str
    fn: Callable[..., str | None]
    args: list[Arg]
    help: str
    logged: bool = True  # queries (LIST, HELP) are not written to the log


REGISTRY: dict[str, Command] = {}


def command(name: str, *args: Arg, help: str = "", logged: bool = True):
    """Register a handler. The handler gets (ctx, **parsed_args)."""

    def deco(fn):
        REGISTRY[name.upper()] = Command(name.upper(), fn, list(args), help, logged)
        return fn

    return deco


@dataclass
class Result:
    line: str
    ok: bool
    message: str = ""


@dataclass
class Processor:
    model: Model = field(default_factory=Model)
    view: ViewHooks | None = None
    log: list[str] = field(default_factory=list)
    listeners: list[Callable[[Result], None]] = field(default_factory=list)

    def run(self, line: str) -> Result:
        """Run one command line and return what happened. Never raises."""
        text = _strip_comment(line).strip()
        if not text:
            return Result("", True)
        try:
            cmd, values = self._parse(text)
            message = cmd.fn(self, **values) or ""
            if cmd.logged:
                self.log.append(_normalize(text))
            res = Result(text, True, message)
        except (CommandError, ModelError) as exc:
            res = Result(text, False, str(exc))
        except Exception as exc:  # kernel failures should not kill the app
            res = Result(text, False, f"{type(exc).__name__}: {exc}")
        for fn in list(self.listeners):
            fn(res)
        return res

    def run_script(self, text: str) -> list[Result]:
        results = []
        for line in text.splitlines():
            r = self.run(line)
            if r.line:
                results.append(r)
                if not r.ok:
                    break
        return results

    def _parse(self, text: str) -> tuple[Command, dict[str, Any]]:
        parts = [p.strip() for p in text.split(",")]
        name = parts[0].upper()
        cmd = REGISTRY.get(name)
        if cmd is None:
            raise CommandError(f"unknown command {parts[0]!r} (type HELP for a list)")
        raw = parts[1:]
        if len(raw) > len(cmd.args):
            raise CommandError(f"{name} takes at most {len(cmd.args)} arguments, got {len(raw)}")
        values: dict[str, Any] = {}
        for i, arg in enumerate(cmd.args):
            s = raw[i] if i < len(raw) else ""
            if s == "":
                if arg.default is None:
                    raise CommandError(f"{name}: argument '{arg.name}' is required")
                values[arg.name] = arg.default
                continue
            try:
                if arg.type is str:
                    values[arg.name] = s.upper()
                elif arg.type is int:
                    values[arg.name] = int(float(s))
                else:
                    values[arg.name] = float(s)
            except ValueError:
                raise CommandError(f"{name}: '{arg.name}' must be a number, got {s!r}") from None
        return cmd, values


def _strip_comment(line: str) -> str:
    i = line.find("!")
    return line if i < 0 else line[:i]


def _normalize(text: str) -> str:
    parts = [p.strip() for p in text.split(",")]
    parts[0] = parts[0].upper()
    return ", ".join(parts)
