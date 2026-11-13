! Prototype 2: the lower body as NSURF of closed NURBS rows, capped with FILL and SEWn.
! Smooth with no waves; this became the method of the example.
LAYER, build, NEW
LAYER, build
*MACRO, tsec, x, w, zb, zt, cr
  NURBS, 3, (x,0,zb), (x,0.6*w,zb), (x,w,zb), (x,w+15,0.5*(zb+zt)), (x,w,zt), (x,0.55*w,zt+cr), (x,0,zt+cr), (x,-0.55*w,zt+cr), (x,-w,zt), (x,-w-15,0.5*(zb+zt)), (x,-w,zb), (x,-0.6*w,zb), CLOSE
*END
tsec, 0, 640, 340, 560, 10
tsec, 0, 820, 260, 660, 20
tsec, 300, 880, 190, 760, 40
tsec, 900, 900, 170, 830, 50
tsec, 1500, 905, 170, 880, 40
tsec, 2300, 905, 170, 900, 30
tsec, 3100, 905, 175, 920, 30
tsec, 3700, 895, 190, 950, 40
tsec, 4250, 860, 240, 950, 40
tsec, 4420, 820, 300, 900, 30
tsec, 4420, 660, 380, 820, 10
NSURF, 3, 1,2,3,4,5,6,7,8,9,10,11
NAME, LAST, tubskin
FILL, G0, 1
NAME, LAST, cap1
FILL, G0, 11
NAME, LAST, cap2
SEW, tubskin, cap1, cap2
NAME, LAST, tub
LAYER, paint, NEW, #b01c22
LAYER, build, OFF
LAYER, paint, ADD, tub
CHECK, tub
ECHO, VOL(tub)
