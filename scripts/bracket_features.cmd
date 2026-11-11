! A shelled, drafted housing with holes, built on datum planes.
! Change W, H or WALL and everything follows: the planes move with the faces.
W = 80
D = 50
H = 30
WALL = 2.5
BLOCK, 0,0,0, W, D, H
NAME, LAST, housing

! datum planes from faces and numbers
PLANE, top, FACE, 6                  ! on the top face
PLANE, mid, MID, 1, 2                ! half way between the end faces
PLANE, side, MID, 3, 4
AXIS, centre, PLANES, mid, side      ! the vertical centre line
POINT, corner, VERTEX, 1

! tilt the four sides by 3 degrees about the base, so it leaves a mould
SEL, S, FACE, ID, 1, 4
DRAFT, 3

! hollow it out, open at the bottom
SEL, S, FACE, NORMAL, 0,0,-1
SHELL, WALL

! holes drilled on the top face, drawn in the top plane's own coordinates
WORKPLANE, top
HOLE, housing, -25, 0, 0, 8, 0, CBORE, 13, 1.5
HOLE, housing, 25, 0, 0, 8, 0, CSINK, 14
HOLE, housing, 0, 0, 0, 12
WORKPLANE, OFF
