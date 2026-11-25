"""Tooltips with a picture (PLAN item 94): hover a toolbar button, see what it makes.

Each ribbon button's tooltip says what it does and what it runs ("Runs:
FILLET, ..."). When there is a picture of that command's example (the same
pictures as the user guide's command pages, made small by ``python -m modeler
docs --tips`` into gui/tip_pictures/), the tooltip shows it under the text.
View > Preferences > "Pictures in tooltips" turns them off.
"""

from __future__ import annotations

import html
import os
import re

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tip_pictures")
SETTING = "view/pictureTips"
PLAIN = "plain_tip"  # the action property that keeps the tooltip as text
# buttons whose example picture says nothing about the button (files, undo, how the view looks)
SKIP = {"OPEN", "SAVE", "IMPORT", "EXPORT", "RESUME", "UNDO", "REDO", "CLEAR", "PICKMODE", "PICKREGION",
        "VIEW", "FIT", "RUN", "INPUT", "HELP"}
_RUNS = re.compile(r"Runs:\s*([A-Za-z*/][A-Za-z0-9_]*)")


def command_of(tip: str) -> str:
    """The command a tooltip says the button runs ("Runs: HOLE, ..." -> HOLE)."""
    m = _RUNS.search(tip or "")
    return m.group(1).upper() if m else ""


def picture_for(cmd: str) -> str:
    """The small picture of a command's example, or ""."""
    if not cmd or cmd in SKIP:
        return ""
    name = re.sub(r"[^\w-]", "", cmd.lower()) + ".png"
    path = os.path.join(DIR, name)
    return path if os.path.isfile(path) else ""


def rich_tip(tip: str, picture: str) -> str:
    text = html.escape(tip).replace("\n", "<br>")
    src = picture.replace(os.sep, "/")
    return (f"<div style='max-width:260px'>{text}<br>"
            f"<img src='{html.escape(src)}' width='240' height='160'></div>")


def enabled(win) -> bool:
    s = getattr(getattr(win, "shell", None), "settings", None)
    if s is None:
        return True
    v = s.value(SETTING, True)
    return v not in (False, "false", "0", 0)


def apply(win, on: bool | None = None) -> int:
    """Give every ribbon button with a picture its picture tooltip (or plain text again). How many."""
    from . import toolbars

    on = enabled(win) if on is None else on
    n = 0
    for tb in toolbars.groups(win):
        for a in tb.actions():
            plain = a.property(PLAIN)
            if plain is None:
                plain = a.toolTip()
                a.setProperty(PLAIN, plain)
            pic = picture_for(command_of(plain))
            if on and pic:
                a.setToolTip(rich_tip(plain, pic))
                n += 1
            else:
                a.setToolTip(plain)
    return n


def set_enabled(win, on: bool) -> None:
    s = getattr(getattr(win, "shell", None), "settings", None)
    if s is not None:
        s.setValue(SETTING, bool(on))
    apply(win, on)
