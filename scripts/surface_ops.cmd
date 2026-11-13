! Freeform surface operations (M5 part 2): a G2 blend between two surfaces,
! extending and trimming a surface, and moving or replacing faces of a solid.

! ---- two curved panels with a gap, bridged by a smooth G2 blend ----
NURBS, 3, (0, 0, 0), (0, 10, 6), (0, 20, 6), (0, 30, 0)
NURBS, 3, (-25, 0, 0), (-25, 10, 8), (-25, 20, 8), (-25, 30, 0)
NSURF, 1, LAST-1, LAST
NAME, LAST, left
NURBS, 3, (15, 0, 6), (15, 10, 12), (15, 20, 12), (15, 30, 6)
NURBS, 3, (40, 0, 4), (40, 10, 8), (40, 20, 8), (40, 30, 4)
NSURF, 1, LAST-1, LAST
NAME, LAST, right
! the edges facing each other: at x = 0 on the left panel, at x = 15 on the right
SEL, S, EDGE, BOX, -0.1, -1, -1, 0.1, 31, 20
SEL, R, EDGE, BODY, left
E1 = SELID(1)
SEL, S, EDGE, BOX, 14.9, -1, -1, 15.1, 31, 20
SEL, R, EDGE, BODY, right
E2 = SELID(1)
BLEND, G2, E1, E2
NAME, LAST, bridge
SEW, left, bridge, right
NAME, LAST, skin

! ---- a panel carried on 6 past one edge, with a round hole trimmed out ----
NURBS, 3, (0, 50, 0), (0, 60, 4), (0, 70, 4), (0, 80, 0)
NURBS, 3, (30, 50, 2), (30, 60, 6), (30, 70, 6), (30, 80, 2)
NSURF, 1, LAST-1, LAST
NAME, LAST, panel
EXTEND, panel, 6, U1
CIRCLE, 15, 65, 20, 6
NAME, LAST, hole
TRIM, panel, hole, 15, 65, 4

! ---- a block whose top takes the shape of a wavy surface, and one side moved in ----
BLOCK, 60, 0, 0, 30, 30, 10
NAME, LAST, base
SURFACE, PARAM, u, v, 13 + 2*sin(12*u)*sin(12*v), 50, 100, -10, 40
NAME, LAST, wave
SEL, S, FACE, NORMAL, 0, 0, 1
SEL, R, FACE, BODY, base
REPLACEFACE, wave
HIDE, wave
SEL, S, FACE, NORMAL, 1, 0, 0
SEL, R, FACE, BODY, base
MOVEFACE, -6, 0, 0
