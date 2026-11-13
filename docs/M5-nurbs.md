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

## What is left of M5

In the suggested order, about three items per pull request:

1. Guide-curve lofts, sweeps that follow a surface's normal, and zebra /
   curvature / draft analysis in the view.
2. Deformers: `FLOW` (text along a curve), `BEND`, `TWIST`, `TAPER`,
   `STRETCH`, and `SWEEPVOL`.
3. The M5 exit test: a computer mouse shell from curves, G2 blends, shelled
   to 2 mm; flow a text along a curve.
