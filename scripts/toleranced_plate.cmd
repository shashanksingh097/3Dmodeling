! Tolerances (NOTE, STACKUP, SECTION): a bearing plate with datums A (the bottom) and B (the left side),
! the top held flat and parallel to A, the bore placed to A and B and toleranced H7, and a stack-up of
! the shaft's end play through the plate. SECTION cuts the view open through the bore.
BLOCK, 0,0,0, 120,80,20
NAME, LAST, plate
HOLE, plate, 60,40,20, 30
SEL, S, FACE, LOC, Z, 0
NOTE, DATUM, A
SEL, S, FACE, LOC, X, 0
NOTE, DATUM, B
SEL, S, FACE, LOC, Z, 20
NOTE, GDT, FLATNESS, 0.02
NOTE, GDT, PARALLELISM, 0.05, A
SEL, S, FACE, TYPE, CYLINDER
NOTE, FIT, H7
NOTE, GDT, POSITION, D0.05, A, B
SEL, NONE
STACKUP, +20.2 ±0.05, -20 ±0.05, MIN=0.05, MAX=0.4
SECTION, ZX, ABOVE, 40
FIT
