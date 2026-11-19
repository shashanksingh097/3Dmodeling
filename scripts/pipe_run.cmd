! Pipes and cables (ROUTE, ROUTES): a water line along a skid, bent at each corner, with a branch that
! joins it as a tee, and a cable bundle of seven wires run beside it on a tray. ROUTES lists each
! route's length, straight pieces and bends, and the total per size.
L = 600
BLOCK, -40, -60, -40, L + 80, 260, 10
NAME, LAST, skid
COLOR, skid, GREY
POLYLINE, (0,0,40), (L,0,40), (L,180,40), (L,180,240)
NAME, LAST, main_path
ROUTE, main_path, PIPE, 28x2, 50, water
POLYLINE, (L/2,0,40), (L/2,0,140), (L/2 + 120,0,140)
NAME, LAST, branch_path
ROUTE, branch_path, PIPE, 28x2, 50
BLOCK, 0, 150, -30, L - 100, 40, 4
NAME, LAST, tray
COLOR, tray, ORANGE
POLYLINE, (0,170,-20), (L - 150,170,-20), (L - 150,170,100), (L - 60, 170, 100)
NAME, LAST, cable_path
ROUTE, cable_path, CABLE, 7x4, 30
COLOR, cable_1, BLUE
HIDE, main_path
HIDE, branch_path
HIDE, cable_path
ROUTES
FIT
