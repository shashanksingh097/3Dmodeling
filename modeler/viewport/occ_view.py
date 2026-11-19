"""OCCT 3D view (AIS / V3d) embedded in a PySide6 widget.

The viewport never changes the model. A click is turned into command text
(``PICK, FACE, 12``) and handed to the processor through the ``command``
signal, exactly as if it had been typed. The viewport then redraws from model
change events, so scripted ``PICK``/``SEL`` commands highlight the same way.

Mouse:
    left click          pick (Ctrl/Shift+click adds, Alt+click removes);
                        in sketch mode the click goes to the sketch tool
                        (gui/sketch_tools.py), which writes sketch commands
    left drag           orbit
    middle or right drag pan  (Shift+left drag also pans)
    wheel               zoom at the cursor
"""

from __future__ import annotations

import ctypes
import os
import sys
import traceback

from OCP.AIS import AIS_InteractiveContext, AIS_Shape
from OCP.Aspect import (
    Aspect_DisplayConnection,
    Aspect_GradientFillMethod,
    Aspect_TOTP_LEFT_LOWER,
    Aspect_TypeOfLine,
)
from OCP.Graphic3d import Graphic3d_MaterialAspect, Graphic3d_NameOfMaterial
from OCP.OpenGl import OpenGl_GraphicDriver
from OCP.Prs3d import Prs3d_LineAspect, Prs3d_TypeOfHighlight
from OCP.StdSelect import StdSelect_BRepOwner
from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SHAPE, TopAbs_VERTEX
from OCP.V3d import V3d_TypeOfOrientation, V3d_Viewer, V3d_ZBUFFER
from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QWidget

from ..core.model import Event, Model, ModelError
from ..geometry import meshbody as mb

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


def _num(v) -> str:
    v = round(float(v), 4) + 0.0
    return str(int(v)) if v.is_integer() else f"{v:g}"


def _on_top(ctx, ais) -> None:
    """Sketches lie on faces: draw them in front, so the face never hides them."""
    from OCP.Graphic3d import Graphic3d_ZLayerId_Topmost

    ais.SetZLayer(Graphic3d_ZLayerId_Topmost)
    ctx.SetZLayer(ais, Graphic3d_ZLayerId_Topmost)


def _coloured_mesh(m, rgb):
    """An AIS_Triangulation of an analysis mesh with a colour at every node."""
    from OCP.AIS import AIS_Triangulation
    from OCP.gp import gp_Pnt
    from OCP.Poly import Poly_Triangle, Poly_Triangulation

    try:  # OCP 8
        from OCP.collections import HArray1_int as _HInts
    except ImportError:  # OCP 7.x
        from OCP.TColStd import TColStd_HArray1OfInteger as _HInts

    from OCP.gp import gp_Dir

    n, k = len(m.nodes), len(m.tris)
    tri = Poly_Triangulation(n, k, False, True)
    for i, (q, nv) in enumerate(zip(m.nodes, m.normals), 1):
        tri.SetNode(i, gp_Pnt(*map(float, q)))
        ln = float((nv ** 2).sum()) ** 0.5
        tri.SetNormal(i, gp_Dir(*map(float, nv / ln)) if ln > 1e-12 else gp_Dir(0, 0, 1))
    for i, (a, b, c) in enumerate(m.tris, 1):
        tri.SetTriangle(i, Poly_Triangle(int(a) + 1, int(b) + 1, int(c) + 1))
    cols = _HInts(1, n)
    c8 = (rgb.clip(0, 1) * 255).round().astype(int)
    for i, (r, g, b) in enumerate(c8, 1):
        cols.SetValue(i, int((255 << 24) | (int(b) << 16) | (int(g) << 8) | int(r)) - (1 << 32))
    ais = AIS_Triangulation(tri)
    ais.SetColors(cols)
    # plain white plastic, so the node colours show as they are (the default material tints them gold)
    from OCP.Graphic3d import Graphic3d_MaterialAspect, Graphic3d_NameOfMaterial
    from OCP.Prs3d import Prs3d_ShadingAspect

    asp = Prs3d_ShadingAspect()
    mat = Graphic3d_MaterialAspect(Graphic3d_NameOfMaterial.Graphic3d_NameOfMaterial_Plastified)
    mat.SetColor(_rgb(1, 1, 1))
    asp.SetMaterial(mat)
    asp.SetColor(_rgb(1, 1, 1))
    ais.Attributes().SetShadingAspect(asp)
    return ais


def _mark_position(sk, c):
    """Where a constraint's mark goes: next to the middle of its first curve."""
    for r in c.refs:
        try:
            ref = sk.ref(r)
        except Exception:
            return None
        if ref.fixed:
            continue
        g = ref.geo
        off = 0.025 * sk.extent()
        if ref.is_point:
            p = sk.pt(ref.point)
            return (p[0] + off, p[1] + off)
        if g.kind == "LINE":
            a, b = sk.pt(g.pts["S"]), sk.pt(g.pts["E"])
            dx, dy = b[0] - a[0], b[1] - a[1]
            L = (dx * dx + dy * dy) ** 0.5 or 1.0
            return ((a[0] + b[0]) / 2 + dy / L * off * 1.4 + dx / L * off, (a[1] + b[1]) / 2 - dx / L * off * 1.4 + dy / L * off)
        if g.kind == "SPLINE":
            p = sk.pt(g.pts["S"])
            return (p[0] + off, p[1] + off)
        c0 = sk.pt(g.pts["C"])
        rad = sk.radius(g) if g.kind in ("ARC", "CIRCLE") else abs(sk.x[g.r])
        return (c0[0] - rad * 0.7 - off, c0[1] + rad * 0.7 + off)
    return None


def _capsule(ptr: int):
    new = ctypes.pythonapi.PyCapsule_New
    new.restype = ctypes.py_object
    new.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p]
    return new(ptr, None, None)


# 3D view backgrounds (Preferences): name -> (bottom, top) colours of the gradient
BACKGROUNDS = {
    "grey": ((0.20, 0.22, 0.26), (0.55, 0.58, 0.62)),
    "dark": ((0.06, 0.07, 0.09), (0.20, 0.22, 0.26)),
    "light": ((0.72, 0.75, 0.80), (0.96, 0.97, 0.98)),
    "white": ((1.0, 1.0, 1.0), (1.0, 1.0, 1.0)),
}


class OccViewport(QWidget):
    command = Signal(str)  # command text for the processor
    ready = Signal()
    edit_dimension = Signal(str)  # double-click on a sketch size: its label (C4)
    sketch_hover = Signal(str)  # status text while sketching (where the mouse is)
    body_menu = Signal(int, object)  # right click without dragging: (body under the cursor or 0, global QPoint)
    knife_changed = Signal(bool)  # the Knife tool went on or off
    sculpt_changed = Signal(bool)  # sculpting went on or off
    sculpt_stroke = Signal(int, object, object)  # (mesh body, N x 3 hit points, keyboard modifiers)

    background = "grey"

    def set_background(self, name: str) -> None:
        """The 3D view's background, one of BACKGROUNDS."""
        if name not in BACKGROUNDS:
            raise ValueError(name)
        self.background = name
        if getattr(self, "_initialized", False):
            self._apply_background()
            self.view.Redraw()

    def _apply_background(self) -> None:
        lo, hi = BACKGROUNDS.get(self.background, BACKGROUNDS["grey"])
        self.view.SetBgGradientColors(_rgb(*lo), _rgb(*hi),
                                      Aspect_GradientFillMethod.Aspect_GradientFillMethod_Vertical, True)
        ink = _rgb(0.1, 0.1, 0.1) if sum(lo) > 1.5 else _rgb(1, 1, 1)  # the axes' labels stay readable
        self.view.TriedronDisplay(Aspect_TOTP_LEFT_LOWER, ink, 0.08, V3d_ZBUFFER)

    def __init__(self, model: Model, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = model
        self.pick_mode = "FACE"
        self._ais: dict[int, AIS_Shape] = {}
        self._drawn_color: dict[int, tuple | None] = {}  # body ID -> colour it was drawn in
        self._datum_ais: list = []  # datum planes, axes, points and their labels (never pickable)
        self._clip = None  # the SECTION clip plane, if any
        self._sketch_ais: list = []  # sketch curves, points and labels (never pickable)
        self._preview_ais: list = []  # what a sketch tool is drawing
        self._mark_ais: list = []  # what the assistant points at (set_marks)
        self._path_ais = None  # MILL's milling path (show_toolpath)
        self._note_ais: list = []  # NOTE: notes pinned to the model
        self._ghost_ais: list = []  # what an editor previews (not bodies: never pickable)
        self._cp = None  # gui.point_edit.PointEditor while control points are shown (CPOINTS)
        self._cp_ais: list = []  # the control points, their net, and a dragged shape's preview
        self._an = None  # commands.analysis_handlers.Analysis while a body is shown coloured (ANALYZE)
        self._an_ais = None  # the coloured mesh drawn in place of that body
        self._an_hidden: int | None = None  # the body whose own drawing is erased meanwhile
        self._shown_active: str | None = None  # the open sketch the view last turned to
        self._mode_pending = False
        self.sketcher = None  # gui.sketch_tools.SketchController, set by the main window
        self.knife = False  # the Knife tool is on: a left drag draws a stroke to cut along
        self.knife_width = 0.0  # 0: split; more: cut a slot this wide
        self._knife_px: list[tuple[int, int]] = []
        self._knife_ais = None
        self.sculpt_on = False  # Sculpt: a left drag over a mesh body is a brush stroke
        self._sculpt_mods = Qt.NoModifier
        self.sculpt_settings = None  # the Sculpt tab's Settings (brush, radius ...), set by the tab
        self._live = None  # the stroke being dragged (sculpt_tool.LiveStroke)
        self._patch_ais = None  # on a big mesh: the moved triangles, drawn over the body while dragging
        self._topo = (None, None)  # (triangles array, its neighbour lists): kept while the triangles stay
        self._brush_ais = None  # the brush circle under the mouse
        self._mask_ais = None  # frozen areas, drawn dark over the body
        self._hover_at = 0.0
        self._initialized = False
        self._press: QPoint | None = None
        self._drag = ""  # "", "rotate", "pan", "sketch", "point" (a control point)
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
        self._apply_background()
        self.view.SetProj(_VIEWS["ISO"])
        self.view.MustBeResized()
        self._initialized = True
        if getattr(self, "_pending_section", None) is not None:
            self.set_section(self._pending_section)

        for body in self.model.bodies.values():
            self._display_body(body.id, update=False)
        self._show_datums()
        self._show_sketches()
        self._show_notes()
        self._sync_selection()
        self._draw_control_points()
        self._draw_analysis()
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
            self._sync_size()
            self.view.Redraw()

    def _sync_size(self) -> None:
        """Tell OCCT when the native window changed size (a resize can land
        before the view exists, e.g. while docks are laid out)."""
        size = self._window.Size()
        if size != getattr(self, "_known_size", None):
            self._known_size = size
            self._window.DoResize()
            self.view.MustBeResized()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._initialized:
            self._sync_size()
            self.view.Redraw()

    def _px(self, pos) -> tuple[int, int]:
        """Qt logical coordinates -> OCCT device pixels (HiDPI aware)."""
        r = self.devicePixelRatioF()
        return int(pos.x() * r), int(pos.y() * r)

    # ---- ViewHooks used by view commands ------------------------------
    def set_view(self, name: str) -> None:
        if self._initialized:
            self._sync_size()
            self.view.SetProj(_VIEWS[name])
            self.view.FitAll(0.1, False)
            self.view.Redraw()

    def fit(self) -> None:
        if self._initialized:
            self._sync_size()
            self.view.FitAll(0.1, False)
            self.view.Redraw()

    def fit_bodies(self, ids: list[int]) -> None:
        """Zoom so these bodies fill the view (FIT, b)."""
        if not self._initialized:
            return
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib

        box = Bnd_Box()
        for bid in ids:
            if bid in self.model.bodies:
                BRepBndLib.Add_s(self.model.bodies[bid].shape, box)
        if box.IsVoid():
            return
        self._sync_size()
        self.view.FitAll(box, 0.1, False)
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
        self._apply_body_event(ev)
        if self._cp is not None and ev.kind not in ("selection", "sketch_selection"):
            # (an edit removes the body and adds it back under the same ID: keep the editor)
            self._cp.refresh()
            self._draw_control_points()
        if self._an is not None and ev.kind not in ("selection", "sketch_selection"):
            self._draw_analysis()
        if self.sculpt_on and ev.kind not in ("selection", "sketch_selection"):
            self.draw_mask()

    def _apply_body_event(self, ev: Event) -> None:
        if ev.kind == "body_added":
            first = not self._ais
            self._display_body(ev.body_id, update=False)
            if first:
                self._show_datums()  # their size follows the model's
                self.view.FitAll(0.1, False)
        elif ev.kind == "body_removed":
            ais = self._ais.pop(ev.body_id, None)
            if ais is not None:
                self.context.Remove(ais, False)
        elif ev.kind == "cleared":
            self.context.RemoveAll(False)
            self._cp_ais.clear()
            self._an_ais, self._an_hidden = None, None
            self._brush_ais = self._mask_ais = self._patch_ais = None
            self._ais.clear()
            self._datum_ais.clear()
            self._sketch_ais.clear()
            self._preview_ais.clear()
            self._mark_ais.clear()
            self._path_ais = None
            self._note_ais = []
        elif ev.kind == "restored":  # undo/redo or a history replay: show the model as it is now
            self.context.RemoveAll(False)
            self._cp_ais.clear()
            self._an_ais, self._an_hidden = None, None
            self._brush_ais = self._mask_ais = self._patch_ais = None
            self._ais.clear()
            self._datum_ais.clear()
            self._sketch_ais.clear()
            self._preview_ais.clear()
            self._mark_ais.clear()
            self._path_ais = None
            for bid in self.model.bodies:
                self._display_body(bid, update=False)
            self._note_ais = []
            self._show_datums()
            self._show_sketches()
            self._show_notes()
            self._sync_selection()
            return
        elif ev.kind in ("sketch", "sketch_selection"):
            self._show_sketches()
        elif ev.kind == "datums":
            self._show_datums()
        elif ev.kind == "notes":
            self._show_notes()
        elif ev.kind == "selection":
            self._sync_selection()
            return
        elif ev.kind in ("visibility", "style"):  # one body shown, hidden, recoloured or moved to a layer
            ais = self._ais.pop(ev.body_id, None)
            if ais is not None:
                self.context.Remove(ais, False)
            if ev.body_id in self.model.bodies:
                self._display_body(ev.body_id, update=False)
            self._sync_selection()
        elif ev.kind == "layers":  # a layer switched on or off, or recoloured: redraw what changed
            for bid in list(self.model.bodies):
                ais = self._ais.get(bid)
                if ais is not None and self.model.is_shown(bid) and self._drawn_color.get(bid) == self._look(bid):
                    continue
                if ais is not None:
                    self.context.Remove(self._ais.pop(bid), False)
                self._display_body(bid, update=False)
            self._show_datums()
            self._sync_selection()
        self.context.UpdateCurrentViewer()

    def _look(self, bid: int) -> tuple:
        """What a body's drawing depends on besides its shape: colour and see-through."""
        return (self.model.display_color(bid), self.model.display_transparency(bid))

    def _display_body(self, bid: int, update: bool = True) -> None:
        if not self.model.is_shown(bid):
            return
        shape = self.model.bodies[bid].shape
        ais = AIS_Shape(shape)
        col = self.model.display_color(bid)  # own colour, else layer, else material
        self._drawn_color[bid] = self._look(bid)
        if self.model.bodies[bid].entity_ids["FACE"]:
            ais.SetMaterial(Graphic3d_MaterialAspect(Graphic3d_NameOfMaterial.Graphic3d_NameOfMaterial_Steel))
            face = col if col else (0.62, 0.66, 0.72)
            ais.SetColor(_rgb(*face))
            # (not on mesh bodies: finding a big triangulation's border costs more than drawing it)
            ais.Attributes().SetFaceBoundaryDraw(not mb.is_mesh(shape))
            # edges a darker shade of the body: panel lines and shut gaps read at any zoom
            edge = _rgb(*(0.4 * c for c in face))
            ais.Attributes().SetFaceBoundaryAspect(Prs3d_LineAspect(edge, Aspect_TypeOfLine.Aspect_TOL_SOLID, 1.0))
        else:  # a curve (path or profile): draw it bright and a little thicker
            ais.SetColor(_rgb(*col) if col else _rgb(1.0, 0.62, 0.15))
            ais.SetWidth(2.5)
        self.context.Display(ais, 1, 0, False)
        self._activate(ais)
        self._ais[bid] = ais
        if self.model.active_sketch:
            self.context.SetTransparency(ais, 0.8, False)
        elif self.model.display_transparency(bid) > 0:
            self.context.SetTransparency(ais, self.model.display_transparency(bid), False)
        if update:
            self.context.UpdateCurrentViewer()

    # ---- datums ---------------------------------------------------------
    def _show_datums(self) -> None:
        """Draw every datum: planes as see-through squares, axes as long thin
        lines, points as stars, each with its name. They are references, not
        bodies, so they are never pickable (a click goes through them)."""
        from OCP.AIS import AIS_TextLabel
        from OCP.TCollection import TCollection_ExtendedString

        from ..core import datum as dt
        from ..geometry import features as ft

        ctx = self.context
        for ais in self._datum_ais:
            ctx.Remove(ais, False)
        self._datum_ais = []
        m = self.model
        items = list(m.datums.values())
        wp = m.workplane
        if wp is not None and wp.name.upper() not in m.datums:
            items.append(wp)
        if not items:
            return
        # size: a little bigger than the model, around its middle
        shapes = [b.shape for i, b in m.bodies.items() if m.is_shown(i)]
        mid, size = (0.0, 0.0, 0.0), 20.0
        if shapes:
            from ..commands.queries import bbox

            boxes = [bbox(s) for s in shapes]
            lo = [min(b[i] for b in boxes) for i in range(3)]
            hi = [max(b[i + 3] for b in boxes) for i in range(3)]
            mid = tuple((lo[i] + hi[i]) / 2 for i in range(3))
            size = max(8.0, 0.4 * dt.norm(dt.sub(hi, lo)))
        for d in items:
            is_wp = wp is not None and d.name.upper() == wp.name.upper()
            if d.kind == "PLANE":
                shape = ft.plane_face(d, mid, size)
                ais = AIS_Shape(shape)
                ais.SetColor(_rgb(0.35, 0.85, 0.45) if is_wp else _rgb(0.35, 0.6, 1.0))
                ais.SetTransparency(0.82)
                ais.Attributes().SetFaceBoundaryDraw(True)
                u, v, _ = d.local(mid)
                at = d.point(u - size * 0.95, v + size * 0.95)
            elif d.kind == "AXIS":
                t = dt.dot(dt.sub(mid, d.origin), d.z)
                c = dt.add(d.origin, dt.mul(d.z, t))
                from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
                from OCP.gp import gp_Pnt

                p0, p1 = dt.add(c, dt.mul(d.z, -1.3 * size)), dt.add(c, dt.mul(d.z, 1.3 * size))
                shape = BRepBuilderAPI_MakeEdge(gp_Pnt(*p0), gp_Pnt(*p1)).Edge()
                ais = AIS_Shape(shape)
                ais.SetColor(_rgb(1.0, 0.85, 0.2))
                ais.SetWidth(1.5)
                at = p1
            else:
                from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
                from OCP.gp import gp_Pnt

                shape = BRepBuilderAPI_MakeVertex(gp_Pnt(*d.origin)).Vertex()
                ais = AIS_Shape(shape)
                ais.SetColor(_rgb(1.0, 0.4, 0.8))
                at = d.origin
            ctx.Display(ais, 1, 0, False)
            ctx.Deactivate(ais)
            self._datum_ais.append(ais)
            label = AIS_TextLabel()
            label.SetText(TCollection_ExtendedString(d.name + ("  (work plane)" if is_wp else "")))
            from OCP.gp import gp_Pnt

            label.SetPosition(gp_Pnt(*at))
            label.SetColor(_rgb(1, 1, 1))
            label.SetHeight(14)
            ctx.Display(label, False)
            ctx.Deactivate(label)
            self._datum_ais.append(label)

    # ---- notes ----------------------------------------------------------
    def _show_notes(self) -> None:
        """Draw the model's notes (NOTE): the text, a leader line to what it is about, and for a size the
        line between its two points with short end marks. Drawn on top, never pickable."""
        from OCP.AIS import AIS_TextLabel
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
        from OCP.Graphic3d import Graphic3d_ZLayerId_Topmost
        from OCP.TCollection import TCollection_ExtendedString
        from OCP.gp import gp_Pnt

        ctx = self.context
        for ais in self._note_ais:
            ctx.Remove(ais, False)
        self._note_ais = []
        blue = _rgb(0.05, 0.25, 0.75)

        def line(a, b):
            if sum((x - y) ** 2 for x, y in zip(a, b)) < 1e-18:
                return
            ais = AIS_Shape(BRepBuilderAPI_MakeEdge(gp_Pnt(*a), gp_Pnt(*b)).Edge())
            ais.SetColor(blue)
            ais.SetWidth(1.5)
            ctx.Display(ais, 0, -1, False)
            ctx.Deactivate(ais)
            ctx.SetZLayer(ais, Graphic3d_ZLayerId_Topmost)
            self._note_ais.append(ais)

        for n in self.model.notes:
            if n.anchor is not None:
                line(n.at, n.anchor)
            if n.span is not None:
                a, b = n.span
                line(a, b)
                d = [y - x for x, y in zip(a, b)]
                ln = sum(q * q for q in d) ** 0.5 or 1.0
                # end marks square to the size, in the plane with Z (or X for a vertical size)
                ref = (0.0, 0.0, 1.0) if abs(d[2]) < 0.9 * ln else (1.0, 0.0, 0.0)
                c = (d[1] * ref[2] - d[2] * ref[1], d[2] * ref[0] - d[0] * ref[2], d[0] * ref[1] - d[1] * ref[0])
                cl = sum(q * q for q in c) ** 0.5 or 1.0
                t = [q / cl * 0.04 * ln for q in c]
                for e in (a, b):
                    line(tuple(x - y for x, y in zip(e, t)), tuple(x + y for x, y in zip(e, t)))
            label = AIS_TextLabel()
            label.SetText(TCollection_ExtendedString(n.text, True))  # (UTF-8: the diameter sign)
            label.SetPosition(gp_Pnt(*n.at))
            label.SetColor(blue)
            label.SetHeight(15)
            ctx.Display(label, False)
            ctx.Deactivate(label)
            ctx.SetZLayer(label, Graphic3d_ZLayerId_Topmost)
            self._note_ais.append(label)
        ctx.UpdateCurrentViewer()

    # ---- sketches -------------------------------------------------------
    def _show_sketches(self) -> None:
        """Draw the open sketch (white: still free, green: fully defined,
        dashed blue: construction, orange: selected) with its sizes and
        constraint marks, and the other sketches not yet used by a feature
        as thin orange curves. Never pickable: sketch mode finds what is
        under the mouse itself, in the sketch plane."""
        ctx = self.context
        for ais in self._sketch_ais:
            ctx.Remove(ais, False)
        self._sketch_ais = []
        m = self.model
        active = m.sketches.get(m.active_sketch) if m.active_sketch else None
        for sk in m.sketches.values():
            if sk is active or sk.used_by:
                continue
            self._draw_sketch(sk, faint=True)
        if active is not None:
            preview = getattr(self.sketcher, "preview", None) if self.sketcher else None
            self._draw_sketch(preview.sketch if preview is not None and preview.sketch is not None else active)
        if m.active_sketch != self._shown_active and not self._mode_pending:
            # entering or leaving sketch mode: wait until the command (or a whole
            # history replay, which opens and closes many sketches) is done
            from PySide6.QtCore import QTimer

            self._mode_pending = True
            QTimer.singleShot(0, self._sketch_mode_changed)

    def _sketch_mode_changed(self) -> None:
        self._mode_pending = False
        m = self.model
        if m.active_sketch == self._shown_active:
            return
        self._shown_active = m.active_sketch
        active = m.sketches.get(m.active_sketch) if m.active_sketch else None
        self._dim_bodies(active is not None)
        if active is not None:
            self.turn_to(active.frame)
        if self.sketcher is not None:
            self.sketcher.reset()
        self.set_preview(None)

    def _dim_bodies(self, on: bool) -> None:
        """See-through bodies while sketching, so the sketch reads on any face."""
        for bid, ais in self._ais.items():
            back = self.model.display_transparency(bid) if bid in self.model.bodies else 0.0
            self.context.SetTransparency(ais, 0.8 if on else back, False)
        self._sync_selection()

    def _draw_sketch(self, sk, faint: bool = False) -> None:
        from OCP.AIS import AIS_TextLabel
        from OCP.Aspect import Aspect_TypeOfLine, Aspect_TypeOfMarker
        from OCP.BRep import BRep_Builder
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
        from OCP.gp import gp_Pnt
        from OCP.Prs3d import Prs3d_LineAspect, Prs3d_PointAspect
        from OCP.TCollection import TCollection_ExtendedString
        from OCP.TopoDS import TopoDS_Compound

        from ..gui.sketch_tools import dimension_geometry
        from ..sketch import profile as prof

        ctx = self.context
        sel = set(self.model.sketch_selection) if not faint else set()
        groups: dict[tuple, list] = {}
        points: dict[tuple, list] = {}
        for g in sk.geos.values():
            done = sk.fully_defined(g)
            if faint:
                style = ("faint",)
            elif str(g.n) in sel:
                style = ("sel",)
            elif g.construction:
                style = ("constr",)
            else:
                style = ("done",) if done else ("free",)
            if g.kind != "POINT":
                groups.setdefault(style, []).append(prof.edge(sk, g))
            if not faint:
                for role, i in g.pts.items():
                    name = str(g.n) if g.kind == "POINT" else f"{g.n}.{role}"
                    key = ("sel",) if name in sel or (g.kind == "POINT" and str(g.n) in sel) else (
                        ("done",) if done else ("free",))
                    points.setdefault(key, []).append(sk.frame.point(*sk.pt(i)))
        colors = {"sel": _rgb(1.0, 0.55, 0.0), "constr": _rgb(0.45, 0.7, 1.0), "done": _rgb(0.3, 0.95, 0.45),
                  "free": _rgb(0.97, 0.97, 0.97), "faint": _rgb(1.0, 0.62, 0.15)}
        b = BRep_Builder()
        for (style,), edges in groups.items():
            comp = TopoDS_Compound()
            b.MakeCompound(comp)
            for e in edges:
                b.Add(comp, e)
            ais = AIS_Shape(comp)
            width = 1.2 if style == "faint" else (3.0 if style == "sel" else 2.2)
            kind = Aspect_TypeOfLine.Aspect_TOL_DASH if style == "constr" else Aspect_TypeOfLine.Aspect_TOL_SOLID
            asp = Prs3d_LineAspect(colors[style], kind, width)
            dr = ais.Attributes()
            dr.SetWireAspect(asp)
            dr.SetFreeBoundaryAspect(asp)
            dr.SetUnFreeBoundaryAspect(asp)
            dr.SetLineAspect(asp)
            ais.SetColor(colors[style])
            ais.SetWidth(width)
            ctx.Display(ais, 0, 0, False)
            _on_top(ctx, ais)
            ctx.Deactivate(ais)
            self._sketch_ais.append(ais)
        for (style,), pts in points.items():
            comp = TopoDS_Compound()
            b.MakeCompound(comp)
            for q in pts:
                b.Add(comp, BRepBuilderAPI_MakeVertex(gp_Pnt(*q)).Vertex())
            ais = AIS_Shape(comp)
            ais.Attributes().SetPointAspect(Prs3d_PointAspect(Aspect_TypeOfMarker.Aspect_TOM_O_POINT, colors[style], 1.6))
            ctx.Display(ais, 0, 0, False)
            _on_top(ctx, ais)
            ctx.Deactivate(ais)
            self._sketch_ais.append(ais)
        if faint:
            return
        # the sketch's own axes through its origin (ORIGIN, H and V in commands)
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge as _Edge

        from ..gui.sketch_tools import _bounds

        lo_u, lo_v, hi_u, hi_v = _bounds(sk)
        pad = 0.15 * sk.extent()
        axes = TopoDS_Compound()
        b.MakeCompound(axes)
        for a, e in (((min(lo_u, 0) - pad, 0.0), (max(hi_u, 0) + pad, 0.0)),
                     ((0.0, min(lo_v, 0) - pad), (0.0, max(hi_v, 0) + pad))):
            b.Add(axes, _Edge(gp_Pnt(*sk.frame.point(*a)), gp_Pnt(*sk.frame.point(*e))).Edge())
        ais = AIS_Shape(axes)
        asp = Prs3d_LineAspect(_rgb(0.55, 0.6, 0.7), Aspect_TypeOfLine.Aspect_TOL_DOTDASH, 1.0)
        ais.Attributes().SetWireAspect(asp)
        ais.Attributes().SetLineAspect(asp)
        ais.SetColor(_rgb(0.55, 0.6, 0.7))
        ctx.Display(ais, 0, 0, False)
        _on_top(ctx, ais)
        ctx.Deactivate(ais)
        self._sketch_ais.append(ais)
        # sizes and constraint marks
        marks = {"HORIZONTAL": "H", "VERTICAL": "V", "PARALLEL": "\u2225", "PERPENDICULAR": "\u22a5", "EQUAL": "=",
                 "TANGENT": "T", "CONCENTRIC": "\u25ce", "MIDPOINT": "M", "SYMMETRIC": "S", "FIX": "\u2693"}
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge

        dim_lines = TopoDS_Compound()
        b.MakeCompound(dim_lines)
        n_dim = 0
        for c in sk.cons.values():
            if c.is_dim:
                segs, at = dimension_geometry(sk, c)
                for a, e in segs:
                    if (a[0] - e[0]) ** 2 + (a[1] - e[1]) ** 2 > 1e-18:
                        b.Add(dim_lines, BRepBuilderAPI_MakeEdge(gp_Pnt(*sk.frame.point(*a)),
                                                                  gp_Pnt(*sk.frame.point(*e))).Edge())
                        n_dim += 1
                text = {"DIAMETER": "\u2300", "RADIUS": "R", "ARCLEN": "\u2312", "MAJOR": "R", "MINOR": "R"}.get(c.kind, "") + _num(c.value) + (
                    "\u00b0" if c.kind == "ANGLE" else "")
                color = colors["sel"] if c.label in sel else _rgb(1.0, 0.9, 0.35)
                height = 15
            elif c.kind in marks and not c.auto:
                at = _mark_position(sk, c)
                if at is None:
                    continue
                text, color, height = marks[c.kind], _rgb(0.75, 0.85, 1.0), 12
            else:
                continue
            label = AIS_TextLabel()
            label.SetText(TCollection_ExtendedString(text, True))
            label.SetPosition(gp_Pnt(*sk.frame.point(*at)))
            label.SetColor(color)
            label.SetHeight(height)
            ctx.Display(label, False)
            _on_top(ctx, label)
            ctx.Deactivate(label)
            self._sketch_ais.append(label)
        if n_dim:
            ais = AIS_Shape(dim_lines)
            asp = Prs3d_LineAspect(_rgb(1.0, 0.85, 0.25), Aspect_TypeOfLine.Aspect_TOL_SOLID, 1.0)
            ais.Attributes().SetWireAspect(asp)
            ais.Attributes().SetFreeBoundaryAspect(asp)
            ais.Attributes().SetLineAspect(asp)
            ais.SetColor(_rgb(1.0, 0.9, 0.35))
            ctx.Display(ais, 0, 0, False)
            _on_top(ctx, ais)
            ctx.Deactivate(ais)
            self._sketch_ais.append(ais)

    def turn_to(self, frame) -> None:
        """Look straight at a plane, its Y up (entering a sketch)."""
        if not self._initialized:
            return
        from OCP.gp import gp_Dir

        self._sync_size()
        cam = self.view.Camera()
        cam.SetDirection(gp_Dir(*(-c for c in frame.z)))  # from the eye towards the plane
        cam.SetUp(gp_Dir(*frame.y))
        self.view.FitAll(0.1, False)
        self.view.Redraw()

    def snapshot(self, width: int, height: int, view: str = "", marks=None) -> bytes | None:
        """A PNG of the 3D view as the user sees it (or from a named view or a direction
        "dx,dy,dz", fitted), optionally with orange marks; the user's camera and marks are
        put back afterwards. None when there is no view."""
        if not self._initialized:
            return None
        import tempfile

        from OCP.Graphic3d import Graphic3d_Camera
        from OCP.Image import Image_AlienPixMap
        from OCP.TCollection import TCollection_AsciiString

        self._sync_size()
        cam = self.view.Camera()
        saved = Graphic3d_Camera()
        saved.Copy(cam)
        old_marks = [ais.Shape() for ais in self._mark_ais]
        path = ""
        try:
            name = (view or "").strip().upper()
            if name in _VIEWS:
                self.view.SetProj(_VIEWS[name])
                self.view.FitAll(0.08, False)
            elif name.count(",") == 2:
                dx, dy, dz = (float(v) for v in name.split(","))
                self.view.SetProj(dx, dy, dz)
                self.view.SetUp(0, 0, 1)
                self.view.FitAll(0.08, False)
            elif name == "FIT":
                self.view.FitAll(0.08, False)
            if marks is not None:
                self.set_marks(marks)
            self.view.Redraw()
            fd, path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            pix = Image_AlienPixMap()
            if not (self.view.ToPixMap(pix, int(width), int(height)) and pix.Save(TCollection_AsciiString(path))):
                return None
            with open(path, "rb") as f:
                return f.read()
        finally:
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass
            cam.Copy(saved)
            if marks is not None:
                self.set_marks(old_marks)
            self.view.Redraw()

    def set_marks(self, shapes) -> None:
        """Draw shapes in orange over the model (what the assistant points at); [] clears."""
        if not self._initialized:
            return
        from OCP.Aspect import Aspect_TOL_SOLID, Aspect_TOM_BALL
        from OCP.Graphic3d import Graphic3d_ZLayerId_Topmost
        from OCP.Prs3d import Prs3d_LineAspect, Prs3d_PointAspect

        ctx = self.context
        for ais in self._mark_ais:
            ctx.Remove(ais, False)
        self._mark_ais = []
        orange = _rgb(1.0, 0.45, 0.0)
        for shape in shapes:
            ais = AIS_Shape(shape)
            ais.SetColor(orange)
            ais.SetWidth(4.0)
            dr = ais.Attributes()
            for asp in (dr.WireAspect(), dr.FreeBoundaryAspect(), dr.UnFreeBoundaryAspect(), dr.LineAspect()):
                asp.SetColor(orange)
                asp.SetWidth(4.0)
            dr.SetPointAspect(Prs3d_PointAspect(Aspect_TOM_BALL, orange, 3.0))
            dr.SetFaceBoundaryDraw(True)  # outlines too: a face seen edge-on still shows
            dr.SetFaceBoundaryAspect(Prs3d_LineAspect(orange, Aspect_TOL_SOLID, 4.0))
            ais.SetTransparency(0.5)
            ctx.Display(ais, 1, -1, False)  # shaded, not pickable
            ctx.SetZLayer(ais, Graphic3d_ZLayerId_Topmost)
            self._mark_ais.append(ais)
        ctx.UpdateCurrentViewer()

    def render_nice(self, path: str, width: int, height: int, view: str = "", frames: int = 0,
                    floor: bool = True, shadows: bool = True) -> list[str]:
        """A ray-traced picture (RENDER); see viewport/nice_render.py."""
        from . import nice_render

        return nice_render.render(self, path, width, height, view, frames, floor, shadows)

    def show_toolpath(self, shape) -> None:
        """Draw a milling path (MILL) as thin cyan lines over the model; None hides it."""
        if not self._initialized:
            return
        ctx = self.context
        if self._path_ais is not None:
            ctx.Remove(self._path_ais, False)
            self._path_ais = None
        if shape is not None:
            from OCP.Prs3d import Prs3d_LineAspect
            from OCP.Aspect import Aspect_TOL_SOLID

            cyan = _rgb(0.1, 0.85, 0.95)
            ais = AIS_Shape(shape)
            asp = Prs3d_LineAspect(cyan, Aspect_TOL_SOLID, 1.5)
            for setter in ("SetWireAspect", "SetFreeBoundaryAspect", "SetLineAspect"):
                getattr(ais.Attributes(), setter)(asp)
            ais.SetColor(cyan)
            ctx.Display(ais, 0, -1, False)
            _on_top(ctx, ais)
            ctx.Deactivate(ais)
            self._path_ais = ais
        ctx.UpdateCurrentViewer()

    def set_preview(self, pv) -> None:
        """Draw what a sketch tool is making (dashed), and the point it snaps to."""
        if not self._initialized:
            return
        from OCP.Aspect import Aspect_TypeOfLine, Aspect_TypeOfMarker
        from OCP.BRep import BRep_Builder
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeVertex
        from OCP.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Pnt
        from OCP.Prs3d import Prs3d_LineAspect, Prs3d_PointAspect
        from OCP.TopoDS import TopoDS_Compound

        ctx = self.context
        for ais in self._preview_ais:
            ctx.Remove(ais, False)
        self._preview_ais = []
        m = self.model
        sk = m.sketches.get(m.active_sketch) if m.active_sketch else None
        if pv is not None and sk is not None:
            if pv.sketch is not None:  # dragging: redraw the moved copy
                self._show_sketches()
            f = sk.frame
            comp = TopoDS_Compound()
            b = BRep_Builder()
            b.MakeCompound(comp)
            n = 0
            for a, c in pv.lines:
                if (a[0] - c[0]) ** 2 + (a[1] - c[1]) ** 2 > 1e-18:
                    b.Add(comp, BRepBuilderAPI_MakeEdge(gp_Pnt(*f.point(*a)), gp_Pnt(*f.point(*c))).Edge())
                    n += 1
            for c, r in pv.circles:
                if r > 1e-9:
                    circ = gp_Circ(gp_Ax2(gp_Pnt(*f.point(*c)), gp_Dir(*f.z), gp_Dir(*f.x)), r)
                    b.Add(comp, BRepBuilderAPI_MakeEdge(circ).Edge())
                    n += 1
            for pts in pv.arcs:
                poly = BRepBuilderAPI_MakePolygon()
                for q in pts:
                    poly.Add(gp_Pnt(*f.point(*q)))
                if poly.IsDone():
                    b.Add(comp, poly.Wire())
                    n += 1
            if n:
                ais = AIS_Shape(comp)
                asp = Prs3d_LineAspect(_rgb(0.4, 0.9, 1.0), Aspect_TypeOfLine.Aspect_TOL_DOT, 1.8)
                ais.Attributes().SetWireAspect(asp)
                ais.Attributes().SetFreeBoundaryAspect(asp)
                ais.Attributes().SetLineAspect(asp)
                ais.SetColor(_rgb(0.4, 0.9, 1.0))
                ctx.Display(ais, 0, 0, False)
                _on_top(ctx, ais)
                ctx.Deactivate(ais)
                self._preview_ais.append(ais)
            for at, text in getattr(pv, "marks", []):  # constraints the click would add
                from OCP.AIS import AIS_TextLabel
                from OCP.TCollection import TCollection_ExtendedString

                label = AIS_TextLabel()
                label.SetText(TCollection_ExtendedString(text, True))
                label.SetPosition(gp_Pnt(*f.point(*at)))
                label.SetColor(_rgb(0.4, 0.9, 1.0))
                label.SetHeight(12)
                ctx.Display(label, False)
                _on_top(ctx, label)
                ctx.Deactivate(label)
                self._preview_ais.append(label)
            if pv.snap is not None:
                v = BRepBuilderAPI_MakeVertex(gp_Pnt(*f.point(*pv.snap))).Vertex()
                ais = AIS_Shape(v)
                ais.Attributes().SetPointAspect(Prs3d_PointAspect(Aspect_TypeOfMarker.Aspect_TOM_RING1,
                                                                  _rgb(1.0, 0.3, 0.9), 2.5))
                ctx.Display(ais, 0, 0, False)
                _on_top(ctx, ais)
                ctx.Deactivate(ais)
                self._preview_ais.append(ais)
        ctx.UpdateCurrentViewer()

    def set_ghosts(self, ghosts) -> None:
        """Draw shapes that are not bodies: ``(shape, kind)`` with kind "solid"
        (see-through) or "curve" (bright, drawn on top). Empty clears them."""
        if not self._initialized:
            return
        ctx = self.context
        for ais in self._ghost_ais:
            ctx.Remove(ais, False)
        self._ghost_ais = []
        for shape, kind in ghosts:
            if shape is None or shape.IsNull():
                continue
            ais = AIS_Shape(shape)
            if kind == "curve":
                ais.SetColor(_rgb(1.0, 0.25, 0.85))
                ais.SetWidth(4.0)
                ctx.Display(ais, 0, 0, False)
                _on_top(ctx, ais)
            else:
                ais.SetColor(_rgb(0.35, 0.85, 1.0))
                ctx.Display(ais, 1, 0, False)
                ctx.SetTransparency(ais, 0.55, False)
            ctx.Deactivate(ais)
            self._ghost_ais.append(ais)
        ctx.UpdateCurrentViewer()

    # ---- control points (CPOINTS) ----------------------------------------------
    def show_control_points(self, bid: int | None) -> None:
        """Show the control points of a curve or surface body so they can be dragged; None hides them."""
        from ..gui.point_edit import PointEditor

        self._cp = None
        if bid is not None and bid in self.model.bodies:
            ed = PointEditor(self.model, bid)
            self._cp = ed if ed.geometry is not None else None
        if self._initialized:
            self._draw_control_points()

    @property
    def control_points(self):
        return self._cp

    def _draw_control_points(self) -> None:
        if not self._initialized:
            return
        from OCP.Aspect import Aspect_TypeOfLine, Aspect_TypeOfMarker
        from OCP.BRep import BRep_Builder
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeVertex
        from OCP.gp import gp_Pnt
        from OCP.Prs3d import Prs3d_LineAspect, Prs3d_PointAspect
        from OCP.TopoDS import TopoDS_Compound

        ctx = self.context
        for ais in self._cp_ais:
            ctx.Remove(ais, False)
        self._cp_ais = []
        ed = self._cp
        if ed is None:
            ctx.UpdateCurrentViewer()
            return

        def compound(shapes):
            comp, b = TopoDS_Compound(), BRep_Builder()
            b.MakeCompound(comp)
            for sh in shapes:
                b.Add(comp, sh)
            return comp

        def show(shape, setup):
            ais = AIS_Shape(shape)
            setup(ais)
            ctx.Display(ais, 0, 0, False)
            _on_top(ctx, ais)
            ctx.Deactivate(ais)
            self._cp_ais.append(ais)

        segs = [BRepBuilderAPI_MakeEdge(gp_Pnt(*a), gp_Pnt(*c)).Edge()
                for a, c in ed.lines() if sum((x - y) ** 2 for x, y in zip(a, c)) > 1e-18]
        if segs:
            def net(ais):
                asp = Prs3d_LineAspect(_rgb(1.0, 0.75, 0.2), Aspect_TypeOfLine.Aspect_TOL_DASH, 1.2)
                ais.Attributes().SetWireAspect(asp)
                ais.Attributes().SetLineAspect(asp)
                ais.SetColor(_rgb(1.0, 0.75, 0.2))
            show(compound(segs), net)
        moving = ed.drag.index if ed.drag is not None else None
        for colour, which in (((1.0, 0.85, 0.1), lambda k: k != moving), ((1.0, 0.25, 0.85), lambda k: k == moving)):
            verts = [BRepBuilderAPI_MakeVertex(gp_Pnt(*q)).Vertex() for k, q in ed.points() if which(k)]
            if verts:
                def marks(ais, colour=colour):
                    ais.Attributes().SetPointAspect(Prs3d_PointAspect(Aspect_TypeOfMarker.Aspect_TOM_BALL,
                                                                      _rgb(*colour), 2.2))
                show(compound(verts), marks)
        pv = ed.preview()
        if pv is not None:
            def ghost(ais):
                ais.SetColor(_rgb(1.0, 0.25, 0.85))
                ais.SetWidth(3.0)
            show(pv, ghost)
        ctx.UpdateCurrentViewer()

    # ---- surface analysis (ANALYZE) -----------------------------------------------
    def eye_direction(self):
        """Unit direction from the model towards the eye (None before the view exists)."""
        if not self._initialized:
            return None
        v = self.view.Proj()
        return tuple(float(x) for x in v)

    def show_analysis(self, analysis) -> None:
        """Colour a body by an analysis (zebra, curvature, draft); None ends it."""
        self._an = analysis
        if self._initialized:
            self._draw_analysis()

    @property
    def analysis(self):
        return self._an

    def _draw_analysis(self) -> None:
        if not self._initialized:
            return
        ctx = self.context
        if self._an_ais is not None:
            ctx.Remove(self._an_ais, False)
            self._an_ais = None
        if self._an_hidden is not None:
            ais = self._ais.get(self._an_hidden)
            if ais is not None and not ctx.IsDisplayed(ais):
                ctx.Display(ais, 1, 0, False)
                self._activate(ais)
            self._an_hidden = None
        a = self._an
        if a is None or a.body not in self.model.bodies or not self.model.is_shown(a.body):
            ctx.UpdateCurrentViewer()
            return
        from ..geometry import analysis as an

        try:
            m = an.mesh(self.model.bodies[a.body].shape)
            rgb = an.colours(m, a.mode, a.direction, a.angle, field=getattr(a, "field", None),
                             scale=getattr(a, "scale", 0.0))
        except Exception:  # noqa: BLE001  (a picture problem must not stop the app)
            traceback.print_exc()
            ctx.UpdateCurrentViewer()
            return
        self._an_ais = _coloured_mesh(m, rgb)
        ctx.Display(self._an_ais, 0, -1, False)  # (a triangulation draws in mode 0 only)
        ctx.Deactivate(self._an_ais)
        own = self._ais.get(a.body)
        if own is not None:
            ctx.Erase(own, False)
            self._an_hidden = a.body
        ctx.UpdateCurrentViewer()

    def _ray(self, x: int, y: int):
        X, Y, Z, vx, vy, vz = self.view.ConvertWithProj(x, y)
        return (X, Y, Z), (vx, vy, vz)

    def plane_point(self, x: int, y: int):
        """Where device pixel (x, y) hits the open sketch's plane, as (u, v); None if no sketch is open."""
        m = self.model
        sk = m.sketches.get(m.active_sketch) if m.active_sketch else None
        if sk is None or not self._initialized:
            return None
        X, Y, Z, vx, vy, vz = self.view.ConvertWithProj(x, y)
        f = sk.frame
        n = f.z
        den = vx * n[0] + vy * n[1] + vz * n[2]
        if abs(den) < 1e-9:
            return None
        t = ((f.origin[0] - X) * n[0] + (f.origin[1] - Y) * n[1] + (f.origin[2] - Z) * n[2]) / den
        hit = (X + t * vx, Y + t * vy, Z + t * vz)
        u, v, _ = f.local(hit)
        return u, v

    def pixel_of(self, u: float, v: float) -> tuple[int, int]:
        """Device pixel of sketch point (u, v) of the open sketch."""
        m = self.model
        sk = m.sketches[m.active_sketch]
        return self.view.Convert(*sk.frame.point(u, v))

    def _tol(self, x: int, y: int, px: int = 9) -> float:
        a = self.plane_point(x, y)
        b = self.plane_point(x + px, y)
        if a is None or b is None:
            return 1.0
        return max(1e-9, ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5)

    def _sketching(self) -> bool:
        return self.sketcher is not None and bool(self.model.active_sketch)

    def _sketch_commands(self, cmds) -> None:
        for c in cmds:
            self.command.emit(c)

    # ---- knife ----------------------------------------------------------
    def set_knife(self, on: bool) -> None:
        """Turn the Knife tool on or off (Esc ends it)."""
        if on and self.sculpt_on:
            self.set_sculpt(False)
        self.knife = bool(on)
        self._knife_px = []
        self._draw_knife()
        self.setCursor(Qt.CrossCursor if self.knife else Qt.ArrowCursor)
        self.knife_changed.emit(self.knife)

    # ---- sculpt ---------------------------------------------------------
    def set_sculpt(self, on: bool) -> None:
        """Turn sculpting on or off (Esc ends it). The Knife goes off while it is on."""
        if on and self.knife:
            self.set_knife(False)
        self.sculpt_on = bool(on)
        self._knife_px = []
        self._live = None
        self._draw_knife()
        self._draw_brush(None)
        self.draw_mask()
        self.setCursor(Qt.CrossCursor if self.sculpt_on else Qt.ArrowCursor)
        self.sculpt_changed.emit(self.sculpt_on)

    def _topology(self, tris):
        from ..geometry import sculpt as sc

        if self._topo[0] is not tris:
            self._topo = (tris, sc.Topology.of(tris, int(tris.max()) + 1))
        return self._topo[1]

    def _sculpt_start(self, x: int, y: int, mods) -> None:
        """A press in sculpt mode: start a live stroke on the mesh body under the mouse."""
        from ..gui import sculpt_tool as st

        self._live = None
        s = self.sculpt_settings
        body = self._sculpt_target([(x, y)])
        if s is None or body is None:
            return
        shape = self.model.bodies[body].shape
        live = st.LiveStroke(body, shape, s, bool(mods & Qt.ControlModifier), bool(mods & Qt.ShiftModifier))
        live.topo = self._topology(live.tris) if live.brush != "MASK" else None
        mask = self.model.masks.get(body)
        live.mask = mask if mask is not None and len(mask) == len(live.pts0) else None
        self._live = live
        self._sculpt_move(x, y)

    def _sculpt_move(self, x: int, y: int) -> None:
        live = self._live
        if live is None:
            return
        h = live.hit(*self._ray(x, y))
        if h is None:
            return
        self._draw_brush(h, update=False)
        if live.add(h):
            if len(live.tris) >= live.BIG:
                self._draw_patch(live.patch(), live.body)
            else:
                ais = self._ais.get(live.body)
                if ais is not None:
                    ais.SetShape(live.preview())
                    self.context.Redisplay(ais, False)
        self.context.UpdateCurrentViewer()

    def _draw_patch(self, shape, bid: int | None = None) -> None:
        """The moved part of a big mesh, drawn in front of the body (None removes it)."""
        ctx = self.context
        if self._patch_ais is not None:
            ctx.Remove(self._patch_ais, False)
            self._patch_ais = None
        if shape is None:
            return
        ais = AIS_Shape(shape)
        ais.SetMaterial(Graphic3d_MaterialAspect(Graphic3d_NameOfMaterial.Graphic3d_NameOfMaterial_Steel))
        col = self.model.display_color(bid) if bid in self.model.bodies else None
        ais.SetColor(_rgb(*(col or (0.62, 0.66, 0.72))))
        ctx.Display(ais, 1, -1, False)
        ctx.Deactivate(ais)
        _on_top(ctx, ais)
        self._patch_ais = ais

    def _end_live(self, live) -> None:
        """The drag is over: take the preview away when the body did not change (Esc, a failed command)."""
        self._draw_patch(None)
        body = self.model.bodies.get(live.body)
        ais = self._ais.get(live.body)
        if live.changed and body is not None and ais is not None and body.shape.IsSame(live.shape) \
                and not ais.Shape().IsSame(live.shape):
            ais.SetShape(live.shape)
            self.context.Redisplay(ais, False)
        self.context.UpdateCurrentViewer()

    def _brush_hover(self, x: int, y: int) -> None:
        """The brush circle where the mouse is over a mesh body (at most every 30 ms)."""
        import time

        from ..geometry import meshbody as mb
        from ..gui.sculpt_tool import ray_hit

        now = time.perf_counter()
        if now - self._hover_at < 0.03:
            return
        self._hover_at = now
        body = self._sculpt_target([(x, y)])
        hit = None
        if body is not None:
            pts, tris = mb.arrays(self.model.bodies[body].shape)
            hit = ray_hit(pts, tris, *self._ray(x, y), with_normal=True)
        self._draw_brush(hit)

    def _draw_brush(self, hit, update: bool = True) -> None:
        """A circle of the brush's radius on the surface (hit = point or (point, normal); None hides it)."""
        if not self._initialized:
            return
        import numpy as np
        from OCP.AIS import AIS_Shape
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
        from OCP.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Pnt
        from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB

        ctx = self.context
        if self._brush_ais is not None:
            ctx.Remove(self._brush_ais, False)
            self._brush_ais = None
        s = self.sculpt_settings
        if hit is not None and self.sculpt_on and s is not None:
            if isinstance(hit, tuple):
                c, n = hit
            else:
                c = hit
                n = np.asarray(self._ray(0, 0)[1], dtype=float) * -1  # face the eye
            n = np.asarray(n, dtype=float)
            if np.linalg.norm(n) > 1e-12:
                circ = gp_Circ(gp_Ax2(gp_Pnt(*map(float, c)), gp_Dir(*map(float, n))), float(s.radius))
                ais = AIS_Shape(BRepBuilderAPI_MakeEdge(circ).Edge())
                ais.SetColor(Quantity_Color(0.55, 0.3, 0.9, Quantity_TOC_RGB) if s.brush == "MASK"
                             else Quantity_Color(0.2, 0.6, 1.0, Quantity_TOC_RGB))
                ais.SetWidth(2.0)
                ctx.Display(ais, False)
                ctx.Deactivate(ais)
                _on_top(ctx, ais)
                self._brush_ais = ais
        if update:
            ctx.UpdateCurrentViewer()

    def draw_mask(self) -> None:
        """While sculpting, frozen areas of mesh bodies are drawn dark over them."""
        if not self._initialized:
            return
        ctx = self.context
        if self._mask_ais is not None:
            ctx.Remove(self._mask_ais, False)
            self._mask_ais = None
        if self.sculpt_on:
            from OCP.AIS import AIS_Shape
            from OCP.BRep import BRep_Builder
            from OCP.TopoDS import TopoDS_Compound

            from ..geometry import meshbody as mb
            from ..gui.sculpt_tool import mask_overlay

            faces = []
            for bid, mask in self.model.masks.items():
                if bid in self.model.bodies and self.model.is_shown(bid):
                    shape = self.model.bodies[bid].shape
                    if mb.is_mesh(shape):
                        got = mask_overlay(*mb.arrays(shape), mask)
                        if got is not None:
                            faces.append(mb.make_shape(*got, remember=False))
            if faces:
                comp = TopoDS_Compound()
                bb = BRep_Builder()
                bb.MakeCompound(comp)
                for f in faces:
                    bb.Add(comp, f)
                ais = AIS_Shape(comp)
                ais.SetColor(_rgb(0.42, 0.2, 0.62))
                ctx.Display(ais, 1, -1, False)
                ctx.Deactivate(ais)
                ctx.SetTransparency(ais, 0.15, False)
                self._mask_ais = ais
        ctx.UpdateCurrentViewer()

    def _sculpt_target(self, px) -> int | None:
        from ..geometry import meshbody as mb

        m = self.model
        if m.selection_kind == "BODY" and len(m.selection) == 1:
            b = m.selection[0]
            if b in m.bodies and mb.is_mesh(m.bodies[b].shape):
                return b
        step = max(1, len(px) // 12)
        found = None
        for x, y in px[::step]:
            b = self.body_at(int(x), int(y))
            if b is not None and b in m.bodies and mb.is_mesh(m.bodies[b].shape):
                found = b
                break
        self.context.ClearDetected(False)  # finding it must not light the body up
        return found

    def _sculpt_done(self) -> None:
        """The stroke is finished: where its pixels meet the mesh, for the Sculpt tool."""
        import numpy as np

        from ..geometry import meshbody as mb
        from ..gui.sculpt_tool import ray_hit

        px, self._knife_px = self._knife_px, []
        self._draw_knife()
        live, self._live = self._live, None
        if live is not None:
            if len(live.hits) == 0:
                self.sketch_hover.emit(f"Sculpt: the stroke missed body {live.body}")
                self._end_live(live)
                return
            self.sculpt_stroke.emit(live.body, np.vstack(live.hits), self._sculpt_mods)
            self._end_live(live)
            return
        body = self._sculpt_target(px)
        if body is None:
            self.sketch_hover.emit("Sculpt: drag over a mesh body (TOMESH a solid first, or use Make sculptable)")
            return
        pts, tris = mb.arrays(self.model.bodies[body].shape)
        hits, last = [], None
        for x, y in px:
            if (x, y) == last:
                continue
            last = (x, y)
            h = ray_hit(pts, tris, *self._ray(int(x), int(y)))
            if h is not None:
                hits.append(h)
        if not hits:
            self.sketch_hover.emit(f"Sculpt: the stroke missed body {body}")
            return
        self.sculpt_stroke.emit(body, np.vstack(hits), self._sculpt_mods)

    def _draw_knife(self) -> None:
        """The stroke being drawn, in front of everything."""
        if not self._initialized:
            return
        from OCP.AIS import AIS_Shape
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon
        from OCP.gp import gp_Pnt
        from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB

        ctx = self.context
        if self._knife_ais is not None:
            ctx.Remove(self._knife_ais, False)
            self._knife_ais = None
        pts = self._knife_px
        if len(pts) >= 2:
            poly = BRepBuilderAPI_MakePolygon()
            last = None
            for x, y in pts:
                if (x, y) == last:
                    continue
                last = (x, y)
                poly.Add(gp_Pnt(*self._ray(int(x), int(y))[0]))
            if poly.IsDone():
                ais = AIS_Shape(poly.Shape())
                ais.SetColor(Quantity_Color(0.2, 0.6, 1.0, Quantity_TOC_RGB) if self.sculpt_on
                             else Quantity_Color(1.0, 0.2, 0.2, Quantity_TOC_RGB))
                ais.SetWidth(2.5)
                ctx.Display(ais, False)
                ctx.Deactivate(ais)
                _on_top(ctx, ais)
                self._knife_ais = ais
        ctx.UpdateCurrentViewer()

    def _knife_cut(self) -> None:
        """The stroke is finished: send the SPLINE and KNIFE for the body it crossed."""
        from ..gui import knife_tool as kt

        px, self._knife_px = self._knife_px, []
        self._draw_knife()
        m = self.model
        sel = m.selection[0] if (m.selection_kind == "BODY" and len(m.selection) == 1) else None
        body = kt.target_body(px, self.body_at, sel)
        if body is None or body not in m.bodies:
            self.sketch_hover.emit("Knife: draw the stroke across a body (or pick the body first)")
            return
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib

        box = Bnd_Box()
        BRepBndLib.Add_s(m.bodies[body].shape, box, True)
        lo, hi = box.CornerMin(), box.CornerMax()
        centre = ((lo.X() + hi.X()) / 2, (lo.Y() + hi.Y()) / 2, (lo.Z() + hi.Z()) / 2)
        for c in kt.knife_commands(px, self._ray, centre, body, self.knife_width):
            self.command.emit(c)

    # ---- section view ---------------------------------------------------
    def set_section(self, section) -> None:
        """Cut the view open along a plane (SECTION). section = (datum, side) or None."""
        if not self._initialized:
            self._pending_section = section
            return
        from OCP.Graphic3d import Graphic3d_ClipPlane
        from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

        if self._clip is not None:
            self.view.RemoveClipPlane(self._clip)
            self._clip = None
        if section is not None:
            d, side = section
            keep = d.z if side == "ABOVE" else tuple(-c for c in d.z)  # towards the half that stays
            clip = Graphic3d_ClipPlane(gp_Pln(gp_Pnt(*d.origin), gp_Dir(*keep)))
            clip.SetCapping(True)
            clip.SetCappingColor(_rgb(0.85, 0.35, 0.3))
            clip.SetOn(True)
            self.view.AddClipPlane(clip)
            self._clip = clip
        self.view.Redraw()

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
        # bodies picked in the model tree show whatever a click picks; faces,
        # edges and vertices only in their own pick mode
        if m.selection and (kind == self.pick_mode or kind == "BODY") and not m.active_sketch:
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

    def body_at(self, x: int, y: int) -> int | None:
        """The body under device pixel (x, y), whatever is being picked."""
        self.context.MoveTo(x, y, self.view, False)
        if not self.context.HasDetected():
            return None
        detected = self.context.DetectedInteractive()
        for bid, ais in self._ais.items():
            if ais is detected:
                return bid
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
        if self._sketching() and e.button() == Qt.LeftButton:
            uv = self.plane_point(x, y)
            if uv is not None and self.sketcher.tool in ("SELECT", "FREEHAND", "TRIM"):
                self.sketcher.press(*uv, self._tol(x, y))
                if self.sketcher.drag or self.sketcher.stroke is not None:
                    self._drag = "sketch"
                    return
            if self.sketcher.tool != "SELECT":
                self._drag = "pan" if e.modifiers() & Qt.ShiftModifier else ""
                return
        if self.knife and not self._sketching() and e.button() == Qt.LeftButton:
            self._knife_px = [(x, y)]
            self._drag = "knife"
            return
        if self.sculpt_on and not self._sketching() and e.button() == Qt.LeftButton:
            self._knife_px = [(x, y)]
            self._sculpt_mods = e.modifiers()
            self._drag = "sculpt"
            self._sculpt_start(x, y, e.modifiers())
            return
        if (self._cp is not None and e.button() == Qt.LeftButton
                and self._cp.press(x, y, lambda q: self.view.Convert(*q))):
            self._drag = "point"
            self._draw_control_points()
            return
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
        moved = self._press is not None and (pos - self._press).manhattanLength() > _CLICK_TOLERANCE
        if self._sketching() and (self._press is None or self._drag == "sketch"):
            uv = self.plane_point(x, y)
            if uv is not None:
                self.sketcher.no_auto = bool(e.modifiers() & Qt.ShiftModifier)
                if self._drag != "sketch" or moved:
                    pv = self.sketcher.move(*uv, self._tol(x, y))
                    self.set_preview(pv)
                self.sketch_hover.emit(f"u {uv[0]:.3f}   v {uv[1]:.3f}")
            return
        if self._drag in ("knife", "sculpt"):
            self._knife_px.append((x, y))
            if self._drag == "sculpt":
                self._sculpt_move(x, y)
            self._draw_knife()
            return
        if self.sculpt_on and self._press is None and not self._sketching():
            self._brush_hover(x, y)
            return  # no hover highlight while sculpting: the brush circle shows where it acts
        if self._drag == "point":
            if moved:
                self._cp.move(self._ray(x, y))
                self._draw_control_points()
            return
        if moved:
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
        drag, self._drag = self._drag, ""
        x, y = self._px(pos)
        if self._sketching():
            uv = self.plane_point(x, y)
            if drag == "sketch":
                stroke = self.sketcher.stroke
                moved = moved or bool(stroke and len(stroke) > 2)  # a closed stroke ends where it began
                cmds = self.sketcher.release(*uv, self._tol(x, y)) if (moved and uv is not None) else []
                self.sketcher.drag = None
                if not moved and uv is not None:
                    cmds = self.sketcher.click(*uv, self._tol(x, y), bool(e.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier)))
                self.set_preview(None)
                self._sketch_commands(cmds)
                if not cmds:
                    self._show_sketches()
                    self.context.UpdateCurrentViewer()
                return
            if not moved and e.button() == Qt.RightButton:
                self.sketcher.finish()
                self.set_preview(None)
                return
            if not moved and e.button() == Qt.LeftButton and uv is not None:
                add = bool(e.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier))
                self.sketcher.no_auto = bool(e.modifiers() & Qt.ShiftModifier)
                self._sketch_commands(self.sketcher.click(*uv, self._tol(x, y), add))
                self.set_preview(self.sketcher.move(*uv, self._tol(x, y)) if self.sketcher.tool != "SELECT" else None)
            return
        if drag == "knife":
            self._knife_px.append((x, y))
            self._knife_cut()
            return
        if drag == "sculpt":
            self._knife_px.append((x, y))
            self._sculpt_done()
            return
        if drag == "point":
            if not moved:
                self._cp.cancel()
            text = self._cp.release() if self._cp is not None else None
            self._draw_control_points()
            if text:
                self.command.emit(text)
            return
        if not moved and e.button() == Qt.LeftButton:
            self.click(x, y, e.modifiers())
        elif not moved and e.button() == Qt.RightButton:  # a right drag pans; a right click opens the menu
            bid = self.body_at(x, y)
            self.body_menu.emit(bid or 0, e.globalPosition().toPoint())

    def mouseDoubleClickEvent(self, e) -> None:
        if not (self._initialized and self._sketching() and self.sketcher.tool == "SELECT"):
            return
        x, y = self._px(e.position().toPoint())
        uv = self.plane_point(x, y)
        if uv is None:
            return
        name = self.sketcher.hit(*uv, self._tol(x, y))
        if name and name.startswith("C") and name[1:].isdigit():
            self.edit_dimension.emit(name)

    def keyPressEvent(self, e) -> None:
        if self._drag == "sculpt" and e.key() == Qt.Key_Escape and self._live is not None:
            live, self._live = self._live, None
            self._end_live(live)
        if self._drag in ("knife", "sculpt") and e.key() == Qt.Key_Escape:
            self._drag, self._press, self._knife_px = "", None, []
            self._draw_knife()
            return
        if self.knife and e.key() == Qt.Key_Escape:
            self.set_knife(False)
            return
        if self.sculpt_on and e.key() == Qt.Key_Escape:
            self.set_sculpt(False)
            return
        if self._drag == "point" and e.key() == Qt.Key_Escape:
            self._cp.cancel()
            self._drag, self._press = "", None
            self._draw_control_points()
            return
        if self._sketching() and e.key() == Qt.Key_Escape:
            self.sketcher.finish()
            self.set_preview(None)
            return
        super().keyPressEvent(e)

    def wheelEvent(self, e) -> None:
        if not self._initialized:
            return
        x, y = self._px(e.position().toPoint())
        step = int(e.angleDelta().y() / 8)
        self.view.StartZoomAtPoint(x, y)
        self.view.ZoomAtPoint(x, y, x + step, y + step)
