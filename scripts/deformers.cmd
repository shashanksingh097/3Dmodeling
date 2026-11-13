! Deformers and swept volumes (M5 part 4): BEND, TWIST, TAPER, STRETCH, FLOW, SWEEPVOL.
! A deformed body keeps its ID and its faces keep theirs, so later steps that pick them still work.

! ---- a flat bar bent into a quarter circle, and one bent more towards its far end ----
BLOCK, 0, 0, 0, 100, 10, 4
NAME, LAST, bar
BEND, bar, 90
BLOCK, 0, 30, 0, 100, 10, 4
NAME, LAST, hook
BEND, hook, 150, X, Z, t**2

! ---- a square column, twisted half a turn and tapered to a point-ish top ----
BLOCK, 140, -6, 0, 12, 12, 80
NAME, LAST, column
TWIST, column, 180
TAPER, column, 0.4, Z
! a round bar twisted out and back: the ends stay where they were
BLOCK, 170, -4, 0, 8, 8, 60
NAME, LAST, wave
TWIST, wave, 60, Z, sin(180*t)

! ---- a block stretched to twice its length, keeping its volume ----
BLOCK, 200, 0, 0, 30, 12, 12
NAME, LAST, plug
STRETCH, plug, 2

! ---- a word laid along an arc, fitted to its length ----
TEXT, "FLOW", 0, -60, 0, 16, 3
NAME, LAST, label
ARC, 0, -60, 0, 50, -30, 0, 100, -60, 0
NAME, LAST, arc
FLOW, label, arc, FIT

! ---- a slot cut by an end mill moving along a curve ----
BLOCK, 130, -100, -10, 90, 60, 10
NAME, LAST, plate
CYL, 140, -80, -4, 3, 10
NAME, LAST, cutter
SPLINE, (140, -80, -4), (170, -60, -4), (200, -75, -4), (210, -55, -4)
NAME, LAST, track
SWEEPVOL, cutter, track
SUBTRACT, plate, LAST
DELETE, cutter
