! A circle drawn in a plane that contains the path: no thickness.
! expect: refused "lies along the path"
LINE, 0,0,0, 0,0,30
CIRCLE, 0,0,0, 5, 1,0,0
SWEEP, LAST, LAST-1
