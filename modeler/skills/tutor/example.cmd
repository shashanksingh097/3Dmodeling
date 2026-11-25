! The first tutorial's part, written the way the lesson teaches it: a shape, a name, sizes
! (with units), holes and rounded corners. Each line is what a button in the window writes.
BLOCK, 0, 0, 0, 80 mm, 50 mm, 10 mm
NAME, LAST, plate
HOLE, plate, 15, 25, 10, 8
HOLE, plate, 65, 25, 10, 8
SEL, S, EDGE, AT, 0, 0, 5
SEL, A, EDGE, AT, 80, 0, 5
SEL, A, EDGE, AT, 80, 50, 5
SEL, A, EDGE, AT, 0, 50, 5
FILLET, 5
SEL, NONE
ASSERT, HOLES(plate, 8), EQ, 2
ASSERT, NFACES(plate, "cylinder"), EQ, 6
