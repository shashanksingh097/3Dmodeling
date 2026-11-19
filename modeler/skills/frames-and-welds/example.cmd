! A welded table frame: a mitred top frame of square tube, four legs butted under it, a brace of angle,
! welds on every joint and the cut list.
W = 600
D = 400
H = 450
T = 30
POLYLINE, (0,0,H), (W,0,H), (W,D,H), (0,D,H), CLOSE
NAME, LAST, top_path
MEMBER, top_path, SQUARE, 30x2, MITRE, rail
HIDE, top_path
*DO, i, 0, 1
  *DO, j, 0, 1
    POLYLINE, (T/2 + i*(W - T), T/2 + j*(D - T), 0), (T/2 + i*(W - T), T/2 + j*(D - T), H - T/2)
    HIDE, LAST
    MEMBER, LAST, SQUARE, 30x2, BUTT, leg
  *ENDDO
*ENDDO
POLYLINE, (T, T/2, 120), (W - T, T/2, 120)
NAME, LAST, brace_path
MEMBER, brace_path, ANGLE, 25x25x3, BUTT, brace, 180
HIDE, brace_path
WELD, ALL, 4
CUTLIST
ASSERT, VALID(rail_1)
ASSERT, VALID(leg_1)
ASSERT, BBOX(rail_1).dx, EQ, W + T, 0.01
ASSERT, OVERLAP(leg_1, rail_1), EQ, 0
