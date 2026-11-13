! Prototype 4: the tyre, rim and brake parts, tried on their own before going on the car.
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
*PART, brake
  TUBE, 0, -20, 0, 165, 70, 28, 0, 1, 0
  NAME, LAST, disc
  CYL, 0, -30, 118, 5, 50, 0, 1, 0
  ARRAY, POLAR, LAST, 24, 360, 0, 0, 0, 0, 1, 0, CUT, disc
  CYL, 0, -45, 0, 188, 80, 0, 1, 0, 64
  NAME, LAST, cal
  CYL, 0, -50, 0, 120, 90, 0, 1, 0
  SUBTRACT, cal, LAST
  BLOCK, -200, -6, -200, 400, 12, 400
  SUBTRACT, cal, LAST
  ROTATE, cal, 30, 0, 0, 0, 0, 1, 0
*ENDPART
LAYER, tyres, NEW, #202022
LAYER, rims, NEW, #9da3ab
LAYER, brakes, NEW, #c23b22
LAYER, tyres
INST, tyre, 0, 0, 0
LAYER, rims
INST, rim, 0, 0, 0
LAYER, brakes
INST, brake, 0, 0, 0
