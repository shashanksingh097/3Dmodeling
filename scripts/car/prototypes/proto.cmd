! Prototype 1: the whole body as one LOFT through 14 closed SPLINE sections.
! Rejected: the loft came out wavy and boxy (see the README).
*MACRO, sec, x, w, zb, zw, zbelt, wb, wr, zr
  SPLINE, (x,0,zb), (x,0.8*w,zb), (x,0.97*w,zb+0.3*(zw-zb)), (x,w,zw), (x,wb,zbelt), (x,wr+0.3*(wb-wr),zbelt+0.55*(zr-zbelt)), (x,wr,zr-0.12*(zr-zbelt)), (x,0,zr), (x,-wr,zr-0.12*(zr-zbelt)), (x,-wr-0.3*(wb-wr),zbelt+0.55*(zr-zbelt)), (x,-wb,zbelt), (x,-w,zw), (x,-0.97*w,zb+0.3*(zw-zb)), (x,-0.8*w,zb), CLOSE
*END
sec, 0, 700, 300, 430, 560, 650, 400, 600
sec, 40, 820, 220, 420, 640, 780, 500, 680
sec, 250, 870, 180, 460, 720, 840, 550, 770
sec, 700, 895, 170, 500, 800, 865, 580, 860
sec, 1250, 900, 160, 520, 860, 870, 610, 930
sec, 1550, 900, 160, 520, 880, 870, 640, 1150
sec, 1900, 900, 160, 520, 890, 868, 650, 1390
sec, 2450, 900, 160, 520, 900, 865, 655, 1430
sec, 3000, 900, 165, 520, 910, 865, 630, 1400
sec, 3350, 898, 175, 520, 930, 865, 590, 1220
sec, 3700, 890, 190, 520, 950, 860, 560, 1010
sec, 4150, 870, 230, 520, 940, 840, 540, 970
sec, 4360, 800, 320, 520, 900, 760, 470, 910
sec, 4400, 700, 400, 520, 840, 650, 400, 860
LOFT, 1,2,3,4,5,6,7,8,9,10,11,12,13,14
NAME, LAST, master
ECHO, VOL(master)
CHECK, master
