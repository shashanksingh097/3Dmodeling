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

gsec, 1120, 830, 790, 700, 830, 5
NAME, LAST, cowl
gsec, 1350, 820, 730, 760, 960, 30
gsec, 1750, 800, 665, 760, 1300, 40
gsec, 2000, 795, 645, 760, 1490, 35
gsec, 2800, 795, 645, 770, 1500, 35
gsec, 3250, 785, 625, 780, 1450, 35
gsec, 3650, 770, 585, 800, 1160, 25
gsec, 3880, 750, 560, 780, 990, 10
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

! ---------------------------------------------------------------- cutting tools
! A box with rounded edges running along axis ax (1 = x, 2 = y, 3 = z),
! grown by g on every side (negative g shrinks it).
*MACRO, rbox, x0, y0, z0, x1, y1, z1, r, ax, g=0
  cx = 0.5*(x0 + x1)
  cy = 0.5*(y0 + y1)
  cz = 0.5*(z0 + z1)
  *IF, ax == 3
    RECT, cx, cy, z0 - g, x1 - x0 + 2*g, y1 - y0 + 2*g, r + g
    LINE, cx, cy, z0 - g, cx, cy, z1 + g
  *ELSEIF, ax == 2
    RECT, cx, y0 - g, cz, x1 - x0 + 2*g, z1 - z0 + 2*g, r + g, 0, 1, 0
    LINE, cx, y0 - g, cz, cx, y1 + g, cz
  *ELSE
    RECT, x0 - g, cy, cz, y1 - y0 + 2*g, z1 - z0 + 2*g, r + g, 1, 0, 0
    LINE, x0 - g, cy, cz, x1 + g, cy, cz
  *ENDIF
  SWEEP, LAST-1, LAST
*END

! Cut a panel out of the skin: the panel is the skin inside the box shrunk by
! SHUT, and the skin loses the box grown by SHUT, which leaves the shut line.
*MACRO, panel, name, x0, y0, z0, x1, y1, z1, r, ax
  rbox, x0, y0, z0, x1, y1, z1, r, ax, -SHUT
  RG = LAST
  COPY, skin
  INTERSECT, LAST, RG
  NAME, LAST, name
  LAYER, paint, ADD, LAST
  rbox, x0, y0, z0, x1, y1, z1, r, ax, SHUT
  SUBTRACT, skin, LAST
*END

! the same panel on the left (+y) and the right (-y) side
*MACRO, panel2, name, x0, z0, x1, z1, yin, r, ax=2
  panel, "" + name + "_l", x0, yin, z0, x1, 1200, z1, r, ax
  panel, "" + name + "_r", x0, -1200, z0, x1, -yin, z1, r, ax
*END

! ---------------------------------------------------------------- body panels
! The lower body becomes a 3 mm skin. Panels are cut from it in order: what
! one panel takes, the later ones no longer see, so a rough box is enough
! where an earlier panel already holds the edge.
COPY, tub
NAME, LAST, skin
PICK, BODY, skin
SHELL, THK
panel2, headlamp, 30, 520, 470, 900, 430, 70, 3
panel2, taillamp, 4080, 720, 4500, 1000, 520, 50, 3
panel, bumper_f, -100, -1200, 0, 360, 1200, 1300, 10, 2
panel, hood, 360, -690, 500, 1240, 690, 1300, 60, 3
panel2, fender, 360, 255, 1262, 1300, 600, 20
panel2, door_f, 1262, 255, 2330, 1300, 600, 30
panel2, door_r, 2330, 255, 3180, 1300, 600, 30
panel, bumper_r, 4290, -1200, 0, 4600, 1200, 1300, 10, 2
panel, trunk, 3860, -690, 760, 4290, 690, 1300, 60, 3
panel2, quarter, 3180, 255, 4290, 1300, 600, 20
NAME, skin, bodyframe   ! what is left: sills, cowl, floor, wheel wells

! ---------------------------------------------------------------- glass and pillars
! The openings, as solids: windscreen and rear window seen from above, the
! side windows seen from the side.
POLYLINE, (1150,-770,880), (1150,770,880), (1985,605,880), (1985,-605,880), CLOSE
LINE, 1150, 0, 880, 1150, 0, 1700
SWEEP, LAST-1, LAST
NAME, LAST, o_ws
POLYLINE, (3290,-600,990), (3290,600,990), (3830,690,990), (3830,-690,990), CLOSE
LINE, 3290, 0, 990, 3290, 0, 1700
SWEEP, LAST-1, LAST
NAME, LAST, o_rw
*DO, s, -1, 1, 2
  POLYLINE, (1480,300*s,940), (2050,300*s,1385), (2375,300*s,1395), (2375,300*s,940), CLOSE
  LINE, 1480, 300*s, 940, 1480, 1200*s, 940
  SWEEP, LAST-1, LAST
  NAME, LAST, "o_sf_" + ("l" if s > 0 else "r")
  POLYLINE, (2455,300*s,940), (2455,300*s,1395), (3040,300*s,1390), (3500,300*s,950), CLOSE
  LINE, 2455, 300*s, 940, 2455, 1200*s, 940
  SWEEP, LAST-1, LAST
  NAME, LAST, "o_sr_" + ("l" if s > 0 else "r")
*ENDDO

! the cabin as a 4 mm skin: the openings give the glass, the rest is the roof and pillars
COPY, cabin
NAME, LAST, glassskin
PICK, BODY, glassskin
SHELL, 4
*MACRO, pane, name, opening
  COPY, glassskin
  INTERSECT, LAST, opening
  NAME, LAST, name
  LAYER, glass, ADD, LAST
*END
KEEP, ON                 ! the openings are needed again below
pane, windscreen, o_ws
pane, backlight, o_rw
pane, glass_fl, o_sf_l
pane, glass_fr, o_sf_r
pane, glass_rl, o_sr_l
pane, glass_rr, o_sr_r
KEEP, OFF

COPY, glassskin
NAME, LAST, roof
SUBTRACT, roof, o_ws, o_rw, o_sf_l, o_sf_r, o_sr_l, o_sr_r
LAYER, paint, ADD, roof
HIDE, tub
HIDE, cabin
HIDE, glassskin

! ---------------------------------------------------------------- details
! A chunk of the lower body inside a box, moved in by d (out when d < 0):
! anything trimmed by it follows the body's curves at that distance.
*MACRO, under, x0, y0, z0, x1, y1, z1, d
  BLOCK, x0, y0, z0, x1 - x0, y1 - y0, z1 - z0
  BX = LAST
  COPY, tub
  INTERSECT, BX, LAST      ! the box first, so the result stays on the current layer
  OFFSET, LAST, -d
*END

! lamps: the lens is the panel cut above, in see-through glass; behind it a
! dark housing, a light strip and (headlamps) two projectors
*MACRO, lampguts, nm, x0, y0, z0, x1, y1, z1, r, head
  LAYER, nm, ADD, nm
  MATERIAL, nm, GLASS
  LAYER, trim
  under, x0, y0, z0, x1, y1, z1, 40
  NAME, LAST, "" + nm + "_housing"
  LAYER, "lamps" if head else "redlamps"
  under, x0, y0, z0, x1, y1, z1, 10
  S1 = LAST
  BLOCK, x0 - 100, y0 - 100, z0 + 40, x1 - x0 + 200, y1 - y0 + 200, 16
  INTERSECT, S1, LAST
  S1 = LAST
  under, x0, y0, z0, x1, y1, z1, 22
  SUBTRACT, S1, LAST
  NAME, LAST, "" + nm + "_strip"
  *IF, head
    LAYER, chrome
    under, x0, y0, z0, x1, y1, z1, 14
    P1 = LAST
    YM = 0.5*(y0 + y1)
    CYL, x0 - 100, YM - 0.2*(y1 - y0), z0 + 0.55*(z1 - z0) - 60, 38, 700, 1, 0, 0
    CYL, x0 - 100, YM + 0.18*(y1 - y0), z0 + 0.55*(z1 - z0) - 60, 38, 700, 1, 0, 0
    UNION, LAST-1, LAST
    INTERSECT, LAST, P1
    NAME, LAST, "" + nm + "_projectors"
  *ENDIF
  LAYER, build
*END
LAYER, headlamp_l, NEW, #b8c8d8
LAYER, headlamp_r, NEW, #b8c8d8
LAYER, taillamp_l, NEW, #c0141e
LAYER, taillamp_r, NEW, #c0141e
lampguts, "headlamp_l", 30, 430, 520, 470, 900, 900, 70, 1
lampguts, "headlamp_r", 30, -900, 520, 470, -430, 900, 70, 1
lampguts, "taillamp_l", 4080, 520, 720, 4500, 1000, 1000, 50, 0
lampguts, "taillamp_r", 4080, -1000, 720, 4500, -520, 1000, 50, 0

! front grille: an opening in the bumper with a honeycomb insert behind it
rbox, -100, -400, 395, 250, 400, 515, 45, 1
SUBTRACT, bumper_f, LAST
LAYER, trim
under, -100, -440, 360, 300, 440, 550, 22
NAME, LAST, grille
LAYER, build
*DO, row, 0, 1
  POLYGON, -60, -400 + 20*row, 410 + 34.6*row, 17, 6, 1, 0, 0, 30
  LINE, -60, -400 + 20*row, 410 + 34.6*row, 320, -400 + 20*row, 410 + 34.6*row
  SWEEP, LAST-1, LAST
  ARRAY, LINEAR, LAST, 21 - row, 0, 40, 0, 3 - row, 0, 0, 69.2, CUT, grille
*ENDDO
LAYER, trim
CYL, 60, 0, 455, 40, 80, -1, 0, 0
NAME, LAST, badge
LAYER, chrome
TEXT, "3D", 40, 0, 440, 34, 30, -1, 0, 0, , CENTER, , BOLD
TX = LAST
under, -100, -60, 400, 100, 60, 500, 15
INTERSECT, TX, LAST
NAME, LAST, badge_text
LAYER, build

! lower intakes with fog lamps, and the number plate between them
*DO, sd, -1, 1, 2
  rbox, -100, (260 if sd > 0 else -640), 222, 250, (640 if sd > 0 else -260), 330, 35, 1
  SUBTRACT, bumper_f, LAST
  LAYER, trim
  BLOCK, 110, (240 if sd > 0 else -660), 240, 25, 420, 105
  NAME, LAST, "intake_" + ("l" if sd > 0 else "r")
  LAYER, lamps
  CYL, 70, sd*560, 276, 30, 45, 1, 0, 0
  NAME, LAST, "foglamp_" + ("l" if sd > 0 else "r")
  LAYER, build
*ENDDO
*MACRO, plate, nm, x0, x1, zc, nx, txt
  LAYER, lamps
  under, x0, -250, zc - 55, x1, 250, zc + 55, -6
  NAME, LAST, nm
  LAYER, trim
  TEXT, txt, (x1 if nx < 0 else x0), 0, zc - 24, 62, (x1 - x0)*1.2, nx, 0, 0, , CENTER, , BOLD
  TX = LAST
  under, x0, -250, zc - 60, x1, 250, zc + 60, -8
  INTERSECT, TX, LAST
  NAME, LAST, "" + nm + "_text"
  LAYER, build
*END
plate, plate_f, -80, 120, 282, -1, "CMD 3D"

! rear: number plate, a diffuser with fins, two exhaust tips
plate, plate_r, 4300, 4520, 540, 1, "CMD 3D"
rbox, 4150, -660, 200, 4600, 660, 335, 30, 1
SUBTRACT, bumper_r, LAST
LAYER, trim
under, 4150, -700, 150, 4600, 700, 380, 25
NAME, LAST, diffuser
under, 4150, -700, 150, 4600, 700, 380, 3
NAME, LAST, finclip
KEEP, ON                 ! finclip trims every fin, so it must stay
*DO, f, -2, 2
  BLOCK, 4150, f*210 - 4, 150, 450, 8, 230
  INTERSECT, LAST, finclip
  UNION, diffuser, LAST
*ENDDO
KEEP, OFF
LAYER, chrome
*DO, sd, -1, 1, 2
  TUBE, 4250, sd*470, 262, 44, 38, 165, 1, 0, 0
  NAME, LAST, "exhaust_" + ("l" if sd > 0 else "r")
*ENDDO

! black sills under the doors, and a fuel flap on the right
*DO, sd, -1, 1, 2
  LAYER, trim
  under, 1290, (560 if sd > 0 else -1200), 120, 3150, (1200 if sd > 0 else -560), 232, -7
  NAME, LAST, "sill_" + ("l" if sd > 0 else "r")
*ENDDO
LAYER, build
TUBE, 3930, -1100, 800, 80, 76, 300, 0, 1, 0
SUBTRACT, quarter_r, LAST

! mirrors: a housing lofted through three ellipses on a short arm, and its glass
*PART, wingmirror
  ELLIPSE, -80, 120, 30, 50, 28, 1, 0, 0
  ELLIPSE, -35, 132, 30, 92, 52, 1, 0, 0
  ELLIPSE, 8, 138, 30, 104, 60, 1, 0, 0
  LOFT, LAST-2, LAST-1, LAST
  NAME, LAST, cap
  ELLIPSE, -30, 0, 0, 45, 16, 0, 1, 0
  ELLIPSE, -30, 90, 22, 26, 13, 0, 1, 0
  LOFT, LAST-1, LAST
  UNION, cap, LAST
  ELLIPSE, 0, 138, 30, 94, 52, 1, 0, 0       ! a shallow recess for the glass
  LINE, 0, 138, 30, 30, 138, 30
  SWEEP, LAST-1, LAST
  SUBTRACT, cap, LAST
*ENDPART
*PART, mirrorglass
  ELLIPSE, 1, 138, 30, 93, 51, 1, 0, 0
  LINE, 1, 138, 30, 4, 138, 30
  SWEEP, LAST-1, LAST
*ENDPART
LAYER, paint
INST, wingmirror, 1470, 845, 880
NAME, LAST, mirror_l
MIRROR, mirror_l, 0, 0, 0, 0, 1, 0
NAME, LAST, mirror_r
LAYER, glass
INST, mirrorglass, 1470, 845, 880
NAME, LAST, mirrorglass_l
MATERIAL, LAST, GLASS
COLOR, LAST, #c8d4dc
MIRROR, mirrorglass_l, 0, 0, 0, 0, 1, 0
NAME, LAST, mirrorglass_r

! door handles: a rounded bar standing a little proud of each door
*PART, handle
  SLOT, 0, -20, 0, 150, 28, 0, 1, 0
  LINE, 0, -20, 0, 0, 14, 0
  SWEEP, LAST-1, LAST
*ENDPART
LAYER, chrome
*DO, sd, -1, 1, 2
  INST, handle, 2150, sd*902, 830, (0 if sd > 0 else 180)
  NAME, LAST, "handle_f_" + ("l" if sd > 0 else "r")
  INST, handle, 3020, sd*900, 855, (0 if sd > 0 else 180)
  NAME, LAST, "handle_r_" + ("l" if sd > 0 else "r")
*ENDDO

! a lip spoiler on the trunk lid: an airfoil swept between two curved rails
LAYER, build
AIRFOIL, 4170, -640, 985, 130, 0015, 0, -1, 0, , 0
NAME, LAST, sfoil
LINE, 4170, -640, 985, 4170, 640, 985
NAME, LAST, sspan
SPLINE, (4170, -640, 985), (4165, 0, 1004), (4170, 640, 985)
NAME, LAST, sle
SPLINE, (4300, -640, 985), (4305, 0, 1012), (4300, 640, 985)
NAME, LAST, ste
LAYER, paint
RAILSWEEP, sfoil, sle, ste, sspan
NAME, LAST, spoiler

! a fin antenna on the back of the roof, lofted through three airfoils
! (its height comes from the roof itself: the top of a thin slice through it)
LAYER, build
BLOCK, 3060, -5, 1000, 20, 10, 700
BX = LAST
COPY, roof
INTERSECT, BX, LAST
ZF = BBOX(LAST).zmax
AIRFOIL, 3000, 0, ZF - 12, 170, 0018
AIRFOIL, 3045, 0, ZF + 30, 110, 0018
AIRFOIL, 3095, 0, ZF + 60, 40, 0018
LAYER, trim
LOFT, LAST-2, LAST-1, LAST
NAME, LAST, antenna
LAYER, build

! ---------------------------------------------------------------- wheels
! Each wheel is four parts (tyre, rim, brake disc, caliper), drawn with the
! axle along y and the outside of the wheel towards +y, placed four times.
*PART, tyre, R=330, W=225, RI=232
  TUBE, 0, -W/2, 0, R, RI, W, 0, 1, 0
  NAME, LAST, t
  SEL, S, EDGE, RADIUS, EQ, R
  FILLET, 42
  *DO, i, -1, 1
    TUBE, 0, i*52 - 6, 0, R + 5, R - 10, 12, 0, 1, 0
    SUBTRACT, t, LAST
  *ENDDO
  BLOCK, -4, 60, R - 12, 8, 60, 20
  ARRAY, POLAR, LAST, 64, 360, 0, 0, 0, 0, 1, 0, CUT, t
  BLOCK, -4, -120, R - 12, 8, 60, 20
  ROTATE, LAST, 2.8, 0, 0, 0, 0, 1, 0
  ARRAY, POLAR, LAST, 64, 360, 0, 0, 0, 0, 1, 0, CUT, t
*ENDPART
*PART, rim, R=230
  RECT, -20, 92, 72, 28, 30, 8
  RECT, -46, 76, R - 24, 34, 22, 6
  LOFT, LAST-1, LAST
  NAME, LAST, spoke
  RECT, 20, 92, 72, 28, 30, 8
  RECT, 46, 76, R - 24, 34, 22, 6
  LOFT, LAST-1, LAST
  UNION, spoke, LAST
  ARRAY, POLAR, spoke, 5, 360, 0, 0, 0, 0, 1, 0, FUSE
  TUBE, 0, -95, 0, R + 2, R - 14, 180, 0, 1, 0
  UNION, spoke, LAST
  TUBE, 0, 68, 0, R + 12, R - 28, 22, 0, 1, 0
  UNION, spoke, LAST
  CYL, 0, 50, 0, 88, 52, 0, 1, 0
  UNION, spoke, LAST
  CYL, 0, 100, 52, 11, 12, 0, 1, 0
  ARRAY, POLAR, LAST, 5, 360, 0, 0, 0, 0, 1, 0, FUSE
  UNION, spoke, LAST
  CYL, 0, 100, 0, 34, 6, 0, 1, 0
  UNION, spoke, LAST
*ENDPART
*PART, disc
  TUBE, 0, -20, 0, 165, 70, 28, 0, 1, 0
  NAME, LAST, disc
  CYL, 0, -30, 118, 5, 50, 0, 1, 0
  ARRAY, POLAR, LAST, 24, 360, 0, 0, 0, 0, 1, 0, CUT, disc
  CYL, 0, -30, 140, 5, 50, 0, 1, 0
  ROTATE, LAST, 7.5, 0, 0, 0, 0, 1, 0
  ARRAY, POLAR, LAST, 24, 360, 0, 0, 0, 0, 1, 0, CUT, disc
*ENDPART
*PART, caliper
  CYL, 0, -45, 0, 188, 80, 0, 1, 0, 64
  NAME, LAST, cal
  CYL, 0, -50, 0, 120, 90, 0, 1, 0
  SUBTRACT, cal, LAST
  BLOCK, -200, -6, -200, 400, 12, 400
  SUBTRACT, cal, LAST
  ROTATE, cal, 30, 0, 0, 0, 0, 1, 0
*ENDPART

*MACRO, wheel, x, side, tag
  A = 0 if side > 0 else 180
  LAYER, tyres
  INST, tyre, x, side*TRACK, RW, A
  NAME, LAST, "tyre_" + tag
  LAYER, rims
  INST, rim, x, side*TRACK, RW, A
  NAME, LAST, "rim_" + tag
  LAYER, chrome
  INST, disc, x, side*TRACK, RW, A
  NAME, LAST, "disc_" + tag
  LAYER, brakes
  INST, caliper, x, side*TRACK, RW, A
  NAME, LAST, "caliper_" + tag
*END
wheel, FA, 1, "fl"
wheel, FA, -1, "fr"
wheel, FB, 1, "rl"
wheel, FB, -1, "rr"
LAYER, build
LAYER, build, OFF
LAYER, paint
VIEW, ISO
FIT
