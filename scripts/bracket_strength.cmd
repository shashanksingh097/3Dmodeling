! A first strength check (STRESS): an aluminium L-bracket bolted to a wall by its back plate, with
! 400 N hanging from the end of its arm. CM names the faces so the check reads plainly; STRESS colours
! the part (red: the 99.5% stress) and gives the largest stress, deflection and safety factor.
BLOCK, 0, 0, 0, 60, 40, 6
NAME, LAST, bracket
BLOCK, 0, 0, 0, 6, 40, 50
UNION, bracket, LAST
SEL, S, EDGE, LOC, X, 6
SEL, R, EDGE, LOC, Z, 6
FILLET, 3                             ! round the inside corner
CYL, 45, 20, -1, 4, 10
SUBTRACT, bracket, LAST
MATERIAL, bracket, ALUMINIUM
SEL, S, FACE, NORMAL, -1, 0, 0
CM, wall, FACE
SEL, S, FACE, NORMAL, 1, 0, 0
SEL, R, FACE, LOC, X, 60
CM, tip, FACE
SEL, NONE
STRESS, bracket, wall, tip, FORCE, 0, 0, -400
FIT
