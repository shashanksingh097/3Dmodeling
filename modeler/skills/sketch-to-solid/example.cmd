! A plate sketched with sizes from parameters, a boss sketched on its top face, and a turned knob.
W = 80
H = 50
T = 6
HOLE_D = 8
SKETCH, base, XY
SRECT, 0, 0, W, H
SCON, COINCIDENT, 1.S, ORIGIN
SDIM, LENGTH, 1, W
SDIM, LENGTH, 2, H
SCIRCLE, 12, 12, HOLE_D/2
SCIRCLE, W - 12, 12, HOLE_D/2
ENDSKETCH
EXTRUDE, base, T
NAME, LAST, plate
SEL, S, FACE, NORMAL, 0,0,1
SKETCH, boss, FACE, SEL
SCIRCLE, 0, 8, 10
ENDSKETCH
EXTRUDE, boss, 12, ADD, plate
SEL, NONE
SKETCH, knob_s, ZX
SPOLY, 0, 0, 15, 0, 15, 4, 10, 10, 0, 10, CLOSE
ENDSKETCH
REVOLVE, knob_s, V
NAME, LAST, knob
MOVE, knob, 150, 0, 0
ASSERT, VALID(plate)
ASSERT, PIECES(plate), EQ, 1
ASSERT, HOLES(plate, HOLE_D), EQ, 2
ASSERT, BBOX(plate).dz, EQ, T + 12, 0.01
ASSERT, VALID(knob)
ASSERT, BBOX(knob).dx, EQ, 30, 0.01
