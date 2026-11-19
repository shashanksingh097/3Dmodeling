! Shapes on curves: a vase lofted through round, square and round sections, a pipe bent along a spline,
! a twisted bar swept round a ring, and a surface checked for smoothness.
CIRCLE, 0, 0, 0, 12
RECT, 0, 0, 18, 26, 26, 6
CIRCLE, 0, 0, 36, 9
LOFT, LAST - 2, LAST - 1, LAST
NAME, LAST, vase
SPLINE, (60,0,0), (80,10,10), (100,0,20), (120,10,30)
NAME, LAST, tube_path
PIPE, tube_path, 4, 3
NAME, LAST, tube
CIRCLE, 0, 90, 0, 28
NAME, LAST, ring_path
RECT, 28, 90, 0, 4, 10, 0.8, 0, 1, 0
SWEEP, LAST, ring_path, 360*t
NAME, LAST, ring
ANALYZE, vase, CURVATURE
ASSERT, VALID(vase)
ASSERT, BBOX(vase).dz, EQ, 36, 0.01
ASSERT, VALID(tube)
! hollow: (4^2 - 3^2) x pi x the path length (about 78)
ASSERT, VOL(tube), BETWEEN, 1650, 1770
ASSERT, VALID(ring)
ASSERT, PIECES(ring), EQ, 1
