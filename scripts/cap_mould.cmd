! Mould tools and notes (PARTING, MOLD, NOTE, FITS): a round cap moulded in ABS. Its side gets 2
! degrees of draft, so PARTING finds every face coming out of one half with a flat parting line at
! the bottom. MOLD makes the two halves round it with 0.5% shrink, shown pulled apart. The bearing
! bore is machined after moulding: NOTE, FIT pins its H7 size, NOTE, SIZE the cap's height, and a
! note says the material. FITS gives the fit with a g6 shaft.
CYL, 0, 0, 0, 30, 14
NAME, LAST, cap
MATERIAL, cap, ABS
SEL, S, FACE, LOC, Z, 0
SEL, A, FACE, LOC, Z, 14
SEL, INVE
DRAFT, 2
SEL, S, EDGE, LOC, Z, 14
FILLET, 3
PARTING, cap
MOLD, cap, 8, 0.5
MOVE, cap_top, 0, 0, 45
MOVE, cap_bottom, 0, 0, -30
HOLE, cap, 0, 0, 14, 12
SEL, S, FACE, TYPE, CYLINDER
NOTE, FIT, H7
FITS, H7/g6
NOTE, SIZE, 31, 0, 0, 31, 0, 14
NOTE, "ABS, 0.5% shrink", -45, 0, 25, -25, 0, 8
SEL, NONE
