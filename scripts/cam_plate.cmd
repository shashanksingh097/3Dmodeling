! A cam plate drawn with ellipses: an elliptical outline, a slot along a
! curved path (SOFFSET2), a hole that touches two edges (SCIRCLET), and an
! elliptical window. Change A or B and the outline follows.
A = 50
B = 32
SKETCH, cam, XY
SELLIPSE, 0, 0, A, B, 0, H              ! the outline: radius A along u, B across
SCON, COINCIDENT, 1.C, ORIGIN
SDIM, MAJOR, 1, A
SDIM, MINOR, 1, B
SARC, 0, -40, 50, 60, 120               ! a curved path ...
SOFFSET2, 4, 2                          ! ... made a slot 8 wide with round ends
SELLIPSE, -24, -14, 9, 5, 30            ! an elliptical window, turned 30 deg
SLINE, 18, -4, 40, -4, CONSTR           ! two construction edges ...
SLINE, 18, -4, 18, -24, CONSTR
SCIRCLET, 8, 9, R, 4, AT, 23, -9        ! ... and a hole of radius 4 touching both
ENDSKETCH
EXTRUDE, cam, 6
