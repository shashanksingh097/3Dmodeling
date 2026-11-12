! A pipe round a closed trefoil knot: a closed solid with no caps inside.
! expect: ok volume=8800
CURVE, PARAM, 8*(sin(t) + 2*sin(2*t)), 8*(cos(t) - 2*cos(2*t)), -8*sin(3*t), 0, 360, 180
PIPE, LAST, 3.5
