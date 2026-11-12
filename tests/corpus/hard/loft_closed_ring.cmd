! A closed loft round a ring of four circles, each turned along the ring (this failed at random before).
! expect: ok
CIRCLE, 20,0,0, 3, 0,1,0
CIRCLE, 0,20,0, 3, -1,0,0
CIRCLE, -20,0,0, 3, 0,-1,0
CIRCLE, 0,-20,0, 3, 1,0,0
LOFT, 1, 2, 3, 4, CLOSED
