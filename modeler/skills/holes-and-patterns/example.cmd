! A flange: a 30 mm bore, N counterbored bolt holes on a circle, and a grid of small vent holes in a tab.
N = 6
PCD = 80
D = 8
CYL, 0, 0, 0, 50, 12
NAME, LAST, flange
HOLE, flange, 0, 0, 12, 30
HOLE, flange, PCD/2, 0, 12, D, 0, CBORE, 14, 3
PATTERN, POLAR, flange, 1, N
BLOCK, 45, -15, 0, 40, 30, 4
UNION, flange, LAST
HOLE, flange, 60, -9, 4, 3
PATTERN, LINEAR, flange, 1, 4, 6, 0, 0, 4, 0, 6, 0
ASSERT, VALID(flange)
ASSERT, PIECES(flange), EQ, 1
ASSERT, HOLES(flange, 30, 1), EQ, 1
ASSERT, HOLES(flange, D, 1), EQ, N
ASSERT, HOLES(flange, 3, 1), EQ, 16
