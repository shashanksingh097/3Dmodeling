! A gear pair at the right centre distance, the second gear turned half a tooth so the teeth mesh,
! and a disc cam with its roller lifted by CAMLIFT at the cam angle A.
M = 2
Z1 = 20
Z2 = 30
A = 40
GEAR, 0, 0, 0, M, Z1, 10, , , 8
NAME, LAST, pinion
GEAR, M*(Z1 + Z2)/2, 0, 0, M, Z2, 10, , , 8
NAME, LAST, wheel
ROTATE, wheel, 180/Z2, M*(Z1 + Z2)/2, 0, 0
LAW = "R10/150 D30 F10/150 D30"
CAM, 0, 80, 0, LAW, 25, 6, 10, DISC, 8
ROTATE, cam_1, A, 0, 80, 0, 0, 0, 1
MOVE, cam_1_roller, CAMLIFT(LAW, A), 0, 0
ASSERT, VALID(pinion)
ASSERT, VALID(wheel)
ASSERT, OVERLAP(pinion, wheel), EQ, 0
ASSERT, BBOX(pinion).dx, EQ, M*(Z1 + 2), 0.05
ASSERT, OVERLAP(cam_1, cam_1_roller), EQ, 0
