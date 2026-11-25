"""LAYOUT: which panels show, for the job at hand (PLAN item 94).

A layout is the set of panels (docks) that are open, the one in front where
panels share a place, and the ribbon tab. Five come built in:

    modelling   Model tree, History, Properties, Parameters, Output; the Model tab
    sketch      History, Properties, Output; the Sketch tab (Features when no sketch is open)
    assembly    Model tree, Properties, Parameters, History, Output; the Model tab
    drawing     History, Parameters, Output; the Inspect tab
    sculpt      only the Output, small: room for the 3D view; the Sculpt tab

``LAYOUT, SAVE, name`` keeps the window as it is now under a name of your
own; ``LAYOUT, name`` brings it back. ``LAYOUT, RESET`` is the layout the
window first opens with, and ``LAYOUT, DELETE, name`` forgets a saved one.

The window does the work (gui/layouts.py, through ``Processor.ui``); without
a window LAYOUT can only list the layouts. Not a history step.
"""

from __future__ import annotations

import json

from .processor import Arg, CommandError, Processor, Raw, command

# panel object names (gui/main_window.py _dock: the title in lower case)
PANELS = ("model", "history", "properties", "parameters", "layers", "assistant", "output")

BUILT_IN: dict[str, dict] = {
    # the History and Output panels stay closed in every layout but drawing (PLAN item 120): the status
    # bar's buttons and Ctrl+H open them when wanted, and the history is kept all the same
    "modelling": {"about": "making parts: the model tree with properties and parameters, and a big view",
                  "show": ("model", "properties", "parameters"),
                  "front": ("properties",), "tab": "Model"},
    "sketch": {"about": "drawing sketches: properties beside a big view",
               "show": ("model", "properties"), "front": ("properties",),
               "tab": "Sketch", "tab_else": "Features"},
    "assembly": {"about": "putting parts together: the model tree, properties and parameters",
                 "show": ("model", "properties", "parameters"),
                 "front": ("parameters",), "tab": "Model"},
    "drawing": {"about": "drawings and checks: history, parameters and the output",
                "show": ("history", "parameters", "output"), "front": ("parameters",), "tab": "Inspect"},
    "sculpt": {"about": "sculpting: everything put away, for the most room",
               "show": (), "front": (), "tab": "Sculpt"},
}
# the panels a new window shows, and LAYOUT, RESET brings back
DEFAULT_SHOWN = ("model", "properties", "parameters")
NAMES = {"MODELING": "modelling", "MODEL": "modelling", "SKETCHING": "sketch", "ASSEMBLE": "assembly",
         "DRAWINGS": "drawing", "SCULPTING": "sculpt"}
ACTIONS = ("LIST", "SAVE", "RESET", "DELETE", "JSON")


def canonical(name: str) -> str:
    key = name.strip().strip('"').upper()
    return NAMES.get(key, key.lower())


def _ui(p: Processor, what: str):
    ui = p.ui
    if ui is None or not hasattr(ui, "layouts"):
        raise CommandError(f"LAYOUT, {what}: layouts are panels of the window; there is no window here")
    return ui


def listing(p: Processor) -> dict:
    ui = p.ui
    saved = list(ui.layouts.saved_names()) if ui is not None and hasattr(ui, "layouts") else []
    current = ui.layouts.current if ui is not None and hasattr(ui, "layouts") else ""
    return {"built_in": {k: v["about"] for k, v in BUILT_IN.items()}, "saved": saved, "current": current}


@command(
    "LAYOUT",
    Arg("action", Raw, "", help="a layout's name (modelling, sketch, assembly, drawing, sculpt or one you "
                                "saved), or SAVE, RESET, DELETE, LIST, JSON"),
    Arg("name", Raw, "", help="with SAVE or DELETE: the layout's name"),
    logged=False,
    help="Show the panels for the job at hand: LAYOUT, sketch (a big view, history and properties), "
         "LAYOUT, sculpt (everything put away), LAYOUT, modelling, assembly or drawing. LAYOUT, SAVE, mine "
         "keeps the window as it is now; LAYOUT, mine brings it back; LAYOUT, RESET is the first layout. "
         "In the window: View > Layout.",
)
def layout(p: Processor, action, name):
    word = (action or "").strip().strip('"')
    up = word.upper()
    name = (name or "").strip().strip('"')
    if up in ("", "LIST"):
        d = listing(p)
        lines = ["layouts (LAYOUT, name shows one):"]
        lines += [f"  {k:<10} {v}" for k, v in d["built_in"].items()]
        if d["saved"]:
            lines.append("  saved: " + ", ".join(d["saved"]))
        if d["current"]:
            lines.append(f"now: {d['current']}")
        return "\n".join(lines)
    if up == "JSON":
        return json.dumps(listing(p), indent=1)
    if up == "SAVE":
        if not name:
            raise CommandError("LAYOUT, SAVE: give it a name, e.g. LAYOUT, SAVE, mine")
        if canonical(name) in BUILT_IN:
            raise CommandError(f"LAYOUT, SAVE: {canonical(name)} is a built-in layout: choose another name")
        _ui(p, "SAVE").layouts.save(name)
        return f"saved this layout as {name} (LAYOUT, {name} brings it back)"
    if up == "DELETE":
        if not name:
            raise CommandError("LAYOUT, DELETE: give the saved layout's name")
        if not _ui(p, "DELETE").layouts.delete(name):
            raise CommandError(f"LAYOUT, DELETE: no saved layout {name!r}")
        return f"deleted the layout {name}"
    if up == "RESET":
        _ui(p, "RESET").layouts.reset()
        return "the window's first layout"
    key = canonical(word)
    ui = _ui(p, word)
    if key in BUILT_IN:
        ui.layouts.apply(key, BUILT_IN[key])
        return f"layout {key}: {BUILT_IN[key]['about']}"
    if ui.layouts.restore(word):
        return f"layout {word}"
    names = ", ".join(list(BUILT_IN) + list(ui.layouts.saved_names()))
    raise CommandError(f"LAYOUT: no layout {word!r}: there are {names}")
