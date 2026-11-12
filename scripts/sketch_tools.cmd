! A plate drawn with the sketch editing tools: rounded corners, a ring
! offset from a bore, a ring of holes and mirrored slots. Change W or H
! (or any size) and everything follows.
W = 80
H = 50
SKETCH, plate, XY
SRECT, -40,-25, 40,25
SDIM, LENGTH, 1, W
SDIM, LENGTH, 2, H
SCON, SYMMETRIC, 1.S, 1.E, V
SCON, SYMMETRIC, 2.S, 2.E, H
SFILLET, 1.E, 2.E, 3.E, 4.E, 8        ! all four corners; the corners stay as points 5, 7, 9, 11
SCIRCLE, 0, 0, 12
SOFFSET, 3, 13                        ! a ring 3 outside the bore
SCIRCLE, 18, 0, 2
SPATTERN, POLAR, 6, 360, O, 15        ! six holes round the middle
SSLOT, -30, -15, -20, -15, 2.5
SMIRROR, H, 21, 22, 23, 24            ! the slot again on the other side
ENDSKETCH
EXTRUDE, plate, 6
