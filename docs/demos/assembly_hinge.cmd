! # An assembly: a hinge on a base
! Two hinge leaves, a pin and two screws on a base plate. The leaf and the screw are
! parts, defined once and placed as copies; coordinate systems on the parts say where
! they join, so each copy is placed by one MATE. Then the mates, the fits and the parts
! list are checked, and the whole assembly is written to one STEP file.
! ## The parts
*PART, leaf, W=40, L=30, T=3, R=4, K=0
  BLOCK, 0, 0, 0, W, L, T
  NAME, LAST, plate
  CYL, K, L, T/2, R, W/2, 1, 0, 0   ! the knuckle round the pin, along X, half the width from K
  UNION, plate, LAST
  CYL, -1, L, T/2, 2.1, W + 2, 1, 0, 0
  SUBTRACT, plate, LAST             ! the hole for the pin
  BLOCK, W/2 - K, L - R - 0.5, -R, W/2, R + 1, 2*R
  SUBTRACT, plate, LAST             ! room for the other leaf's knuckle
  HOLE, plate, 10, 12, T, 3.4
  HOLE, plate, W - 10, 12, T, 3.4
*ENDPART
*PART, screw, D=3, L=10
  CYL, 0, 0, 0, D, 2                ! the head
  CYL, 0, 0, -L, D/2, L             ! the shank
  UNION, 1, 2
*ENDPART
! ## The base, and the copies placed anywhere to start with
BLOCK, -20, -20, -8, 80, 45, 8      ! it ends before the knuckles
NAME, LAST, base
COLOR, base, GREY
INST, leaf, -70, 10, 20
NAME, LAST, fixed
COLOR, fixed, BLUE
INST, leaf, 100, 0, 0, K=20
NAME, LAST, moving
COLOR, moving, ORANGE
CYL, 0, -50, 0, 2, 44
NAME, LAST, pin
! ## Where they join: coordinate systems on the bodies
CSYS, seat, base, 0, 0, 0             ! on the base's top
CSYS, under, fixed, -70, 10, 20       ! the fixed leaf's corner, underneath
MATE, FRAME, seat, under
CSYS, axis, fixed, -2, 30, 1.5, 1, 0, 0     ! the pin's line, through the knuckle (the leaf is in place now)
CSYS, axis2, moving, 98, 30, 1.5, 1, 0, 0, 180 ! the same line on the copy at x = 100, X turned half round
CSYS, end, pin, 0, -50, 0             ! the pin's end, Z along it
MATE, FRAME, axis, end
! the moving leaf on the same line, the hinge opened out flat
MATE, FRAME, axis, axis2
! ## Screws through the fixed leaf into the base, standing on the leaf
*DO, i, 1, 2
  HOLE, base, 10 + (i - 1) * 20, 12, 0, 3.4
  INST, screw, 10 + (i - 1) * 20, 12, 3
*ENDDO
! ## Checked
MATES
CLEARANCE, pin, fixed
BOM
ASSERT, BBOX(pin).dx, EQ, 44
! ## The assembly in one STEP file, each part a solid of its own
EXPORT, STEP, "hinge.step"
VIEW, ISO
FIT
