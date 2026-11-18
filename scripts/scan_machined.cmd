! Scan to CAD for machined parts (SEGMENT, RECONSTRUCT): a mesh of a block with a bore, a boss and a dome
! is split at its sharp edges, each region is fitted exactly as a plane, cylinder or sphere, and the
! fitted faces are joined into one exact solid. Here the mesh is made with TOMESH; a real scan is IMPORTed.
BLOCK, 0, 0, 0, 60, 40, 20
NAME, LAST, part
CYL, 35, 20, -1, 5, 30
SUBTRACT, part, LAST
CYL, 45, 20, 20, 6, 10
UNION, part, LAST
SPHERE, 15, 20, 20, 5
UNION, part, LAST
TOMESH, part
NAME, part, scan
! what is in the scan: 10 regions, each with its fit
SEGMENT, scan
RECONSTRUCT, scan
NAME, LAST, solid
MOVE, solid, 0, 50, 0
COLOR, solid, ORANGE
FIT
