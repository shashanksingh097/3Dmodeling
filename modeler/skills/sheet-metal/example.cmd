! A bent bracket: a plate with a hole and a slot, a wall bent up at the front, one bent down at 45 degrees,
! and the flat blank beside it.
W = 60
D = 40
T = 2
SKETCH, base, XY
SRECT, 0, 0, W, D
SCIRCLE, W/2, D/2, 6
SSLOT, 12, 10, 12, 30, 2.5
ENDSKETCH
SHEET, base, T, 2
NAME, LAST, bracket
SEL, S, EDGE, AT, W/2, 0, T
FLANGE, , 25
SEL, S, EDGE, AT, W, D/2, 0
FLANGE, , 15, 45
SEL, NONE
SHEETINFO, bracket
UNFOLD, bracket
NAME, LAST, blank
ASSERT, VALID(bracket)
ASSERT, PIECES(bracket), EQ, 1
ASSERT, VALID(blank)
ASSERT, BBOX(blank).dz, EQ, T, 0.01
ASSERT, HOLES(blank, 12, 1), EQ, 1
! flat length: plate + wall + bend allowance (angle x (r + K x t) = pi/2 x 2.88 for the 90 degree bend)
ASSERT, BBOX(blank).dy, EQ, D + 25 + PI/2*(2 + 0.44*T), 0.01
