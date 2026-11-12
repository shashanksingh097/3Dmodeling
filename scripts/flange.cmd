! Pipe flange, fully parametric.
! Change any value below (or edit it in the History panel) and the model rebuilds.
D_FLANGE = 80          ! flange diameter
T_FLANGE = 10          ! flange thickness
D_HUB = 40             ! hub diameter
H_HUB = 30             ! hub height above the flange
D_BORE = 24            ! bore diameter
N_BOLTS = 6            ! number of bolt holes
D_BOLT = 8             ! bolt hole diameter
PCD = 60               ! bolt circle diameter
R_FILLET = 3           ! hub-to-flange fillet
C_BORE = 1.5           ! chamfer on the bore and hub top

CYL, 0,0,0, D_FLANGE/2, T_FLANGE
NAME, LAST, flange
CYL, 0,0,T_FLANGE, D_HUB/2, H_HUB
UNION, flange, LAST

! a hole through everything, as a reusable command
*MACRO, drill, x, y, d
  CYL, x, y, -1, d/2, T_FLANGE + H_HUB + 2
  SUBTRACT, flange, LAST
*END

drill, 0, 0, D_BORE
*DO, i, 0, N_BOLTS - 1
  A = i * 360 / N_BOLTS
  drill, PCD/2 * cos(A), PCD/2 * sin(A), D_BOLT
*ENDDO

! fillet the circular edge where the hub meets the flange top
SEL, S, EDGE, RADIUS, EQ, D_HUB/2
SEL, R, EDGE, LOC, Z, T_FLANGE
FILLET, R_FILLET

! chamfer the bore's top and the hub's outer top edge
SEL, S, EDGE, LOC, Z, T_FLANGE + H_HUB
CHAMFER, C_BORE

! the flange top face, saved as a named set for later steps
SEL, S, FACE, NORMAL, 0,0,1
SEL, R, FACE, LOC, Z, T_FLANGE
CM, flange_top, FACE

! checks that hold for any values above: the step fails if one does not
ASSERT, VALID(flange)
ASSERT, HOLES(flange, D_BOLT), EQ, N_BOLTS
ASSERT, HOLES(flange, D_BORE, 1), EQ, 1          ! the bore goes all the way through
ASSERT, BBOX(flange).dz, EQ, T_FLANGE + H_HUB, 0.001
ASSERT, SYMMETRIC(flange, "YZ")

*MSG, "flange volume: ", round(VOL(flange)), " mm3"
VIEW, ISO
FIT
