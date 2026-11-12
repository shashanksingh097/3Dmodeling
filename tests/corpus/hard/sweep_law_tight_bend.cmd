! A section sweep (with a twist law) round a bend too tight for it.
! expect: refused "runs into itself"
ARC, 0,0,0, 5,5,0, 10,0,0
RECT, 0,0,0, 16, 4, 0, 0,1,0
SWEEP, LAST, LAST-1, 30*t
