! The rest of M4 in one script: text, a loft along a spine, an equation
! surface, and direct face editing. Change any number and run again.

! ---- a name plate with raised and engraved letters ----------------------------
W = 70
BLOCK, 0, -60, 0, W, 24, 4
NAME, LAST, plate
TEXT, "M4 DONE", W/2, -54, 4, 9, 1.2, , , , , CENTER, , BOLD   ! raised letters
UNION, plate, LAST
TEXT, "No 16", 4, -58.5, 3.4, 4, 1                       ! engraved 0.6 deep
SUBTRACT, plate, LAST

! ---- a duct that bends and changes shape: round, then a rounded square, then round
R = 50
ARC, 0, 0, 0, R*(1 - cos(45)), 0, R*sin(45), R, 0, R
NAME, LAST, spine
CIRCLE, 0, 0, 0, 9
NAME, LAST, inlet
RECT, R*(1 - cos(45)), 0, R*sin(45), 20, 14, 4, sin(45), 0, cos(45)
NAME, LAST, middle
CIRCLE, R, 0, R, 5, 1, 0, 0
NAME, LAST, outlet
SPINELOFT, spine, inlet, middle, outlet
NAME, LAST, duct

! ---- a wavy cover from an equation, thickened to 2 ----------------------------
SURFACE, PARAM, 80 + u, v - 30, 3*sin(6*u)*cos(6*v), 0, 60, 0, 60, 30, 30, 2
NAME, LAST, cover

! ---- a torus from its equation is a solid ---------------------------------------
SURFACE, PARAM, (12 + 4*cos(v))*cos(u) + 110, (12 + 4*cos(v))*sin(u) + 45, 4*sin(v), 0, 360, 0, 360
NAME, LAST, ring

! ---- direct editing on a block with a hole: no history needed ------------------
BLOCK, -60, -20, 0, 40, 30, 10
NAME, LAST, blk
CYL, -40, -5, -1, 4, 12
SUBTRACT, blk, LAST
SEL, S, FACE, BODY, blk
SEL, R, FACE, NORMAL, 0, 0, 1
PUSHPULL, 6                       ! the top goes up by 6
SEL, S, FACE, BODY, blk
SEL, R, FACE, TYPE, CYLINDER
PUSHPULL, -2                      ! the hole grows from radius 4 to 6
SEL, NONE
