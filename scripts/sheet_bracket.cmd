! Sheet metal (SHEET, FLANGE, UNFOLD): a bent bracket and its flat blank (docs/sheet-metal.md).
W = 60
D = 40
T = 2
SKETCH, base, XY
SRECT, 0, 0, W, D
SCIRCLE, W/2, D/2, 6
SSLOT, 12, 10, 12, 30, 2.5
ENDSKETCH
! a 2 mm plate, bend radius 2, K-factor 0.44
SHEET, base, T, 2
NAME, LAST, bracket
! the front edge of the top face bends up 90 degrees, 25 long
SEL, S, EDGE, AT, W/2, 0, T
FLANGE, , 25
! the right edge of the bottom face bends down 45 degrees
SEL, S, EDGE, AT, W, D/2, 0
FLANGE, , 15, 45
! the back edge bends up a lip, 120 degrees, tighter radius
SEL, S, EDGE, AT, W/2, D, T
FLANGE, , 10, 120, 1
SEL, NONE
SHEETINFO, bracket
! the flat blank beside it (UNFOLD, bracket, blank.dxf also writes the DXF to cut)
UNFOLD, bracket
NAME, LAST, blank
FIT
