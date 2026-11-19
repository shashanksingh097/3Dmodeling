! A plate held by an M8 cap screw with a washer and a nut, a clearance hole checked with CLEARANCE,
! and a short stud with a real M6 thread.
T = 10
BLOCK, -30, -20, 0, 60, 40, T
NAME, LAST, plate
HOLE, plate, 0, 0, T, 9
FASTENER, WASHER, M8, 0, 0, T
NAME, LAST, washer
FASTENER, CAP, M8, 0, 0, T + 1.6, 25
NAME, LAST, screw
FASTENER, NUT, M8, 0, 0, 0
NAME, LAST, nut
CYL, 50, 0, 0, 3, 16
NAME, LAST, stud
SEL, S, FACE, TYPE, CYLINDER
SEL, R, FACE, RADIUS, EQ, 3
THREAD, , 10
SEL, NONE
FITS, H7/g6, 8
ASSERT, CLEARANCE(screw, plate), GE, 0.4
ASSERT, OVERLAP(screw, plate), EQ, 0
ASSERT, TOUCH(washer, plate)
ASSERT, TOUCH(nut, plate)
ASSERT, VALID(stud)
