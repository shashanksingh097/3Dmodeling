! The M5 exit test: a computer mouse shell built from curves. The top and the side wall
! are joined by a G2 blend (no jump in curvature), the skin is sewn into a solid, shelled
! to 2 mm with the bottom open, and a name is flowed along a curve laid on the top.

L = 110                                  ! length
WALL = 2                                 ! shell thickness
SIDE_H = 14                              ! height of the straight side wall

! ---- the plan outline, at any size s about its middle and height z ----
*MACRO, OUTLINE, s, z
SPLINE, (L/2 - 55*s, 0, z), (L/2 - 47*s, 22*s, z), (L/2 - 20*s, 26*s, z), (L/2 + 15*s, 31*s, z), (L/2 + 43*s, 25*s, z), (L/2 + 55*s, 0, z), (L/2 + 43*s, -25*s, z), (L/2 + 15*s, -31*s, z), (L/2 - 20*s, -26*s, z), (L/2 - 47*s, -22*s, z), CLOSE
*END

! ---- the side wall: from the foot up to a slightly smaller outline ----
OUTLINE, 1, 0
NAME, LAST, foot
OUTLINE, 0.97, SIDE_H
NAME, LAST, waist
LOFT, foot, waist, SURFACE
NAME, LAST, side

! ---- the top: a hump towards the back, cut to an inset outline laid onto it ----
SURFACE, PARAM, u, v, 20 + 16*exp(-((u - 68)/45)**2) * (1 - (v/48)**2), -10, 120, -45, 45
NAME, LAST, top
OUTLINE, 0.84, 60
NAME, LAST, rim_plan
PROJECT, rim_plan, top, 0, 0, -1
NAME, LAST, rim
TRIM, top, rim, L/2, 0, 30, KEEP
COPY, top
NAME, LAST, top_ref                      ! a copy to lay the logo's curve on later

! ---- the G2 blend all round, between the side's upper edge and the top's rim ----
SEL, S, EDGE, BODY, side
SEL, R, EDGE, BOX, -10, -50, SIDE_H - 1, 130, 50, SIDE_H + 1
E_SIDE = SELID(1)
SEL, S, EDGE, BODY, top
E_TOP = SELID(1)
BLEND, G2, E_SIDE, E_TOP
NAME, LAST, round

! ---- close the bottom and sew everything into one solid ----
FILL, G0, foot
NAME, LAST, base
SEW, side, round, top, base
NAME, LAST, mouse
ANALYZE, mouse                           ! the two blend joins come out G2; the foot edge is the only crease

! ---- hollow it out, open at the bottom ----
SEL, S, FACE, BOX, -10, -50, -0.1, 130, 50, 0.1
SEL, R, FACE, BODY, mouse
SHELL, WALL
SEL, NONE
T_SHELL = MINWALL(mouse)                 ! the thinnest wall of the shell: 2

! ---- the split between the two buttons, and a scroll wheel ----
BLOCK, -5, -0.6, 10, 50, 1.2, 40
SUBTRACT, mouse, LAST
BLOCK, 20, -4.5, 10, 16, 9, 40
SUBTRACT, mouse, LAST
CYL, 28, -3, 23, 6.2, 6, 0, 1, 0
NAME, LAST, wheel

! ---- a name flowed along a curve on the top ----
ARC, 84, -16, 60, 78, 0, 60, 84, 16, 60
NAME, LAST, logo_arc
PROJECT, logo_arc, top_ref, 0, 0, -1
NAME, LAST, logo_line
TEXT, "M5 MOUSE", 0, 0, 0, 7, 1.2
NAME, LAST, logo
FLOW, logo, logo_line, FIT               ! half of each letter sinks into the wall, half stands proud
UNION, mouse, logo

! ---- tidy up: the construction curves are no longer needed ----
DELETE, top_ref
DELETE, logo_line
DELETE, logo_arc
DELETE, foot
DELETE, waist
DELETE, rim
DELETE, rim_plan
