! Prototype 3: the lower body plus the cabin, both as NSURF of closed NURBS rows.
LAYER, build, NEW
LAYER, build
*MACRO, tsec, x, w, zb, zt, cr
  h = zt - zb
  NURBS, 3, (x,0,zb), (x,0.6*w,zb), (x,0.93*w,zb), (x,w,zb+0.18*h), (x,w+14,zb+0.55*h), (x,w,zt-0.1*h), (x,0.9*w,zt), (x,0.5*w,zt+cr), (x,0,zt+cr), (x,-0.5*w,zt+cr), (x,-0.9*w,zt), (x,-w,zt-0.1*h), (x,-w-14,zb+0.55*h), (x,-w,zb+0.18*h), (x,-0.93*w,zb), (x,-0.6*w,zb), CLOSE
*END
*MACRO, gsec, x, w, wr, zb, zr, cr
  h = zr - zb
  NURBS, 3, (x,0,zb), (x,0.5*w,zb), (x,w,zb), (x,0.5*(w+wr),zb+0.55*h), (x,wr,zr), (x,0.5*wr,zr+cr), (x,0,zr+cr), (x,-0.5*wr,zr+cr), (x,-wr,zr), (x,-0.5*(w+wr),zb+0.55*h), (x,-w,zb), (x,-0.5*w,zb), CLOSE
*END
tsec, 0, 600, 360, 540, 5
tsec, 0, 800, 270, 640, 15
tsec, 120, 860, 220, 700, 25
tsec, 500, 895, 175, 770, 45
tsec, 1100, 905, 170, 840, 45
tsec, 1800, 910, 170, 880, 30
tsec, 2600, 910, 172, 905, 25
tsec, 3300, 905, 180, 930, 30
tsec, 3900, 890, 200, 960, 40
tsec, 4300, 860, 240, 960, 35
tsec, 4440, 820, 300, 930, 20
tsec, 4440, 640, 400, 840, 5
NSURF, 3, 1,2,3,4,5,6,7,8,9,10,11,12
NAME, LAST, tubskin
FILL, G0, 1
NAME, LAST, cap1
FILL, G0, 12
NAME, LAST, cap2
SEW, tubskin, cap1, cap2
NAME, LAST, tub
gsec, 1150, 770, 720, 800, 830, 5
gsec, 1550, 760, 660, 800, 1150, 30
gsec, 1950, 740, 620, 800, 1460, 30
gsec, 2700, 745, 625, 810, 1480, 30
gsec, 3250, 735, 600, 820, 1440, 30
gsec, 3700, 715, 570, 840, 1100, 25
gsec, 3900, 700, 550, 850, 950, 5
NSURF, 3, LAST-6, LAST-5, LAST-4, LAST-3, LAST-2, LAST-1, LAST
NAME, LAST, gskin
FILL, G0, LAST-7
NAME, LAST, gcap1
FILL, G0, LAST-2
NAME, LAST, gcap2
SEW, gskin, gcap1, gcap2
NAME, LAST, cabin
LAYER, paint, NEW, #b01c22
LAYER, glass, NEW, #1d2733
LAYER, build, OFF
LAYER, paint, ADD, tub
LAYER, glass, ADD, cabin
CHECK, tub
CHECK, cabin
