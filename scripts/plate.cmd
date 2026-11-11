! plate with a row of holes; change W or N and it rebuilds
W = 60
N = 4
BLOCK, 0,0,0, W,20,5
NAME, LAST, plate
*MACRO, drill, x, y, d=6
  CYL, x, y, -1, d/2, 7
  SUBTRACT, plate, LAST
*END
*DO, i, 1, N
  drill, i*W/(N+1), 10
*ENDDO
SEL, S, FACE, NORMAL, 0,0,1      ! the top face, chosen by meaning, not number
CM, top, FACE
