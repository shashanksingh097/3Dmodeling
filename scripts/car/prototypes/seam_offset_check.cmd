! Debug: an early copy of the start of car_body.cmd, then two boxes cut from the lower body on
! the left and right. The left piece has one face more (the seam of the closed rows runs
! through it), which is why OFFSET of that piece failed; see docs/example-car.md.
! A detailed car body, built only with the command language.
! x runs from the front bumper (x = 0) to the back, y to the car's left, z up; mm.
! The lower body and the cabin are two smooth NURBS surfaces (rows of control
! points, closed with flat patches and sewn into solids). The lower body is
! hollowed into a 3 mm skin and cut into panels with shut lines; the cabin
! becomes a frame of roof and pillars with glass set into it. Wheels, lights,
! mirrors and other add-ons are parts placed on both sides.

FA = 880                 ! front axle
FB = 3560                ! rear axle
TRACK = 790              ! wheel centre from the middle
RW = 330                 ! wheel radius (tyre)
ARCH = 372               ! wheel arch radius
SHUT = 3                 ! half the shut-line gap between panels
THK = 3                  ! panel thickness

LAYER, build, NEW        ! curves and cutters: switched off at the end
LAYER, paint, NEW, #a3151d
LAYER, glass, NEW, #1b2430
LAYER, trim, NEW, #26282c
LAYER, chrome, NEW, #c9ccd1
LAYER, lamps, NEW, #e9eef2
LAYER, redlamps, NEW, #b0101a
LAYER, tyres, NEW, #202022
LAYER, rims, NEW, #9da3ab
LAYER, brakes, NEW, #c23b22
LAYER, build

! ---------------------------------------------------------------- master shapes
! One section of the lower body: closed control polygon around the car.
*MACRO, tsec, x, w, zb, zt, cr, b=0
  ! b pushes the side out (over the wheels); the shoulder is a crisp line under the top
  h = zt - zb
  NURBS, 3, (x,0,zb), (x,0.6*w,zb), (x,0.88*w,zb), (x,0.97*w+0.5*b,zb+0.15*h), (x,w+b,zb+0.45*h), (x,w+0.6*b+4,zt-0.22*h), (x,w-6,zt-0.06*h), (x,0.88*w,zt), (x,0.5*w,zt+cr), (x,0,zt+cr), (x,-0.5*w,zt+cr), (x,-0.88*w,zt), (x,-w+6,zt-0.06*h), (x,-w-0.6*b-4,zt-0.22*h), (x,-w-b,zb+0.45*h), (x,-0.97*w-0.5*b,zb+0.15*h), (x,-0.88*w,zb), (x,-0.6*w,zb), CLOSE
*END
! One section of the cabin: sides lean in towards the roof.
*MACRO, gsec, x, w, wr, zb, zr, cr
  h = zr - zb
  NURBS, 3, (x,0,zb), (x,0.5*w,zb), (x,w,zb), (x,0.5*(w+wr),zb+0.55*h), (x,wr,zr), (x,0.5*wr,zr+cr), (x,0,zr+cr), (x,-0.5*wr,zr+cr), (x,-wr,zr), (x,-0.5*(w+wr),zb+0.55*h), (x,-w,zb), (x,-0.5*w,zb), CLOSE
*END

tsec, 0, 560, 330, 520, 5
NAME, LAST, nose
tsec, 0, 700, 255, 600, 15
tsec, 150, 830, 205, 665, 30
tsec, 480, 880, 175, 720, 50, 10
tsec, FA, 890, 172, 770, 50, 30
tsec, 1350, 895, 170, 840, 40, 8
tsec, 2200, 900, 170, 890, 25
tsec, 3000, 900, 175, 925, 25, 12
tsec, FB, 900, 185, 950, 35, 36
tsec, 4000, 885, 205, 970, 40, 12
tsec, 4320, 850, 245, 965, 35
tsec, 4440, 800, 310, 935, 15
tsec, 4440, 620, 410, 850, 5
NAME, LAST, tail
NSURF, 3, nose, LAST-11, LAST-10, LAST-9, LAST-8, LAST-7, LAST-6, LAST-5, LAST-4, LAST-3, LAST-2, LAST-1, tail
NAME, LAST, tubskin
! a power bulge down the middle of the hood: lift the top control points of two rows
! (POLES, tubskin lists them: row 4 is x = 480, row 5 the front axle; point 10 is the top middle)
MOVEPT, tubskin, (4, 10), 0, 0, 22
MOVEPT, tubskin, (5, 10), 0, 0, 30
MOVEPT, tubskin, (6, 10), 0, 0, 18
FILL, G0, nose
NAME, LAST, tubcap1
FILL, G0, tail
NAME, LAST, tubcap2
SEW, tubskin, tubcap1, tubcap2
NAME, LAST, tub

gsec, 1120, 830, 790, 760, 790, 5
NAME, LAST, cowl
gsec, 1350, 820, 730, 760, 960, 30
gsec, 1750, 800, 665, 760, 1300, 40
gsec, 2000, 795, 645, 760, 1490, 35
gsec, 2800, 795, 645, 770, 1500, 35
gsec, 3250, 785, 625, 780, 1450, 35
gsec, 3650, 770, 585, 800, 1160, 25
gsec, 3880, 750, 560, 820, 990, 10
NAME, LAST, deck
NSURF, 3, cowl, LAST-6, LAST-5, LAST-4, LAST-3, LAST-2, LAST-1, deck
NAME, LAST, cabskin
FILL, G0, cowl
NAME, LAST, cabcap1
FILL, G0, deck
NAME, LAST, cabcap2
SEW, cabskin, cabcap1, cabcap2
NAME, LAST, cabin

! wheel wells: a round pocket on each side at each axle
*DO, k, 0, 1
  XA = FA if k == 0 else FB
  CYL, XA, 560, RW, ARCH, 500, 0, 1, 0
  SUBTRACT, tub, LAST
  CYL, XA, -1060, RW, ARCH, 500, 0, 1, 0
  SUBTRACT, tub, LAST
*ENDDO
LAYER, paint, ADD, tub
LAYER, glass, ADD, cabin

BLOCK, -100, 240, 205, 400, 420, 145
COPY, tub
INTERSECT, LAST, LAST-1
DESCRIBE, LAST, FACES
BLOCK, -100, -660, 205, 400, 420, 145
COPY, tub
INTERSECT, LAST, LAST-1
DESCRIBE, LAST, FACES
