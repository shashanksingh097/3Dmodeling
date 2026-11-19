! A moulded case (BOSS, SNAP, VENT): a box hollowed to 2 mm walls and open at the bottom, with
! four screw bosses with ribs on the inside of the top, two snap hooks standing on the open rim, a vent of six
! slots in the top, and a second, turned vent in one end wall. The case is shown upside down
! (open side up) so the bosses and hooks can be seen; SNAP reports the bending strain each
! hook takes to snap in.
BLOCK, 0, 0, 0, 90, 60, 30
NAME, LAST, case
MATERIAL, case, ABS
SEL, S, FACE, LOC, Z, 0
SHELL, 2
SEL, S, FACE, LOC, Z, 30
VENT, 6, 30, 2.5, 6, 0, 0, 0, 0
SEL, S, FACE, LOC, X, 90
VENT, 4, 16, 2, 4.5, 90
BOSS, case, 10, 10, 28, 20, 7, 2.5, 4, 0, 0, 0, -1
BOSS, case, 80, 10, 28, 20, 7, 2.5, 4, 0, 0, 0, -1
BOSS, case, 10, 50, 28, 20, 7, 2.5, 4, 0, 0, 0, -1
BOSS, case, 80, 50, 28, 20, 7, 2.5, 4, 0, 0, 0, -1
SNAP, case, 45, 0.4, 0, 10, 8, 1.2, 0.8, 0, 0, -1, 0, -1, 0
SNAP, case, 45, 59.6, 0, 10, 8, 1.2, 0.8, 0, 0, -1, 0, 1, 0
SEL, NONE
