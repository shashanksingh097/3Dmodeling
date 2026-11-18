# Sheet metal (PLAN item 19)

`SHEET`, `FLANGE`, `UNFOLD` and `SHEETINFO`, in
`modeler/commands/sheet_handlers.py` and `modeler/geometry/sheetmetal.py`.
How to use them: LANGUAGE.md section 31.

## The record

A sheet metal body is an ordinary solid plus a `Sheet` record in
`Model.sheets` (body ID to record): the sketch plane (origin, x, y, normal),
thickness `t`, bend radius `r`, K-factor `k` and a tuple of `Flange`s. The
record is in model snapshots, so undo, redo and history rebuilds carry it.
`Model.replace` moves it to the new body when the first input had one, so
`HOLE`, `SUBTRACT`, `FILLET` and the like keep a part sheet metal. `FLANGE`
keeps the body's ID.

## A flange

The section is drawn at one end of the bend edge in the plane made of the
outward direction (in the sheet plane, square to the edge, away from the
material) and the sheet normal (flipped for a bottom-face edge): an annular
sector with radii `r` and `r + t` about a centre `r` above the edge,
starting straight down and turning through the bend angle, then the wall,
a `t` wide rectangle along the bend's end tangent. The section is pushed
along the edge (`BRepPrimAPI_MakePrism`) and fused to the plate with
`combine(..., merge=True)`, which joins the faces that line up.

Which side is outward is found by testing a point a little way off the
edge, half the thickness into the plate, with `BRepClass3d_SolidClassifier`.

## The flat pattern

`UNFOLD` collects the planar faces of the body that lie in the sheet plane
(the plate's bottom face, with its holes), adds for each flange a rectangle
of depth `angle (r + k t) + length` beyond its bend edge, fuses them and
unifies the result into one face. The blank body is that face pushed `t`
along the normal and moved along the sheet's x past the part. With `k = 0.5`
the blank's volume equals the part's exactly (an annular sector's area is
`angle t (r + t/2)`), which the tests check.

The DXF (`sheetmetal.dxf`) is plain R12 ASCII written by hand: layers
OUTLINE (white, continuous), BEND (red, CENTER line type) and TEXT; curved
outline edges become short lines within 1/800 of the blank's size.

## Not yet

- Bends along a sketched line across the plate (folding it in place).
- Holes cut into a flange wall showing in the flat pattern, and flanges on
  flange walls (the record would need the wall's own plane).
- Corner reliefs where flanges meet; today the corner stays open.
