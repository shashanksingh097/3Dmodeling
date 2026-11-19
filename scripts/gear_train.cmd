! Gears and fasteners (GEAR, FASTENER): a pinion driving a bigger gear on a plate, a planet
! inside a ring gear, and a rack. The 20-tooth pinion and the 30-tooth gear sit at the centre
! distance module x (20 + 30) / 2 = 50, the bigger one turned half a tooth (180/30 degrees) so
! the teeth fall into the gaps. The rack runs under the pinion, its pitch line on the pinion's
! pitch circle (0.02 lower, for a little play) and a gap (they come every 2 pi from its start) under the
! pinion's centre. Each gear has a bore and runs on a cap screw through the plate,
! with a washer under the head and a nut underneath.
BLOCK, -50, -40, -8, 210, 90, 8
NAME, LAST, plate
MATERIAL, plate, ALUMINIUM
GEAR, 0, 0, 0, 2, 20, 10, , , 8
NAME, LAST, pinion
GEAR, 50, 0, 0, 2, 30, 10, , , 8
NAME, LAST, wheel
ROTATE, wheel, 6, 50, 0, 0
GEAR, 125, 0, 0, 1, 50, 6, INTERNAL, , 62
NAME, LAST, ring
GEAR, 140, 0, 0, 1, 20, 6, , , 6
NAME, LAST, planet
GEAR, -43.982297, -20.02, 0, 2, 8, 8, RACK
NAME, LAST, rack
FASTENER, WASHER, M8, 0, 0, 10
FASTENER, CAP, M8, 0, 0, 11.6, 25
FASTENER, NUT, M8, 0, 0, -8
FASTENER, WASHER, M8, 50, 0, 10
FASTENER, CAP, M8, 50, 0, 11.6, 25
FASTENER, NUT, M8, 50, 0, -8
CLASH, pinion, wheel
CLASH, ring, planet
CLASH, rack, pinion
