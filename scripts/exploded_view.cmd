! Exploded views (XSTEP, XSHOW) and a label wrapped onto a cone (WRAP): a box with a lid, four screws
! and a conical knob. XSTEP records how the parts come apart; XSHOW shows it with trail lines, and
! the parts go back before the next command (or XSHOW alone).
BLOCK, -30, -20, 0, 60, 40, 20
NAME, LAST, box
BLOCK, -30, -20, 20, 60, 40, 4
NAME, LAST, lid
COLOR, lid, ORANGE
CYL, -25, -15, 14, 2, 14
NAME, LAST, screw_1
COLOR, LAST, GREY
CYL, 25, -15, 14, 2, 14
NAME, LAST, screw_2
COLOR, LAST, GREY
CYL, -25, 15, 14, 2, 14
NAME, LAST, screw_3
COLOR, LAST, GREY
CYL, 25, 15, 14, 2, 14
NAME, LAST, screw_4
COLOR, LAST, GREY
CONE, 0, 0, 24, 10, 6, 12
NAME, LAST, knob
COLOR, knob, BLUE
! a band of text-like marks round the knob: the sketch is laid on the cone's development
PLANE, w, XZ, -20
SKETCH, marks, w
SRECT, -1, 27, 1, 33
SRECT, 4, 27, 6, 33
SRECT, -6, 27, -4, 33
ENDSKETCH
SEL, S, FACE, TYPE, CONE
WRAP, marks, , 0.6
DATUM, DELETE, w
! the exploded view: the knob and screws first, then the lid
XSTEP, apart, knob, 0, 0, 30
XSTEP, apart, "screw_1 screw_2 screw_3 screw_4", 0, 0, 45
XSTEP, apart, "lid knob", 0, 0, 25
! show it with: XSHOW, apart  (and XSHOW alone to put the parts back)
FIT
