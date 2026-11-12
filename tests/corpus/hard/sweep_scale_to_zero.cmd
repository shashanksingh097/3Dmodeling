! A scale law that reaches 0.
! expect: refused "scale must stay above 0"
LINE, 0,0,0, 0,0,30
CIRCLE, 0,0,0, 5
SWEEP, LAST, LAST-1, 0, 1-t
