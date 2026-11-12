# M4 part 4: text, spine lofts, equation surfaces and face editing

This finishes M4. The commands are in LANGUAGE.md section 20, and
`scripts/m4_shapes.cmd` uses all of them.

| Command | What it makes |
|---------|---------------|
| `TEXT` | Letters from a font: flat faces, or solid letters with a depth |
| `SPINELOFT` | A loft through sections placed along a curved centre line |
| `SURFACE, PARAM` | An exact surface from x(u,v), y(u,v), z(u,v); a solid when it closes, a wall when given a thickness |
| `PUSHPULL` | Moves selected faces along their normals; the faces around them follow |
| `DELFACE` | Removes selected faces and closes the gap |

## Design

* **Text.** OCCT's font builder (`StdPrs_BRepFont`, `StdPrs_BRepTextBuilder`)
  turns the font's outlines into exact faces. Fonts are found by name through
  the system font list (`sans-serif`, `serif`, `monospace` are aliases that
  exist on Windows, macOS and Linux), or loaded from a file path. Solid
  letters are a prism of the faces. The letters are placed with the same
  plane rule as profiles, and on the work plane when one is set.
* **Spine lofts.** The spine is cut into 800 rotation-minimizing frames. Each
  section is matched to the frame whose plane passes nearest its centre, and
  its points are read in that frame (64 points, counter-clockwise, starting
  at the same side, so the loft does not twist by accident). Between sections
  the points are blended with a cubic through all the sections (uneven
  Catmull-Rom), and each blend is set square to the spine at its own frame.
  One smooth loft goes through all of them. The number of loft sections
  follows the spine's bend (one per 6 degrees, at least 4 per gap).
* **Equation surfaces.** The equation is sampled on a grid and
  `GeomAPI_PointsToBSplineSurface` interpolates it. When the grid closes in
  both directions, or in one with both other ends shrunk to a point (a
  sphere's poles), the surface is split into four patches and sewn: the
  shared edges sew as any faces would, and the shell becomes a solid. An open
  surface is thickened with `MakeThickSolidBySimple`. A sphere of radius 10
  comes out within 0.001% of its volume, a torus within 0.1%.
* **Push/pull** is an offset of only the chosen faces
  (`BRepOffset_MakeOffset` with `SetOffsetOnFace`, intersection joins), so the
  faces around them extend or trim to meet them, whatever their type. The
  maker reports every face and edge as "generated", so the history passed to
  the model uses that, and face and edge IDs survive the edit.
* **Delete faces** is OCCT's defeaturing (`BRepAlgoAPI_Defeaturing`), which
  removes faces and extends the neighbours to close the gap, with history.
* Every result is checked like the other features: an empty, invalid or
  unchanged body is an error and the model stays as it was.

## Tests

`tests/test_shapes4.py`: text size, baseline, alignment, a side plane,
engraving, a missing font; spine loft sections sorted along the spine, the
ends where they were drawn, a straight spine giving the exact cone volume,
surface mode and errors; a torus and a sphere from equations to 0.1% of their
volumes, an open surface and a flat one thickened to the exact volume; push/pull
of a flat face with face IDs kept, of a hole's wall to the exact volume, too
far through a part refused; removing a hole and a fillet back to the exact
block; the forms.
