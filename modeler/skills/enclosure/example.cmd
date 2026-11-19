! A two-part case: a base shell with a lip, four screw bosses and a vent, and a lid with the matching groove.
W = 80
D = 50
H = 25
T = 2
BLOCK, 0, 0, 0, W, D, H
NAME, LAST, base
MATERIAL, base, ABS
SEL, S, FACE, LOC, Z, H
SHELL, T
! the walls, checked before the 0.8 lip (MINWALL counts the lip too)
ASSERT, MINWALL(base), GE, T - 0.1
SEL, S, FACE, LOC, Z, H
LIP, , 2, 0.8
BOSS, base, 8, 8, T, 12, 6, 2.5
BOSS, base, W - 8, 8, T, 12, 6, 2.5
BOSS, base, 8, D - 8, T, 12, 6, 2.5
BOSS, base, W - 8, D - 8, T, 12, 6, 2.5
SEL, S, FACE, LOC, X, W
VENT, 4, 12, 2, 4, 90
SEL, NONE
BLOCK, 0, 0, H + 10, W, D, 8
NAME, LAST, lid
MATERIAL, lid, ABS
SEL, S, FACE, LOC, Z, H + 10
SHELL, T
SEL, S, FACE, LOC, Z, H + 10
LIP, , 2, 0.8, GROOVE, 0.2
SEL, NONE
ASSERT, VALID(base)
ASSERT, PIECES(base), EQ, 1
ASSERT, VALID(lid)
ASSERT, HOLES(base, 2.5), EQ, 4
ASSERT, BBOX(base).dz, EQ, H + 2, 0.01
