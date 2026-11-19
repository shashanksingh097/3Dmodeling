! Getting parts made: a 3D print check on a hook, milling paths for a pocketed plate, and the parting
! line and mould halves for a round cap with draft.
BLOCK, 0, 0, 0, 40, 8, 60
NAME, LAST, hook
BLOCK, 0, 0, 44, 40, 40, 8
UNION, hook, LAST
PRINTCHECK, hook, BEST
ASSERT, VALID(hook)
ASSERT, OVERHANGS(hook, 45, "+X"), EQ, 0, 1
BLOCK, 100, 0, 0, 80, 60, 16
NAME, LAST, plate
BLOCK, 112, 12, 6, 48, 36, 20
SUBTRACT, plate, LAST
SEL, S, FACE, LOC, Z, 6
CM, floor, FACE
SEL, NONE
MILL, plate, POCKET, floor, 6, 4
CYL, 0, 150, 0, 30, 14
NAME, LAST, cap
MATERIAL, cap, ABS
! draft on the side face only: the cap's faces, less its top and bottom
SEL, S, FACE, BODY, cap
SEL, U, FACE, LOC, Z, 0
SEL, U, FACE, LOC, Z, 14
DRAFT, 2
SEL, NONE
PARTING, cap
MOLD, cap, 8, 0.5
ASSERT, VALID(cap_top)
ASSERT, VALID(cap_bottom)
