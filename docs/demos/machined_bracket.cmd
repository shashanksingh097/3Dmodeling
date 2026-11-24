! # A machined bracket
! An angle bracket milled from aluminium: a base with four counterbored holes, an upright
! with a slot, a rounded inside corner and bevelled outside edges. Every size is a
! parameter, so the same history makes the bracket in any size.
W = 80          ! width
D = 50          ! depth of the base
H = 60          ! height of the upright
T = 8           ! thickness
R = 6           ! inside corner radius
! ## The two plates
BLOCK, 0, 0, 0, W, D, T
NAME, LAST, bracket
BLOCK, 0, D - T, T, W, T, H - T
UNION, bracket, LAST
! ## The inside corner, rounded
SEL, S, EDGE, AT, W/2, D - T, T
FILLET, R
! ## Four counterbored holes for M6 screws, placed by one hole and a pattern
HOLE, bracket, 12, 12, T, 6.6, 0, CBORE, 11, 4
PATTERN, LINEAR, bracket, 1, 2, W - 24, 0, 0, 2, 0, D - 2*T - 18, 0
! ## A slot in the upright: a block cut through it
BLOCK, W/2 - 15, D - T - 1, H - 25, 30, T + 2, 10
SUBTRACT, bracket, LAST
! ## The outside edges bevelled
SEL, S, EDGE, AT, W/2, 0, T
SEL, A, EDGE, AT, W/2, D, H
CHAMFER, 1
! ## Checked, then written out
MATERIAL, bracket, ALUMINIUM
CHECK, bracket
MASSPROP, bracket
ASSERT, BBOX(bracket).dx, EQ, W
ASSERT, BBOX(bracket).dz, EQ, H
DRAWING, "bracket.pdf", STANDARD, bracket
EXPORT, STEP, "bracket.step", bracket
EXPORT, STL, "bracket.stl", bracket
VIEW, ISO
FIT
