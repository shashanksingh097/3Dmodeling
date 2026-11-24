! # From a scan to an exact part
! A scanned part arrives as triangles (an STL file). The scan is split into regions at its
! sharp edges, each region is fitted exactly as a plane, cylinder or sphere, and the fitted
! faces are joined into one solid that can be edited, drawn and machined. Then the solid is
! measured against the scan.
! ## The scan
! (Here the "scanned" part is made first and written as STL, so the example needs no files;
! with a real scan, start at IMPORT.)
BLOCK, 0, 0, 0, 60, 40, 20
NAME, LAST, part
CYL, 35, 20, -1, 5, 30
SUBTRACT, part, LAST
CYL, 45, 20, 20, 6, 10
UNION, part, LAST
SPHERE, 15, 20, 20, 5
UNION, part, LAST
EXPORT, STL, "scan.stl", part
CLEAR
IMPORT, STL, "scan.stl", scan, MESH
COLOR, scan, GREY
! ## What is in it: regions, each with the shape that fits it best
SEGMENT, scan
! ## The exact solid
RECONSTRUCT, scan
NAME, LAST, solid
COLOR, solid, ORANGE
CHECK, solid
! ## How far is the solid from the scan?
DEVIATION, scan, solid, 0.05
! ## Written out, ready for the next step
EXPORT, STEP, "part.step", solid
MOVE, solid, 0, 50, 0
VIEW, ISO
FIT
