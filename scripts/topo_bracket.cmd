! A quick topology check (TOPOPT): which 30% of a plate carries a load best? The plate is held
! at its left end and pulled down at the middle of its right end; TOPOPT keeps the material that
! makes it stiffest, as a mesh body to model a real part after. The plate itself is hidden.
BLOCK, 0, 0, 0, 120, 8, 50
NAME, LAST, plate
BLOCK, 116, 0, 20, 4, 8, 10
NAME, LAST, pad
UNION, plate, pad
SEL, S, FACE, NORMAL, -1, 0, 0
CM, wall, FACE
SEL, S, FACE, NORMAL, 1, 0, 0
SEL, R, FACE, LOC, X, 120
CM, tip, FACE
SEL, NONE
TOPOPT, plate, wall, tip, FORCE, 0, 0, -1000, 0.3, 30
FIT
