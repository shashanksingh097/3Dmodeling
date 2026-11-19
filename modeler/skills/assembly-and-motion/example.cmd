! A small assembly: a base with two pins placed as copies of one part, a lid on a hinge driven by the
! angle A, a check through the range of motion, a gravity check and the parts list.
A = 30
*PART, pin, D=6, L=8
  CYL, 0, 0, 0, D/2, L
*ENDPART
BLOCK, 0, 0, 0, 60, 40, 10
NAME, LAST, base
MATERIAL, base, ALUMINIUM
HOLE, base, 10, 20, 10, 6, 8
HOLE, base, 50, 20, 10, 6, 8
! the pins sit in 8 deep holes, flush with the top, so the lid can close over them
INST, pin, 10, 20, 2
NAME, LAST, pin_a
INST, pin, 50, 20, 2
NAME, LAST, pin_b
BLOCK, 0, 0, 10, 60, 40, 3
NAME, LAST, lid
MATERIAL, lid, ABS
ROTATE, lid, -A, 0, 0, 10, 0, 1, 0
MOTION, A, 0, 120, 12
! the hinge holds the lid, so it is listed as fastened (without it GRAVITY says the open lid tips off)
GRAVITY, base, "lid"
BOM
ASSERT, OVERLAP(lid, base), EQ, 0
ASSERT, TOUCH(lid, base)
ASSERT, OVERLAP(pin_a, base), EQ, 0
ASSERT, OVERLAP(pin_a, lid), EQ, 0
ASSERT, GROUPS(), EQ, 1
