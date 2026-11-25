! Getting geometry ready for the analysis app: the middle surface of a bent bracket, the water
! inside a pipe, the air round a part, and two touching blocks that share their face.
BLOCK, 0, 0, 0, 100, 50, 2
NAME, LAST, bracket
BLOCK, 0, 0, 0, 2, 50, 40
UNION, bracket, LAST
MIDSURFACE, bracket
ASSERT, AREA(bracket_mid, "BODY"), BETWEEN, 6890, 6910
CYL, 200, 0, 0, 10, 80
NAME, LAST, pipe
CYL, 200, 0, 0, 8, 80
SUBTRACT, pipe, LAST
FLUIDVOLUME, pipe
ASSERT, VOL(pipe_fluid), BETWEEN, 16080, 16090
BLOCK, 0, 200, 0, 30, 20, 10
NAME, LAST, part
ENCLOSURE, part, BOX, 20
ASSERT, VALID(enclosure)
BLOCK, 0, 400, 0, 20, 20, 20
NAME, LAST, left
BLOCK, 20, 405, 5, 10, 10, 10
NAME, LAST, right
SHAREFACES, "left right"
MERGEFACES, bracket
