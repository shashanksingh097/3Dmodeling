"""PLUGINS: the plug-ins found, their commands and what is wrong with any that did not load
(PLAN item 74; modeler/plugins.py)."""

from __future__ import annotations

from .processor import Arg, Processor, command


@command(
    "PLUGINS",
    Arg("action", str, "", "RELOAD reads the plug-in folder again"),
    logged=False,
    help="The plug-ins in the plug-in folder, their commands, and why any did not load: PLUGINS · PLUGINS, RELOAD "
         "reads the folder again (after you change a file). Plug-ins are turned on and off in Preferences > "
         "Plug-ins.",
)
def plugins_(p: Processor, action):
    from .. import plugins

    if action == "RELOAD":
        plugins.load_all()
    elif action:
        from .processor import CommandError

        raise CommandError("PLUGINS: the only action is RELOAD")
    found = plugins.plugins()
    p.give_report("PLUGINS", {"folder": plugins.folder(), "plugins": [
        {"name": pl.name, "file": pl.path, "on": pl.enabled, "commands": list(pl.commands), "problem": pl.problem,
         "about": pl.about} for pl in found]})
    if not found:
        return f"no plug-ins (put .py files in {plugins.folder()}; Preferences > Plug-ins adds an example)"
    lines = [f"{len(found)} plug-in{'s' if len(found) != 1 else ''} in {plugins.folder()}:"]
    for pl in found:
        state = ("off" if not pl.enabled else f"not loaded: {pl.problem}" if pl.problem
                 else ", ".join(pl.commands))
        lines.append(f"  {pl.name}: {state}")
    return "\n".join(lines)
