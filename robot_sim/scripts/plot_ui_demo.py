#!/usr/bin/env python3
"""Draw the "user drops an obstacle, robot drives around it" demo.

Input : /tmp/ui_run.csv  (x,y,yaw samples logged from /odom)
Output: results/figs/ui_obstacle_demo.png

English labels on purpose: the WSL matplotlib install has no CJK font.
"""
import math
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle

CSV = sys.argv[1] if len(sys.argv) > 1 else '/tmp/ui_run.csv'
OBS = (7.0, 2.62)
START = (6.85, 3.95)
GOAL = (7.0, 1.0)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   '..', '..', 'results', 'figs', 'ui_obstacle_demo.png')

pts = []
for line in open(CSV):
    p = line.strip().split(',')
    if len(p) == 3:
        pts.append((float(p[0]), float(p[1]), float(p[2])))

fig, ax = plt.subplots(figsize=(9, 5.2), dpi=140)
ax.set_facecolor('#f4f4f4')

# field
ax.add_patch(Rectangle((0, 0), 16, 8, facecolor='#e8e8e8', edgecolor='#666', lw=1))

# parking zones
for label, x0, x1, color in (('A', 0, 3, '#2f6fd0'), ('B', 5, 9, '#2aa845'),
                             ('C', 11, 14, '#ef8a1f')):
    ax.add_patch(Rectangle((x0, 0), x1 - x0, 2, facecolor=color, alpha=0.35,
                           edgecolor=color, lw=1))
    ax.text((x0 + x1) / 2, 1.0, label, ha='center', va='center', fontsize=11,
            fontweight='bold', color=color)

# walls / pillars / base station
for wx in (4.3, 10.0):
    ax.add_patch(Rectangle((wx - 0.05, 2.0), 0.1, 1.8, facecolor='#c9bd2c'))
for px_, py_ in ((3.5, 6.0), (9.5, 6.0), (14.5, 6.0)):
    ax.add_patch(Rectangle((px_ - 0.1, py_ - 0.1), 0.2, 0.2, facecolor='#a83232'))
ax.add_patch(Rectangle((6.4, 3.4), 1.2, 1.2, facecolor='#1a1a5e'))
ax.text(7.0, 4.0, 'base', color='white', ha='center', va='center', fontsize=8)

# obstacle placed from the panel
ax.add_patch(Rectangle((OBS[0] - 0.25, OBS[1] - 0.25), 0.5, 0.5,
                       facecolor='#f04a12', edgecolor='white', lw=1.2, zorder=5))
ax.text(OBS[0], OBS[1] + 0.42, 'obstacle (clicked on map)', ha='center',
        fontsize=8.5, color='#c03000')

# trajectory
xs = [p[0] for p in pts]
ys = [p[1] for p in pts]
ax.plot(xs, ys, '-', color='#22a0ff', lw=2.0, zorder=4, label='trajectory (/odom)')
ax.scatter([xs[0]], [ys[0]], s=60, c='#0b8f3a', zorder=6, label='start')
ax.scatter([GOAL[0]], [GOAL[1]], s=120, c='#0b3f8f', marker='*', zorder=6, label='goal (B zone)')

# min clearance
mind = min(math.hypot(x - OBS[0], y - OBS[1]) for x, y in zip(xs, ys))
gap = mind - 0.25 - 0.15
ax.text(0.4, 7.55, 'min gap body-to-obstacle: %.2f m   |   samples: %d'
        % (gap, len(pts)), fontsize=9, color='#333')

ax.set_xlim(-0.4, 16.4)
ax.set_ylim(-0.4, 8.4)
ax.set_aspect('equal')
ax.set_xlabel('x [m]')
ax.set_ylabel('y [m]')
ax.set_title('Obstacle placed from the panel before departure -> Nav2 detours around it')
ax.legend(loc='lower right', fontsize=8, framealpha=0.9)
plt.tight_layout()
os.makedirs(os.path.dirname(OUT), exist_ok=True)
plt.savefig(OUT)
print('saved', OUT)
print('min dist %.3f  gap %.3f  final err %.3f'
      % (mind, gap, math.hypot(xs[-1] - GOAL[0], ys[-1] - GOAL[1])))
