! # Sheet metal: a bent cover
! A cover bent from 1.5 mm steel: a flat blank with holes and a slot, flanges bent up on
! its edges, then unfolded again into the flat shape the laser cuts, written as DXF.
W = 120         ! width
D = 80          ! depth
T = 1.5         ! sheet thickness
F = 25          ! flange height
! ## The flat plate, from a sketch
SKETCH, base, XY
SRECT, 0, 0, W, D
SCIRCLE, 20, 20, 3
SCIRCLE, W - 20, 20, 3
SCIRCLE, 20, D - 20, 3
SCIRCLE, W - 20, D - 20, 3
SSLOT, W/2 - 20, D/2, W/2 + 20, D/2, 4
ENDSKETCH
! a 1.5 mm sheet, bend radius 2, K-factor 0.44
SHEET, base, T, 2
NAME, LAST, cover
MATERIAL, cover, STEEL
! ## Flanges bent up on the front and back, a short lip on the right
SEL, S, EDGE, AT, W/2, 0, T
FLANGE, , F
SEL, S, EDGE, AT, W/2, D, T
FLANGE, , F
SEL, S, EDGE, AT, W, D/2, T
FLANGE, , 10
SEL, NONE
SHEETINFO, cover
! ## The flat blank, and the files for the workshop
UNFOLD, cover, "cover_blank.dxf"
NAME, LAST, blank
MOVE, blank, 0, -2 * D, 0
ASSERT, BBOX(blank).dz, EQ, T, 0.001
EXPORT, STEP, "cover.step", cover
DRAWING, "cover.pdf", STANDARD, cover
VIEW, ISO
FIT
