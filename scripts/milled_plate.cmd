! 2.5D milling (MILL): a plate with a pocket around a round boss and two bolt holes. The pocket
! is cleared down to its floor in rings, from the middle out to the wall, 4 mm a cut with a 6 mm
! end mill; MILL, ..., file.nc writes the G-code. The cyan lines are the tool's centre.
BLOCK, 0, 0, 0, 80, 60, 16
NAME, LAST, plate
BLOCK, 12, 12, 6, 48, 36, 20
SUBTRACT, plate, LAST
CYL, 36, 30, 6, 7, 10
UNION, plate, LAST
CYL, 70, 10, -1, 3, 20
SUBTRACT, plate, LAST
CYL, 70, 50, -1, 3, 20
SUBTRACT, plate, LAST
SEL, S, FACE, LOC, Z, 6
CM, floor, FACE
SEL, NONE
MILL, plate, POCKET, floor, 6, 4
