! Implicit shapes and lattices (M6 part 2): IMPLICIT, SMIN blends, LATTICE.
! An implicit shape is where a field f(x, y, z) is at most 0. The result is a mesh body.

! ---- two balls joined by a smooth blend (a "metaball") ----
R = 10
IMPLICIT, a, BALL(0, 0, 0, R), -11, -11, -11, 11, 11, 11
IMPLICIT, b, BALL(16, 0, 0, 7), 8, -8, -8, 24, 8, 8
IMPLICIT, blob, SMIN(a, b, 5), -12, -12, -12, 25, 12, 12, 0.4
DELETE, a
DELETE, b
COLOR, blob, PINK

! ---- a superquadric: a rounded box written as one equation ----
IMPLICIT, pillow, ABS((x - 50)/12)**4 + ABS(y/9)**4 + ABS(z/6)**4 - 1, 37, -10, -7, 63, 10, 7
COLOR, pillow, PURPLE

! ---- a cube of gyroid walls, 1 thick, cut by a box ----
IMPLICIT, gyro, MAX(ABS(GYROID(10)) - 0.5, BOX(90, 0, 0, 24, 24, 24)), 77, -13, -13, 103, 13, 13, 0.35
COLOR, gyro, TEAL

! ---- a bracket filled with a gyroid, keeping a 1.5 thick outer skin ----
BLOCK, 0, 40, -10, 50, 25, 20
NAME, LAST, bracket
LATTICE, bracket, GYROID, 8, 1, 1.5
! cut away a corner to show the inside
BLOCK, 25, 35, 0, 30, 17.5, 20
SUBTRACT, bracket, LAST
COLOR, bracket, ORANGE

! ---- a cylinder of octet struts, and a ball of BCC struts ----
CYL, 75, 52, -10, 12, 22
NAME, LAST, post
LATTICE, post, OCTET, 6, 1.2
SPHERE, 105, 52, 0, 11
NAME, LAST, ball
LATTICE, ball, BCC, 5, 1.2
COLOR, post, GREY
COLOR, ball, BLUE

ASSERT, VOL(blob), GT, 4/3*PI*R**3
ASSERT, VOL(bracket), LT, 50*25*20
