# More sketch tools and the grouped toolbars

PLAN.md items 7 (first part) and 8, asked for by the user after the M3
leftovers. Commands are in LANGUAGE.md section 16; the user guide has the
mouse tools.

## What was added

| Command | Mouse tool | Code |
|---------|------------|------|
| `SCHAMFER` | Chamfer (K): click a corner | `sketch/edit_more.py` `chamfer` |
| `SSPLIT` | Split (B): click where (a circle: twice) | `split` |
| `SCORNER` | Corner (O): click the part of each curve to keep | `corner` |
| `STRIM` with several pieces | Trim (T): drag across pieces | `trim_many` |
| `STRANSFORM` | **Move/Copy…** button | `transform` |
| `SARCT`, `SCIRCLE3`, `SRECTC`, `SRECT3`, `SNGON`, `SSLOTARC` | Tangent arc, 3-point circle, Centre rect, Angled rect, Polygon, Arc slot | `sketch/draw.py` |
| `SLINE, ..., CONSTR` | Centreline | - |

The commands are in `commands/sketch_more_handlers.py`; the mouse tools in
`gui/sketch_tools.py` (Qt-free, tested headless in `tests/test_sketch_more.py`).

## Design

* **Chamfer** shares the fillet's way of keeping a corner
  (`edit_more._keep_corner`): the corner becomes a construction point on
  both lines, constraints on the corner move to it, and a length to the
  corner becomes a distance to it. The sizes are two `DIST` dimensions from
  that point (or a `DIST` and an `ANGLE`). Each records in `data["arg"]`
  which argument of the `SCHAMFER` line it came from (counted from the end),
  so double-click editing and **Sizes of sketch** change the right number;
  `sketch_tools.dimension_edit` takes that index.
* The chamfer line is drawn so that its angle to the first line reads as the
  angle asked for (it runs away from the corner when the corner is the first
  line's end, towards it otherwise), so the `ANGLE` dimension shows 30, not
  150.
* **Split** keeps the pieces in one chain (coincident ends) and on the
  original line (`ON`) or circle (`COINCIDENT` centres). A circle split at
  k places becomes k arcs. A split made by a crossing curve keeps the split
  points `ON` it.
* **Corner** chooses which end of each curve moves: the side away from the
  click (the part clicked is kept), or without clicks the end nearer the
  crossing. With several crossings (a line and an arc) the one that moves
  the ends least, and is nearest the clicks, wins.
* **Power trim** is one `STRIM` with several (curve, point) picks, so it is
  one history step and one undo. Picks run in order; a curve cut in the
  middle by an earlier pick lives on as two curves, and a later pick on it
  goes to whichever is under its point. The mouse tool walks the dragged
  path in steps of under half the snap distance and keeps one pick per
  distinct piece.
* **STRANSFORM** moves the points of the geometry and takes along the
  constraints whose every reference is in the selection. Ties to the rest of
  the sketch (other curves, the origin, the axes) are dropped and named. A
  turn by a quarter swaps `HORIZONTAL`/`VERTICAL` and `HDIST`/`VDIST`; any
  other turn drops them. A scale multiplies the sizes. A copy re-adds the
  internal constraints on the new geometry (their sides are read again from
  the copy) and is not held to the original, unlike `SPATTERN`.
* **Polygon**: corners `ON` a construction circle plus equal sides. With
  `OUT` the sides must touch the given circle; equal sides that only touch a
  circle can still lean (for an even count, tangent lengths can alternate),
  so a second construction circle through the corners keeps it regular.
* **Arc slot**: a construction middle arc, outer and inner arcs concentric
  with it, round ends centred on its ends and tangent to both sides, and the
  two ends equal: 6 degrees of freedom (centre, radius, two angles, width).
* Degrees of freedom: numbers no geometry uses any more (a deleted curve, a
  circle turned into arcs) are now treated as fixed by the solver, so the
  sketch's count is right after a trim or split of a circle.

## Toolbars

* The groups live on ribbon tabs (`gui/toolbars.py`, class `Ribbon`, a
  `QTabWidget` in one fixed toolbar at the top), so all the buttons take
  the height of one row. The first version put each group in a toolbar of
  its own, which took four rows with icons; the user asked for tabs.
  Each group is a `QToolBar` with its name in small grey text under it and
  a thin line after it. Tabs: Home (File, Edit, Pick, View), Model
  (Shapes, Booleans, Patterns), Features (Sketch, Datums, Features),
  Freeform, Inspect (Measure). In sketch mode three tabs appear and the
  first is opened: Sketch (Sketch draw), Sketch edit, Constrain
  (Constraints and Sizes); closing the sketch hides them and goes back to
  the tab used before.
* Quick-access icons at the right of the tab names (Undo, Redo, the four
  pick modes, Fit) stay in reach on every tab; they are the same actions as
  on Home.
* Double-click a tab, or **View > Collapse ribbon**, folds the ribbon to its
  tab names; clicking a tab then opens it for one use. **View > Ribbon tab**
  jumps to a tab. The open tab and the fold are kept in the settings
  (`ribbonTab`, `ribbonCollapsed`).
* `gui/icons.py` draws every icon in code from a small table of strokes on
  a 24 x 24 grid, in the palette's text colour with one accent colour for
  the part that matters, so one style covers light and dark themes. Icons
  are made when the window is built; a theme switch while running (M8
  preferences) will need them made again.
* **View > Toolbar buttons**: icons with names under or beside them, icons
  only (names in the tooltips) or names only. Saved in the settings
  (`toolbarButtons`).
* New buttons: Cone, Torus, Union, Subtract, Intersect, Array, Pattern,
  Mirror (forms), and Fillet and Chamfer (3D edges, forms).

## Left for later (PLAN.md item 7)

Ellipse and elliptical arc (a new curve kind for the solver, profiles and
trimming), circle tangent to curves, join and convert to a spline, offset
both sides with caps, trim and extend for splines, arc-length and
point-to-circle sizes, the intersection curve, and constraints made while
drawing.
