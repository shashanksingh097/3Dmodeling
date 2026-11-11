"""OCCT 3D view (AIS / V3d) embedded in a PySide6 widget.

The viewport never changes the model. A click is turned into command text
(``PICK, FACE, 12``) and handed to the processor through the ``command``
signal, exactly as if it had been typed. The viewport then redraws from model
change events, so scripted ``PICK``/``SEL`` commands highlight the same way.

Mouse:
    left click          pick (Ctrl/Shift+click adds, Alt+click removes)
    left drag           orbit
    middle or right drag pan  (Shift+left drag also pans)
    wheel               zoom at the cursor
"""

from __future__ import annotations

import ctypes
import sys
import traceback

from OCP.AIS import AIS_InteractiveContext, AIS_Shape
from OCP.Aspect import (
    Aspect_DisplayConnection,
    Aspect_GradientFillMethod,
    Aspect_TOTP_LEFT_LOWER,
)
from OCP.Graphic3d import Graphic3d_MaterialAspect, Graphic3d_NameOfMaterial
from OCP.OpenGl import OpenGl_GraphicDriver
from OCP.Prs3d import Prs3d_TypeOfHighlight
from OCP.StdSelect import StdSelect_BRepOwner
from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SHAPE, TopAbs_VERTEX
from OCP.V3d import V3d_TypeOfOrientation, V3d_Viewer, V3d_ZBUFFER
from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QWidget

from ..core.model import Event, Model, ModelError

_TOPABS = {"BODY": TopAbs_SHAPE, "FACE": TopAbs_FACE, "EDGE": TopAbs_EDGE, "VERTEX": TopAbs_VERTEX}

_O = V3d_TypeOfOrientation
_VIEWS = {
    "ISO": _O.V3d_XposYnegZpos,
    "TOP": _O.V3d_Zpos,
    "BOTTOM": _O.V3d_Zneg,
    "FRONT": _O.V3d_Yneg,
    "BACK": _O.V3d_Ypos,
    "LEFT": _O.V3d_Xneg,
    "RIGHT": _O.V3d_Xpos,
}

_CLICK_TOLERANCE = 4  # px of movement still counted as a click


def _rgb(r: float, g: float, b: float) -> Quantity_Color:
    return Quantity_Color(r, g, b, Quantity_TOC_RGB)


def _native_window(display: Aspect_DisplayConnection, wid: int):
    """Wrap Qt's native window handle in the OCCT window class for this OS."""
    if sys.platform == "win32":
        from OCP.WNT import WNT_Window as Win

        args_list = [(wid,), (_capsule(wid),)]
    elif sys.platform == "darwin":
        from OCP.Cocoa import Cocoa_Window as Win

        args_list = [(wid,), (_capsule(wid),)]
    else:
        from OCP.Xw import Xw_Window as Win

        args_list = [(display, wid)]
    last: Exception | None = None
    for args in args_list:
        try:
            return Win(*args)
        except TypeError as exc:  # binding wants a different handle type
            last = exc
    raise RuntimeError(f"could not wrap native window handle: {last}")


def _capsule(ptr: int):
    new = ctypes.pythonapi.PyCapsule_New
    new.restype = ctypes.py_object
    new.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p]
    return new(ptr, None, None)


class OccViewport(QWidget):
    command = Signal(str)  # command text for the processor
    ready = Signal()

    def __init__(self, model: Model, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = model
        self.pick_mode = "FACE"
        self._ais: dict[int, AIS_Shape] = {}
        self._initialized = False
        self._press: QPoint | None = None
        self._drag = ""  # "", "rotate", "pan"
        self._last = QPoint()

        for attr in (
            Qt.WA_NativeWindow,
            Qt.WA_PaintOnScreen,
            Qt.WA_NoSystemBackground,
            Qt.WA_OpaquePaintEvent,
        ):
            self.setAttribute(attr)
        self.setAutoFillBackground(False)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(320, 240)
        model.subscribe(self._on_model_event)

    # ---- OCCT setup ------------------------------------------------------
    def paintEngine(self):  # Qt must not paint over the OpenGL surface
        return None

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._initialized:
            self._init_occ()

    def _init_occ(self) -> None:
        self._display = Aspect_DisplayConnection()
        self._driver = OpenGl_GraphicDriver(self._display, False)
        self.viewer = V3d_Viewer(self._driver)
        self.viewer.SetDefaultLights()
        self.viewer.SetLightOn()
        self.context = AIS_InteractiveContext(self.viewer)
        self.context.SetDisplayMode(1, False)  # shaded
        self.context.SetAutomaticHilight(True)
        self._style_highlight()

        self.view = self.viewer.CreateView()
        self._window = _native_window(self._display, int(self.winId()))
        self.view.SetWindow(self._window)
        if not self._window.IsMapped():
            self._window.Map()
        self.view.SetBgGradientColors(_rgb(0.20, 0.22, 0.26), _rgb(0.55, 0.58, 0.62),
                                    Aspect_GradientFillMethod.Aspect_GradientFillMethod_Vertical, True)
        self.view.TriedronDisplay(Aspect_TOTP_LEFT_LOWER, _rgb(1, 1, 1), 0.08, V3d_ZBUFFER)
        self.view.SetProj(_VIEWS["ISO"])
        self.view.MustBeResized()
        self._initialized = True

        for body in self.model.bodies.values():
            self._display_body(body.id, update=False)
        self._sync_selection()
        self.view.FitAll(0.1, False)
        self.view.Redraw()
        self.ready.emit()

    def _style_highlight(self) -> None:
        T = Prs3d_TypeOfHighlight
        colors = {
            T.Prs3d_TypeOfHighlight_Selected: _rgb(1.0, 0.55, 0.0),
            T.Prs3d_TypeOfHighlight_LocalSelected: _rgb(1.0, 0.55, 0.0),
            T.Prs3d_TypeOfHighlight_Dynamic: _rgb(0.3, 0.8, 1.0),
            T.Prs3d_TypeOfHighlight_LocalDynamic: _rgb(0.3, 0.8, 1.0),
        }
        for kind, color in colors.items():
            style = self.context.HighlightStyle(kind)
            style.SetColor(color)
            style.SetDisplayMode(1)

    def call_when_ready(self, fn) -> None:
        """Run ``fn`` now if the 3D view exists, else once it is created."""
        if self._initialized:
            fn()
        else:
            self.ready.connect(fn)

    # ---- painting and resizing -----------------------------------------
    def paintEvent(self, event) -> None:
        if self._initialized:
            self.view.Redraw()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._initialized:
            self.view.MustBeResized()

    def _px(self, pos) -> tuple[int, int]:
        """Qt logical coordinates -> OCCT device pixels (HiDPI aware)."""
        r = self.devicePixelRatioF()
        return int(pos.x() * r), int(pos.y() * r)

    # ---- ViewHooks used by view commands ------------------------------
    def set_view(self, name: str) -> None:
        if self._initialized:
            self.view.SetProj(_VIEWS[name])
            self.view.FitAll(0.1, False)
            self.view.Redraw()

    def fit(self) -> None:
        if self._initialized:
            self.view.FitAll(0.1, False)
            self.view.Redraw()

    def set_pick_mode(self, kind: str) -> None:
        self.pick_mode = kind
        if not self._initialized:
            return
        self.context.ClearSelected(False)
        for ais in self._ais.values():
            self._activate(ais)
        self._sync_selection()

    def _activate(self, ais: AIS_Shape) -> None:
        self.context.Deactivate(ais)
        self.context.Activate(ais, AIS_Shape.SelectionMode_s(_TOPABS[self.pick_mode]))

    # ---- model -> display ---------------------------------------------
    def _on_model_event(self, ev: Event) -> None:
        if not self._initialized:
            return
        try:
            self._apply_event(ev)
        except Exception:  # a display problem must not undo a model change
            traceback.print_exc()

    def _apply_event(self, ev: Event) -> None:
        if ev.kind == "body_added":
            first = not self._ais
            self._display_body(ev.body_id, update=False)
            if first:
                self.view.FitAll(0.1, False)
        elif ev.kind == "body_removed":
            ais = self._ais.pop(ev.body_id, None)
            if ais is not None:
                self.context.Remove(ais, False)
        elif ev.kind == "cleared":
            self.context.RemoveAll(False)
            self._ais.clear()
        elif ev.kind == "selection":
            self._sync_selection()
            return
        self.context.UpdateCurrentViewer()

    def _display_body(self, bid: int, update: bool = True) -> None:
        ais = AIS_Shape(self.model.bodies[bid].shape)
        ais.SetMaterial(Graphic3d_MaterialAspect(Graphic3d_NameOfMaterial.Graphic3d_NameOfMaterial_Steel))
        ais.SetColor(_rgb(0.62, 0.66, 0.72))
        ais.Attributes().SetFaceBoundaryDraw(True)
        self.context.Display(ais, 1, 0, False)
        self._activate(ais)
        self._ais[bid] = ais
        if update:
            self.context.UpdateCurrentViewer()

    def _sync_selection(self) -> None:
        """Make the highlighted entities match model.selection.

        We build our own owners for the selected sub-shapes instead of
        looking up the ones OCCT made for picking: that lookup is not exposed
        the same way in every OCP version, and a fresh owner highlights the
        same. Clicks never select directly (they emit PICK commands), so
        these owners are the only selected ones.
        """
        ctx = self.context
        ctx.ClearSelected(False)
        m = self.model
        kind = m.selection_kind
        if m.selection and kind == self.pick_mode:
            for gid in m.selection:
                if kind == "BODY":
                    bid, shape = gid, m.bodies[gid].shape
                else:
                    bid = m.entity_owner(kind, gid)[0]
                    shape = m.entity_shape(kind, gid)
                ais = self._ais.get(bid)
                if ais is None:
                    continue
                owner = StdSelect_BRepOwner(shape, ais, 0, kind != "BODY")
                ctx.AddOrRemoveSelected(owner, False)
        ctx.UpdateCurrentViewer()

    # ---- picking --------------------------------------------------------
    def pick_at(self, x: int, y: int) -> tuple[str, int] | None:
        """What is under device pixel (x, y): (kind, id) or None."""
        self.context.MoveTo(x, y, self.view, False)
        if not self.context.HasDetected():
            return None
        shape = self.context.DetectedShape()
        detected = self.context.DetectedInteractive()
        for bid, ais in self._ais.items():
            if ais is not detected:
                continue
            if self.pick_mode == "BODY":
                return "BODY", bid
            try:
                return self.pick_mode, self.model.find_entity(bid, self.pick_mode, shape)
            except ModelError:
                return None
        return None

    def click(self, x: int, y: int, modifiers=Qt.NoModifier) -> str | None:
        """Turn a click at device pixel (x, y) into a command and emit it."""
        hit = self.pick_at(x, y)
        if hit is None:
            text = "SEL, NONE" if self.model.selection else None
        else:
            kind, gid = hit
            if modifiers & Qt.AltModifier:
                mode = ", U"
            elif modifiers & (Qt.ControlModifier | Qt.ShiftModifier):
                mode = ", A"
            else:
                mode = ""
            text = f"PICK, {kind}, {gid}{mode}"
        if text:
            self.command.emit(text)
        return text

    # ---- mouse ------------------------------------------------------------
    def mousePressEvent(self, e) -> None:
        if not self._initialized:
            return
        self._press = e.position().toPoint()
        self._last = self._press
        x, y = self._px(self._press)
        if e.button() == Qt.LeftButton and not (e.modifiers() & Qt.ShiftModifier):
            self._drag = "rotate"
            self.view.StartRotation(x, y)
        else:
            self._drag = "pan"

    def mouseMoveEvent(self, e) -> None:
        if not self._initialized:
            return
        pos = e.position().toPoint()
        x, y = self._px(pos)
        if self._press is not None and (pos - self._press).manhattanLength() > _CLICK_TOLERANCE:
            if self._drag == "rotate":
                self.view.Rotation(x, y)
            elif self._drag == "pan":
                lx, ly = self._px(self._last)
                self.view.Pan(x - lx, ly - y)
            self._last = pos
        elif self._press is None:
            self.context.MoveTo(x, y, self.view, True)  # hover highlight

    def mouseReleaseEvent(self, e) -> None:
        if not self._initialized or self._press is None:
            return
        pos = e.position().toPoint()
        moved = (pos - self._press).manhattanLength() > _CLICK_TOLERANCE
        self._press = None
        self._drag = ""
        if not moved and e.button() == Qt.LeftButton:
            self.click(*self._px(pos), e.modifiers())

    def wheelEvent(self, e) -> None:
        if not self._initialized:
            return
        x, y = self._px(e.position().toPoint())
        step = int(e.angleDelta().y() / 8)
        self.view.StartZoomAtPoint(x, y)
        self.view.ZoomAtPoint(x, y, x + step, y + step)
