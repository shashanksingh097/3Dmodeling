! Scan to CAD (FITSURF): smooth NURBS surfaces fitted to meshes (docs/mesh-fit.md).
! A sculpted head stands in for a scanned part.
SPHERE, 0, 0, 0, 20
NAME, LAST, scan
TOMESH, scan
REMESH, scan, 0.8
STROKE, S1, "0,-20,-2  0,-20,0  0,-20,2"
SCULPT, scan, INFLATE, 5, 0.9, S1
STROKE, S2, "6,-18,6  10,-17,7  14,-15,7"
SCULPT, scan, CLAY, 4, 0.6, S2, X
! the whole closed mesh: one smooth surface wrapped round it, closed into a solid
FITSURF, scan, ALL, 0.15
NAME, LAST, fitted
MOVE, fitted, 50, 0, 0
! only the face of it: paint the region, then fit that region as one trimmed face
MASK, scan, PAINT, 0, -20, 2, 16
FITSURF, scan, MASK, 0.1
NAME, LAST, front
MOVE, front, 100, 0, 0
! the fitted solid is ordinary CAD: it takes booleans, fillets and shells
CYL, 50, 0, -30, 4, 60
SUBTRACT, fitted, LAST
