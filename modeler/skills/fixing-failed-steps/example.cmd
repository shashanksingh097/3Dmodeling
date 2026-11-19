! The fixes in order: shell first and fillet after (the other way round SHELL fails), a fillet below
! the largest radius the message gives, and tools that overlap the body so the boolean leaves one piece.
W = 40
BLOCK, 0, 0, 0, W, 30, 10
NAME, LAST, box
SEL, S, FACE, LOC, Z, 10
SHELL, 2
SEL, S, EDGE, LOC, Z, 0
FILLET, 1.5
SEL, NONE
BLOCK, W - 1, 10, 0, 10, 10, 6
UNION, box, LAST
ASSERT, VALID(box)
ASSERT, PIECES(box), EQ, 1
CHECK, box
