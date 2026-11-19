! A first strength check on an aluminium L-bracket (STRESS), and a quick look at where a plate carries
! its load (TOPOPT keeps 30% of it as a mesh to model a lighter part after).
BLOCK, 0, 0, 0, 60, 40, 6
NAME, LAST, bracket
BLOCK, 0, 0, 0, 6, 40, 50
UNION, bracket, LAST
SEL, S, EDGE, LOC, X, 6
SEL, R, EDGE, LOC, Z, 6
FILLET, 3
MATERIAL, bracket, ALUMINIUM
SEL, S, FACE, NORMAL, -1, 0, 0
CM, wall, FACE
SEL, S, FACE, NORMAL, 1, 0, 0
SEL, R, FACE, LOC, X, 60
CM, tip, FACE
SEL, NONE
STRESS, bracket, wall, tip, FORCE, 0, 0, -400
! the same check as numbers that stay in the script: SAFETY, MAXSTRESS and DEFLECT take STRESS's arguments
ASSERT, SAFETY(bracket, "wall", "tip", 0, 0, -400), GE, 2
ASSERT, DEFLECT(bracket, "wall", "tip", 0, 0, -400), LT, 1
BLOCK, 100, 0, 0, 120, 8, 50
NAME, LAST, plate
SEL, S, FACE, LOC, X, 100
CM, fixed_end, FACE
SEL, S, FACE, LOC, X, 220
CM, loaded_end, FACE
SEL, NONE
TOPOPT, plate, fixed_end, loaded_end, FORCE, 0, 0, -1000, 0.3, 12, 5
ASSERT, VALID(bracket)
ASSERT, MASS(bracket), BETWEEN, 0.06, 0.08
ASSERT, VALID(topo_1)
