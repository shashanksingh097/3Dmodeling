! A handle outline made with spline editing: a stepped top edge and a nose
! joined into one smooth spline (SJOIN), carried on to the base (SEXTEND),
! the base extended to meet it, and the top left corner rounded with a
! fillet between a line and a spline.
SKETCH, handle, XY
SLINE, 0, 0, 60, 0                       ! 1: the base
SLINE, 0, 0, 0, 12                       ! 2: the left end
SCON, COINCIDENT, 1.S, 2.S
SLINE, 0, 12, 20, 12                     ! 3, 4, 5: a step-shaped top edge ...
SARC, 30, 12, 10, 0, 180
SARC, 50, 12, 10, 180, 360
SSPLINE, 60, 12, 70, 20, 78, 14          ! 6: ... and a nose
SJOIN, 3, 4, 5, 6                        ! joined into one smooth spline (7)
SCON, COINCIDENT, 7.S, 2.E
SEXTEND, 7.E, 1                          ! carried on until it meets the base's line
SEXTEND, 1.E, 7                          ! and the base carried on to meet it
SFILLET, 2.E, 3                          ! round the top left corner (line and spline)
SCIRCLE, 12, 5, 2.5                      ! a hole for a lanyard
ENDSKETCH
EXTRUDE, handle, 8
