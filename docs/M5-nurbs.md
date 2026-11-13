# M5: NURBS freeform

Part 1 adds freeform modeling with control points; part 2 adds blends,
extending and trimming surfaces, and moving or replacing faces. The language
is in LANGUAGE.md section 24 (and section 20 for `MOVEFACE`/`REPLACEFACE`).
What is left of M5 is listed at the end.

## What was built

| Item (PLAN.md 5.3) | Commands | Code |
|---|---|---|
| NURBS curves: control points, degree, weights, knots | `NURBS`, `MOVEPT`, `WEIGHT`, `KNOT`, `DEGREE`, `REBUILD`, `POLES`, `POLE()`, `NPOLES()` | `geometry/nurbs.py`, `commands/nurbs_handlers.py` |
| NURBS surfaces: control net, network of curves, patch, sew to solid | `NSURF`, `NETWORK`, `FILL`, `SEW` | same |
| Control-point editing in the viewport | `CPOINTS`, the Control points button; a drag runs `MOVEPT` | `gui/point_edit.py` (no Qt), `viewport/occ_view.py` |

Every command has a form (Commands menu, "Freeform (NURBS)"), except
`CPOINTS`, which is the toolbar button.

## Design

- **Bodies stay plain shapes.** A NURBS curve is a wire of one B-spline
  edge, a surface is one face. Nothing extra is stored: an edit reads the
  B-spline back from the shape (`curve_of`, `surface_of`), changes a copy
  and makes a new shape. Lines, arcs and untrimmed faces are converted to
  their exact B-spline on the way, so every curve can be edited.
- **IDs survive edits.** The new shape is built the same way as the old one,
  so faces, edges and vertices match by position (`SameTopology`), and
  `Model.replace(..., same_id=True)` keeps the body's ID. Later steps that
  use the body or its picked edges keep working.
- **Trimmed faces are refused** for point edits: moving a pole would pull
  the surface away from its edges. `REBUILD` refits such a face over its
  whole parameter box.
- **`REBUILD`** is our own least-squares fit (numpy, Cox-de Boor basis):
  the kernel's approximation cannot be told how many control points to use.
  Closed curves get a periodic fit; the kernel counts periodic poles from
  its own start, so the fit tries each shift and keeps the one that matches.
- **`NETWORK`** is the Gordon construction, sampled: loft through the u
  curves + loft through the v curves - the surface through their crossing
  points, using natural cubic spline blending and a shape-keeping cubic to
  map each curve's own parameter onto the network's. The sum is sampled on
  a 41 x 41 grid and interpolated with one B-spline surface, so it passes
  through every curve at the samples (tested within 0.02 on a 20 mm
  network). Crossings are found by sampling both curves and refining.
- **`FILL`** is OCCT's plate filling (`BRepOffsetAPI_MakeFilling`) with 24
  points per curve and 4 iterations. A picked edge brings its face, so G1/G2
  are measured and reported.
- **Dragging** moves a point in the plane through it facing the screen (the
  mouse ray meets that plane). The preview is the shape rebuilt from a copy
  of the B-spline on each mouse move; the history only gets the one
  `MOVEPT` on release, with the distance rounded to 4 decimals.

## Gotchas

- `GeomAbs_G2` is 3, but the plate solver reads the continuity as an order
  0, 1 or 2 and throws "The continuity is not G0 G1 or G2". G2 is passed as
  `GeomAbs_C1` (= 2). G2 then works; it reaches about 0.003 degrees in
  normals and a curvature mismatch around 0.1 on the test case.
- OCP 7 has no copy constructor for `Geom_BSplineCurve`/`Surface`.
  `GeomConvert.CurveToBSplineCurve_s` / `SurfaceToBSplineSurface_s` return a
  copy when given a B-spline, so `nurbs.copy()` uses them.
- `BRep_Tool.Curve_s(edge, first, last)` returns only the curve in OCP 8
  (the range comes from `BRep_Tool.Range_s(edge)`).
- A line's curve is endless: trim it to the edge's range before converting.
- An edit removes the body and adds it back, so the viewport's point editor
  must not drop the body when it briefly disappears.
- The corpus check used to call every non-solid body bad; an open surface
  now only has to be valid.

## Part 2: blends, extend, trim, move and replace faces

| Item | Commands | Code |
|---|---|---|
| Blend between surfaces with G1/G2 | `BLEND` | `geometry/surface_ops.py`, `commands/surface_handlers.py` |
| Extend, offset, trim by curves | `EXTEND`, `TRIM` (`OFFSET` already worked on surfaces) | same |
| Move a face by a vector, replace a face | `MOVEFACE`, `REPLACEFACE` | same |

- **`BLEND`** is exact across the gap: at each of 61 stations along the
  edges it is a Bezier curve (cubic for G1, quintic for G2) whose end
  derivatives come from the surfaces: the derivative across the edge for
  G1, and also the second derivative for G2 (scaled together so the
  curvature is kept). Along the edges, each row of Bezier control points is
  interpolated with the same parameters, so the rows share one knot vector
  and make one B-spline surface. Measured on the test panels: normals meet
  within 0.02 degrees; G2 matches the panel's curvature to 3e-5 where G1 is
  off by 0.035.
- Which way is "out of the face" is asked of the face (a classifier) only
  at the middle of the edge; the other stations follow their neighbour. At
  an edge's end a small step can leave the face either way past the
  corner, which flipped the end rows of the first version.
- **`EXTEND`** evaluates the B-spline past its ends (the end spans carry
  on) and refits; the kernel's `GeomLib::ExtendSurfByLength` replaces its
  handle argument, which a Python binding cannot hand back.
- **`TRIM`** projects the curve with `BRepOffsetAPI_NormalProjection` and
  splits with `BRepFeat_SplitShape`; the piece nearest the point is removed
  or kept.
- **`MOVEFACE` / `REPLACEFACE`**: grow the solid with a prism of the face
  along its outward normal if the new surface lies outside, then split it
  with the new surface (`BRepAlgoAPI_Splitter`) and keep the one piece on
  the solid's side; the surface is extended on all sides only if it does
  not cut cleanly as given. Face IDs come from geometry (`SurfaceMatch`):
  every old face goes to the new faces lying on its surface, the replaced
  face to those on the new surface. The boolean makers' own history
  scrambled them.

Part 2 gotchas:

- `BRepLProp_SLProps.MeanCurvature()` returns 0 unless
  `IsCurvatureDefined()` was called first (that call computes them).
- A half-space cut by a big curved face gave garbage on a wavy surface; the
  splitter with a side test is reliable.

## Part 3: guide-curve lofts, sweeps on a surface, analysis

| Item | Commands | Code |
|---|---|---|
| Loft with guide curves | `LOFT, ..., GUIDE, g1, g2` | `geometry/sweep.py` (`guide_loft`) |
| Sweep following a surface's normal | `SWEEP ... NORMAL, ..., surface`, `PROJECT` | `geometry/sweep.py` (`OnSurface`), `geometry/surface_ops.py` (`project`) |
| Zebra, curvature and draft analysis | `ANALYZE`, the Zebra button | `geometry/analysis.py`, `commands/analysis_handlers.py`, viewport |

- **Guide lofts** are built from point columns: each section is cut where
  the guides cross it, every piece gets the same number of points on every
  section, and each column is a cubic through the sections. A guide's own
  column is then replaced by the guide, and the columns between two guides
  move by a smoothstep blend of the two guides' corrections (so the side is
  C1 across a guide). Round closed sections each guide's pull is split into
  a scale about the section's centre and a slide, and those are blended
  instead: blending the plain pulls shifted a vase sideways where it had no
  guide, rather than letting it swell all round. Station curves
  (6 to 24 per span, by how much the guides turn) go to `ThruSections`.
  Measured: guides followed within 0.003 on a 40 long vase, sections within
  1e-3.
- **`NORMAL` sweeps**: the exact sweep uses `BRepOffsetAPI_MakePipeShell.
  SetMode(support)`, which needs the path's edges to have curves on the
  surface. A `PROJECT` result has them; a path made on its own does not, and
  `SetMode` returns False. Then the sweep goes through sections whose frames
  take the surface normal at each station (`frames()` with an `OnSurface`
  mode), turned so the first frame is the usual start frame, as `FRENET`
  does.
- **Analysis in words**: joins are judged along each edge between two
  faces at 9 points: the angle between normals (crease above 0.25 degrees),
  then the normal curvature straight across the edge on each side (from the
  principal curvatures and their directions; G1 if they differ by more than
  10%). Checked on the test panels: a G1 blend comes out "tangent only", a
  G2 blend "smooth in curvature".
- **Colours**: a fine mesh of each face (a copy, so the model's own
  triangulation is untouched) with normals and curvatures at the nodes,
  drawn as an `AIS_Triangulation` with node colours in place of the body.

Part 3 gotchas:

- `AIS_Triangulation` draws only in display mode 0; displayed in the
  context's default shaded mode (1) it shows nothing.
- Its default material tints node colours gold; set a white plastic
  shading aspect.
- `Poly_Triangulation.SetNormal` takes a `gp_Dir` in both OCP 7 and 8
  (`gp_Vec3f` exists only in OCP 7's `gp`).
- Zebra stripes need about 5 mesh nodes per stripe period: 24 stripes over
  180 degrees with an angular mesh deflection of 0.05 rad.


## Part 4: deformers and swept volumes

`BEND`, `TWIST`, `TAPER`, `STRETCH` and `FLOW` (commands/deform_handlers.py)
are point maps run through one engine (geometry/deform.py); `SWEEPVOL` is
geometry/sweptvol.py.

- **The engine** copies the body and turns it into NURBS
  (`BRepBuilderAPI_NurbsConvert`), then edits every surface and edge curve
  *in place*: raise the degree to 3, make it non-periodic, insert knots so
  each direction has 8 spans. It then moves the control points so the
  surface goes through the mapped points at the Greville points (the same
  knots and weights; rational surfaces are solved in homogeneous form and
  divided back). The error is measured at span midpoints; where it is above
  1e-4 of the body's size the spans double, up to 64. Knot insertion keeps
  the parameterisation, so the pcurves on each face stay valid, and as the
  faces keep their identity the body keeps its topology: `SameTopology`
  maps old to new one to one and the model replaces the body with the same
  IDs. Vertices are moved, then `SameParameter`, `ShapeFix_Shape` and a
  validity check.
- **Faceted bodies** (200 or more planar faces, as imported from a mesh)
  are triangulated, their points moved and rebuilt as a mesh body.
- **The maps** work in a frame from the body's bounding box: `t` along the
  axis, an up and a side direction. `BEND` keeps the centre line's length
  (R = L / angle; with a law it integrates the centre line's direction);
  past the ends it goes on straight. `FLOW` samples 400 frames along the
  curve (the `SWEEP` frame code) and interpolates between them.
- **`SWEEPVOL`**: a ball gives an exact round pipe (`exact_sweep` of a
  circle) fused with the ball at both ends; a cylinder moving square to its
  axis gives its rectangle swept with `MakePipeShell.SetMode(gp_Dir(axis))`
  (binormal mode keeps it upright), fused with the cylinder at both ends.
  Anything else: copies spaced so the ridge between two is under the
  tolerance (spacing 2 sqrt(r^2 - (r - tol)^2), r half the tool's size), at
  most 400, fused, then `UnifySameDomain`. Measured: a 3 radius end mill 30
  along a line gives exactly pi 9 10 + 6 10 30 = 2082.74.

Part 4 gotchas:

- `IncreaseDegree` after `SetUNotPeriodic` raised OutOfRange on periodic
  surfaces: raise the degree first.
- `InsertUKnot` outside the surface's knot range raises ConstructionError:
  insert only inside `Bounds()` (a converted face can use part of a
  larger surface).
- Faces and edges placed by a `TopLoc_Location` (common after a `MOVE`)
  hold their geometry in local coordinates: map points through the
  location, deform, and map back.
- Some edges stay Bezier after `NurbsConvert`: replace their curve by a
  `GeomConvert` B-spline with `BRep_Builder.UpdateEdge` and set its range.
- Pcurves are stored against the surface handle: replacing a face's
  surface instead of editing it loses them.
- A pipe of a solid (`MakePipe` of each face of a cutter) failed or
  crashed; prisms of solids are not supported either; hence the special
  cases and copies.
- `GeomAbs` enum values cannot be sorted in OCP: count them instead.

## The exit test: a computer mouse shell

`scripts/mouse.cmd` (tests/test_mouse.py) meets the M5 exit test:

- **From curves**: a closed plan outline (a `SPLINE` through ten points, in
  a macro so it can be drawn at any size and height) gives the side wall
  (`LOFT ... SURFACE` from the foot to a 0.97 copy 14 up) and, laid onto an
  equation surface with a hump towards the back, the rim the top is
  trimmed to.
- **G2 blends**: one `BLEND, G2` all round, from the side's upper edge to the
  top's rim. `ANALYZE` judges both joins G2; the foot is the only crease.
- **Solid, shelled to 2 mm**: `FILL` closes the bottom, `SEW` makes the
  solid, `SHELL` opens the bottom face; `MINWALL` gives 2.0 right after.
  A button split and a slot for a scroll wheel are cut afterwards (`MINWALL`
  then finds thinner spots where those cuts meet the curved wall at a
  glancing angle, as it should).
- **Text flowed along a curve**: an arc laid onto a copy of the top with
  `PROJECT` (laid on the shell it would land on both the outer and inner
  skin), the text `FLOW`ed along it with `FIT` and joined with `UNION`.

Two fixes it needed:

- **`BLEND` between two closed loops**: before, the blend's two seam edges
  missed each other by about 0.1 (each end row was built from a one-sided
  tangent) and the start of the second loop was matched to the first only
  by luck. Now a closed side takes its tangent across the seam, the second
  loop is turned to start across from the first and to run the same way
  round, and each row of control points is interpolated as a periodic
  curve, then clamped at the seam, so the seam closes exactly and the
  blend runs on smoothly over it.
- **`ANALYZE` on nearly flat faces**: the side wall bends with a radius of
  about 30 m; the blend matched it, but a 10% test on curvatures that small
  (3e-5 against 4.6e-5) called the join G1. A bend wider than 100 times
  the body's size now counts as flat.

## What is left of M5

In the suggested order, about three items per pull request:

1. Done (part 4): deformers `FLOW`, `BEND`, `TWIST`, `TAPER`, `STRETCH`,
   and `SWEEPVOL`.
2. Done: the M5 exit test (`scripts/mouse.cmd`, see above). M5 is complete.
