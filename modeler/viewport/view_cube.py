"""The view cube (PLAN item 93): a small cube in the top right corner of the 3D view.

A click on a face, an edge or a corner turns the view to look from there; the
arrows beside it turn the view by 90 degrees and the house goes back to the
standard (iso) view. Each click writes the ordinary view command (``VIEW, TOP``,
``VIEW, TOP FRONT``, ``VIEW, TURN, LEFT``, ``VIEW, HOME``), so it shows in the
output and works the same typed. The cube is OCCT's AIS_ViewCube; its clicks
are read here instead of letting it turn the camera by itself.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QToolButton

from ..core.views import name_of

SIZE = 46  # the cube's edge in pixels (device independent)
CORNER = 78  # its centre's distance from the top right corner
SETTING = "view/viewCube"

# the arrows: (text, what VIEW, TURN does, tool tip)
ARROWS = (("◀", "LEFT", "Turn the model 90° to the left (its right side comes to the front)"),
          ("▶", "RIGHT", "Turn the model 90° to the right (its left side comes to the front)"),
          ("▲", "UP", "Turn the model 90° up (look from above)"), ("▼", "DOWN", "Turn the model 90° down (look from below)"),
          ("⟲", "CCW", "Roll the view 90° anticlockwise"), ("⟳", "CW", "Roll the view 90° clockwise"))


class ViewCube:
    def __init__(self, viewport) -> None:
        from OCP.AIS import AIS_ViewCube
        from OCP.Aspect import Aspect_TypeOfTriedronPosition
        from OCP.Graphic3d import Graphic3d_TransformPers, Graphic3d_TransModeFlags

        self.vp = viewport
        cube = AIS_ViewCube()
        r = viewport.devicePixelRatioF()
        cube.SetSize(SIZE * r)
        cube.SetFontHeight(9 * r)
        cube.SetBoxColor(_color(0.93, 0.94, 0.96))
        cube.SetDrawAxes(False)
        cube.SetTransformPersistence(Graphic3d_TransformPers(
            Graphic3d_TransModeFlags.Graphic3d_TMF_TriedronPers, Aspect_TypeOfTriedronPosition.Aspect_TOTP_RIGHT_UPPER,
            _vec2i(int(CORNER * r), int(CORNER * r))))
        self.cube = cube
        self.visible = False
        self.buttons: dict[str, QToolButton] = {}
        for text, how, tip in ARROWS:
            self.buttons[how] = self._button(text, tip, f"VIEW, TURN, {how}")
        self.buttons["HOME"] = self._button("⌂", "The standard view (iso), everything in sight", "VIEW, HOME")
        self.place()

    def _button(self, text: str, tip: str, command: str) -> QToolButton:
        b = QToolButton(self.vp)
        b.setAttribute(Qt.WA_NativeWindow, True)  # shows over the OpenGL window
        b.setText(text)
        b.setToolTip(f"{tip} ({command})")
        b.setFixedSize(22, 22)
        b.setAutoRaise(False)
        b.setFocusPolicy(Qt.NoFocus)
        b.setStyleSheet("QToolButton { background: rgba(240,242,246,220); border: 1px solid #b8bec8; "
                        "border-radius: 4px; font-size: 12px; padding: 0; } QToolButton:hover { background: #dde6f5; }")
        b.clicked.connect(lambda _=False, c=command: self.vp.command.emit(c))
        b.hide()
        return b

    def place(self) -> None:
        """The arrows round the cube, the house below it."""
        w = self.vp.width()
        cx, cy = w - CORNER, CORNER
        half = SIZE * 0.95 + 14
        spots = {"LEFT": (cx - half - 11, cy - 11), "RIGHT": (cx + half - 11, cy - 11),
                 "UP": (cx - 11, cy - half - 11), "DOWN": (cx - 11, cy + half - 11),
                 "CCW": (cx - half - 11, cy - half - 11), "CW": (cx + half - 11, cy - half - 11),
                 "HOME": (cx + half - 11, cy + half - 11)}
        for how, b in self.buttons.items():
            x, y = spots[how]
            b.move(int(max(0, x)), int(max(0, y)))

    def show(self, on: bool = True) -> None:
        ctx = self.vp.context
        if on and not self.visible:
            ctx.Display(self.cube, False)
        elif not on and self.visible:
            ctx.Remove(self.cube, False)
        self.visible = on
        for b in self.buttons.values():
            b.setVisible(on)
            if on:
                b.raise_()
        self.place()
        self.vp.context.UpdateCurrentViewer()

    def near(self, x: int, y: int) -> bool:
        """Device pixel (x, y) is in the cube's corner of the view."""
        r = self.vp.devicePixelRatioF()
        w = self.vp.width() * r
        return abs(x - (w - CORNER * r)) <= SIZE * r and abs(y - CORNER * r) <= SIZE * r

    def hit(self, x: int, y: int) -> str:
        """The VIEW words for the cube's face, edge or corner at device pixel (x, y), or ""."""
        from OCP.AIS import AIS_ViewCubeOwner

        if not self.visible or not self.near(x, y):
            return ""
        ctx = self.vp.context
        ctx.MoveTo(x, y, self.vp.view, False)
        if not ctx.HasDetected():
            return ""
        owner = ctx.DetectedOwner()
        if not isinstance(owner, AIS_ViewCubeOwner):
            return ""
        return name_of(owner.MainOrientation())


def _vec2i(x: int, y: int):
    """A 2D integer vector: OCP 8 binds it in OCP.collections, OCP 7 as Graphic3d_Vec2i."""
    try:
        from OCP.collections import Vec2_int

        return Vec2_int(x, y)
    except ImportError:
        from OCP.Graphic3d import Graphic3d_Vec2i

        return Graphic3d_Vec2i(x, y)


def _color(r: float, g: float, b: float):
    from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB

    return Quantity_Color(r, g, b, Quantity_TOC_RGB)
