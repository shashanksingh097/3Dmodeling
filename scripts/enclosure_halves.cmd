! Ribs, lips and wrapped text (RIB, LIP, WRAP): two halves of an enclosure and a knurled knob.
W = 60
D = 40
H = 18
T = 2
! the base half: an open box with a rib across the floor and a lip on its rim
BLOCK, 0, 0, 0, W, D, H
NAME, LAST, base
SEL, S, FACE, AT, W/2, D/2, H
SHELL, T
PLANE, mid, XZ, D/2
SKETCH, r1, mid
SLINE, -(W - T), H/2, -T, H/2
ENDSKETCH
RIB, r1, 1.5, base
SEL, S, FACE, AT, T/2, D/2, H
LIP, , 2, 0.8
! the lid: the same box, upside down above it, with the matching groove
BLOCK, 0, 0, H + 15, W, D, 8
NAME, LAST, lid
SEL, S, FACE, AT, W/2, D/2, H + 15
SHELL, T
SEL, S, FACE, AT, T/2, D/2, H + 15
LIP, , 2, 0.8, GROOVE, 0.2
! a gusset in the corner of an angle bracket
BLOCK, 80, 0, 0, 40, 30, 4
NAME, LAST, angle
BLOCK, 80, 0, 0, 4, 30, 40
UNION, angle, LAST
PLANE, g, XZ, 15
SKETCH, gs, g
SLINE, -84, 30, -110, 4
ENDSKETCH
RIB, gs, 3, angle
! a knob with raised grips and a sunk band wrapped round it
CYL, 150, 20, 0, 12, 20
NAME, LAST, knob
PLANE, k, XZ, 5
SKETCH, grips, k
SRECT, -150 - 28 - 1.5, 5, -150 - 28 + 1.5, 17
SRECT, -150 - 21 - 1.5, 5, -150 - 21 + 1.5, 17
SRECT, -150 - 14 - 1.5, 5, -150 - 14 + 1.5, 17
SRECT, -150 - 7 - 1.5, 5, -150 - 7 + 1.5, 17
SRECT, -150 + 0 - 1.5, 5, -150 + 0 + 1.5, 17
SRECT, -150 + 7 - 1.5, 5, -150 + 7 + 1.5, 17
SRECT, -150 + 14 - 1.5, 5, -150 + 14 + 1.5, 17
SRECT, -150 + 21 - 1.5, 5, -150 + 21 + 1.5, 17
SRECT, -150 + 28 - 1.5, 5, -150 + 28 + 1.5, 17
ENDSKETCH
SEL, S, FACE, AT, 162, 20, 10
WRAP, grips, , 1
SKETCH, band, k
SRECT, -150 - 35, 1.5, -150 + 35, 3
ENDSKETCH
SEL, S, FACE, AT, 162, 20, 10
WRAP, band, , 0.4, CUT
SEL, NONE
! the planes were only for the sketches
DATUM, DELETE, mid
DATUM, DELETE, g
DATUM, DELETE, k
FIT
