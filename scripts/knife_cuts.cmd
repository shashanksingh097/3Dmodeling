! Knife and freehand cuts (M6 part 3): KNIFE, sketch splines (SSPLINE).
! In the app, the Knife button lets you draw the stroke over the view, and the
! sketcher's Freehand tool draws SSPLINE; these lines are what they write.

! ---- a block cut in two along a wavy stroke, seen from above ----
BLOCK, 0, 0, 0, 40, 24, 12
NAME, LAST, loaf
SPLINE, (14, -4, 30), (22, 6, 30), (16, 14, 30), (24, 28, 30)
KNIFE, loaf, LAST
! loaf (the bigger piece) keeps its ID; the other piece is body 3: pull it away to show the cut
MOVE, 3, -8, 0, 0
COLOR, loaf, ORANGE

! ---- a disc and a cookie cutter: a closed stroke cuts out its inside ----
CYL, 70, 12, 0, 16, 8
NAME, LAST, disc
SPLINE, (70, 2, 20), (80, 12, 20), (77, 21, 20), (70, 17, 20), (63, 21, 20), (60, 12, 20), CLOSE
KNIFE, disc, LAST
MOVE, 6, 0, 0, 12
COLOR, 6, RED
COLOR, disc, TEAL

! ---- a slot cut along a curve through a mesh ball ----
IMPLICIT, ball, BALL(115, 12, 6, 12), 102, -1, -7, 128, 25, 19
SPLINE, (100, 6, 30), (112, 14, 30), (122, 8, 30), (132, 16, 30)
KNIFE, ball, LAST, 2.5
COLOR, ball, PURPLE

! ---- a plate with a freehand pocket and a freehand boss (sketch splines) ----
BLOCK, 0, 40, 0, 60, 36, 6
NAME, LAST, plate
PLANE, top, XY, 6
SKETCH, pocket, top
SSPLINE, 8, 46, 20, 66, 34, 70, 30, 52, 20, 48, CLOSE
ENDSKETCH
EXTRUDE, pocket, -3, CUT, plate
NAME, LAST, plate
SKETCH, boss, top
SSPLINE, 40, 46, 54, 50, 50, 64, 42, 70, CLOSE
ENDSKETCH
EXTRUDE, boss, 8, ADD, plate
COLOR, LAST, GRAY
DATUM, DELETE, top

! the two pieces of the loaf still make the whole block
ASSERT, VOL(loaf) + VOL(3), EQ, 40*24*12, 0.01
