! An imported-style part: two 6 holes made 8 in one step, then checked.
BLOCK, 0, 0, 0, 80, 40, 10
NAME, LAST, part
SEL, S, FACE, LOC, Z, 10
HOLE, part, 20, 20, 10, 6
HOLE, part, 60, 20, 10, 6
RESIZE, part, HOLE, EQ, 6, 8
ASSERT, HOLES(part), EQ, 2
