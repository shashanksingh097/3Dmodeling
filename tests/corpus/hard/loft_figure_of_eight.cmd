! A section that crosses itself.
! expect: refused "section 1 crosses itself"
POLYLINE, (0,0,0), (10,10,0), (10,0,0), (0,10,0), CLOSE
RECT, 5,5,10, 10, 10
LOFT, 1, 2
