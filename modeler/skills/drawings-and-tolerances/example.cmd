! A bearing plate ready for a drawing: title block values, datums A and B, flatness and parallelism on the
! top, the bore placed to A and B with an H7 fit, and a stack-up of the shaft's end play.
! DRAWING, "plate.pdf", STANDARD, plate, , A4 would then write the sheet.
PROPERTY, TITLE, Bearing plate
PROPERTY, NUMBER, BP-001
BLOCK, 0, 0, 0, 120, 80, 20
NAME, LAST, plate
MATERIAL, plate, ALUMINIUM
HOLE, plate, 60, 40, 20, 30
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
FITS, H7/g6, 30
STACKUP, +20.2 ±0.05, -20 ±0.05, MIN=0.05, MAX=0.4
ASSERT, VALID(plate)
ASSERT, HOLES(plate, 30, 1), EQ, 1
