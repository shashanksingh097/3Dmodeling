! A plate from a sketch, a boss sketched on its top face, a pocket cut
! through, and a pulley revolved about a construction line.
! Change W, H or HOLE_D in the Parameters panel and everything follows.
W = 100
H = 60
T = 8
HOLE_D = 10

SKETCH, base, XY
SRECT, 0, 0, W, H
SCON, COINCIDENT, 1.S, ORIGIN
SDIM, LENGTH, 1, W
SDIM, LENGTH, 2, H
*DO, i, 0, 1
  SCIRCLE, 12 + i*(W - 24), 12, HOLE_D/2
*ENDDO
SDIM, DIAMETER, 5, HOLE_D
SCON, EQUAL, 5, 6
SDIM, HDIST, ORIGIN, 5.C, 12
SDIM, VDIST, ORIGIN, 5.C, 12
SCON, HORIZONTAL, 5.C, 6.C
SDIM, HDIST, 6.C, 2.S, 12
ENDSKETCH
EXTRUDE, base, T
NAME, LAST, plate

SEL, S, FACE, NORMAL, 0,0,1
SKETCH, boss, FACE, SEL
SCIRCLE, 0, 10, 15
SDIM, DIAMETER, 1, 30
ENDSKETCH
EXTRUDE, boss, 20, ADD, plate

SKETCH, slot, XY
SSLOT, 30, 45, 70, 45, 5
ENDSKETCH
EXTRUDE, slot, 0, CUT, plate

SKETCH, pulley, ZX
SLINE, 0, 120, 0, 160, V, CONSTR
SPOLY, 5, 130, 5, 150, 25, 150, 25, 144, 20, 142, 20, 138, 25, 136, 25, 130, CLOSE
ENDSKETCH
REVOLVE, pulley, 1
CHECK
