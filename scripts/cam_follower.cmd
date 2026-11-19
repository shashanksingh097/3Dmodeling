! Cams and more gears: a disc cam lifting its roller (CAM, CAMLIFT), a barrel cam with its groove,
! a pair of bevel gears at right angles, and a worm driving a worm wheel. Change A to turn the cam;
! the roller follows by CAMLIFT.
A = 40
LAW = "R12/150 D30 F12/150 D30"
CAM, 0, 0, 0, LAW, 30, 8, 12, DISC, 10
ROTATE, cam_1, A, 0, 0, 0, 0, 0, 1
MOVE, cam_1_roller, CAMLIFT(LAW, A), 0, 0
CAM, -110, 0, 0, "R30/180H F30/180H", 30, 6, 80, BARREL, 12
! a bevel pair, 20 teeth meshing with 30, the axes meeting at a right angle
GEAR, 0, 90, 0, 2, 20, 10, BEVEL, 0, 8, 20, 0, 0, 1, 30
GEAR, 20.1, 90, 30, 2, 30, 10, BEVEL, 0, 10, 20, -1, 0, 0, 20
ROTATE, LAST, 6, 20.1, 90, 30, -1, 0, 0
! a single-start worm along X and its wheel
GEAR, 70, 0, 0, 2, 1, 60, WORM, 0, 0, 20, 1, 0, 0
GEAR, 100, -8, 40.15, 2, 30, 16, WORMWHEEL, 0, 10, 20, 0, 1, 0
ROTATE, LAST, 8, 100, -8, 40.15, 0, 1, 0
