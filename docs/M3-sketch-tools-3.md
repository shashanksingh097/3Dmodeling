# Sketch tools, part 3: ellipses, constraints while drawing, and the rest

The second part of PLAN.md item 7, after docs/M3-sketch-tools-2.md. The
commands are in LANGUAGE.md section 16; this note is about how they work.

| Command | Tool / button | Does |
|---------|---------------|------|
| `SELLIPSE`, `SEARC` | Ellipse (I), Elliptical arc | ellipses and elliptical arcs |
| `SDIM, MAJOR / MINOR` | Size… | an ellipse's two radii |
| `SDIM, ARCLEN` | Arc length… | the length along an arc or elliptical arc |
| `SDIM, DIST, point, circle` | Size… | how far a point is from a circle's rim |
| `SCIRCLET` | Tangent circle | a circle touching two curves (with a radius) or three |
| `SOFFSET2` | Offset both… | a slot along a path, or an outline inside and outside |
| `SINTERSECT` | Cut bodies… | where bodies cut the sketch plane, as fixed curves |
| (made while drawing) | Auto constraints | ON, TANGENT, PERPENDICULAR from where you click |

## Ellipses

* Stored as the centre `C`, the end of the first axis `A` (a point, so the
  axis can be dragged, made level with `SCON, HORIZONTAL, n.C, n.A`, or
  sized with `MAJOR`) and the second radius (one number, like a circle's
  radius). An elliptical arc (`EARC`) adds its ends `S` and `E`, which a
  built-in rule keeps on the ellipse. Five degrees of freedom, seven for an
  arc.
* Positions round it are the parametric angle t (degrees): C + a cos t
  along the axis + b sin t across. The arc runs counter-clockwise from S to
  E. `sketch/ellipse.py` has the plain 2D math (frame, point, parameter,
  nearest point, crossings with lines, circles and other ellipses).
* "On the ellipse" is the distance along the ray from the centre, scaled:
  (k − 1)·r where k = √((x/a)² + (y/b)²). It is exact on the curve, smooth,
  and has a clean slope there, which the solver needs.
* A line tangent to an ellipse: the centre's distance from the line equals
  the ellipse's reach across it, √((a·n·x̂)² + (b·n·ŷ)²), on the side the
  centre was on when the constraint was added.
* OCCT wants the bigger radius first in `gp_Elips`; when the second radius
  is bigger the frame is turned a quarter and the angles with it.
* Trimming a whole ellipse makes an elliptical arc in place (like a circle
  becomes an arc). Pieces of one ellipse (trim in the middle, split) are
  held together by the same centre, the same axis point and `EQUAL` (both
  radii), not by a point ON the other piece: at the ends of the major axis a
  point ON both ellipses does not fix the second radius.
* Not for ellipses yet: fillet, chamfer, offset, corner, and tangency to a
  circle or another ellipse. The messages say so.

## Constraints made while drawing

* The controller (`gui/sketch_tools.py`) works out what a click would add:
  `on_curve` (a click on a curve, not on a point, goes onto it and adds
  `SCON, ON`), and for the Line tool `line_relation` (drawn on from the end
  of an arc or elliptical arc along it: `TANGENT`; turning square off the
  line before: `PERPENDICULAR`). Level and upright lines keep their H / V.
* `Preview.marks` carries the words shown by the cursor before the click
  (On 3, Tangent, Perpendicular, H, V); the viewport draws them as small
  labels.
* The relations are plain `SCON` lines sent after the drawing line, so
  undo, the history and scripts see ordinary steps.
* Shift held (`no_auto`) or the **Auto constraints** switch (`auto`) turns
  them off.

## Tangent circle, offset both sides, sections

* `SCIRCLET` puts a circle at the clicked place, adds the TANGENT
  constraints (and the RADIUS with two curves), then first solves for the
  new circle alone with everything else held (so the curves it touches do
  not move), then the whole sketch. Which of the possible circles you get
  is the one nearest the place, inside or outside as it starts.
* `SOFFSET2` is two `SOFFSET` chains (held by OFFSET constraints) and, for
  an open path, a cap at each end: a half circle centred on the path's end
  (COINCIDENT with it) through the two offset ends, or a straight line with
  `FLAT`. The path becomes construction geometry.
* `SINTERSECT` cuts each body with the sketch plane (`BRepAlgoAPI_Section`),
  lays the edges in the sketch like `SPROJECT` (now also ellipses), fixes
  them and ties ends that meet, so a closed section is a profile at once.

## Left for later (PLAN.md item 7)

Join and convert to a spline, trim and extend for splines, a fillet between
a spline and a line, and an offset of a chain that crosses itself.
