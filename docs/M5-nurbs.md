# M5 part 1: NURBS curves and surfaces

This part of M5 adds freeform modeling with control points. The language is
in LANGUAGE.md section 24. What is left of M5 is listed at the end.

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

## What is left of M5

In the suggested order, about three items per pull request:

1. Blends between surfaces with G1/G2 (`BLEND`), extend, offset and trim
   surfaces by curves; move a face by a vector and replace a face.
2. Guide-curve lofts, sweeps that follow a surface's normal, and zebra /
   curvature / draft analysis in the view.
3. Deformers: `FLOW` (text along a curve), `BEND`, `TWIST`, `TAPER`,
   `STRETCH`, and `SWEEPVOL`.
4. The M5 exit test: a computer mouse shell from curves, G2 blends, shelled
   to 2 mm; flow a text along a curve.
