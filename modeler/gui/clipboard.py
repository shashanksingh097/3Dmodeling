"""Edit > Copy, Paste and Duplicate (PLAN item 107): Ctrl+C, Ctrl+V and Ctrl+D.

Copy takes the picked bodies, picked faces, or (while sketching) the picked sketch geometry, and
puts them on the system clipboard (as clip data, see :mod:`modeler.commands.clip_handlers`, plus a
line of text). Paste runs ordinary history steps that make copies under the mouse; Duplicate makes
copies beside the originals without touching the clipboard. A text field with the focus keeps its
own Ctrl+C and Ctrl+V.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from PySide6.QtCore import QMimeData
from PySide6.QtWidgets import QApplication

from ..commands import clip_handlers as ch
from ..commands.processor import CommandError

if TYPE_CHECKING:
    from .main_window import MainWindow


def take(win: MainWindow) -> dict:
    """Clip data for what is picked now."""
    p = win.processor
    m = p.model
    if m.active_sketch and m.sketch_selection:
        return ch.copy_sketch(p, list(m.sketch_selection))
    if m.selection and m.selection_kind == "BODY":
        return ch.copy_bodies(p, list(m.selection))
    if m.selection and m.selection_kind == "FACE":
        return ch.copy_faces(p, list(m.selection))
    raise CommandError("pick bodies, faces or sketch geometry to copy first")


def _say(win: MainWindow, text: str) -> None:
    win.statusBar().showMessage(text, 5000)


def _label(data: dict) -> str:
    if data["kind"] == "sketch":
        n = len(data["nums"])
        return f"{n} sketch curve{'s' if n != 1 else ''} of {data['sketch']}"
    names = [it["name"] for it in data["items"]]
    return f"{len(names)} bod{'ies' if len(names) != 1 else 'y'} ({', '.join(names[:4])}{'…' if len(names) > 4 else ''})"


def copy(win: MainWindow) -> dict | None:
    try:
        data = take(win)
    except CommandError as exc:
        _say(win, f"Copy: {exc}")
        return None
    md = QMimeData()
    md.setData(ch.MIME, json.dumps(data).encode("utf-8"))
    md.setText(f"3D modeling: {_label(data)}")
    QApplication.clipboard().setMimeData(md)
    win._last_clip = data
    _say(win, f"Copied {_label(data)}. Ctrl+V pastes under the mouse, also in another project.")
    return data


def clip(win: MainWindow) -> dict | None:
    """The clip data on the system clipboard (or the last copy, if the clipboard can't hold it)."""
    md = QApplication.clipboard().mimeData()
    if md is not None and md.hasFormat(ch.MIME):
        try:
            return json.loads(bytes(md.data(ch.MIME)).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None
    return getattr(win, "_last_clip", None)


def _run(win: MainWindow, lines: list[str], what: str) -> bool:
    if not lines:
        _say(win, f"{what}: nothing to paste")
        return False
    res = win.execute("\n".join(lines))
    if not res.ok:
        _say(win, f"{what}: {res.message}")
    return res.ok


def paste(win: MainWindow) -> bool:
    data = clip(win)
    if not data:
        text = QApplication.clipboard().text().strip()
        if text:  # plain text: commands, pasted into the command line to look at first
            win.cmdline.setText(text.splitlines()[0])
            win.cmdline.setFocus()
            _say(win, "Paste: the text is in the command line; Enter runs it")
            return False
        _say(win, "Paste: copy bodies, faces or sketch geometry first (Ctrl+C)")
        return False
    p = win.processor
    point = win.viewport.paste_point() if hasattr(win.viewport, "paste_point") else None
    if data.get("kind") == "sketch" and point is not None:
        point = (point[0], point[1], 0.0)
    try:
        off = ch.offset_to(data, point) if point is not None else None
        lines = ch.paste_lines(p, data, off)
    except CommandError as exc:
        _say(win, f"Paste: {exc}")
        return False
    return _run(win, lines, "Paste")


def duplicate(win: MainWindow) -> bool:
    try:
        data = take(win)
        lines = ch.paste_lines(win.processor, data)
    except CommandError as exc:
        _say(win, f"Duplicate: {exc}")
        return False
    return _run(win, lines, "Duplicate")
