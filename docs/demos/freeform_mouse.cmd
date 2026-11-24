! # A freeform part: a computer mouse
! A smooth body made from curves rather than blocks: curves across and along the top
! make one surface through all of them, a flat patch closes the bottom and the two are
! sewn into a solid. Its smoothness is checked with a report (and, in the app, zebra
! stripes: ANALYZE, mouse, ZEBRA).
L = 110         ! length
W = 64          ! width
H = 38          ! height at the hump
! ## Curves across the top (front to back) ...
SPLINE, (0, 0.18*W, 0), (L/2, 0, 0), (L, 0.12*W, 0)
NAME, LAST, u1
SPLINE, (-0.06*L, W/2, 0), (L/5, W/2, 0.6*H), (L/2, W/2, H), (0.8*L, W/2, 0.8*H), (1.05*L, W/2, 0)
NAME, LAST, u2
SPLINE, (0, 0.82*W, 0), (L/2, W, 0), (L, 0.88*W, 0)
NAME, LAST, u3
! ## ... and along it (side to side), each meeting all three
SPLINE, (0, 0.18*W, 0), (-0.06*L, W/2, 0), (0, 0.82*W, 0)
NAME, LAST, v1
SPLINE, (L/2, 0, 0), (L/2, W/5, 0.8*H), (L/2, W/2, H), (L/2, 4*W/5, 0.8*H), (L/2, W, 0)
NAME, LAST, v2
SPLINE, (L, 0.12*W, 0), (1.05*L, W/2, 0), (L, 0.88*W, 0)
NAME, LAST, v3
! ## One surface through the network, a flat bottom, sewn into a solid
NETWORK, u1, u2, u3, ACROSS, v1, v2, v3
NAME, LAST, top
FILL, G0, u1, v3, u3, v1
NAME, LAST, bottom
SEW, top, bottom
NAME, LAST, mouse
COLOR, mouse, BLUE
! ## A groove between the two buttons, cut along the top
BLOCK, 0.45*L, W/2 - 0.6, 0, 0.6*L, 1.2, H + 5
SUBTRACT, mouse, LAST
! ## How smooth is it?
CHECK, mouse
CONTINUITY, mouse
INSPECT, mouse
ASSERT, BBOX(mouse).dz, EQ, H, 0.5          ! the surface may rise a little above its curves
ASSERT, VOL(mouse), GT, 0.3 * L * W * H
! ## Written out: exact STEP for the mould maker, STL for a 3D printer
EXPORT, STEP, "mouse.step", mouse
EXPORT, STL, "mouse.stl", mouse
VIEW, ISO
FIT
