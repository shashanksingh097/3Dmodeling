"""The boxes beside the cursor while sketching (PLAN item 87).

The viewport sends the sketcher's fields (gui/sketch_typed.py) with every
mouse move and key: one box per size (length and angle, width and height,
radius), each showing the size the mouse gives now. A box that is fixed by a
typed value is drawn bold with an = sign, the box being typed into has a frame
and the text typed so far. Clicking a box starts typing into it.

The window never takes the keyboard: the keys go to the 3D view, which hands
them to the sketcher, so drawing goes on with the mouse at any time.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel

HINT = "Type a size, Tab: next box, Enter: place it, Esc: clear"


class _Box(QLabel):
    def __init__(self, owner, index: int) -> None:
        super().__init__()
        self.owner, self.index = owner, index
        self.setCursor(Qt.IBeamCursor)
        self.setMinimumWidth(72)

    def mousePressEvent(self, e) -> None:
        self.owner.start_typing(self.index)


class ValueBoxes(QFrame):
    def __init__(self, win) -> None:
        super().__init__(win, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setObjectName("value_boxes")
        self.setFrameShape(QFrame.StyledPanel)
        self.win = win
        self.boxes: list[_Box] = []
        self.fields: list = []
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 2, 3, 2)
        lay.setSpacing(4)
        self._lay = lay
        self.note = QLabel("")
        self.note.setObjectName("value_boxes_note")
        lay.addWidget(self.note)
        self.setToolTip(HINT)
        self.hide()

    def _ensure(self, n: int) -> None:
        while len(self.boxes) < n:
            b = _Box(self, len(self.boxes))
            self._lay.insertWidget(len(self.boxes), b)
            self.boxes.append(b)
        for i, b in enumerate(self.boxes):
            b.setVisible(i < n)

    def show_fields(self, fields, at: QPoint, error: str = "") -> None:
        """Show ``fields`` (gui.sketch_typed.Field) beside the global point ``at``; none: hide."""
        self.fields = list(fields or [])
        if not self.fields:
            self.hide()
            return
        self._ensure(len(self.fields))
        pal = self.palette()
        hi = pal.highlight().color().name()
        for b, f in zip(self.boxes, self.fields):
            name = {"deg": "°"}.get(f.unit, "")
            txt = (f.buffer + "▏") if f.editing else (f.shown() + name)
            lock = "= " if f.fixed and not f.editing else ""
            style = "border: 1px solid palette(mid); border-radius: 3px; padding: 1px 5px;"
            if f.editing:
                style = f"border: 2px solid {hi}; border-radius: 3px; padding: 0px 4px;"
            elif f.fixed:
                style += " font-weight: bold;"
            b.setStyleSheet(f"QLabel {{ {style} }}")
            b.setText(f"{f.label} {lock}{txt}")
        self.note.setText(error)
        self.note.setVisible(bool(error))
        self.note.setStyleSheet("color: #c0392b;" if error else "")
        self.adjustSize()
        self.move(at + QPoint(20, 22))
        if not self.isVisible():
            self.show()
        self.raise_()

    def start_typing(self, index: int) -> None:
        vp = self.win.viewport
        sk = getattr(vp, "sketcher", None)
        if sk is None or not sk.typing_fields():
            return
        sk.typed.focus = index
        sk.typed.buffer = ""
        vp.setFocus()
        vp.emit_typed()
