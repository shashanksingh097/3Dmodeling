! A pipe round the sharp corner of a polyline.
! expect: refused "sharp corner at t = 0.5"
POLYLINE, (0,0,0), (20,0,0), (20,20,0)
PIPE, LAST, 3
