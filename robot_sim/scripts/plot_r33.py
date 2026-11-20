#!/usr/bin/env python3
"""R3.3 — merge the two scenario logs and plot the recorded trajectories.

Inputs : results/r33_avoid.json, results/r33_block.json
Outputs: results/r33_obstacle_trials.json, results/figs/r33_obstacle_trials.png

Run:
    python3 robot_sim/scripts/plot_r33.py
"""
import json
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
RES = os.path.join(ROOT, 'results')

ROBOT_HALF = 0.15          # conservative body half-extent for the gap metric
METRIC_RADIUS = 0.20       # radius that was subtracted when logging clearance

FIELDS = dict(
    x=(0.0, 16.0), y=(0.0, 8.0),
    zones=[('A', 0.0, 3.0, '#2f6fd0'), ('B', 5.0, 9.0, '#2aa845'), ('C', 11.0, 14.0, '#ef8a1f')],
    walls=[(4.3, 2.0, 0.1, 1.8), (10.0, 2.0, 0.1, 1.8)],
    pillars=[(3.5, 6.0), (9.5, 6.0), (14.5, 6.0)],
    base=(7.0, 4.0),
)


def load(name):
    path = os.path.join(RES, name)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def enrich(trials):
    for t in trials:
        c = t.get('min_body_clearance_m')
        if c is None:
            t['min_surface_distance_m'] = None
            t['min_body_gap_m'] = None
            t['collision'] = None
            continue
        surf = round(c + METRIC_RADIUS, 3)
        t['min_surface_distance_m'] = surf
        t['min_body_gap_m'] = round(surf - ROBOT_HALF, 3)
        t['collision'] = surf < ROBOT_HALF
    return trials


def draw_field(ax):
    fx, fy = FIELDS['x'], FIELDS['y']
    ax.add_patch(Rectangle((fx[0], fy[0]), fx[1] - fx[0], fy[1] - fy[0],
                           facecolor='#9a9a9a', edgecolor='#555555', lw=1.0, zorder=0))
    for name, x0, x1, color in FIELDS['zones']:
        ax.add_patch(Rectangle((x0, 0.0), x1 - x0, 2.0, facecolor=color,
                               edgecolor='white', alpha=0.85, lw=1.0, zorder=1))
        ax.text((x0 + x1) / 2, 1.0, name, color='white', fontsize=11,
                ha='center', va='center', weight='bold', zorder=6)
    for x, y, w, h in FIELDS['walls']:
        ax.add_patch(Rectangle((x - w / 2, y), w, h, facecolor='#d8cc3a',
                               edgecolor='#8a8018', lw=0.8, zorder=2))
    for x, y in FIELDS['pillars']:
        ax.add_patch(Rectangle((x - 0.1, y - 0.1), 0.2, 0.2, facecolor='#a83232',
                               edgecolor='#6d1f1f', lw=0.8, zorder=2))
    bx, by = FIELDS['base']
    ax.add_patch(Rectangle((bx - 0.6, by - 0.6), 1.2, 1.2, facecolor='#1a1a5e',
                           edgecolor='white', lw=1.0, zorder=3))
    ax.text(bx, by - 0.95, 'base', color='white', fontsize=9, ha='center', zorder=6)
    ax.set_xlim(fx[0] - 0.7, fx[1] + 0.7)
    ax.set_ylim(fy[0] - 0.7, fy[1] + 1.4)
    ax.set_aspect('equal')
    ax.set_xlabel('x [m]')
    ax.set_ylabel('y [m]')
    ax.grid(True, ls=':', lw=0.5, color='#dddddd')


def plot_group(ax, group, trials, title, color, obstacle_draw):
    draw_field(ax)
    obstacle_draw(ax)
    shades = ['#1f4e79', '#2f6fd0', '#6aa6e0', '#9dc4ee']
    for i, t in enumerate(trials):
        traj = t.get('trajectory') or []
        if not traj:
            continue
        xs = [p[1] for p in traj]
        ys = [p[2] for p in traj]
        line, = ax.plot(xs, ys, color=shades[i % len(shades)], lw=1.8, alpha=0.95, zorder=5,
                        label='T%d  %s  gap %s m' % (
                            i + 1,
                            'reached' if t.get('success') else 'blocked',
                            '--' if t.get('min_body_gap_m') is None else '%.2f' % t['min_body_gap_m']))
        ax.plot(xs[0], ys[0], 'o', color='#1f4e79', ms=5.5, zorder=7)
        ax.plot(xs[-1], ys[-1], 's', color='#7a4b00', ms=5, zorder=7)
    ax.legend(loc='upper right', fontsize=7.5, framealpha=0.9)
    ax.set_title(title, fontsize=11, weight='bold')


def main():
    avoid = load('r33_avoid.json')
    block = load('r33_block.json')
    if avoid:
        enrich(avoid['trials'])
    if block:
        enrich(block['trials'])

    fig, axes = plt.subplots(1, 2, figsize=(15.5, 5.6), dpi=150)

    if avoid:
        def draw_box(ax):
            ax.add_patch(Rectangle((7.0 - 0.25, 2.4 - 0.25), 0.5, 0.5,
                                   facecolor='#f04a12', edgecolor='black', lw=0.9, zorder=4))
            ax.annotate('dynamic obstacle\ninserted mid-run', xy=(7.45, 2.45),
                        fontsize=7, color='#a02000', zorder=9)
            ax.plot(7.0, 1.0, '*', color='black', ms=9, zorder=8)
            ax.annotate('goal', xy=(7.0, 0.62), fontsize=7.5, ha='center')
        plot_group(axes[0], 'avoid', avoid['trials'],
                   'Avoidance group: obstacle on the path, %d/%d reached goal'
                   % (sum(1 for t in avoid['trials'] if t.get('success')), len(avoid['trials'])),
                   '#2f6fd0', draw_box)

    if block:
        def draw_wall(ax):
            ax.add_patch(Rectangle((0.0, 2.4 - 0.15), 16.0, 0.3,
                                   facecolor='#f04a12', edgecolor='black', lw=0.9, zorder=4))
            ax.annotate('16 m blocking wall (inserted mid-run)', xy=(1.2, 2.62),
                        fontsize=7, color='#a02000', zorder=9)
            ax.plot(7.0, 1.0, '*', color='black', ms=9, zorder=8)
            ax.annotate('unreachable goal', xy=(7.0, 0.62), fontsize=7.5, ha='center')
        plot_group(axes[1], 'block', block['trials'],
                   'Blocking group: full-width wall, %d/%d reached goal'
                   % (sum(1 for t in block['trials'] if t.get('success')), len(block['trials'])),
                   '#c0392b', draw_wall)

    fig.suptitle('R3.3 dynamic obstacle + replanning (Gazebo / Nav2, simulated)',
                 fontsize=13.5, weight='bold')
    fig.tight_layout(rect=[0, 0, 1, 0.94])

    fig_dir = os.path.join(RES, 'figs')
    os.makedirs(fig_dir, exist_ok=True)
    png = os.path.join(fig_dir, 'r33_obstacle_trials.png')
    fig.savefig(png)
    print('saved -> %s' % png)

    def summary(g, kind):
        trials = g['trials']
        gaps = [t['min_body_gap_m'] for t in trials if t.get('min_body_gap_m') is not None]
        return {
            'runs': len(trials),
            'reached_goal': sum(1 for t in trials if t.get('success')),
            'success_rate': round(sum(1 for t in trials if t.get('success')) / len(trials), 3),
            'min_body_gap_m': round(min(gaps), 3) if gaps else None,
            'collisions': sum(1 for t in trials if t.get('collision')),
            'mean_replans': round(sum(t.get('replans_after_insert', 0) for t in trials) / len(trials), 1),
            'obstacle': kind,
        }

    merged = {
        'milestone': 'R3.3',
        'statement': '两组记录：绕障（可通行，车绕过并到达）/ 完全阻断（全场隔墙，车无法到达）',
        'groups': {},
    }
    if avoid:
        merged['groups']['avoid'] = {
            'goal': avoid['goal'],
            'obstacle': {'shape': 'box 0.5 x 0.5 x 0.6 m', 'pose': [7.0, 2.4]},
            'trials': avoid['trials'],
            'summary': summary(avoid, 'box 0.5x0.5 at (7.0, 2.4), inserted mid-run'),
        }
    if block:
        merged['groups']['block'] = {
            'goal': block['goal'],
            'obstacle': {'shape': 'wall 16.4 x 0.3 x 0.6 m', 'pose': [8.0, 2.4]},
            'trials': block['trials'],
            'summary': summary(block, 'full-width wall at y=2.4'),
        }

    out = os.path.join(RES, 'r33_obstacle_trials.json')
    with open(out, 'w') as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print('saved -> %s' % out)


if __name__ == '__main__':
    main()
