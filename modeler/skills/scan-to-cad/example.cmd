! Scan to CAD: a machined part turned into a mesh (a real scan would be IMPORTed), split into regions at its
! sharp edges, each fitted exactly as a plane, cylinder or sphere, and joined back into one exact solid.
BLOCK, 0, 0, 0, 60, 40, 20
NAME, LAST, part
CYL, 35, 20, -1, 5, 30
SUBTRACT, part, LAST
CYL, 45, 20, 20, 6, 10
UNION, part, LAST
TOMESH, part
NAME, part, scan
SEGMENT, scan
RECONSTRUCT, scan
NAME, LAST, solid
ASSERT, VALID(solid)
ASSERT, PIECES(solid), EQ, 1
! the bore comes back as 9.99 across, not exactly 10: fits follow the scan, so check counts and sizes with a tolerance
ASSERT, HOLES(solid), EQ, 1
ASSERT, BBOX(solid).dz, EQ, 30, 0.05
