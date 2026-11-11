! M2 shell demo: patterns (ARRAY), keeping boolean inputs (KEEP), and a
! chain whose links follow a curve, turning a quarter turn each.

! a round plate with 8 holes on a circle (POLAR) and a 3 x 3 grid of pins (LINEAR)
CYL, 0,0,0, 40, 6
NAME, LAST, plate
CYL, 30,0,-1, 4, 8
ARRAY, POLAR, LAST, 8, 360, 0,0,0, 0,0,1, FUSE
SUBTRACT, plate, LAST
CYL, -10,-10,6, 2.5, 10
ARRAY, LINEAR, LAST, 3, (10,0,0), 3, (0,10,0), FUSE
UNION, plate, LAST

! a chain hanging on a curve: one link, copied along the path
SPLINE, (60,-40,40), (90,-10,20), (120,20,30), (150,50,10)
NAME, LAST, chain_path
TORUS, 60,-40,40, 4, 1.2, 0.7,-0.7,0
ARRAY, PATH, LAST, chain_path, 14, 90*round(13*t)

! KEEP: cut a pocket but keep the cutting tool (hidden, same name) to use again
KEEP, ON
BLOCK, -20,60,0, 40,30,10
NAME, LAST, block
SPHERE, 0,75,12, 9
NAME, LAST, ball
SUBTRACT, block, ball
SHOW, ball
MOVE, ball, 0,0,22
KEEP, OFF
