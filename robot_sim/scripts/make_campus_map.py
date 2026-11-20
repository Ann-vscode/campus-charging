#!/usr/bin/env python3
"""R3.2 - generate the 2D occupancy map of the campus charging scene.

The map is derived from robot_sim/worlds/campus.world so the robot laser
and the costmap agree about where walls / pillars / piles are.
World frame: 16 m x 8 m, origin (0,0), 1 pixel = 0.05 m.
PGM values: 0 = occupied, 254 = free.
"""
import os

RES = 0.05
W_M, H_M = 16.0, 8.0
PAD = 0.04

# (name, centre_x, centre_y, size_x, size_y) copied from campus.world
OBSTACLES = [
    ("obstacle_wall_AB", 4.3, 2.9, 0.10, 1.80),
    ("obstacle_wall_BC", 10.0, 2.9, 0.10, 1.80),
    ("obstacle_pillar_1", 3.5, 6.0, 0.20, 0.20),
    ("obstacle_pillar_2", 9.5, 6.0, 0.20, 0.20),
    ("obstacle_pillar_3", 14.5, 6.0, 0.20, 0.20),
    ("base_station_pole", 7.0, 3.25, 0.12, 0.12),
    ("charging_pile_1", 6.0, 4.5, 0.12, 0.12),
    ("charging_pile_2", 6.2, 4.5, 0.12, 0.12),
    ("charging_pile_3", 6.4, 4.5, 0.12, 0.12),
    ("charging_pile_4", 6.6, 4.5, 0.12, 0.12),
    ("charging_pile_5", 6.8, 4.5, 0.12, 0.12),
]


def main():
    out_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "maps"))
    w_px = int(round(W_M / RES))
    h_px = int(round(H_M / RES))
    grid = [[254] * w_px for _ in range(h_px)]

    for _name, cx, cy, sx, sy in OBSTACLES:
        x0, x1 = cx - sx / 2 - PAD, cx + sx / 2 + PAD
        y0, y1 = cy - sy / 2 - PAD, cy + sy / 2 + PAD
        c0 = max(0, int(x0 / RES))
        c1 = min(w_px - 1, int(x1 / RES))
        r0 = max(0, h_px - 1 - int(y1 / RES))
        r1 = min(h_px - 1, h_px - 1 - int(y0 / RES))
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                grid[r][c] = 0

    pgm_path = os.path.join(out_dir, "campus_map.pgm")
    with open(pgm_path, "wb") as f:
        f.write(b"P5\n%d %d\n255\n" % (w_px, h_px))
        f.write(bytes(b for row in grid for b in row))

    yaml_path = os.path.join(out_dir, "campus_map.yaml")
    with open(yaml_path, "w") as f:
        f.write("image: campus_map.pgm\n")
        f.write("mode: trinary\n")
        f.write("resolution: %.3f\n" % RES)
        f.write("origin: [0.0, 0.0, 0.0]\n")
        f.write("negate: 0\n")
        f.write("occupied_thresh: 0.65\n")
        f.write("free_thresh: 0.196\n")

    occ = sum(1 for row in grid for v in row if v == 0)
    print("map: %dx%d px, %d occupied cells -> %s" % (w_px, h_px, occ, pgm_path))


if __name__ == "__main__":
    main()