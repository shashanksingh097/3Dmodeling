! A face sculpted on a ball: every stroke is one SCULPT step (LANGUAGE.md section 28).
! In the window the Sculpt tab writes these lines for you as you drag over the mesh.
SPHERE, 0, 0, 0, 20
NAME, LAST, head
TOMESH, head
REMESH, head, 0.6
! brow ridges (the mirror in x = 0 makes both)
STROKE, S1, "4,-19,6  6,-19,6.5  8,-19,7  10,-19,7.5  12,-19,8"
SCULPT, head, CLAY, 4, 0.8, S1, X
! the nose
STROKE, S2, "0,-20,-2  0,-20,0  0,-20,2"
SCULPT, head, INFLATE, 4, 0.9, S2
! the mouth
STROKE, S3, "2,-18,-8  4,-18,-8.4  6,-18,-8.9  9,-18,-9.5"
SCULPT, head, CREASE, 2.5, 0.6, S3, X
! keep the brows, then dig the eye sockets
MASK, head, PAINT, 0, 0, 0, 4, 1, S1
STROKE, S4, "6,-16,2  7.5,-16,2  9,-16,2"
SCULPT, head, DRAW, 3, -0.8, S4, X
MASK, head, CLEAR
SCULPT, head, SMOOTH, 3, 0.5, S4, X
