! Test: the 3 mm SHELL of the lower body and the first panels cut with the panel macros.
! Run from the repository folder (it RUNs scripts/car_body.cmd first).
RUN, "scripts/car_body.cmd"     ! the finished car (for its macros), then cut two panels again under new names
COPY, tub
NAME, LAST, skin
PICK, BODY, skin
SHELL, THK
panel, hood_test, 360, -690, 500, 1240, 690, 1300, 40, 3
panel2, fender_test, 360, 255, 1262, 1300, 600, 20
LIST, BODIES
