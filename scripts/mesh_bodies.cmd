! Mesh bodies (M6 part 1): TOMESH, mesh booleans, SMOOTH, REMESH, SIMPLIFY, deformers on meshes.
! A mesh body keeps its triangles as one mesh, so booleans stay fast at any size (they run in
! manifold3d). It keeps its ID through every mesh command, like any other body.

! ---- a ball lamp shade: a thin sphere with 24 round windows, all cut as a mesh ----
R = 30
SPHERE, 0, 0, 0, R
NAME, LAST, shade
TOMESH, shade
SPHERE, 0, 0, 0, R - 2
SUBTRACT, shade, LAST
! each cylinder goes right through, so it opens two windows
*DO, i, 0, 5
  CYL, -(R + 2)*COS(i*60)*COS(25), -(R + 2)*SIN(i*60)*COS(25), -(R + 2)*SIN(25), 6, 2*R + 4, COS(i*60)*COS(25), SIN(i*60)*COS(25), SIN(25)
  SUBTRACT, shade, LAST
  CYL, -(R + 2)*COS(i*60 + 30)*COS(25), -(R + 2)*SIN(i*60 + 30)*COS(25), (R + 2)*SIN(25), 6, 2*R + 4, COS(i*60 + 30)*COS(25), SIN(i*60 + 30)*COS(25), -SIN(25)
  SUBTRACT, shade, LAST
*ENDDO
! a neck on top, joined on as a mesh too
TUBE, 0, 0, R - 4, 8, 5, 14
UNION, shade, LAST
COLOR, shade, ORANGE

! ---- a pebble: a box made fine enough to bend, then smoothed round ----
BLOCK, 60, -20, -12, 44, 30, 20
NAME, LAST, pebble
TOMESH, pebble
REMESH, pebble, 1.5
SMOOTH, pebble, 40, 0.6
COLOR, pebble, GREY

! ---- a twisted bar: deformers move every point of a mesh body ----
BLOCK, 125, -6, -15, 12, 12, 60
NAME, LAST, bar
TOMESH, bar
REMESH, bar, 2
TWIST, bar, 120, Z
! fewer triangles where the bar is flat
SIMPLIFY, bar, 0.02
COLOR, bar, TEAL

ASSERT, VOL(shade), GT, 0
! smoothing keeps the size: the pebble holds about as much as the box it came from
ASSERT, VOL(pebble), EQ, 44*30*20, 1500
