---
name: sheet-metal
description: Bent sheet metal parts - a plate cut from a sketch, walls bent along its edges or along a sketched line, and the flat blank with bend allowance written to DXF. Use for brackets, covers, chassis, clips and anything folded from one sheet.
commands: SKETCH, SHEET, FLANGE, SBEND, UNFOLD, SHEETINFO, HOLE, TOSHEET
---
# Sheet metal

## Steps

0. **A bent part from elsewhere** (an imported STEP): `TOSHEET, part [, K]`
   finds its thickness, bends and walls, then `UNFOLD` and `SHEETINFO` work
   on it. Only walls bent straight off the base are found; a part with walls
   of several thicknesses is refused with the reason.
1. **Parameters**: thickness `T`, bend radius `R` (often = T), K-factor
   (0.44 unless the shop says otherwise).
2. **The flat plate**: a sketch of the outline (holes in the sketch become
   holes in the plate), then `SHEET, base, T [, R [, K]]`. Name it.
3. **Walls along edges**: select an edge of the plate, `FLANGE, , length
   [, angle [, r]]`. An edge of the **top** face bends up, of the **bottom**
   face bends down. Find the edge by a point on it:
   `SEL, S, EDGE, AT, W/2, 0, T` (front edge, top face).
   The part grows past the edge by the radius plus the thickness.
4. **Bends across the plate**: a sketch with one straight line seen square to
   the plate, then `SBEND, part, sketch [, angle, r, UP/DOWN, FLIP]`. Do it
   before flanging the side that turns.
5. **Holes**: through the plate with `HOLE` (they show in the flat pattern).
6. **Flat blank**: `UNFOLD, part` (a body beside it), `UNFOLD, part,
   blank.dxf` also writes the DXF (outline, bend lines with direction,
   angle and radius). `SHEETINFO, part` lists every flange and its flat
   length.

```cmd
SKETCH, s, XY
SRECT, 0, 0, 60, 40
ENDSKETCH
SHEET, s, 2
NAME, LAST, plate
SEL, S, EDGE, AT, 30, 0, 2
FLANGE, , 20
SEL, NONE
```

## Check the result

* `VALID(part)`, `PIECES(part), EQ, 1`.
* The blank is flat: `BBOX(blank).dz, EQ, T, 0.01`.
* Its length is the plate plus each wall plus the bend allowance
  `angle (radians) x (r + K x T)`; SHEETINFO prints each flat length, so
  check against those numbers rather than working them out by hand.

## Mistakes to avoid

* Picking an edge of the side face (thickness edge) instead of the top or
  bottom face: the flange then goes the wrong way or is refused.
* Flanges on two neighbouring edges meet with an open corner: that is
  expected (it is how the blank is cut).
* A flange cannot start from another flange's wall.
* `SHELL` and `FILLET` on sheet metal: they turn it into an ordinary solid
  that cannot unfold. Use SHEET, FLANGE and SBEND instead.
