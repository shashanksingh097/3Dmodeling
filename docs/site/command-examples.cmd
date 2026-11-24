! One small, complete example for every command, for the user guide website.
!
! Each example starts with a line "@ NAME" and runs on its own in a new,
! empty model (tests/test_docsite.py runs every one, so they cannot go stale).
! The "!" lines right under the "@" line are the example's caption.
! Words after the name:
!   pic     the website shows a picture of the model it makes
!   window  needs the app's 3D view; the headless test skips it
! Commands that work on a file make the file first, in the same example.

! ===================================================================== Parameters

@ CONFIG
! Two sizes of one plate: a configuration is a named set of parameter values.
W = 40
BLOCK, 0,0,0, W, 20, 5
CONFIG, wide, "W = 80"
USECONFIG, wide
ASSERT, BBOX(1).dx, EQ, 80

@ USECONFIG
! Switch between configurations; DEFAULT goes back to the history's own values.
W = 40
BLOCK, 0,0,0, W, 20, 5
CONFIG, small, "W = 20"
USECONFIG, small
USECONFIG, DEFAULT
USECONFIG

@ DRIVE
! Move an assembly by a parameter without changing the history.
A = 0
BLOCK, 0,0,0, 40, 30, 5
NAME, LAST, base
BLOCK, 0,0,5, 40, 30, 2
NAME, LAST, lid
ROTATE, lid, -A, 0,0,5, 0,1,0
DRIVE, A, 75
DRIVE

! ===================================================================== Solids

@ BLOCK pic
! A box 40 long, 20 deep and 10 high, its corner at the origin.
BLOCK, 0,0,0, 40, 20, 10

@ CYL pic
! A cylinder of radius 10 and height 30 standing on the origin, and one lying along X.
CYL, 0,0,0, 10, 30
CYL, 20,0,5, 5, 40, 1,0,0

@ TUBE pic
! A pipe: outer radius 12, inner radius 9, 40 long.
TUBE, 0,0,0, 12, 9, 40

@ SPHERE pic
! A ball of radius 15 around the origin.
SPHERE, 0,0,0, 15

@ CONE pic
! A cone from radius 12 at the base to 4 at the top, 25 high.
CONE, 0,0,0, 12, 4, 25

@ TORUS pic
! A ring: 20 from the centre to the middle of the tube, tube radius 5.
TORUS, 0,0,0, 20, 5

@ WEDGE pic
! A wedge: base 40 x 20, 15 high, its top face only 10 long.
WEDGE, 0,0,0, 40, 15, 20, 10

@ SPRING pic
! A compression spring: radius 10, pitch 6, 8 turns of 1.5 wire, closed and ground ends.
SPRING, 0,0,0, 10, 6, 8, 1.5, , , , , 1, GROUND

! ===================================================================== Sketch

@ SKETCH pic
! Draw a plate with a hole on the XY plane, then push it up 6.
SKETCH, plate, XY
SRECT, 0, 0, 60, 40
SCIRCLE, 30, 20, 8
ENDSKETCH
EXTRUDE, plate, 6

@ EXTRUDE pic
! A plate, then a boss added on its top face and a pocket cut into it.
SKETCH, s1, XY
SRECT, 0, 0, 60, 40
ENDSKETCH
EXTRUDE, s1, 8
NAME, LAST, plate
PLANE, top, XY, 8
SKETCH, s2, top
SCIRCLE, 20, 20, 8
ENDSKETCH
EXTRUDE, s2, 10, ADD, plate
SKETCH, s3, top
SRECT, 38, 10, 52, 30
ENDSKETCH
EXTRUDE, s3, -4, CUT, plate

@ REVOLVE pic
! Turn a profile a full turn about the sketch's vertical axis: a pulley.
SKETCH, pulley, XZ
SPOLY, 5, 0, 30, 0, 30, 4, 22, 8, 30, 12, 30, 16, 5, 16, CLOSE
ENDSKETCH
REVOLVE, pulley, V

@ SDXF
! Read a 2D DXF drawing into a sketch. The first lines make the DXF from a flat plate.
SKETCH, s1, XY
SRECT, 0, 0, 50, 30
SCIRCLE, 25, 15, 6
ENDSKETCH
SHEET, s1, 2
UNFOLD, 1, blank.dxf, NO
CLEAR
SKETCH, s2, XY
SDXF, blank.dxf
ENDSKETCH
EXTRUDE, s2, 4

@ STRACE
! Trace the dark shapes of a picture into a sketch, 60 wide. logo.png comes with the example files.
SKETCH, logo, XY
STRACE, logo.png, 60
ENDSKETCH
EXTRUDE, logo, 3

@ IMAGE
! Show a picture 120 wide on the XY plane, to draw over it. It is not a body; IMAGE, CLEAR takes it away.
IMAGE, logo.png, XY, 120

! ===================================================================== Curves

@ LINE
! A straight curve from (0,0,0) to (50,0,20).
LINE, 0,0,0, 50,0,20

@ ARC
! An arc from one point, through a second, to a third.
ARC, 0,0,0, 25,15,0, 50,0,0

@ POLYLINE
! Straight pieces through four points; CLOSE joins the last to the first.
POLYLINE, (0,0,0), (40,0,0), (40,25,0), (0,25,0), CLOSE

@ SPLINE pic
! A smooth curve through points, used as the path of a pipe.
SPLINE, (0,0,0), (20,15,5), (40,0,15), (60,-10,10)
PIPE, LAST, 3

@ HELIX pic
! A helix of radius 10, pitch 5 and 6 turns, with a round wire swept along it.
HELIX, 0,0,0, 10, 5, 6
PIPE, LAST, 1

@ CURVE pic
! An equation curve (angles in degrees): two turns of a spiral, then a pipe along it.
CURVE, PARAM, 20*cos(t), 20*sin(t), 0.05*t, 0, 720
PIPE, LAST, 2

@ TRACE
! Where the end of a turning arm goes as A runs from 0 to 90, kept as a curve.
A = 0
BLOCK, 0,-2,0, 40, 4, 4
NAME, LAST, arm
ROTATE, arm, A, 0,0,0, 0,0,1
TRACE, A, 0, 90, 9, arm, 40,0,2

! ===================================================================== Profiles

@ CIRCLE
! A circle of radius 10 on the XY plane; a profile for LOFT, SWEEP or EXTRUDE-like steps.
CIRCLE, 0,0,0, 10

@ ELLIPSE
! An ellipse 30 by 15 across, standing in the YZ plane.
ELLIPSE, 0,0,0, 15, 7.5, 1,0,0

@ RECT
! A 40 x 20 rectangle with corner radius 3, centred on the origin.
RECT, 0,0,0, 40, 20, 3

@ POLYGON
! A hexagon with corners 10 from the centre.
POLYGON, 0,0,0, 10, 6

@ STAR
! A five-pointed star, points 20 out, hollows 8 out.
STAR, 0,0,0, 20, 8, 5

@ SLOT
! A slot 50 long and 12 wide.
SLOT, 0,0,0, 50, 12

@ AIRFOIL pic
! A NACA 2412 wing section, chord 100, lofted with a smaller one 150 along Y.
AIRFOIL, 0,0,0, 100, 2412, 0,1,0
AIRFOIL, 10,150,0, 70, 2412, 0,1,0
LOFT, LAST-1, LAST

! ===================================================================== Shapes from curves

@ LOFT pic
! A smooth solid through a square, a circle and a smaller square.
RECT, 0,0,0, 40, 40
CIRCLE, 0,0,30, 15
RECT, 0,0,60, 20, 20
LOFT, LAST-2, LAST-1, LAST

@ SPINELOFT pic
! A duct: three sections placed across a curved centre line.
ARC, 0,0,0, 14.64,0,35.36, 50,0,50
NAME, LAST, spine
CIRCLE, 0,0,0, 9
NAME, LAST, inlet
RECT, 14.64,0,35.36, 20, 14, 4, 0.7071,0,0.7071
NAME, LAST, middle
CIRCLE, 50,0,50, 5, 1,0,0
NAME, LAST, outlet
SPINELOFT, spine, inlet, middle, outlet

@ SWEEP pic
! A rectangle moved 80 up a straight path, twisted 90 degrees and shrunk to half on the way.
RECT, 0,0,0, 30, 10
NAME, LAST, profile
LINE, 0,0,0, 0,0,80
NAME, LAST, path
SWEEP, profile, path, 90*t, 1 - 0.5*t

@ RAILSWEEP pic
! A wing swept along a span line between a leading and a trailing edge rail.
AIRFOIL, 0,0,0, 40, 2412, 0,-1,0, , 0
NAME, LAST, foil
LINE, 0,0,0, 0,120,0
NAME, LAST, spine
SPLINE, (0,0,0), (7,60,2), (28,120,8)
NAME, LAST, le
SPLINE, (40,0,0), (45,60,2), (44,120,8)
NAME, LAST, te
RAILSWEEP, foil, le, te, spine

@ MORPH pic
! A sweep that turns a square into a circle along a path.
LINE, 0,0,0, 0,0,60
NAME, LAST, path
RECT, 0,0,0, 30, 30
CIRCLE, 0,0,0, 15
MORPH, path, 0, 1, , LAST-1, LAST

@ PIPE pic
! A hollow pipe along a spline: outer radius 4, inner 3.
SPLINE, (0,0,0), (30,20,0), (60,0,20)
PIPE, LAST, 4, 3

! ===================================================================== Text and surfaces

@ TEXT pic
! Raised letters 1.5 high standing on a plate, and engraved ones.
BLOCK, 0,0,0, 90, 30, 5
NAME, LAST, plate
TEXT, "M8 BOLT", 8, 10, 5, 10, 1.5
UNION, plate, LAST

@ SURFACE pic
! A wavy surface from an equation, thickened to a 2 thick solid.
SURFACE, PARAM, u, v, 3*sin(6*u)*cos(6*v), 0, 60, 0, 60, 30, 30, 2

! ===================================================================== Freeform (NURBS)

@ NURBS
! A curve from control points; the middle points pull it like magnets.
NURBS, 3, (0,0,0), (10,8,0), (20,-8,0), (30,0,0)

@ NSURF pic
! A surface from four rows of control points.
NURBS, 3, (0,0,0), (10,0,4), (20,0,4), (30,0,0)
NURBS, 3, (0,13,2), (10,13,6), (20,13,6), (30,13,2)
NURBS, 3, (0,26,2), (10,26,6), (20,26,6), (30,26,2)
NURBS, 3, (0,40,0), (10,40,4), (20,40,4), (30,40,0)
NSURF, 3, LAST-3, LAST-2, LAST-1, LAST

@ NETWORK pic
! A dome through a network of three curves each way.
SPLINE, (0,0,0), (30,0,0), (60,0,0)
NAME, LAST, u1
SPLINE, (0,20,0), (15,20,11), (30,20,14), (45,20,10), (60,20,0)
NAME, LAST, u2
SPLINE, (0,40,0), (30,40,0), (60,40,0)
NAME, LAST, u3
SPLINE, (0,0,0), (0,20,0), (0,40,0)
NAME, LAST, v1
SPLINE, (30,0,0), (30,10,10), (30,20,14), (30,30,10), (30,40,0)
NAME, LAST, v2
SPLINE, (60,0,0), (60,20,0), (60,40,0)
NAME, LAST, v3
NETWORK, u1, u2, u3, ACROSS, v1, v2, v3

@ FILL
! Fill the space inside four curves with a smooth patch.
LINE, 0,0,0, 40,0,0
LINE, 40,0,0, 40,30,0
LINE, 40,30,0, 0,30,0
LINE, 0,30,0, 0,0,0
FILL, G0, 1, 2, 3, 4

@ BLEND pic
! Bridge two surfaces with a smooth (G2) surface between their facing edges.
NURBS, 3, (0,0,0), (0,10,6), (0,20,6), (0,30,0)
NURBS, 3, (-25,0,0), (-25,10,8), (-25,20,8), (-25,30,0)
NSURF, 1, LAST-1, LAST
NAME, LAST, left
NURBS, 3, (15,0,6), (15,10,12), (15,20,12), (15,30,6)
NURBS, 3, (40,0,4), (40,10,8), (40,20,8), (40,30,4)
NSURF, 1, LAST-1, LAST
NAME, LAST, right
SEL, S, EDGE, BOX, -0.1,-1,-1, 0.1,31,20
SEL, R, EDGE, BODY, left
E1 = SELID(1)
SEL, S, EDGE, BOX, 14.9,-1,-1, 15.1,31,20
SEL, R, EDGE, BODY, right
E2 = SELID(1)
BLEND, G2, E1, E2

@ SEW
! Sew a dome and a flat base whose edges meet into one closed solid.
SPLINE, (0,0,0), (30,0,0), (60,0,0)
NAME, LAST, u1
SPLINE, (0,20,0), (15,20,11), (30,20,14), (45,20,10), (60,20,0)
NAME, LAST, u2
SPLINE, (0,40,0), (30,40,0), (60,40,0)
NAME, LAST, u3
SPLINE, (0,0,0), (0,20,0), (0,40,0)
NAME, LAST, v1
SPLINE, (30,0,0), (30,10,10), (30,20,14), (30,30,10), (30,40,0)
NAME, LAST, v2
SPLINE, (60,0,0), (60,20,0), (60,40,0)
NAME, LAST, v3
NETWORK, u1, u2, u3, ACROSS, v1, v2, v3
NAME, LAST, dome
FILL, G0, u1, v3, u3, v1
NAME, LAST, base
SEW, dome, base
ASSERT, VALID(LAST)

@ EXTEND
! Carry a surface on 6 past its far edge.
NURBS, 3, (0,0,0), (0,10,4), (0,20,4), (0,30,0)
NURBS, 3, (30,0,2), (30,10,6), (30,20,6), (30,30,2)
NSURF, 1, LAST-1, LAST
NAME, LAST, panel
EXTEND, panel, 6, U1

@ TRIM
! Cut a round hole in a surface with a circle; the piece nearest the point goes.
NURBS, 3, (0,0,0), (0,10,4), (0,20,4), (0,30,0)
NURBS, 3, (30,0,2), (30,10,6), (30,20,6), (30,30,2)
NSURF, 1, LAST-1, LAST
NAME, LAST, panel
CIRCLE, 15,15,20, 6
NAME, LAST, hole
TRIM, panel, hole, 15, 15, 4

@ PROJECT
! Lay a circle straight down onto a curved surface.
NURBS, 3, (0,0,0), (0,10,4), (0,20,4), (0,30,0)
NURBS, 3, (30,0,2), (30,10,6), (30,20,6), (30,30,2)
NSURF, 1, LAST-1, LAST
NAME, LAST, panel
CIRCLE, 15,15,20, 6
PROJECT, LAST, panel, 0,0,-1

@ MOVEPT
! Pull control point 3 of a curve up by 12; the curve follows smoothly.
NURBS, 3, (0,0,0), (15,12,0), (30,-12,0), (45,12,0), (60,0,0)
NAME, LAST, wave
MOVEPT, wave, 3, 0,0,12

@ WEIGHT
! Make control point 2 pull three times as hard.
NURBS, 3, (0,0,0), (15,12,0), (30,-12,0), (45,12,0), (60,0,0)
NAME, LAST, wave
WEIGHT, wave, 2, 3

@ KNOT
! Add a knot half way along: more control points, same shape.
NURBS, 3, (0,0,0), (15,12,0), (30,-12,0), (45,12,0), (60,0,0)
NAME, LAST, wave
KNOT, wave, 0.5
POLES, wave

@ DEGREE
! Raise a curve to degree 5: same shape, more control points.
NURBS, 3, (0,0,0), (15,12,0), (30,-12,0), (45,12,0), (60,0,0)
NAME, LAST, wave
DEGREE, wave, 5

@ REBUILD
! Remake a polyline as one smooth curve with 8 control points.
POLYLINE, (0,0,0), (20,0,0), (20,20,0), (40,20,0)
NAME, LAST, path
REBUILD, path, 8

@ POLES
! List the control points of a curve, with the numbers MOVEPT uses.
NURBS, 3, (0,0,0), (10,8,0), (20,-8,0), (30,0,0)
POLES, LAST

@ ANALYZE pic
! Zebra stripes on a smooth body: every join between faces is judged G2, G1 or creased.
BLOCK, 0,0,0, 40, 30, 20
NAME, LAST, b
SEL, S, EDGE, LOC, Z, 20
FILLET, 6
ANALYZE, b, ZEBRA

@ CONTINUITY
! How well the faces join: a rounded edge is tangent (G1), the rest are sharp.
BLOCK, 0,0,0, 40, 30, 20
SEL, S, EDGE, LOC, Z, 20
FILLET, 6
CONTINUITY, LAST

@ COMB
! A curvature comb on every curved edge of a body.
BLOCK, 0,0,0, 40, 30, 20
SEL, S, EDGE, LOC, Z, 20
FILLET, 6
COMB, LAST

@ INSPECT
! Places worth a second look: here a thin wall round a big hole.
BLOCK, 0,0,0, 40, 20, 10
CYL, 20,10,-1, 9.5, 12
SUBTRACT, 1, 2
INSPECT, LAST

! ===================================================================== Combine

@ UNION pic
! Fuse a block and a cylinder into one body.
BLOCK, 0,0,0, 40, 40, 10
CYL, 20,20,10, 10, 15
UNION, 1, 2

@ SUBTRACT pic
! Cut a cylinder out of a block: a hole.
BLOCK, 0,0,0, 40, 40, 10
NAME, LAST, plate
CYL, 20,20,-1, 8, 12
SUBTRACT, plate, LAST

@ INTERSECT pic
! Keep only what a block and a ball have in common.
BLOCK, -10,-10,-10, 20, 20, 20
SPHERE, 0,0,0, 13
INTERSECT, 1, 2

@ KEEP
! Keep the inputs of booleans (hidden), so they can be used again.
KEEP, ON
BLOCK, 0,0,0, 40, 40, 10
CYL, 20,20,-1, 8, 12
SUBTRACT, 1, 2
KEEP, OFF

! ===================================================================== Features

@ FILLET pic
! Round the four top edges of a block with radius 3.
BLOCK, 0,0,0, 60, 40, 10
SEL, S, EDGE, LOC, Z, 10
FILLET, 3

@ CHAMFER pic
! Bevel the top edges of a block by 2.
BLOCK, 0,0,0, 60, 40, 10
SEL, S, EDGE, LOC, Z, 10
CHAMFER, 2

@ HOLE pic
! A plain through hole, a counterbored hole and a countersunk hole in a plate.
BLOCK, 0,0,0, 90, 40, 10
NAME, LAST, plate
HOLE, plate, 15,20,10, 6
HOLE, plate, 45,20,10, 6, 0, CBORE, 11, 4
HOLE, plate, 75,20,10, 6, 0, CSINK, 12

@ THREAD pic
! An M8 thread on an 8 mm shaft: pick its round side face, then THREAD.
CYL, 0,0,0, 4, 20
SEL, S, FACE, TYPE, CYLINDER
THREAD

@ SHELL pic
! Hollow a box with 2 thick walls, open at the top face.
BLOCK, 0,0,0, 60, 40, 30
PICK, FACE, 6
SHELL, 2

@ DRAFT
! Tilt the four side faces of a block 3 degrees, for a mould.
BLOCK, 0,0,0, 40, 30, 20
SEL, S, FACE, TYPE, PLANE
SEL, U, FACE, NORMAL, 0,0,1
SEL, U, FACE, NORMAL, 0,0,-1
DRAFT, 3

@ OFFSET
! Grow a whole body by 2 all round.
BLOCK, 0,0,0, 30, 20, 10
OFFSET, LAST, 2

@ SPLIT
! Cut a block in two at the XY plane moved up 5; both pieces stay.
BLOCK, 0,0,0, 30, 20, 10
PLANE, mid, XY, 5
SPLIT, 1, mid

@ KNIFE
! Cut a block in two along a curve, straight down through it.
BLOCK, 0,0,0, 60, 40, 20
NAME, LAST, loaf
SPLINE, (10,-10,30), (25,20,30), (40,50,30)
KNIFE, loaf, LAST, 0, 0,0,-1

@ RIB pic
! A 2 thick rib from a sketched line down to the plate and the wall.
BLOCK, 0,0,0, 60, 40, 5
NAME, LAST, base
BLOCK, 0,0,0, 5, 40, 40
UNION, base, LAST
PLANE, mid, ZX, 20
SKETCH, r1, mid                ! on the XZ plane, u runs along -X and v along Z
SLINE, -15, 20, -35, 10
ENDSKETCH
RIB, r1, 2, base

@ LIP
! A lip on the rim of an open box: a band 0.8 wide stands up 2 along the inside edge.
BLOCK, 0,0,0, 60, 40, 20
PICK, FACE, 6
SHELL, 2
SEL, S, FACE, LOC, Z, 20
LIP, , 2, 0.8

@ WRAP pic
! Wrap three bars round a cylinder, standing out 1.
CYL, 0,0,0, 15, 40
PLANE, w, XZ, -15
SKETCH, grips, w
SRECT, -12, 10, -8, 30
SRECT, -2, 10, 2, 30
SRECT, 8, 10, 12, 30
ENDSKETCH
SEL, S, FACE, TYPE, CYLINDER
WRAP, grips, , 1

! ===================================================================== Sheet metal

@ SHEET
! A 2 thick sheet metal plate with a hole and a slot, from a sketch.
SKETCH, base, XY
SRECT, 0, 0, 60, 40
SCIRCLE, 30, 20, 6
SSLOT, 12, 10, 12, 30, 2.5
ENDSKETCH
SHEET, base, 2, 2

@ FLANGE pic
! Bend a 25 wall up along one edge and a 15 wall at 45 degrees along another.
SKETCH, base, XY
SRECT, 0, 0, 60, 40
ENDSKETCH
SHEET, base, 2, 2
NAME, LAST, bracket
SEL, S, EDGE, AT, 30, 0, 2
FLANGE, , 25
SEL, S, EDGE, AT, 60, 20, 0
FLANGE, , 15, 45

@ TOSHEET
! A bent bracket saved as STEP and read back has no sheet metal record;
! TOSHEET finds its thickness and bends so UNFOLD lays it flat.
SKETCH, base, XY
SRECT, 0, 0, 60, 40
ENDSKETCH
SHEET, base, 2, 2
SEL, S, EDGE, AT, 30, 0, 2
FLANGE, , 25
EXPORT, STEP, "tosheet_bracket.step", 1
CLEAR
IMPORT, STEP, "tosheet_bracket.step", bracket
TOSHEET, bracket
UNFOLD, bracket

@ SBEND
! Bend a plate 90 degrees along a line sketched across it.
SKETCH, base, XY
SRECT, 0, 0, 80, 40
ENDSKETCH
SHEET, base, 2, 2
PLANE, top, XY, 2
SKETCH, bendline, top
SLINE, 50, -5, 50, 45
ENDSKETCH
SBEND, 1, bendline

@ UNFOLD pic
! Lay a bent part flat: the flat blank appears beside it.
SKETCH, base, XY
SRECT, 0, 0, 60, 40
ENDSKETCH
SHEET, base, 2, 2
NAME, LAST, bracket
SEL, S, EDGE, AT, 30, 0, 2
FLANGE, , 25
SEL, NONE
UNFOLD, bracket

@ SHEETINFO
! What a sheet metal body is: thickness, bend radius, K-factor and each flange.
SKETCH, base, XY
SRECT, 0, 0, 60, 40
ENDSKETCH
SHEET, base, 2, 2
NAME, LAST, bracket
SEL, S, EDGE, AT, 30, 0, 2
FLANGE, , 25
SHEETINFO, bracket

! ===================================================================== Frames

@ MEMBER pic
! A square-tube frame along a closed path, with mitred corners.
POLYLINE, (0,0,0), (600,0,0), (600,400,0), (0,400,0), CLOSE
NAME, LAST, frame
MEMBER, frame, SQUARE, 40x3

@ WELD
! Weld beads at every joint of a frame.
POLYLINE, (0,0,0), (600,0,0), (600,400,0), (0,400,0), CLOSE
NAME, LAST, frame
MEMBER, frame, SQUARE, 40x3, BUTT
WELD, ALL, 4

@ CUTLIST
! The frame's cut list: each member with its length and end cuts.
POLYLINE, (0,0,0), (600,0,0), (600,400,0), (0,400,0), CLOSE
NAME, LAST, frame
MEMBER, frame, SQUARE, 40x3
CUTLIST

! ===================================================================== Pipes and cables

@ ROUTE pic
! A 22 x 1.5 pipe along a path, bent at the corners.
POLYLINE, (0,0,0), (200,0,0), (200,150,0), (200,150,100)
NAME, LAST, p1
ROUTE, p1, PIPE, 22x1.5

@ ROUTES
! The list of pipes: length, bends and tees.
POLYLINE, (0,0,0), (200,0,0), (200,150,0)
NAME, LAST, p1
ROUTE, p1, PIPE, 22x1.5
ROUTES

! ===================================================================== Standard parts

@ GEAR pic
! Two spur gears that mesh: module 2, 20 and 30 teeth, 10 wide.
GEAR, 0,0,0, 2, 20, 10
GEAR, 50,0,0, 2, 30, 10
CLASH, 1, 2

@ FASTENER pic
! An M8 x 25 cap screw with a washer under its head, standing on z = 10.
FASTENER, WASHER, M8, 0,0,10
FASTENER, CAP, M8, 0,0,11.6, 25

@ CAM pic
! A disc cam that rises 10 over 120 degrees, dwells, falls 10 and dwells, with its roller.
CAM, 0,0,0, "R10/120 D60 F10/120 D60", 30, 8, 12

! ===================================================================== Plastic parts

@ BOSS pic
! A screw boss with four ribs on the floor of a shelled case.
BLOCK, 0,0,0, 60, 40, 20
NAME, LAST, case
PICK, FACE, 6
SHELL, 2
BOSS, case, 30, 20, 2, 10, 7, 2.5

@ SNAP pic
! A cantilever snap hook standing on a plate: 12 long, 6 wide, 1.5 thick.
BLOCK, 0,0,0, 40, 40, 2
NAME, LAST, lid
SNAP, lid, 20, 20, 2, 12, 6, 1.5

@ VENT pic
! Six slots 20 x 2 through the picked top face.
BLOCK, 0,0,0, 60, 40, 3
PICK, FACE, 6
VENT, 6, 20, 2

! ===================================================================== Moulds

@ PARTING
! Which faces come out of which mould half, pulled along Z.
BLOCK, 0,0,0, 40, 30, 10
NAME, LAST, cap
SEL, S, EDGE, LOC, Z, 10
FILLET, 3
PARTING, cap

@ MOLD pic
! The two halves of a mould round a part, 8 margin, 0.5 % shrink.
BLOCK, 0,0,0, 40, 30, 10
NAME, LAST, cap
SEL, S, EDGE, LOC, Z, 10
FILLET, 3
MOLD, cap, 8, 0.5
MOVE, cap_top, 0, 0, 30

! ===================================================================== Edit faces

@ PUSHPULL
! Move the top face of a block up 6; the side faces stretch to meet it.
BLOCK, 0,0,0, 40, 30, 10
PICK, FACE, 6
PUSHPULL, 6

@ DELFACE
! Remove a hole: pick its wall and delete it; the plate closes up.
BLOCK, 0,0,0, 40, 30, 10
HOLE, 1, 20, 15, 10, 8
SEL, S, FACE, TYPE, CYLINDER
DELFACE

@ FEATURES pic
! The holes, rounds, chamfers and rows of holes on a part, found from its faces
! alone, so it works on imported STEP parts too.
BLOCK, 0,0,0, 80,40,10
NAME, LAST, plate
SEL, S, EDGE, LOC, Z, 10
SEL, R, EDGE, LOC, X, 0
FILLET, 3
SEL, S, FACE, LOC, Z, 10
HOLE, plate, 20,20,10, 6
HOLE, plate, 40,20,10, 6
HOLE, plate, 60,20,10, 6
FEATURES, plate

@ DEFEATURE
! Remove every round under 4 and every 6 hole in one step each.
BLOCK, 0,0,0, 80,40,10
NAME, LAST, plate
SEL, S, EDGE, LOC, Z, 10
FILLET, 2
SEL, S, FACE, LOC, Z, 10
HOLE, plate, 20,20,10, 6
DEFEATURE, plate, FILLET, LT, 4
DEFEATURE, plate, HOLE, EQ, 6

@ RESIZE
! Every 6 hole becomes 8, in place, keeping its depth.
BLOCK, 0,0,0, 80,40,10
NAME, LAST, plate
SEL, S, FACE, LOC, Z, 10
HOLE, plate, 20,20,10, 6
HOLE, plate, 60,20,10, 6, 5
RESIZE, plate, HOLE, EQ, 6, 8
FEATURES, plate, HOLE

@ HANDLES
! The drag handles the 3D view shows for a pick, and the step a drag of each
! writes (turn on Home > Drag handles to drag them with the mouse).
BLOCK, 0,0,0, 40,20,10
NAME, LAST, plate
PICK, BODY, plate
HANDLES

@ MOVEFACE
! Move the +X side face of a block 6 in -X.
BLOCK, 0,0,0, 40, 30, 10
SEL, S, FACE, NORMAL, 1,0,0
MOVEFACE, -6, 0, 0

@ REPLACEFACE pic
! Give the top face of a block the shape of a wavy surface.
BLOCK, 0,0,0, 30, 30, 10
NAME, LAST, base
SURFACE, PARAM, u, v, 13 + 2*sin(12*u)*sin(12*v), -10, 40, -10, 40
NAME, LAST, wave
SEL, S, FACE, NORMAL, 0,0,1
SEL, R, FACE, BODY, base
REPLACEFACE, wave
HIDE, wave

! ===================================================================== Deform

@ BEND pic
! Bend a bar into a quarter circle.
BLOCK, 0,0,0, 100, 10, 5
NAME, LAST, bar
BEND, bar, 90

@ TWIST pic
! Twist a square column half a turn.
BLOCK, -10,-10,0, 20, 20, 80
NAME, LAST, column
TWIST, column, 180

@ TAPER pic
! Taper a column to 0.4 of its width at the top.
BLOCK, -10,-10,0, 20, 20, 80
NAME, LAST, column
TAPER, column, 0.4, Z

@ STRETCH
! Stretch a ball to twice its length along X; its sides shrink to keep the volume.
SPHERE, 0,0,0, 10
NAME, LAST, plug
STRETCH, plug, 2

@ FLOW pic
! Lay letters along an arc, stretched to fit it.
TEXT, "FLOW", 0,0,0, 10, 2
NAME, LAST, label
ARC, 0,0,0, 30,15,0, 60,0,0
NAME, LAST, arc
FLOW, label, arc, FIT

@ SWEEPVOL
! The volume a ball cutter sweeps along a track, cut from a block.
BLOCK, 0,0,0, 60, 40, 10
NAME, LAST, part
SPHERE, 0,0,0, 3
NAME, LAST, cutter
SPLINE, (5,5,10), (30,30,8), (55,10,10)
NAME, LAST, track
SWEEPVOL, cutter, track
SUBTRACT, part, LAST

! ===================================================================== Mesh bodies

@ TOMESH
! Turn a solid into a mesh body of triangles.
SPHERE, 0,0,0, 10
NAME, LAST, pebble
TOMESH, pebble

@ TOSOLID
! Turn a mesh body back into a faceted solid.
SPHERE, 0,0,0, 10
TOMESH, LAST, 1
TOSOLID, LAST

@ SMOOTH
! Smooth a mesh body: the corners of a meshed box round off.
BLOCK, 0,0,0, 20, 20, 20
NAME, LAST, pebble
TOMESH, pebble
REMESH, pebble, 1.5
SMOOTH, pebble, 40, 0.6

@ REMESH
! Make a mesh body's triangles finer: no edge longer than 2.
BLOCK, 0,0,0, 40, 10, 10
NAME, LAST, bar
TOMESH, bar
REMESH, bar, 2

@ SIMPLIFY
! Use fewer triangles without moving the surface more than 0.02.
SPHERE, 0,0,0, 10
NAME, LAST, ball
TOMESH, ball, 0.01
SIMPLIFY, ball, 0.02

@ FITSURF
! Scan to CAD: fit one smooth surface to a rounded mesh; a closed mesh gives a solid.
SPHERE, 0,0,0, 10
NAME, LAST, scan
TOMESH, scan
FITSURF, scan, ALL, 0.15

@ SEGMENT
! Split a meshed machined part into regions at its sharp edges, and name each.
BLOCK, 0,0,0, 60, 40, 20
NAME, LAST, part
CYL, 35,20,-1, 5, 30
SUBTRACT, part, LAST
TOMESH, part
SEGMENT, part

@ RECONSTRUCT pic
! Scan to CAD for machined parts: rebuild the exact solid from a mesh.
BLOCK, 0,0,0, 60, 40, 20
NAME, LAST, part
CYL, 35,20,-1, 5, 30
SUBTRACT, part, LAST
TOMESH, part
NAME, part, scan
RECONSTRUCT, scan
MOVE, LAST, 0, 50, 0

@ DEVIATION
! How far a scan is from its model: here a mesh of the part, measured against the part.
BLOCK, 0,0,0, 60, 40, 20
NAME, LAST, part
BLOCK, 0,0,0, 60, 40, 20
TOMESH, LAST, 0.01
NAME, LAST, scan
DEVIATION, scan, part, 0.05

@ IMPLICIT pic
! Two balls blended smoothly into one shape, from an equation.
IMPLICIT, blob, SMIN(BALL(0,0,0,10), BALL(14,0,0,7), 4), -12,-12,-12, 24,12,12

@ LATTICE pic
! Fill a block with a gyroid lattice of cell 8 and walls 1 (add a skin thickness to keep a closed outer wall).
BLOCK, 0,0,0, 40, 40, 20
NAME, LAST, bracket
LATTICE, bracket, GYROID, 8, 1

! ===================================================================== Sculpt

@ SCULPT pic
! Raise a bump on a meshed ball with the DRAW brush along a short stroke.
SPHERE, 0,0,0, 20
NAME, LAST, head
TOMESH, head
REMESH, head, 1.5
STROKE, S1, "0,-20,-4  0,-20,0  0,-20,4"
SCULPT, head, INFLATE, 6, 0.9, S1

@ MASK
! Freeze a region so sculpting leaves it alone, then stroke over it.
SPHERE, 0,0,0, 20
NAME, LAST, head
TOMESH, head
MASK, head, PAINT, 0, -20, 0, 8
STROKE, S1, "0,-20,-4  0,-20,0  0,-20,4"
SCULPT, head, DRAW, 6, 0.9, S1
MASK, head, CLEAR

@ STROKE
! Record the points of a sculpt stroke under a name (the Sculpt tool writes this for you).
STROKE, S1, "0,-20,-2  0,-20,0  0,-20,2"

! ===================================================================== Move and copy

@ MOVE
! Move a body by (30, 0, 10). It keeps its ID and name.
BLOCK, 0,0,0, 10, 10, 10
MOVE, 1, 30, 0, 10

@ ROTATE
! Turn a block 45 degrees about the Z axis.
BLOCK, 0,0,0, 30, 10, 5
ROTATE, 1, 45, 0,0,0, 0,0,1

@ SCALE
! Make a body twice as big about the origin, then a copy only twice as tall.
CYL, 0,0,0, 5, 10
SCALE, 1, 2
CYL, 30,0,0, 5, 10
SCALE, LAST, 1, 30,0,0, 1, 2

@ COPY
! A copy of a body, 30 along X. The copy is LAST.
CYL, 0,0,0, 5, 20
COPY, 1, 30, 0, 0

@ MIRROR pic
! A mirror copy of a wedge in the YZ plane.
WEDGE, 5,0,0, 30, 15, 10, 10
MIRROR, 1, 0,0,0, 1,0,0

@ ARRAY pic
! Eight copies of a hole cutter round the Z axis, all cut from a disc in one step.
CYL, 0,0,0, 40, 8
NAME, LAST, disc
CYL, 30,0,-1, 4, 10
ARRAY, POLAR, LAST, 8, 360, 0,0,0, 0,0,1, CUT, disc

@ PATTERN pic
! Make one hole, then repeat that step five times along X.
BLOCK, 0,0,0, 120, 30, 8
NAME, LAST, plate
HOLE, plate, 10, 15, 8, 6
PATTERN, LINEAR, plate, 1, 5, 25, 0, 0

! ===================================================================== Bodies

@ NAME
! Name the newest body, then use the name.
BLOCK, 0,0,0, 40, 20, 5
NAME, LAST, base
MOVE, base, 0, 0, 10

@ DELETE
! Delete a helper body.
BLOCK, 0,0,0, 40, 20, 5
CYL, 0,0,0, 2, 10
NAME, LAST, helper
DELETE, helper

@ HIDE
! Hide a body in the view; it stays in the model (here the cylinder goes, the block stays).
BLOCK, 0,0,0, 40, 20, 5
CYL, 20,10,5, 5, 20
HIDE, 2

@ SHOW
! Show hidden bodies again.
BLOCK, 0,0,0, 40, 20, 5
HIDE, 1
SHOW

@ CHECK
! Check that every body is a valid, closed solid.
BLOCK, 0,0,0, 40, 20, 5
CHECK
CHECK, 1, FLAWS, 0.01

@ HEAL
! Repair a body (here an exported and re-imported triangle mesh).
BLOCK, 0,0,0, 40, 20, 5
EXPORT, STL, "box.stl"
IMPORT, STL, "box.stl", box
HEAL, box

@ CLEAN
! Join faces that lie on the same surface, such as the seam left by a union.
BLOCK, 0,0,0, 20, 20, 10
BLOCK, 20,0,0, 20, 20, 10
UNION, 1, 2
CLEAN, LAST

@ CLEAR
! Delete every body and start the IDs again; parameters stay.
W = 40
BLOCK, 0,0,0, W, 20, 5
CLEAR
BLOCK, 0,0,0, W, 10, 5

! ===================================================================== Layers, colours, materials

@ LAYER
! Make a layer with a colour; new bodies go on it. Then lock it so nothing on it can change.
BLOCK, -20,-20,-5, 40, 40, 5
LAYER, bolts, NEW, #3080ff
LAYER, bolts
CYL, 0,0,0, 4, 20
CYL, 12,0,0, 4, 20
LAYER, DEFAULT
LAYER, bolts, LOCK

@ COLOR pic
! Colour bodies by name, by hex code or by red, green, blue.
BLOCK, 0,0,0, 40, 20, 5
COLOR, LAST, ORANGE
CYL, 50,10,0, 8, 10
COLOR, LAST, #3080ff

@ MATERIAL
! Give a body a material; MASSPROP then gives its mass.
BLOCK, 0,0,0, 100, 50, 10
MATERIAL, LAST, ALUMINIUM
MASSPROP, LAST

@ ISOLATE
! Show only one body and hide every other one.
BLOCK, 0,0,0, 40, 20, 5
CYL, 50,10,0, 8, 10
NAME, LAST, post
ISOLATE, post
SHOW, ALL

@ FADE
! Draw a body see-through, for the view only.
BLOCK, 0,0,0, 40, 20, 5
NAME, LAST, cover
CYL, 20,10,0, 5, 20
FADE, cover

@ UNFADE
! Draw faded bodies solid again.
BLOCK, 0,0,0, 40, 20, 5
FADE, 1
UNFADE

@ DISPLAY
! Change what the view shows without adding history steps.
BLOCK, 0,0,0, 40, 20, 5
CYL, 50,10,0, 8, 10
DISPLAY, HIDE, 1
DISPLAY, ALL

! ===================================================================== Datums

@ PLANE
! A datum plane on the top face of a block, and one half way between two side faces.
BLOCK, 0,0,0, 40, 20, 10
PLANE, top, FACE, 6
PLANE, mid, MID, 1, 2

@ AXIS
! A datum axis where two datum planes meet.
BLOCK, 0,0,0, 40, 20, 10
PLANE, mid, MID, 1, 2
PLANE, side, MID, 3, 4
AXIS, centre, PLANES, mid, side

@ POINT
! A datum point on a vertex, and one at the centre of a body.
BLOCK, 0,0,0, 40, 20, 10
POINT, corner, VERTEX, 1
POINT, c, CENTER, BODY, 1

@ DATUM
! Remove a datum plane that is no longer needed.
BLOCK, 0,0,0, 40, 20, 10
PLANE, temp, XY, 10
DATUM, DELETE, temp

@ WORKPLANE pic
! Draw on a datum plane: x, y and z are then measured in that plane.
BLOCK, 0,0,0, 40, 30, 10
PLANE, top, FACE, 6
WORKPLANE, top
CYL, 20, 15, 0, 6, 8
WORKPLANE, OFF

! ===================================================================== Select

@ SEL
! Select by what things are: the top face, then every edge at height 10.
BLOCK, 0,0,0, 40, 20, 10
SEL, S, FACE, NORMAL, 0,0,1
SEL, S, EDGE, LOC, Z, 10
LIST

@ CM
! Save the selection as a named set.
BLOCK, 0,0,0, 40, 20, 10
SEL, S, FACE, NORMAL, 0,0,1
CM, top_face, FACE

@ CMSEL
! Select a named set again later.
BLOCK, 0,0,0, 40, 20, 10
SEL, S, EDGE, LOC, Z, 10
CM, top_edges, EDGE
SEL, NONE
CMSEL, S, top_edges
FILLET, 2

@ CMDEL
! Delete a named set.
BLOCK, 0,0,0, 40, 20, 10
SEL, S, FACE, NORMAL, 0,0,1
CM, top_face, FACE
CMDEL, top_face

! ===================================================================== Measure

@ DIST
! The shortest distance between two bodies.
BLOCK, 0,0,0, 10, 10, 10
SPHERE, 30,5,5, 5
DIST, BODY, 1, BODY, 2

@ ANGLE
! The angle between two flat faces.
WEDGE, 0,0,0, 40, 15, 20, 10
ANGLE, FACE, 1, FACE, 3

@ MASSPROP
! Volume, area, centre of mass and moments of inertia, with a density for the mass.
BLOCK, 0,0,0, 100, 50, 10
MASSPROP, 1, 7.85e-6

@ CONFIGOFF
! Leave the hole out of the small size: steps 5 and 6 are off in configuration small.
W = 40
H = 10
BLOCK, 0,0,0, W, 20, H
NAME, LAST, plate
CYL, 10,10,-1, 3, H+2
SUBTRACT, plate, LAST
CONFIG, small, "W = 30, H = 5"
CONFIGOFF, small, "5 6"
USECONFIG, small

@ DESIGNTABLE
! Configurations from a CSV design table. The first lines write the table (EXPORT), then read it back.
W = 40
H = 10
BLOCK, 0,0,0, W, 20, H
CONFIG, small, "W = 30, H = 5"
CONFIG, big, "W = 60, H = 20"
DESIGNTABLE, sizes.csv, EXPORT
DESIGNTABLE, sizes.csv

@ VARIANTS
! Build every configuration on its own and compare size, volume and mass.
W = 40
H = 10
BLOCK, 0,0,0, W, 20, H
CONFIG, small, "W = 30, H = 5"
CONFIG, big, "W = 60, H = 20"
VARIANTS

@ BOM
! The parts list: placed copies of a part are counted together.
*PART, pin, D=4
  CYL, 0,0,0, D/2, 20
*ENDPART
INST, pin, 0,0,0
INST, pin, 10,0,0
INST, pin, 20,0,0, D=6
BOM

@ CLASH
! Do two bodies overlap? It gives the overlap volume, or the gap.
BLOCK, 0,0,0, 20, 20, 20
SPHERE, 20,10,10, 5
CLASH, 1, 2

@ SECTION
! Cut the view open along a plane to look inside (the model is not changed).
BLOCK, 0,0,0, 40, 40, 20
CYL, 20,20,-1, 8, 30
SUBTRACT, 1, 2
SECTION, ZX, ABOVE, 20
SECTION, OFF

@ ECHO
! Print the value of an expression.
BLOCK, 0,0,0, 40, 20, 10
ECHO, VOL(1)/1000

@ LIST
! List the bodies, parameters, named sets and the selection.
W = 40
BLOCK, 0,0,0, W, 20, 10
LIST

! ===================================================================== Notes and fits

@ NOTE
! A note pinned at a point, with a leader, and a size between two points.
BLOCK, 0,0,0, 60, 40, 10
NOTE, "Break edges", 70, 0, 20, 60, 0, 10
NOTE, SIZE, 0,0,0, 60,0,0

@ FITS
! ISO 286 limits for a 25 mm H7/g6 fit.
FITS, H7/g6, 25

@ STACKUP
! The gap a chain of sizes closes on, worst case and statistical.
STACKUP, +100 ±0.1, -60 +0/-0.05, -39.8 ±0.05, MIN=0.05

! ===================================================================== Check

@ DESCRIBE
! The model in words and numbers: size, faces by type, holes.
BLOCK, 0,0,0, 60, 40, 10
NAME, LAST, plate
HOLE, plate, 30, 20, 10, 8
DESCRIBE, plate

@ ASSERT
! Checks that live in the script: the step fails, and says why, when one does not hold.
BLOCK, 0,0,0, 60, 40, 10
NAME, LAST, plate
HOLE, plate, 30, 20, 10, 8
ASSERT, VALID(plate)
ASSERT, HOLES(plate, 8), EQ, 1
ASSERT, BBOX(plate).dz, EQ, 10, 0.01

@ CONTACT
! Do two parts touch? A block resting on another touches on a face.
BLOCK, 0,0,0, 40, 40, 10
NAME, LAST, base
BLOCK, 10,10,10, 20, 20, 10
NAME, LAST, top
CONTACT, base, top

@ CLEARANCE
! How a shaft sits in a hole: both diameters and the gap.
BLOCK, -20,-20,0, 40, 40, 10
NAME, LAST, plate
HOLE, plate, 0, 0, 10, 8.4
CYL, 0,0,-5, 4, 20
NAME, LAST, pin
CLEARANCE, pin, plate

@ RELATE
! Where one body sits relative to another.
BLOCK, 0,0,0, 40, 30, 20
NAME, LAST, box
BLOCK, 0,0,20, 40, 30, 3
NAME, LAST, lid
RELATE, lid, box

@ COMPARE
! Is one body a moved copy of another?
BLOCK, 0,0,0, 30, 20, 10
NAME, LAST, left
COPY, left, 50, 0, 0
NAME, LAST, right
COMPARE, left, right
CYL, 15,10,-1, 3, 12
SUBTRACT, right, LAST
COMPARE, STEP, 5

@ DESIGNCHECK
! Rule checks on a body: broken faces, tiny edges, thin walls under 2.
BLOCK, 0,0,0, 60, 40, 30
NAME, LAST, housing
PICK, FACE, 6
SHELL, 1.5
DESIGNCHECK, housing, 2

@ PROBE
! Shoot a ray down through a plate: every face it crosses and how much material.
BLOCK, 0,0,0, 60, 40, 10
HOLE, 1, 30, 20, 10, 8
PROBE, RAY, 10, 20, 50, 0, 0, -1

@ PROFILE
! A cut through a body, as text: each loop with its lines, arcs and circles.
BLOCK, 0,0,0, 60, 40, 10
NAME, LAST, plate
HOLE, plate, 30, 20, 10, 8
PROFILE, plate, XY, 5

@ THICK
! The thinnest walls of a shelled box.
BLOCK, 0,0,0, 60, 40, 30
NAME, LAST, housing
PICK, FACE, 6
SHELL, 2
THICK, housing

@ REFS
! Every pick the history holds and whether it still points at what was picked.
BLOCK, 0,0,0, 40, 20, 10
SEL, S, FACE, ID, 5, 6
PICK, EDGE, 1
REFS

@ SELFOR
! The SEL lines that pick face 6 by what it is, not by its ID.
BLOCK, 0,0,0, 40, 20, 10
SELFOR, FACE, 6

@ DIFF
! What the last step changed.
BLOCK, 0,0,0, 40, 20, 10
HOLE, 1, 20, 10, 10, 6
DIFF

@ LINT
! Check the history as a script without running it: syntax, unknown commands, raw IDs that may move.
BLOCK, 0,0,0, 40, 20, 10
HOLE, 1, 20, 10, 10, 6
LINT

@ MOTION
! Run a hinged lid from 0 to 180 degrees and look for parts running into each other.
A = 60
BLOCK, 0,0,0, 40, 30, 5
NAME, LAST, base
BLOCK, 0,0,5, 40, 30, 2
NAME, LAST, lid
ROTATE, lid, -A, 0,0,5, 0,1,0
CYL, -20,15,0, 3, 30
NAME, LAST, post
MOTION, A, 0, 180, 12

@ STRESS
! A first strength check: a bracket held at its wall, 400 N down at its tip.
BLOCK, 0,0,0, 60, 40, 6
NAME, LAST, bracket
BLOCK, 0,0,0, 6, 40, 50
UNION, bracket, LAST
MATERIAL, bracket, ALUMINIUM
SEL, S, FACE, NORMAL, -1,0,0
CM, wall, FACE
SEL, S, FACE, NORMAL, 1,0,0
SEL, R, FACE, LOC, X, 60
CM, tip, FACE
SEL, NONE
STRESS, bracket, wall, tip, FORCE, 0, 0, -400

@ TOPOPT pic
! Where does the material carry the load? Keep the stiffest 30 % of a plate.
BLOCK, 0,0,0, 80, 40, 4
NAME, LAST, plate
SEL, S, FACE, NORMAL, -1,0,0
CM, wall, FACE
SEL, S, FACE, NORMAL, 1,0,0
CM, tip, FACE
SEL, NONE
TOPOPT, plate, wall, tip, FORCE, 0, -1000, 0, 0.3, 10

@ GRAVITY
! Will it stand up? A post on a base is fine; a ball in the air is floating.
BLOCK, 0,0,0, 60, 60, 5
NAME, LAST, base
CYL, 30,30,5, 5, 40
NAME, LAST, post
SPHERE, 30, 30, 80, 5
GRAVITY, base

! ===================================================================== Make

@ PRINTCHECK
! Check a part before 3D printing: blue sits on the bed, red needs support.
BLOCK, 0,0,0, 40, 10, 5
BLOCK, 0,0,5, 10, 10, 30
UNION, 1, 2
BLOCK, 0,0,35, 40, 10, 5
UNION, LAST-1, LAST
NAME, LAST, hook
PRINTCHECK, hook

@ MILL pic
! A milling path that clears a pocket down to its floor with a 6 mm mill, 4 a cut.
BLOCK, 0,0,0, 80, 60, 16
NAME, LAST, plate
BLOCK, 12,12,6, 48, 36, 20
SUBTRACT, plate, LAST
SEL, S, FACE, LOC, Z, 6
CM, floor, FACE
SEL, NONE
MILL, plate, POCKET, floor, 6, 4, , plate.nc

! ===================================================================== Parts

@ INST pic
! Define a bolt part once, then place three copies, one bigger.
*PART, bolt, D=8, L=30
  CYL, 0,0,0, D, 5
  CYL, 0,0,-L, D/2, L
  UNION, 1, 2
*ENDPART
INST, bolt, 0, 0, 0
INST, bolt, 30, 0, 0
INST, bolt, 60, 0, 0, D=12, L=40

@ JOINT pic
! A lid on a hinge along the back edge of a box, held open at A degrees.
! DRIVE, A, 90 or MOTION, A, 0, 110, 11 moves it; the joint stays true.
A = 60
BLOCK, 0,0,0, 40,30,10
NAME, LAST, box
BLOCK, 0,0,10, 40,30,2
NAME, LAST, lid
JOINT, REVOLUTE, EDGE, 2, EDGE, 16, A, LIMITS, 0, 110
JOINTS

@ JOINTS
! Every joint, its value now, what it leaves free and any that fight.
BLOCK, -50,-2,-2, 100, 4, 1
NAME, LAST, rail
BLOCK, -5,-2,0, 10, 4, 3
NAME, LAST, car
JOINT, SLIDER, FACE, 6, FACE, 11, 12
JOINTS

@ MATE
! Put a bolt in a hole by its faces: first the axes in line, then the head on the plate.
*PART, bolt, D=8, L=30
  CYL, 0, 0, 0, D, 5
  CYL, 0, 0, -L, D/2, L
  UNION, 1, 2
*ENDPART
CYL, 0, 0, -12, 60, 12
NAME, LAST, plate
HOLE, plate, 45, 0, 0, 8.5
INST, bolt, 200, 80, 40
MATE, CONCENTRIC, FACE, 4, FACE, 8
MATE, COINCIDENT, FACE, 2, FACE, 7

@ MATES
! Check the mates: here a pin sits on a plate, so it can still slide two ways and turn.
BLOCK, 0,0,0, 40, 40, 10
NAME, LAST, base
CYL, 100,0,0, 5, 20
NAME, LAST, pin
MATE, COINCIDENT, FACE, 6, FACE, 9
MATES

@ CSYS
! Coordinate systems on bodies; MATE, FRAME puts the pin's foot on the base's top in one step.
BLOCK, 0,0,0, 40, 40, 10
NAME, LAST, base
CYL, 100,0,0, 5, 20
NAME, LAST, pin
CSYS, top, base, 20, 20, 10
CSYS, foot, pin, 100, 0, 0, 0, 0, -1
MATE, FRAME, top, foot, FLIP
CSYS

@ EXPLODE
! Split a body made of two separate solids into one body per solid.
BLOCK, 0,0,0, 10, 10, 10
BLOCK, 20,0,0, 10, 10, 10
KEEP, OFF
UNION, 1, 2
EXPLODE, LAST

@ XSTEP
! The steps of an exploded view: the lid goes up 40, then the knob 30 more.
BLOCK, -30,-20,0, 60, 40, 20
NAME, LAST, box
BLOCK, -30,-20,20, 60, 40, 4
NAME, LAST, lid
CONE, 0,0,24, 10, 6, 12
NAME, LAST, knob
XSTEP, apart, "lid knob", 0, 0, 40
XSTEP, apart, knob, 0, 0, 30

@ XSHOW
! Show an exploded view, with trail lines.
BLOCK, -30,-20,0, 60, 40, 20
NAME, LAST, box
BLOCK, -30,-20,20, 60, 40, 4
NAME, LAST, lid
CONE, 0,0,24, 10, 6, 12
NAME, LAST, knob
XSTEP, apart, "lid knob", 0, 0, 40
XSTEP, apart, knob, 0, 0, 30
XSHOW, apart

@ LIB
! Link a part file: copies follow the file when it changes. The first lines write the file.
NEWPART, peg
D = 4
CYL, 0,0,0, D/2, 3*D
SAVEPART, peg.cmd
NEW
LIB, LINK, peg.cmd
INST, peg, 0, 0, 0
INST, peg, 10, 0, 0, D=6

@ TAKE
! Use geometry of another part: its top face, its end as a plane, and the hole's axis. Linked, so they follow the part.
*PART, plate, W=40
  BLOCK, 0,0,0, W, 20, 5
  CYL, 10,10,-1, 3, 7
  SUBTRACT, 1, 2
*ENDPART
INST, plate, 0, 0, 0
TAKE, FACE, plate, 3, lid
TAKE, PLANE, plate, 6, end_plane
TAKE, AXIS, plate, FACE 7, hole_axis

@ DEPENDS
! What uses what: parts, the copies placed, and the geometry taken from them.
*PART, plate, W=40
  BLOCK, 0,0,0, W, 20, 5
*ENDPART
INST, plate, 0, 0, 0
TAKE, PLANE, plate, 6, end_plane
DEPENDS

@ LIBSAVE
! Save a part's definition to the part library, for other projects.
*PART, washer, D=8
  TUBE, 0,0,0, D, D/2 + 0.2, 1.5
*ENDPART
LIBSAVE, washer, washer_lib.cmd

! ===================================================================== Settings and files

@ /UNITS
! The model's length unit (MM by default).
/UNITS, IN
BLOCK, 0,0,0, 2, 1, 0.25

@ /TOL
! Extra tolerance for booleans and selecting by place.
/TOL, 0.001
BLOCK, 0,0,0, 10, 10, 10

@ IMPORT
! Read a STEP file; each solid in it becomes a body. The first lines write the file.
CYL, 0,0,0, 10, 20
EXPORT, STEP, "part.step"
CLEAR
IMPORT, STEP, "part.step", part

@ EXPORT
! Write bodies to STEP (exact) and STL (triangles) files.
BLOCK, 0,0,0, 40, 20, 10
EXPORT, STEP, "plate.step"
EXPORT, STL, "plate.stl"

@ DRAWING
! A 2D drawing with front, top, right and iso views and the main sizes.
BLOCK, 0,0,0, 60, 40, 10
HOLE, 1, 30, 20, 10, 8
DRAWING, "plate.svg", STANDARD, , ALL

@ DRAWSHEET
! Drawing sheets kept with the model: the views are made again whenever the drawings are written.
BLOCK, 0,0,0, 60, 40, 10
HOLE, 1, 30, 20, 10, 8
DRAWSHEET, views, STANDARD
DRAWSHEET, plan, TOP, 0, OVERALL, A3
DRAWINGS

@ SHEETTABLE
! A parts list with balloons, a hole table and a revision table on a drawing sheet.
BLOCK, 0,0,0, 60, 40, 10
HOLE, 1, 15, 20, 10, 6
HOLE, 2, 45, 20, 10, 6
DRAWSHEET, plate, STANDARD, 0, ALL, A3
REVISION, A, "First issue"
SHEETTABLE, plate, PARTS+HOLES+REVISIONS

@ REVISION
! Rows of the sheets' revision table; the newest is the title block's REV.
BLOCK, 0,0,0, 60, 40, 10
REVISION, A, "First issue"
REVISION, B, "Corner made bigger", 2026-11-24, Sam
REVISION

@ SHEETDATA
! The rows a sheet's tables will show, as data.
BLOCK, 0,0,0, 60, 40, 10
HOLE, 1, 30, 20, 10, 8
DRAWSHEET, plate, TOP, 0, ALL, A4, , , , , ALL
SHEETDATA, plate

@ DRAWINGS
! Write every sheet as one PDF, a page each, and keep it up to date after every rebuild and save.
BLOCK, 0,0,0, 60, 40, 10
HOLE, 1, 30, 20, 10, 8
DRAWSHEET, views, STANDARD
DRAWSHEET, plan, TOP, 0, OVERALL, A3
DRAWINGS, "plate_sheets.pdf", AUTO

@ PLUGINS
! The plug-ins found in the plug-in folder, their commands, and why any did not load.
PLUGINS

@ BACKUPS
! Every SAVE over a project keeps the one it replaces; BACKUPS lists them.
BLOCK, 0,0,0, 40, 20, 10
SAVE, "safe_demo.m3d"
CYL, 10,10,-1, 3, 12
SAVE
BACKUPS

@ FILES
! The outside files the project reads, and where each was found.
BLOCK, 0,0,0, 40, 20, 10
EXPORT, BREP, "files_demo.brep"
NEW
IMPORT, BREP, "files_demo.brep"
FILES

@ RELINK
! Point the project at a newer version of an imported file: the steps that read it run again.
BLOCK, 0,0,0, 40, 20, 10
EXPORT, BREP, "relink_v1.brep"
NEW
BLOCK, 0,0,0, 60, 20, 10
EXPORT, BREP, "relink_v2.brep"
NEW
IMPORT, BREP, "relink_v1.brep"
RELINK, "relink_v1.brep", "relink_v2.brep"

@ SHARECHECK
! A check before sending the project to someone.
BLOCK, 0,0,0, 40, 20, 10
SAVE, "share_demo.m3d"
SHARECHECK

@ PROPERTY
! The project's properties, shown in a drawing sheet's title block.
PROPERTY, TITLE, Mounting bracket
PROPERTY, NUMBER, MB-001
PROPERTY

@ RENDER window
! A ray traced picture, with shadows and a look from each body's MATERIAL.
BLOCK, 0,0,0, 60, 40, 10
MATERIAL, LAST, ALUMINIUM
RENDER, part.png, 1200, 800, ISO

! ===================================================================== Files and history

@ HIST
! Change the first step of the history: the plate is rebuilt 80 long.
BLOCK, 0,0,0, 40, 20, 5
HOLE, 1, 10, 10, 5, 4
HIST, EDIT, 1, "BLOCK, 0,0,0, 80, 20, 5"
HIST

@ NEW
! Start an empty session (UNDO cannot bring the old one back).
BLOCK, 0,0,0, 40, 20, 5
NEW

@ OPEN
! Save a project and open it again: the history is replayed.
BLOCK, 0,0,0, 40, 20, 5
SAVE, "plate.m3d"
NEW
OPEN, "plate.m3d"

@ SAVE
! Save the project: the history, plus a copy of every imported file.
BLOCK, 0,0,0, 40, 20, 5
SAVE, "plate.m3d"

@ RUN
! Run a script file. The first lines write one (a saved part file is a script too).
NEWPART, peg
D = 4
CYL, 0,0,0, D/2, 3*D
SAVEPART, peg.cmd
NEW
RUN, peg.cmd
INST, peg, 0, 0, 0

@ NEWPART
! Design one part on its own; the parameters set first are its inputs.
NEWPART, peg
D = 4
H = 3*D
CYL, 0,0,0, D/2, H
SEL, S, EDGE, AT, D/2, 0, H
FILLET, D/8
SAVEPART, peg.cmd

@ OPENPART
! Open one part of a part file to change it, then save it back.
NEWPART, peg
D = 4
CYL, 0,0,0, D/2, 3*D
SAVEPART, peg.cmd
OPENPART, peg.cmd

@ SAVEPART
! Save a part document into a part file, as one *PART block.
NEWPART, washer
D = 8
TUBE, 0,0,0, D, D/2 + 0.2, 1.5
SAVEPART, washer.cmd

@ RELOAD
! Read linked part files again; copies update when a file changed.
NEWPART, peg
D = 4
CYL, 0,0,0, D/2, 3*D
SAVEPART, peg.cmd
NEW
LIB, LINK, peg.cmd
INST, peg, 0, 0, 0
RELOAD

@ UNDO
! Take back the last step.
BLOCK, 0,0,0, 40, 20, 5
CYL, 0,0,0, 3, 10
UNDO

@ REDO
! Bring an undone step back.
BLOCK, 0,0,0, 40, 20, 5
CYL, 0,0,0, 3, 10
UNDO
REDO

@ STEPS
! Every history step that made a body, in order.
BLOCK, 0,0,0, 40, 20, 5
NAME, LAST, plate
HOLE, plate, 10, 10, 5, 4
SEL, S, EDGE, LOC, Z, 5
FILLET, 1
STEPS, plate

! ===================================================================== View and picking

@ CPOINTS
! Show the control points of a curve in the view, to drag them with the mouse.
NURBS, 3, (0,0,0), (10,8,0), (20,-8,0), (30,0,0)
CPOINTS, LAST
CPOINTS, OFF

@ FIT
! Zoom to fit everything, or only one body.
BLOCK, 0,0,0, 40, 20, 5
NAME, LAST, plate
FIT, plate
FIT

@ HELP
! Show how to type a command and what its arguments mean.
HELP, HOLE

@ PICK
! What a click in the view writes: pick face 6 (the top), then add face 1.
BLOCK, 0,0,0, 40, 20, 5
PICK, FACE, 6
PICK, FACE, 1, A

@ PICKMODE
! What a click in the view picks: here edges.
PICKMODE, EDGE

@ VIEW
! Look from a standard direction.
BLOCK, 0,0,0, 40, 20, 5
VIEW, TOP
VIEW, ISO

! ===================================================================== Inside a sketch

@ ENDSKETCH
! Finish the open sketch; it stays in the model for EXTRUDE and REVOLVE.
SKETCH, s1, XY
SCIRCLE, 0, 0, 10
ENDSKETCH
EXTRUDE, s1, 5

@ SLINE
! Lines; the second goes on from the end of the first and is held vertical.
SKETCH, s1, XY
SLINE, 0, 0, 40, 0
SLINE, 1.E, 40, 20, V
ENDSKETCH

@ SRECT
! A rectangle from two opposite corners, pushed into a plate.
SKETCH, s1, XY
SRECT, 0, 0, 90, 60
ENDSKETCH
EXTRUDE, s1, 5

@ SRECT3
! A rectangle at any angle: one side from the first point to the second, the third sets the width.
SKETCH, s1, XY
SRECT3, 0, 0, 30, 20, 20, 35
ENDSKETCH
EXTRUDE, s1, 5

@ SRECTC
! A level rectangle from its centre and a corner.
SKETCH, s1, XY
SRECTC, 0, 0, 30, 15
ENDSKETCH
EXTRUDE, s1, 5

@ SCIRCLE
! A circle from its centre and radius.
SKETCH, s1, XY
SCIRCLE, 10, 10, 8
ENDSKETCH
EXTRUDE, s1, 5

@ SCIRCLE3
! A circle through three points.
SKETCH, s1, XY
SCIRCLE3, 0, 0, 20, 0, 10, 10
ENDSKETCH

@ SCIRCLET
! A circle of radius 4 touching two lines, in the corner nearest (6, 6).
SKETCH, s1, XY
SLINE, 0, 0, 40, 0
SLINE, 0, 0, 0, 30
SCIRCLET, 1, 2, R, 4, AT, 6, 6
ENDSKETCH

@ SARC
! An arc: centre, radius, start and end angle (counter-clockwise).
SKETCH, s1, XY
SARC, 0, 0, 20, 0, 120
ENDSKETCH

@ SARC3
! An arc through three points.
SKETCH, s1, XY
SARC3, 0, 0, 15, 10, 30, 0
ENDSKETCH

@ SARCT
! A line, then an arc that carries on smoothly from its end.
SKETCH, s1, XY
SLINE, 0, 0, 30, 0
SARCT, 1.E, 40, 10
ENDSKETCH

@ SELLIPSE
! An ellipse 30 by 15 across, its first axis turned 30 degrees.
SKETCH, s1, XY
SELLIPSE, 0, 0, 15, 7.5, 30
ENDSKETCH
EXTRUDE, s1, 4

@ SEARC
! Half of an ellipse, from 0 to 180 degrees round it.
SKETCH, s1, XY
SEARC, 0, 0, 20, 10, 0, 0, 180
ENDSKETCH

@ SSLOT
! A slot round two centres, radius 5.
SKETCH, s1, XY
SSLOT, 0, 0, 40, 0, 5
ENDSKETCH
EXTRUDE, s1, 4

@ SSLOTARC
! A slot bent along an arc of radius 20 from 20 to 160 degrees.
SKETCH, s1, XY
SSLOTARC, 0, 0, 20, 20, 160, 3.5
ENDSKETCH
EXTRUDE, s1, 4

@ SNGON
! A hexagon, its corners on a circle of radius 10.
SKETCH, s1, XY
SNGON, 0, 0, 6, 10
ENDSKETCH
EXTRUDE, s1, 5

@ SPOLY
! Lines joined end to end; CLOSE joins the last point to the first.
SKETCH, s1, XY
SPOLY, 0,0, 40,0, 40,20, 20,30, 0,20, CLOSE
ENDSKETCH
EXTRUDE, s1, 5

@ SSPLINE pic
! A smooth closed sketch curve through points, pushed into a solid.
SKETCH, s1, XY
SSPLINE, 0,0, 20,-10, 40,0, 30,20, 10,20, CLOSE
ENDSKETCH
EXTRUDE, s1, 5

@ SPOINT
! A sketch point, for constraints to hold things to.
SKETCH, s1, XY
SRECT, 0, 0, 40, 20
SPOINT, 20, 10
SCIRCLE, 20, 10, 4
SCON, COINCIDENT, 6.C, 5
ENDSKETCH

@ SCON
! Hold a circle's centre on the origin and two lines at right angles.
SKETCH, s1, XY
SCIRCLE, 3, 2, 5
SCON, COINCIDENT, 1.C, ORIGIN
SLINE, 10, 0, 40, 3
SLINE, 2.E, 42, 20
SCON, HORIZONTAL, 2
SCON, PERPENDICULAR, 2, 3
ENDSKETCH

@ SCHECK
! What is wrong with a sketch, or still loose: repeated constraints, curves drawn twice, free geometry.
SKETCH, s, XY
SRECT, 0, 0, 40, 20
SDIM, LENGTH, 1, 40
SDIM, LENGTH, 3, 40
SCIRCLE, 20, 10, 5
SCHECK

@ SDIM
! Give sketch geometry sizes: a 60 long side, a radius 8 circle 30 from the left.
W = 60
SKETCH, s1, XY
SRECT, 0, 0, 50, 40
SCIRCLE, 25, 20, 6
SDIM, LENGTH, 1, W
SDIM, RADIUS, 5, 8
SDIM, HDIST, ORIGIN, 5.C, W/2
ENDSKETCH
EXTRUDE, s1, 5

@ SCONSTRUCT
! Turn a line into construction geometry: it helps place things but is not part of the profile.
SKETCH, s1, XY
SRECT, 0, 0, 40, 20
SLINE, 0, 0, 40, 20
SCONSTRUCT, 5
ENDSKETCH
EXTRUDE, s1, 5

@ SDEL
! Delete a sketch curve, with its constraints.
SKETCH, s1, XY
SRECT, 0, 0, 40, 20
SCIRCLE, 20, 10, 4
SDEL, 5
ENDSKETCH

@ SMOVE
! Drag the end of a line to (25, 10); what is tied to it follows.
SKETCH, s1, XY
SLINE, 0, 0, 20, 0
SMOVE, 1.E, 25, 10
ENDSKETCH

@ SSEL
! Select sketch geometry for the constraint buttons (not part of the history).
SKETCH, s1, XY
SLINE, 0, 0, 20, 3
SSEL, 1
SSEL, NONE
ENDSKETCH

@ STRIM
! Trim a line back to the circle that crosses it.
SKETCH, s1, XY
SLINE, -20, 0, 20, 0
SCIRCLE, 0, 0, 10
STRIM, 1, 15, 0
ENDSKETCH

@ SEXTEND
! Extend a line on from its end to the next line it meets.
SKETCH, s1, XY
SLINE, 0, 0, 20, 0
SLINE, 40, -10, 40, 10
SEXTEND, 1.E
ENDSKETCH

@ SFILLET pic
! Round all four corners of a rectangle with radius 8.
SKETCH, s1, XY
SRECT, 0, 0, 60, 40
SFILLET, 1.E, 2.E, 3.E, 4.E, 8
ENDSKETCH
EXTRUDE, s1, 5

@ SCHAMFER
! Cut a corner of a rectangle 6 back along both sides.
SKETCH, s1, XY
SRECT, 0, 0, 60, 40
SCHAMFER, 1.E, 6
ENDSKETCH
EXTRUDE, s1, 5

@ SSPLIT
! Split a line in two at x = 20, so each part can be sized on its own.
SKETCH, s1, XY
SLINE, 0, 0, 40, 0
SSPLIT, 1, 20, 0
ENDSKETCH

@ SCORNER
! Trim or extend two lines so they just meet in a corner.
SKETCH, s1, XY
SLINE, 0, 0, 30, 0
SLINE, 40, 5, 40, 30
SCORNER, 1, 2
ENDSKETCH

@ SOFFSET
! A copy of a closed outline, 3 further out.
SKETCH, s1, XY
SRECT, 0, 0, 40, 20
SOFFSET, 3, 1, 2, 3, 4
ENDSKETCH

@ SOFFSET2
! A slot 8 wide along a path: offset 4 to both sides, with round ends.
SKETCH, s1, XY
SLINE, 0, 0, 30, 0
SLINE, 1.E, 50, 20
SOFFSET2, 4, 1, 2
ENDSKETCH
EXTRUDE, s1, 5

@ SMIRROR
! Mirror a line and an arc about the sketch's vertical axis.
SKETCH, s1, XY
SLINE, 5, 0, 30, 0
SLINE, 1.E, 30, 20
SMIRROR, V, 1, 2
ENDSKETCH

@ SPATTERN pic
! Six holes round the centre of a disc.
SKETCH, s1, XY
SCIRCLE, 0, 0, 30
SCIRCLE, 20, 0, 3
SPATTERN, POLAR, 6, 360, O, 2
ENDSKETCH
EXTRUDE, s1, 5

@ STRANSFORM
! A copy of a circle moved 25 along u.
SKETCH, s1, XY
SCIRCLE, 0, 0, 5
STRANSFORM, MOVE, 25, 0, 1, COPY
ENDSKETCH

@ SJOIN
! Join two lines that meet end to end into one smooth spline.
SKETCH, s1, XY
SLINE, 0, 0, 20, 0
SLINE, 1.E, 30, 15
SJOIN, 1, 2
ENDSKETCH

@ SPROJECT
! Bring the edges of a block's top face into a sketch above it.
BLOCK, 0,0,0, 40, 20, 10
PLANE, above, XY, 20
SKETCH, s1, above
SPROJECT, FACE, 6
ENDSKETCH

@ SINTERSECT
! The section of a ball where it cuts the sketch plane.
SPHERE, 0,0,0, 20
SKETCH, s1, XY
SINTERSECT, 1
ENDSKETCH
