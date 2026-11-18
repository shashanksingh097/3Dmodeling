! Ready to 3D print? (PRINTCHECK): a wall hook with a cable hole through its back and an arm
! sticking out. Built standing up (+Z), the arm's underside and the top of the hole hang
! over more than 45 degrees and are coloured red (they need support); blue sits on the bed.
! PRINTCHECK, hook, BEST tries the six directions: on its side (+X) only the top of the hole needs support.
BLOCK, 0, 0, 0, 40, 8, 60
NAME, LAST, hook
BLOCK, 0, 0, 44, 40, 40, 8
UNION, hook, LAST
BLOCK, 0, 32, 52, 40, 8, 10
UNION, hook, LAST
CYL, 20, -1, 20, 5, 10, 0, 1, 0
SUBTRACT, hook, LAST
PRINTCHECK, hook
