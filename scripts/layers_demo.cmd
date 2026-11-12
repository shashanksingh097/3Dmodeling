! A small pump base sorted into layers: the frame, the bolts and the
! cover each sit on their own layer with their own colour and material.
! Switch a layer off in the Layers panel (or LAYER, cover, OFF) to look
! inside; lock the frame so nothing changes it by accident.
LAYER, frame, NEW, #5a6f8a
LAYER, bolts, NEW, ORANGE
LAYER, cover, NEW, TEAL

LAYER, frame
BLOCK, -40, -25, 0, 80, 50, 8
NAME, LAST, base
MATERIAL, base, CASTIRON
HOLE, base, 0, 0, 8, 30
BLOCK, -40, -25, 8, 8, 50, 30
MATERIAL, LAST, CASTIRON
UNION, base, LAST
*DO, i, -1, 1, 2
  *DO, j, -1, 1, 2
    HOLE, base, 30*i, 17*j, 8, 6.4
  *ENDDO
*ENDDO

LAYER, bolts
*DO, i, -1, 1, 2
  *DO, j, -1, 1, 2
    CYL, 30*i, 17*j, -4, 3, 16
    MATERIAL, LAST, STEEL
  *ENDDO
*ENDDO

LAYER, cover
TUBE, 0, 0, 8, 22, 16, 24
MATERIAL, LAST, ALUMINIUM

LAYER, frame, LOCK
LAYER, DEFAULT
