! Guide-curve lofts, sweeps that follow a surface, and surface analysis (M5 part 3).

! ---- a vase: three sections, and two guide curves its side must run along ----
R0 = 14                                  ! foot radius
CIRCLE, 0, 0, 0, R0
NAME, LAST, foot
ELLIPSE, 0, 0, 30, 18, 12
NAME, LAST, belly
CIRCLE, 0, 0, 60, 8
NAME, LAST, neck
! the outline seen from the front (through x) and from the side (through y)
SPLINE, (R0, 0, 0), (22, 0, 14), (18, 0, 30), (9, 0, 48), (8, 0, 60)
NAME, LAST, front
SPLINE, (0, R0, 0), (0, 15, 14), (0, 12, 30), (0, 7, 48), (0, 8, 60)
NAME, LAST, side
LOFT, foot, belly, neck, GUIDE, front, side
NAME, LAST, vase

! ---- a rib that stays square to a domed panel along a wavy line ----
SURFACE, PARAM, 60 + u, v, 4 - 0.015*(u*u + v*v), -20, 20, -20, 20
NAME, LAST, panel
SPLINE, (46, -14, 20), (55, -4, 20), (64, 2, 20), (74, 12, 20)
PROJECT, LAST, panel, 0, 0, -1            ! drop the line straight down onto the panel
NAME, LAST, track
! the rib's cross-section, drawn where the track starts: 1 wide, 3 tall, standing on the panel
P0 = CURVEPT(track, 0)
T0 = CURVETAN(track, 0)
RECT, P0.x, P0.y, P0.z + 1.5, 1, 3, 0, T0.x, T0.y, T0.z
NAME, LAST, rib_profile
SWEEP, rib_profile, track, , , NORMAL, , , , , , 1, panel
NAME, LAST, rib

! ---- look at it: stripes on the vase, and its joins in words ----
ANALYZE, vase, ZEBRA
