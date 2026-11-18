! Will it stand up? (GRAVITY): a small table on four legs with things on it. The vase stands
! well, the book hangs too far over the edge and tips off, the lamp shade was drawn 0.4 above
! its stand (a gap: it floats), and the side shelf touches only the table's side, so it needs
! fasteners unless it is listed as fastened. Problem parts are marked in the view.
BLOCK, 0, 0, 0, 6, 6, 70
NAME, LAST, leg1
BLOCK, 94, 0, 0, 6, 6, 70
NAME, LAST, leg2
BLOCK, 0, 54, 0, 6, 6, 70
NAME, LAST, leg3
BLOCK, 94, 54, 0, 6, 6, 70
NAME, LAST, leg4
BLOCK, 0, 0, 70, 100, 60, 4
NAME, LAST, top
MATERIAL, leg1, WOOD
MATERIAL, leg2, WOOD
MATERIAL, leg3, WOOD
MATERIAL, leg4, WOOD
MATERIAL, top, WOOD
CYL, 25, 30, 74, 6, 20
NAME, LAST, vase
MATERIAL, vase, GLASS
BLOCK, 88, 20, 74, 30, 20, 4
NAME, LAST, book
CYL, 60, 40, 74, 4, 25
NAME, LAST, stand
CONE, 60, 40, 99.4, 10, 4, 8
NAME, LAST, shade
BLOCK, 100, 10, 68, 15, 40, 4
NAME, LAST, shelf
GRAVITY
