! NURBS freeform (M5 part 1): control-point curves and surfaces,
! a surface through a network of curves, a patch that fills a hole,
! and surfaces sewn into a solid.
L = 60
W = 40
H = 14

! ---- a dome through a network of curves, closed with a flat patch ----
! curves one way (across the width) ...
SPLINE, (0, 0, 0), (L/2, 0, 0), (L, 0, 0)
NAME, LAST, u1
SPLINE, (0, W/2, 0), (L/4, W/2, 0.8*H), (L/2, W/2, H), (3*L/4, W/2, 0.7*H), (L, W/2, 0)
NAME, LAST, u2
SPLINE, (0, W, 0), (L/2, W, 0), (L, W, 0)
NAME, LAST, u3
! ... and the other way, each meeting all three
SPLINE, (0, 0, 0), (0, W/2, 0), (0, W, 0)
NAME, LAST, v1
SPLINE, (L/2, 0, 0), (L/2, W/4, 0.75*H), (L/2, W/2, H), (L/2, 3*W/4, 0.75*H), (L/2, W, 0)
NAME, LAST, v2
SPLINE, (L, 0, 0), (L, W/2, 0), (L, W, 0)
NAME, LAST, v3
NETWORK, u1, u2, u3, ACROSS, v1, v2, v3
NAME, LAST, dome
! the flat bottom: a patch inside the four edge curves
FILL, G0, u1, v3, u3, v1
NAME, LAST, base
SEW, dome, base
NAME, LAST, pebble

! ---- a control-point curve, edited ----
NURBS, 3, (0, -30, 0), (15, -18, 0), (30, -42, 0), (45, -18, 0), (60, -30, 0)
NAME, LAST, wave
MOVEPT, wave, 3, 0, 0, 12
WEIGHT, wave, 2, 3
KNOT, wave, 0.5

! ---- a surface from rows of control points, one point pulled up ----
NURBS, 3, (80, 0, 0), (90, 0, 4), (100, 0, 4), (110, 0, 0)
NURBS, 3, (80, 13, 2), (90, 13, 6), (100, 13, 6), (110, 13, 2)
NURBS, 3, (80, 26, 2), (90, 26, 6), (100, 26, 6), (110, 26, 2)
NURBS, 3, (80, 40, 0), (90, 40, 4), (100, 40, 4), (110, 40, 0)
NSURF, 3, LAST-3, LAST-2, LAST-1, LAST
NAME, LAST, tile
MOVEPT, tile, (2, 2), 0, 0, 10
