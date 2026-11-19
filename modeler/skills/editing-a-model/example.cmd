! A bracket built from parameters, then edited the right way: the parameter lines change, not the shape steps.
W = 60
HD = 6
BLOCK, 0, 0, 0, W, 30, 6
NAME, LAST, bracket
HOLE, bracket, 10, 15, 6, HD
HOLE, bracket, W - 10, 15, 6, HD
ASSERT, BBOX(bracket).dx, EQ, W, 0.01
! make it 80 long with 8 mm holes: two parameter edits; both holes follow W
HIST, EDIT, 1, "W = 80"
HIST, EDIT, 2, "HD = 8"
ASSERT, BBOX(bracket).dx, EQ, 80, 0.01
ASSERT, HOLES(bracket, 8), EQ, 2
ASSERT, HOLES(bracket, 6), EQ, 0
ASSERT, VALID(bracket)
