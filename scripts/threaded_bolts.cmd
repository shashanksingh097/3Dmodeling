! A plate held by 8 bolts and nuts with real ISO metric threads.
! One bolt part and one nut part, each placed 8 times. Change D and every
! bolt and nut is rebuilt at the new size, thread pitch included (PITCH(D)
! looks up the ISO coarse pitch). Each size is built once and copied.
! Each nut is turned so its thread lines up with its bolt's thread, so
! CONTACT finds them touching on the thread flanks, not overlapping.
D = 8            ! bolt size (M8)
L = 30           ! bolt length under the head
T = 10           ! plate thickness
A = 40           ! bolt spacing

*PART, bolt, D=8, L=30, K=0.7*D, B=2*D+6
  ! hexagon head: two hexagons joined by a straight loft
  POLYGON, 0, 0, 0, D*0.9, 6
  POLYGON, 0, 0, K, D*0.9, 6
  LOFT, 1, 2, RULED
  CYL, 0, 0, -L, D/2, L           ! shank
  UNION, 3, 4
  SEL, S, EDGE, AT, 0, D/2, -L    ! the rim at the tip
  CHAMFER, D/10
  SEL, S, FACE, AT, D/2, 0, -L/2  ! the side of the shank
  THREAD, , MIN(B, L)             ! ISO coarse, from the tip
*ENDPART

*PART, nut, D=8, M=0.8*D
  POLYGON, 0, 0, 0, D*0.9, 6
  POLYGON, 0, 0, M, D*0.9, 6
  LOFT, 1, 2, RULED
  HOLE, LAST, 0, 0, M, D - PITCH(D)          ! the tap drill
  SEL, S, FACE, AT, (D - PITCH(D))/2, 0, M/2
  THREAD                                      ! the matching inside thread
*ENDPART

! The bolt's thread groove starts at the tip chamfer (L - D/10 below the
! head), the nut's at its top face; a turn of 360 degrees moves a thread one
! pitch, and half a pitch puts the nut's ridge into the bolt's groove.
P = PITCH(D)
TURN = 360*((L - T - D/10 - P/2) % P)/P

BLOCK, -A/2 - 15, -1.5*A - 15, -T, A + 30, 3*A + 30, T
NAME, LAST, plate
*DO, i, 0, 7
  X = A*((i % 2) - 0.5)
  Y = A*(INT(i/2) - 1.5)
  HOLE, plate, X, Y, 0, D + 1
  INST, bolt, X, Y, 0, D=D, L=L
  INST, nut, X, Y, -T - 0.8*D, TURN, D=D   ! turned TURN degrees about Z
*ENDDO
