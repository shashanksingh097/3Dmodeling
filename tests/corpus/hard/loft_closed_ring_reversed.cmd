! A closed loft round a ring where one circle faces against the ring (this crashed the kernel at times on OCCT 7.9).
! expect: ok
CIRCLE, 20,0,0, 3, 0,-1,0
CIRCLE, 0,20,0, 3, -1,0,0
CIRCLE, -20,0,0, 3, 0,-1,0
CIRCLE, 0,-20,0, 3, 1,0,0
LOFT, 1, 2, 3, 4, CLOSED
