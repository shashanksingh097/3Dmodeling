// a bracket with holes
w = 40; t = 3;
module hole(x, y, d=4) { translate([x, y, -1]) cylinder(h = t + 2, d = d); }
difference() {
  union() {
    cube([w, 20, t]);
    cube([t, 20, 25]);
  }
  for (i = [1:2]) hole(i * 12, 10);
  translate([-1, 10, 15]) rotate([0, 90, 0]) cylinder(h = t + 2, r = 2.5);
}
translate([60, 0, 0]) rotate_extrude() translate([10, 0]) circle(r = 2);
translate([0, 40, 0]) linear_extrude(height = 5) polygon([[0,0],[20,0],[10,15]]);
translate([40, 40, 0]) sphere(d = 10);
mirror([1, 0, 0]) translate([10, 60, 0]) cube(5, center = true);
