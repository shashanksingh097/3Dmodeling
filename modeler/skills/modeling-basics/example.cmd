! A plate with a pocket, two holes and rounded top edges, written so every size is a parameter.
W = 80
D = 50
T = 10
HD = 6
BLOCK, 0, 0, 0, W, D, T
NAME, LAST, plate
BLOCK, W/2 - 15, D/2 - 10, T - 4, 30, 20, 4
SUBTRACT, plate, LAST
HOLE, plate, 10, D/2, T, HD
HOLE, plate, W - 10, D/2, T, HD
SEL, S, EDGE, LOC, Z, T
FILLET, 1
SEL, NONE
ASSERT, VALID(plate)
ASSERT, PIECES(plate), EQ, 1
ASSERT, BBOX(plate).dx, EQ, W, 0.01
ASSERT, BBOX(plate).dz, EQ, T, 0.01
ASSERT, HOLES(plate, HD), EQ, 2
