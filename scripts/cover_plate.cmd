! A cover plate drawn with the newer sketch tools: a chamfer of equal
! sides, a chamfer at an angle, a hexagon window, a slot bent along an arc
! and a hole copied with STRANSFORM. Change W or H and the outline follows.
W = 90
H = 60
SKETCH, cover, XY
SRECT, 0, 0, 90, 60
SCON, COINCIDENT, 1.S, ORIGIN
SDIM, LENGTH, 1, W
SDIM, LENGTH, 2, H
SCHAMFER, 1.E, 8                        ! bottom right: 8 back along both sides
SCHAMFER, 3.E, 6, ANGLE, 30             ! top left: 6 along the top, at 30 deg to it
SFILLET, 2.E, 5                         ! top right
SNGON, 22, 30, 6, 9                     ! a hexagon, its corners on construction circle 11
SSLOTARC, 62, 24, 16, 20, 160, 3.5      ! middle radius 16 from 20 to 160 deg, 7 wide
SCIRCLE, 10, 10, 2.5
STRANSFORM, MOVE, 0, 40, 23, COPY       ! the same hole 40 higher
ENDSKETCH
EXTRUDE, cover, 5
