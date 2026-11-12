! A spine loft whose sections are bigger than the spine's bend.
! expect: refused "bends with a radius"
ARC, 0,0,0, 4,4,0, 8,0,0
CIRCLE, 0,0,0, 6, 0,1,0
CIRCLE, 8,0,0, 6, 0,1,0
SPINELOFT, 1, 2, 3
