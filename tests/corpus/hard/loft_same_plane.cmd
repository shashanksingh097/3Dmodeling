! Two circles in the same plane, one inside the other.
! expect: refused "lie in the same plane"
CIRCLE, 0,0,0, 5
CIRCLE, 0,0,0, 8
LOFT, 1, 2
