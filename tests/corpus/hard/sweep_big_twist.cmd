! A flat bar twisted twice round a straight line: sections never meet.
! expect: ok volume=1200
LINE, 0,0,0, 0,0,30
RECT, 0,0,0, 20, 2
SWEEP, LAST, LAST-1, 720*t
