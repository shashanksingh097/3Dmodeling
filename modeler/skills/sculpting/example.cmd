! Sculpting: a ball turned into a mesh with enough points, brow ridges built up on both sides at once,
! a nose inflated, the brows masked while the eye sockets are dug, then the mask cleared.
SPHERE, 0, 0, 0, 20
NAME, LAST, head
TOMESH, head
REMESH, head, 1
STROKE, S1, "4,-19,6  6,-19,6.5  8,-19,7  10,-19,7.5  12,-19,8"
SCULPT, head, CLAY, 4, 0.8, S1, X
STROKE, S2, "0,-20,-2  0,-20,0  0,-20,2"
SCULPT, head, INFLATE, 4, 0.9, S2
MASK, head, PAINT, 0, 0, 0, 4, 1, S1
STROKE, S4, "6,-16,2  7.5,-16,2  9,-16,2"
SCULPT, head, DRAW, 3, -0.8, S4, X
MASK, head, CLEAR
ASSERT, VALID(head)
ASSERT, BBOX(head).dy, GT, 40
ASSERT, BBOX(head).dx, BETWEEN, 39, 42
! the strokes with X were mirrored, so the face stays symmetric
ASSERT, SYMMETRIC(head, "YZ")
