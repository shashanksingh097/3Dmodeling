! A round plate held down by bolts: one bolt part and one washer part,
! each placed N times on a circle. Change D or N and every copy follows;
! edit the *PART block and every bolt changes shape.
D = 8            ! bolt size
N = 6            ! how many bolts
PCD = 90         ! the circle they sit on

*PART, bolt, D=8, L=30, K=0.7*D
  ! hexagon head: two hexagons joined by a straight loft
  POLYGON, 0, 0, 0, D*0.9, 6
  POLYGON, 0, 0, K, D*0.9, 6
  LOFT, 1, 2, RULED
  CYL, 0, 0, -L, D/2, L           ! shank
  UNION, 3, 4
*ENDPART

*PART, washer, D=8
  TUBE, 0, 0, 0, D, D/2 + 0.2, 1.5
*ENDPART

CYL, 0, 0, -12, 60, 12
NAME, LAST, plate
*DO, i, 1, N
  X = PCD/2*cos(360*i/N)
  Y = PCD/2*sin(360*i/N)
  HOLE, plate, X, Y, 0, D + 0.5
  INST, washer, X, Y, 0, D=D
  INST, bolt, X, Y, 1.5, D=D
*ENDDO
