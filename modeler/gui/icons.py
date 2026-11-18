"""The app's toolbar icons, drawn in code so they share one style and follow
the light or dark theme.

Each icon is a few strokes on a 24 x 24 grid: lines, polylines, circles,
arcs, dots and boxes. Strokes are drawn in the theme's text colour; the part
that says what the button does (the new curve, the face that moves) is
drawn in the accent colour. Nothing has to be learned from an icon alone:
every button keeps its name next to it unless the user chooses icons only.

``icon(name)`` gives a QIcon; ``NAMES`` lists every icon (tests draw them
all). Icons are made from the application palette at the time they are
asked for, so a window built under a dark theme gets light strokes.
"""

from __future__ import annotations


from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap

# op codes: L line x1 y1 x2 y2 · P polyline [(x, y) ...] · Q closed polygon · C circle cx cy r ·
# A arc cx cy r start span (degrees, counter-clockwise as seen, as QPainter.drawArc) · E ellipse cx cy rx ry ·
# AE elliptical arc cx cy rx ry start span · D dot x y · R box x y w h ·
# a leading "*" draws the op in the accent colour, a trailing "f" fills it lightly
_BOX = [("Q", [(4, 15), (13, 19), (20, 14), (20, 7), (11, 4), (4, 8)]),
        ("P", [(4, 8), (13, 11), (20, 7)]), ("L", 13, 11, 13, 19)]

_ICONS: dict[str, list] = {
    # ---- history and files
    "undo": [("A", 13, 12, 7, 200, -200), ("P", [(2, 9), (6, 13), (10, 9)])],
    "redo": [("A", 11, 12, 7, -20, 200), ("P", [(14, 9), (18, 13), (22, 9)])],
    "commands": [("C", 10, 14, 6), ("*L", 14.5, 9.5, 20, 4)],
    "open": [("Q", [(3, 6), (9, 6), (11, 8), (21, 8), (21, 19), (3, 19)]), ("*L", 7, 12, 17, 12)],
    "save": [("Q", [(4, 4), (17, 4), (20, 7), (20, 20), (4, 20)]), ("*R", 8, 4, 8, 5), ("R", 7, 13, 10, 7)],
    "import": [("P", [(4, 14), (4, 20), (20, 20), (20, 14)]), ("*L", 12, 3, 12, 15), ("*P", [(8, 11), (12, 15), (16, 11)])],
    "export": [("P", [(4, 14), (4, 20), (20, 20), (20, 14)]), ("*L", 12, 16, 12, 4), ("*P", [(8, 8), (12, 4), (16, 8)])],
    "recover": [("A", 12, 12, 8, 90, -300), ("*P", [(12, 7), (12, 12), (15, 14)])],
    "savelog": [("R", 5, 3, 14, 18), ("*L", 8, 8, 16, 8), ("*L", 8, 12, 16, 12), ("*L", 8, 16, 13, 16)],
    "runscript": [("R", 4, 3, 13, 18), ("L", 7, 8, 13, 8), ("L", 7, 12, 11, 12), ("*Qf", [(14, 12), (21, 16), (14, 20)])],
    "clear": [("P", [(6, 7), (18, 7)]), ("Q", [(7, 7), (8, 20), (16, 20), (17, 7)]), ("L", 10, 4, 14, 4),
              ("*L", 10, 10, 10, 17), ("*L", 14, 10, 14, 17)],
    # ---- shapes
    "block": [("*Qf", _BOX[0][1])] + _BOX[1:],
    "cylinder": [("*Ef", 12, 6, 7, 2.5), ("L", 5, 6, 5, 18), ("L", 19, 6, 19, 18), ("AE", 12, 18, 7, 2.5, 180, 180)],
    "sphere": [("*Cf", 12, 12, 8), ("AE", 12, 12, 8, 2.5, 180, 180)],
    "cone": [("P", [(5, 18), (12, 3), (19, 18)]), ("*AE", 12, 18, 7, 2.5, 180, 180), ("AE", 12, 18, 7, 2.5, 0, 180)],
    "torus": [("*C", 12, 12, 9), ("C", 12, 12, 3.5)],
    # ---- booleans and patterns
    "union": [("*Cf", 9, 12, 6), ("*Cf", 15, 12, 6)],
    "subtract": [("*Cf", 9, 12, 6), ("C", 15, 12, 6)],
    "intersect": [("C", 9, 12, 6), ("C", 15, 12, 6), ("*Qf", [(12, 7.2), (13.5, 9.5), (13.5, 14.5), (12, 16.8),
                                                               (10.5, 14.5), (10.5, 9.5)])],
    "array": [("R", 3, 13, 5, 5), ("*R", 10, 13, 5, 5), ("*R", 17, 13, 5, 5), ("*R", 10, 6, 5, 5)],
    "pattern": [("C", 12, 12, 7), ("D", 12, 5), ("*D", 19, 12), ("*D", 12, 19), ("*D", 5, 12)],
    "mirror": [("L", 12, 3, 12, 21), ("Q", [(3, 7), (9, 10), (3, 17)]), ("*Q", [(21, 7), (15, 10), (21, 17)])],
    # ---- picking and the view
    "pick_body": [("*Qf", _BOX[0][1])] + _BOX[1:],
    "pick_face": _BOX + [("*Qf", [(4, 8), (13, 11), (20, 7), (11, 4)])],
    "pick_edge": _BOX + [("*L", 13, 11, 13, 19)],
    "pick_vertex": _BOX + [("*D", 13, 11)],
    "iso": _BOX + [("*D", 13, 11)],
    "top": [("R", 5, 5, 14, 14), ("*Rf", 5, 5, 14, 14)],
    "front": [("R", 5, 7, 14, 12), ("P", [(5, 7), (9, 4), (19, 4), (19, 7)]), ("*Rf", 5, 7, 14, 12)],
    "right": [("R", 5, 7, 14, 12), ("P", [(19, 7), (21, 5), (21, 17), (19, 19)]), ("*Q", [(19, 7), (21, 5), (21, 17), (19, 19)])],
    "fit": [("P", [(3, 8), (3, 3), (8, 3)]), ("P", [(16, 3), (21, 3), (21, 8)]), ("P", [(21, 16), (21, 21), (16, 21)]),
            ("P", [(8, 21), (3, 21), (3, 16)]), ("*R", 8, 8, 8, 8)],
    # ---- features
    "sketch": [("R", 3, 5, 18, 14), ("*P", [(6, 15), (10, 9), (14, 13), (18, 8)])],
    "extrude": [("Q", [(4, 18), (12, 21), (20, 18), (12, 15)]), ("*L", 12, 14, 12, 4), ("*P", [(9, 7), (12, 4), (15, 7)])],
    "revolve": [("L", 12, 2, 12, 22), ("*A", 12, 12, 8, 200, 300), ("P", [(18, 5), (20, 8), (17, 9)])],
    "sweep": [("*P", [(3, 19), (8, 12), (14, 11), (20, 5)]), ("C", 5, 17, 3), ("C", 18, 7, 3)],
    "plane": [("*Qf", [(3, 16), (9, 8), (21, 8), (15, 16)])],
    "workplane": [("Q", [(3, 18), (9, 10), (21, 10), (15, 18)]), ("*L", 12, 14, 12, 3), ("*P", [(9, 6), (12, 3), (15, 6)])],
    "hole": _BOX + [("*A", 12, 8, 3, 0, 360)],
    "shell": [("Q", [(4, 6), (20, 6), (20, 19), (4, 19)]), ("*Q", [(7, 6), (17, 6), (17, 16), (7, 16)])],
    "draft": [("L", 3, 20, 21, 20), ("*Qf", [(7, 20), (9, 5), (15, 5), (17, 20)])],
    "pushpull": [("R", 4, 12, 16, 8), ("*Rf", 7, 6, 10, 6), ("*L", 12, 2, 12, 6)],
    "delface": _BOX + [("*L", 6, 3, 18, 15), ("*L", 18, 3, 6, 15)],
    "cpoints": [("*P", [(3, 18), (8, 6), (16, 6), (21, 18)]), ("A", 12, 26, 14, 40, 100), ("*D", 8, 6), ("*D", 16, 6)],
    "knife": [("L", 4, 20, 16, 8), ("*Qf", [(13, 5), (21, 3), (19, 11)])],
    "rib": [("P", [(3, 6), (3, 20), (21, 20)]), ("*Qf", [(3, 9), (18, 20), (3, 20)])],
    "lip": [("P", [(3, 20), (3, 12), (21, 12), (21, 20)]), ("*R", 5, 8, 14, 4)],
    "wrap": [("L", 6, 3, 6, 21), ("L", 18, 3, 18, 21), ("A", 12, 3, 6, 180, 180), ("A", 12, 21, 6, 180, 180),
             ("*Pf", [(9, 8), (15, 10), (15, 15), (9, 13)])],
    "stress": [("L", 3, 4, 3, 20), ("Q", [(3, 10), (19, 12), (19, 16), (3, 16)]), ("*L", 19, 3, 19, 9),
               ("*L", 17, 7, 19, 9), ("*L", 21, 7, 19, 9)],
    "motion": [("L", 4, 20, 20, 20), ("L", 6, 20, 6, 10), ("*L", 6, 10, 18, 5), ("*A", 6, 10, 9, 0, 40)],
    # ---- sheet metal
    "sm_sheet": [("Q", [(3, 15), (10, 9), (21, 9), (14, 15)]), ("*Q", [(3, 17), (14, 17), (14, 15), (3, 15)])],
    "sm_flange": [("Q", [(3, 19), (9, 14), (18, 14), (12, 19)]), ("*P", [(12, 19), (14, 17), (14, 5)]),
                  ("*P", [(18, 14), (20, 12), (20, 2)])],
    "sm_bend": [("Q", [(2, 19), (7, 14), (14, 14), (9, 19)]), ("*L", 9, 21, 16, 12),
                ("*P", [(9, 19), (11, 17), (16, 5), (21, 5), (14, 14)])],
    "xview": [("Q", [(4, 20), (20, 20), (20, 16), (4, 16)]), ("Q", [(4, 9), (20, 9), (20, 5), (4, 5)]),
              ("*L", 8, 16, 8, 9), ("*L", 16, 16, 16, 9)],
    "member": [("Q", [(3, 20), (8, 20), (20, 8), (20, 3)]), ("*L", 3, 20, 3, 15), ("*L", 3, 15, 15, 3),
               ("*L", 15, 3, 20, 3)],
    "cutlist": [("L", 4, 5, 20, 5), ("L", 4, 10, 20, 10), ("L", 4, 15, 20, 15), ("*L", 4, 20, 14, 20)],
    "sm_unfold": [("P", [(3, 19), (12, 19), (14, 17), (14, 7)]), ("*L", 12, 19, 22, 19), ("*L", 17, 17, 17, 21)],
    # ---- sculpt brushes
    "sc_draw": [("L", 2, 18, 22, 18), ("*P", [(4, 18), (8, 13), (12, 10), (16, 13), (20, 18)])],
    "sc_clay": [("L", 2, 18, 22, 18), ("*Pf", [(4, 18), (7, 12), (17, 12), (20, 18)])],
    "sc_inflate": [("C", 12, 12, 4), ("*C", 12, 12, 8)],
    "sc_smooth": [("P", [(2, 15), (6, 11), (10, 16), (14, 10), (18, 16), (22, 12)]), ("*A", 12, 30, 14, 50, 80)],
    "sc_flatten": [("P", [(2, 16), (7, 10), (12, 16), (17, 10), (22, 16)]), ("*L", 2, 13, 22, 13)],
    "sc_pinch": [("L", 12, 4, 12, 20), ("*P", [(3, 8), (9, 12), (3, 16)]), ("*P", [(21, 8), (15, 12), (21, 16)])],
    "sc_crease": [("P", [(2, 8), (9, 8)]), ("*P", [(9, 8), (12, 19), (15, 8)]), ("P", [(15, 8), (22, 8)])],
    "sc_grab": [("L", 2, 19, 22, 19), ("*D", 9, 15), ("*L", 9, 15, 18, 6), ("*P", [(13, 6), (18, 6), (18, 11)])],
    "sc_mask": [("C", 12, 12, 8), ("*Qf", [(12, 4), (12, 20), (7, 18), (4, 12), (7, 6)])],
    "sc_sym": [("L", 12, 3, 12, 21), ("*P", [(9, 7), (4, 12), (9, 17)]), ("*P", [(15, 7), (20, 12), (15, 17)])],
    "sc_sculpt": [("C", 12, 14, 7), ("*L", 15, 3, 21, 9), ("*L", 15, 3, 12, 10)],
    "sc_mesh": [("Q", [(4, 18), (12, 4), (20, 18)]), ("L", 8, 11, 16, 11), ("L", 12, 4, 12, 18),
                ("*L", 4, 18, 20, 18)],
    "sc_fit": [("P", [(3, 18), (6, 13), (9, 15), (12, 9), (15, 12), (18, 7), (21, 10)]),
               ("*A", 12, 26, 15, 35, 110)],
    "zebra": [("C", 12, 12, 8), ("*L", 6, 8, 16, 18), ("*L", 9, 5, 19, 15)],
    "distance": [("D", 4, 12), ("D", 20, 12), ("*L", 4, 12, 20, 12), ("L", 4, 8, 4, 16), ("L", 20, 8, 20, 16)],
    "angle": [("L", 4, 19, 20, 19), ("L", 4, 19, 16, 6), ("*A", 4, 19, 10, 0, 48)],
    "mass": [("Q", [(5, 20), (8, 9), (16, 9), (19, 20)]), ("*C", 12, 6, 3)],
    "clash": [("R", 3, 9, 10, 10), ("R", 11, 5, 10, 10), ("*Rf", 11, 9, 2, 6)],
    "section": _BOX + [("*L", 2, 14, 22, 8)],
    # ---- sketch: drawing
    "s_select": [("*Qf", [(6, 3), (6, 19), (10, 15), (13, 21), (16, 20), (13, 14), (18, 14)])],
    "s_line": [("*L", 4, 18, 20, 6), ("D", 4, 18), ("D", 20, 6)],
    "s_centreline": [("*L", 3, 19, 6, 17), ("*L", 9, 15, 12, 13), ("*L", 15, 11, 18, 9), ("*L", 20, 7, 21, 6.5)],
    "s_rect": [("*R", 4, 6, 16, 12), ("D", 4, 18), ("D", 20, 6)],
    "s_crect": [("*R", 4, 6, 16, 12), ("D", 12, 12), ("D", 20, 6)],
    "s_rect3": [("*Q", [(3, 14), (13, 5), (21, 13), (11, 22)]), ("D", 3, 14), ("D", 13, 5), ("D", 21, 13)],
    "s_circle": [("*C", 12, 12, 8), ("D", 12, 12)],
    "s_circle3": [("*C", 12, 12, 8), ("D", 4, 12), ("D", 17.7, 17.7), ("D", 17.7, 6.3)],
    "s_arc": [("*A", 12, 8, 8, 0, 180), ("D", 4, 16), ("D", 20, 16)],
    "s_tarc": [("L", 3, 18, 11, 18), ("*A", 11, 11, 7, 270, 180), ("D", 11, 18)],
    "s_slot": [("*A", 7, 12, 4, 90, 180), ("*A", 17, 12, 4, -90, 180), ("*L", 7, 8, 17, 8), ("*L", 7, 16, 17, 16)],
    "s_arcslot": [("*A", 12, 20, 13, 30, 120), ("*A", 12, 20, 7, 30, 120), ("A", 12, 20, 10, 30, 120)],
    "s_polygon": [("*Q", [(12, 3), (20, 8), (20, 16), (12, 21), (4, 16), (4, 8)]), ("D", 12, 12)],
    "s_ellipse": [("*E", 12, 12, 9, 5), ("D", 12, 12), ("L", 12, 12, 21, 12)],
    "s_earc": [("*AE", 12, 14, 9, 6, 0, 180), ("D", 3, 14), ("D", 21, 14), ("L", 3, 14, 21, 14)],
    "s_circlet": [("L", 3, 20, 21, 20), ("L", 3, 4, 3, 20), ("*C", 10, 13, 7)],
    "s_offset2": [("P", [(4, 12), (20, 12)]), ("*A", 4, 12, 4, 90, 180), ("*A", 20, 12, 4, -90, 180), ("*L", 4, 8, 20, 8),
                  ("*L", 4, 16, 20, 16)],
    "s_intersect": [("Q", [(4, 8), (14, 4), (20, 8), (10, 12)]), ("L", 10, 12, 10, 20), ("L", 20, 8, 20, 16),
                    ("*L", 2, 16, 22, 16)],
    "s_join": [("L", 3, 18, 9, 9), ("A", 13, 12, 4, 0, 180), ("*P", [(3, 19), (6, 12), (10, 8), (14, 7), (18, 9),
               (21, 14)]), ("D", 9, 9), ("D", 17, 12)],
    "s_auto": [("L", 3, 19, 13, 9), ("*A", 13, 15, 6, 30, 120), ("*D", 13, 9), ("L", 15, 4, 21, 4), ("L", 18, 1, 18, 7)],
    "d_arclen": [("*A", 12, 16, 9, 20, 140), ("L", 4, 18, 7, 13), ("L", 20, 18, 17, 13)],
    "s_point": [("*D", 12, 12), ("L", 12, 5, 12, 8), ("L", 12, 16, 12, 19), ("L", 5, 12, 8, 12), ("L", 16, 12, 19, 12)],
    "s_freehand": [("*P", [(3, 16), (6, 9), (9, 13), (12, 6), (15, 15), (18, 9), (21, 12)])],
    # ---- sketch: editing
    "s_trim": [("L", 12, 3, 12, 21), ("L", 3, 12, 12, 12), ("*L", 12, 12, 21, 12), ("*L", 15, 9, 19, 15)],
    "s_extend": [("L", 20, 3, 20, 21), ("L", 3, 12, 12, 12), ("*L", 12, 12, 20, 12), ("*P", [(16, 9), (19, 12), (16, 15)])],
    "s_fillet": [("L", 4, 4, 4, 12), ("L", 12, 20, 20, 20), ("*A", 12, 12, 8, 180, 90)],
    "s_chamfer": [("L", 4, 4, 4, 13), ("L", 11, 20, 20, 20), ("*L", 4, 13, 11, 20)],
    "s_split": [("L", 3, 12, 10, 12), ("L", 14, 12, 21, 12), ("*D", 10, 12), ("*D", 14, 12), ("*L", 12, 5, 12, 9),
                ("*L", 12, 15, 12, 19)],
    "s_corner": [("L", 5, 19, 5, 14), ("L", 10, 5, 15, 5), ("*L", 5, 14, 5, 5), ("*L", 5, 5, 10, 5), ("*D", 5, 5)],
    "s_axes": [("L", 12, 3, 12, 21), ("L", 3, 12, 21, 12), ("*A", 12, 12, 6, 0, 90)],
    "s_offset": [("P", [(4, 20), (4, 8), (16, 8)]), ("*P", [(8, 20), (8, 12), (16, 12)])],
    "s_mirror": [("L", 12, 3, 12, 21), ("P", [(3, 6), (9, 12), (3, 18)]), ("*P", [(21, 6), (15, 12), (21, 18)])],
    "s_pattern": [("C", 6, 12, 3), ("*C", 12, 12, 3), ("*C", 18, 12, 3)],
    "s_project": [("Q", [(4, 4), (14, 4), (20, 9), (10, 9)]), ("*L", 6, 12, 18, 12), ("L", 9, 9, 9, 12),
                  ("*Q", [(4, 15), (14, 15), (20, 20), (10, 20)])],
    "s_move": [("L", 12, 3, 12, 21), ("L", 3, 12, 21, 12), ("*P", [(9, 6), (12, 3), (15, 6)]),
               ("*P", [(18, 9), (21, 12), (18, 15)]), ("*P", [(9, 18), (12, 21), (15, 18)]), ("*P", [(6, 9), (3, 12), (6, 15)])],
    "s_construction": [("*L", 3, 20, 6, 17), ("*L", 9, 14, 12, 11), ("*L", 15, 8, 18, 5), ("C", 12, 12, 7)],
    "s_delete": [("*L", 6, 6, 18, 18), ("*L", 18, 6, 6, 18)],
    "s_finish": [("*P", [(4, 13), (10, 19), (20, 5)])],
    # ---- sketch: constraints and sizes
    "c_coincident": [("L", 3, 18, 12, 12), ("L", 12, 12, 21, 18), ("*C", 12, 12, 2.5)],
    "c_horizontal": [("*L", 3, 12, 21, 12), ("L", 6, 8, 6, 16), ("L", 18, 8, 18, 16)],
    "c_vertical": [("*L", 12, 3, 12, 21), ("L", 8, 6, 16, 6), ("L", 8, 18, 16, 18)],
    "c_parallel": [("L", 4, 16, 16, 4), ("*L", 8, 20, 20, 8)],
    "c_perpendicular": [("L", 4, 20, 20, 20), ("*L", 10, 20, 10, 4), ("P", [(10, 15), (15, 15), (15, 20)])],
    "c_tangent": [("C", 12, 10, 6), ("*L", 2, 16, 22, 16)],
    "c_equal": [("*L", 5, 9, 19, 9), ("*L", 5, 15, 19, 15)],
    "c_midpoint": [("L", 3, 16, 21, 16), ("*D", 12, 16), ("*L", 12, 6, 12, 12)],
    "c_symmetric": [("L", 12, 3, 12, 21), ("*D", 5, 12), ("*D", 19, 12), ("L", 7, 12, 10, 12), ("L", 14, 12, 17, 12)],
    "c_concentric": [("C", 12, 12, 9), ("*C", 12, 12, 4.5), ("D", 12, 12)],
    "c_fix": [("Q", [(9, 3), (15, 3), (14, 12), (10, 12)]), ("*L", 12, 12, 12, 21), ("L", 6, 12, 18, 12)],
    "d_size": [("L", 4, 6, 4, 18), ("L", 20, 6, 20, 18), ("*L", 4, 12, 20, 12), ("*P", [(7, 9), (4, 12), (7, 15)]),
               ("*P", [(17, 9), (20, 12), (17, 15)])],
    "d_across": [("L", 4, 4, 4, 20), ("L", 20, 10, 20, 20), ("*L", 4, 17, 20, 17), ("*P", [(7, 14), (4, 17), (7, 20)]),
                 ("*P", [(17, 14), (20, 17), (17, 20)])],
    "d_up": [("L", 4, 20, 20, 20), ("L", 10, 4, 20, 4), ("*L", 7, 4, 7, 20), ("*P", [(4, 7), (7, 4), (10, 7)]),
             ("*P", [(4, 17), (7, 20), (10, 17)])],
}

NAMES = tuple(_ICONS)


def _colours() -> tuple[QColor, QColor, bool]:
    app = QGuiApplication.instance()
    pal = app.palette() if app is not None else QPalette()
    ink = pal.color(QPalette.WindowText)
    dark = pal.color(QPalette.Window).lightness() < 128
    accent = QColor("#6aa8ff") if dark else QColor("#1f6fd1")
    return ink, accent, dark


def _pt(x: float, y: float, s: float) -> QPointF:
    return QPointF(x * s, y * s)


def draw(p: QPainter, name: str, size: float, ink: QColor, accent: QColor) -> None:
    """Draw icon ``name`` into a size x size square of the painter."""
    s = size / 24.0
    for op in _ICONS[name]:
        code = op[0]
        acc = code.startswith("*")
        code = code.lstrip("*")
        fill = code.endswith("f") and len(code) > 1
        code = code[:-1] if fill else code
        colour = accent if acc else ink
        pen = QPen(colour, 1.7 * s, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        if fill:
            soft = QColor(colour)
            soft.setAlpha(70)
            p.setBrush(soft)
        else:
            p.setBrush(Qt.NoBrush)
        a = op[1:]
        if code == "L":
            p.drawLine(_pt(a[0], a[1], s), _pt(a[2], a[3], s))
        elif code in ("P", "Q"):
            path = QPainterPath(_pt(*a[0][0], s))
            for q in a[0][1:]:
                path.lineTo(_pt(*q, s))
            if code == "Q":
                path.closeSubpath()
            p.drawPath(path)
        elif code == "C":
            p.drawEllipse(_pt(a[0], a[1], s), a[2] * s, a[2] * s)
        elif code == "A":
            cx, cy, r, start, span = a
            rect = QRectF((cx - r) * s, (cy - r) * s, 2 * r * s, 2 * r * s)
            p.drawArc(rect, int(start * 16), int(span * 16))
        elif code == "E":
            p.drawEllipse(_pt(a[0], a[1], s), a[2] * s, a[3] * s)
        elif code == "AE":
            cx, cy, rx, ry, start, span = a
            p.drawArc(QRectF((cx - rx) * s, (cy - ry) * s, 2 * rx * s, 2 * ry * s), int(start * 16), int(span * 16))
        elif code == "D":
            p.setBrush(colour)
            p.drawEllipse(_pt(a[0], a[1], s), 1.9 * s, 1.9 * s)
        elif code == "R":
            p.drawRect(QRectF(a[0] * s, a[1] * s, a[2] * s, a[3] * s))
        else:  # pragma: no cover - a typo in the table
            raise ValueError(f"icon {name}: unknown op {op[0]}")


def pixmap(name: str, size: int = 24, scale: float = 2.0) -> QPixmap:
    ink, accent, _ = _colours()
    pm = QPixmap(int(size * scale), int(size * scale))
    pm.setDevicePixelRatio(scale)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    draw(p, name, size, ink, accent)
    p.end()
    return pm


_cache: dict[tuple[str, bool], QIcon] = {}


def icon(name: str) -> QIcon:
    """The icon for ``name`` in the current theme (an empty icon for an unknown name)."""
    if name not in _ICONS:
        return QIcon()
    _, _, dark = _colours()
    key = (name, dark)
    if key not in _cache:
        ic = QIcon()
        for size in (16, 24, 32):
            ic.addPixmap(pixmap(name, size))
        _cache[key] = ic
    return _cache[key]


# How toolbar buttons show: the setting's value -> Qt's style
STYLES = {
    "under": Qt.ToolButtonTextUnderIcon,
    "beside": Qt.ToolButtonTextBesideIcon,
    "icons": Qt.ToolButtonIconOnly,
    "names": Qt.ToolButtonTextOnly,
}
STYLE_LABELS = {
    "under": "Icons with names under them",
    "beside": "Icons with names beside them",
    "icons": "Icons only (names in the tooltips)",
    "names": "Names only",
}

