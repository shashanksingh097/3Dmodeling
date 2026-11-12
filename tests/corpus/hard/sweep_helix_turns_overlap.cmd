! A 4 by 4 square on a helix of pitch 2: each turn runs into the next.
! expect: refused "runs into itself: the part at t = 0 meets"
HELIX, 0,0,0, 10, 2, 3
RECT, 10,0,0, 4, 4, 0, 0,1,0
SWEEP, LAST, LAST-1
