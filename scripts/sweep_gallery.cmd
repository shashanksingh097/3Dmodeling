! Shapes on curves: one example of each kind, side by side.

! 1. MORPH: a duct that starts round, turns into a rounded square, then a
!    star, while it twists a quarter turn along an arc.
ARC, 0,0,0, 40,25,0, 80,0,0
NAME, LAST, duct_path
P0 = (0,0,0)
D0 = (0.6, 0.8, 0)                      ! the arc's start direction
CIRCLE, P0, 8, D0
RECT, P0, 14, 14, 3, D0
STAR, P0, 10, 5, 6, D0
MORPH, duct_path, 90*t, 1, MINTWIST, LAST - 2, LAST - 1, LAST

! 2. A spring: the coils get closer at the ends (pitch law) and the wire
!    gets thicker toward the top (radius law).
HELIX, 130,0,0, 14, 9, 6, 0,0,1, 0, RIGHT, 0.5 + 2*t*(1 - t)*2
NAME, LAST, coil
PIPE, coil, 1.6, 0, 0.7 + 0.6*t

! 3. A twisted ring: a flat bar swept round a closed circle, turning one full
!    turn on the way.
CIRCLE, 0,90,0, 28
NAME, LAST, ring_path
RECT, 28,90,0, 4, 10, 0.8, 0,1,0
SWEEP, LAST, ring_path, 360*t

! 4. A vase: LOFT through round, square and round sections.
CIRCLE, 130,90,0, 12
RECT, 130,90,18, 26, 26, 6
CIRCLE, 130,90,36, 9
POLYGON, 130,90,50, 13, 8, , , , 22.5, 2
LOFT, LAST - 3, LAST - 2, LAST - 1, LAST

! 5. A trefoil knot from an equation (angles are in degrees), made into a pipe.
CURVE, PARAM, 70 + 8*(sin(t) + 2*sin(2*t)), 180 + 8*(cos(t) - 2*cos(2*t)), 10 + 8*(-sin(3*t)), 0, 360, 180
NAME, LAST, knot
PIPE, knot, 3.5

! 6. A stretched S-duct: an ellipse that widens sideways and slides up.
SPLINE, (180,-20,0), (200,0,15), (220,20,15), (240,40,30)
NAME, LAST, s_path
ELLIPSE, 180,-20,0, 5, 3, 1,1,0.5
SWEEP, LAST, s_path, 0, 1, , 1 + 1.5*t, 1, 0, 4*t

VIEW, ISO
FIT
