! Two rails that cross.
! expect: refused "rails meet"
LINE, 0,0,0, 0,0,40
LINE, 10,0,0, -10,0,40
LINE, -10,0,0, 10,0,40
AIRFOIL, -10,0,0, 20, 0012, 0,0,1
RAILSWEEP, 4, 3, 2, 1
