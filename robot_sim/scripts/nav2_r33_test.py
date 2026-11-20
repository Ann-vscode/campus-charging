#!/usr/bin/env python3
"""R3.3 acceptance test - dynamic obstacle injection + replanning.

Two scenario groups (per project docs: "绕障 + 完全阻断两组记录"):

  avoid  : a 0.5x0.5 box is inserted on the planned path, laterally offset so
           one side stays passable; the robot is expected to detect it
           (/scan -> local+global costmap), replan and drive around it.
  block  : a full-width wall (16 m) is inserted across the field; no path
           exists from the base station to the south zones, so Nav2 must end
           in failure without the robot colliding with the wall.

Both groups record, per trial: start/end pose, status, elapsed time, number of
global plans published (/plan), path length vs straight line, minimum
body-to-obstacle clearance, and whether a collision (clearance < 0) happened.

Run (Gazebo + nav2 already up):
    python3 robot_sim/scripts/nav2_r33_test.py --mode avoid --runs 3
    python3 robot_sim/scripts/nav2_r33_test.py --mode block --runs 2
"""
import argparse
import json
import math
import os
import time

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import Odometry, Path
from gazebo_msgs.srv import SpawnEntity, DeleteEntity
from std_srvs.srv import Empty
from geometry_msgs.msg import Pose

STATUS_SUCCEEDED = 4
STATUS_ABORTED = 6
STATUS_CANCELED = 5

AVOID_BOX = (0.5, 0.5, 0.6)      # x, y, z  size of the temporary obstacle
BLOCK_WALL = (16.4, 0.3, 0.6)    # full width of the 16 m x 8 m field
ROBOT_RADIUS = 0.20              # effective body radius used for clearance


def box_clearance(px, py, ox, oy, half_x, half_y):
    """Signed surface distance between a point and an axis-aligned box."""
    dx = abs(px - ox) - half_x
    dy = abs(py - oy) - half_y
    if dx > 0 and dy > 0:
        return math.hypot(dx, dy)
    return max(dx, dy)


class R33Node(Node):
    def __init__(self):
        super().__init__('r33_obstacle_trial')
        self.pose = (float('nan'), float('nan'))
        self.plan = []
        self.plan_count = 0
        self.create_subscription(Odometry, '/odom', self.on_odom, 10)
        self.create_subscription(Path, '/plan', self.on_plan, 10)
        self.spawn_cli = self.create_client(SpawnEntity, '/spawn_entity')
        self.del_cli = self.create_client(DeleteEntity, '/delete_entity')
        self.clear_g = self.create_client(Empty, '/global_costmap/clear_entirely_global_costmap')
        self.clear_l = self.create_client(Empty, '/local_costmap/clear_entirely_local_costmap')

    def on_odom(self, msg):
        p = msg.pose.pose.position
        self.pose = (p.x, p.y)

    def on_plan(self, msg):
        pts = [(p.pose.position.x, p.pose.position.y) for p in msg.poses]
        if pts:
            self.plan = pts
            self.plan_count += 1


def sdf_for(name, size, pose_z):
    sx, sy, sz = size
    return """<?xml version="1.0"?>
<sdf version="1.6">
  <model name="%s">
    <static>true</static>
    <pose>0 0 0 0 0 0</pose>
    <link name="link">
      <visual name="visual">
        <geometry><box><size>%.3f %.3f %.3f</size></box></geometry>
        <material>
          <ambient>0.95 0.35 0.1 1</ambient>
          <diffuse>0.95 0.35 0.1 1</diffuse>
        </material>
      </visual>
      <collision name="collision">
        <geometry><box><size>%.3f %.3f %.3f</size></box></geometry>
      </collision>
    </link>
  </model>
</sdf>""" % (name, sx, sy, sz, sx, sy, sz)


def call(node, cli, req, timeout=6.0):
    fut = cli.call_async(req)
    rclpy.spin_until_future_complete(node, fut, timeout_sec=timeout)
    return fut.result() if fut.done() else None


def spawn_box(node, name, x, y, size):
    req = SpawnEntity.Request()
    req.name = name
    req.xml = sdf_for(name, size, 0.0)
    req.initial_pose = Pose()
    req.initial_pose.position.x = float(x)
    req.initial_pose.position.y = float(y)
    req.initial_pose.position.z = float(size[2] / 2.0)
    req.reference_frame = 'world'
    res = call(node, node.spawn_cli, req)
    return bool(res is not None and res.success)


def delete_box(node, name):
    req = DeleteEntity.Request()
    req.name = name
    call(node, node.del_cli, req, timeout=4.0)


def clear_costmaps(node):
    """Drop stale obstacle marks so each trial starts from a clean costmap."""
    for cli in (node.clear_g, node.clear_l):
        if cli.service_is_ready():
            call(node, cli, Empty.Request(), timeout=3.0)


def point_along_plan(node, lead, lateral):
    """Pick a point `lead` metres ahead of the robot along the current /plan."""
    px, py = node.pose
    pts = node.plan
    if len(pts) < 2:
        return None
    # nearest index to the robot
    idx = min(range(len(pts)), key=lambda i: math.hypot(pts[i][0] - px, pts[i][1] - py))
    acc = 0.0
    for i in range(idx + 1, len(pts)):
        acc += math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
        if acc >= lead:
            x, y = pts[i]
            nxt = pts[min(i + 1, len(pts) - 1)]
            ang = math.atan2(nxt[1] - pts[i - 1][1], nxt[0] - pts[i - 1][0])
            nx, ny = -math.sin(ang), math.cos(ang)   # left-hand normal
            return x + lateral * nx, y + lateral * ny, ang
    return None


def make_goal(node, x, y, yaw):
    goal = NavigateToPose.Goal()
    goal.pose.header.frame_id = 'map'
    goal.pose.header.stamp = node.get_clock().now().to_msg()
    goal.pose.pose.position.x = float(x)
    goal.pose.pose.position.y = float(y)
    goal.pose.pose.orientation.z = math.sin(yaw / 2.0)
    goal.pose.pose.orientation.w = math.cos(yaw / 2.0)
    return goal


def run_trial(node, client, mode, trial, goal, args, fixed=None):
    name = 'r33_%s_%d' % (mode, trial)
    size = AVOID_BOX if mode == 'avoid' else BLOCK_WALL
    half_x, half_y = size[0] / 2.0, size[1] / 2.0
    clear_costmaps(node)
    sx, sy = node.pose
    send = client.send_goal_async(make_goal(node, *goal))
    rclpy.spin_until_future_complete(node, send, timeout_sec=30.0)
    gh = send.result()
    if gh is None or not gh.accepted:
        return {'mode': mode, 'trial': trial, 'success': False, 'detail': 'goal rejected'}

    res_fut = gh.get_result_async()
    t0 = time.time()
    spawned = False
    spawn_pos = None
    spawn_time = None
    replans_at_spawn = None
    min_clear = float('inf')
    max_lateral = 0.0
    traj = []
    last_traj_t = 0.0
    path_len = 0.0
    last = node.pose
    last_plan_count = node.plan_count
    replan_after_spawn = 0
    timeout = args.timeout
    reason = 'timeout'

    while rclpy.ok():
        rclpy.spin_once(node, timeout_sec=0.05)
        px, py = node.pose
        if not math.isnan(px):
            path_len += math.hypot(px - last[0], py - last[1])
            last = (px, py)

        if not spawned and not math.isnan(px):
            travelled = math.hypot(px - sx, py - sy)
            if travelled >= args.trigger:
                if fixed is not None:
                    ox, oy = fixed
                elif mode == 'avoid':
                    pick = point_along_plan(node, args.lead, args.lateral)
                    if pick:
                        ox, oy, _ = pick
                    else:
                        ang = math.atan2(goal[1] - py, goal[0] - px)
                        ox = px + args.lead * math.cos(ang) - args.lateral * math.sin(ang)
                        oy = py + args.lead * math.sin(ang) + args.lateral * math.cos(ang)
                else:
                    # wall across the map, ahead of the robot on the way south
                    ox, oy = 8.0, min(py - args.lead, 2.6)
                ok = spawn_box(node, name, ox, oy, size)
                if ok:
                    spawned = True
                    spawn_pos = (ox, oy)
                    spawn_time = time.time()
                    replans_at_spawn = node.plan_count
                    print('  inserted %s at (%.2f, %.2f) after travelling %.2f m'
                          % (name, ox, oy, travelled), flush=True)

        if spawned and node.plan_count != last_plan_count:
            replan_after_spawn += node.plan_count - last_plan_count
            last_plan_count = node.plan_count

        if spawned and not math.isnan(px):
            c = box_clearance(px, py, spawn_pos[0], spawn_pos[1], half_x, half_y) - ROBOT_RADIUS
            if c < min_clear:
                min_clear = c

        if not math.isnan(px):
            # perpendicular distance from the start->goal straight line
            dx, dy = goal[0] - sx, goal[1] - sy
            seg = math.hypot(dx, dy)
            if seg > 0.5:
                lat = abs((px - sx) * dy - (py - sy) * dx) / seg
                if lat > max_lateral:
                    max_lateral = lat
            now = time.time() - t0
            if now - last_traj_t >= 0.5:
                last_traj_t = now
                traj.append([round(now, 1), round(px, 2), round(py, 2),
                             round(min_clear, 2) if min_clear != float('inf') else None])

        if res_fut.done():
            reason = 'finished'
            break
        if time.time() - t0 > timeout:
            gh.cancel_goal_async()
            reason = 'timeout'
            break

    status = None
    if res_fut.done() and res_fut.result() is not None:
        status = res_fut.result().status
    elapsed = time.time() - t0
    ex, ey = node.pose
    err = math.hypot(ex - goal[0], ey - goal[1])
    straight = math.hypot(goal[0] - sx, goal[1] - sy)

    rec = {
        'mode': mode,
        'trial': trial,
        'goal': [goal[0], goal[1]],
        'start': [round(sx, 3), round(sy, 3)],
        'end': [round(ex, 3), round(ey, 3)],
        'arrival_error_m': round(err, 3) if not math.isnan(err) else None,
        'elapsed_s': round(elapsed, 1),
        'status': status,
        'status_name': {4: 'SUCCEEDED', 5: 'CANCELED', 6: 'ABORTED'}.get(status, str(status)),
        'success': status == STATUS_SUCCEEDED,
        'detail': reason,
        'obstacle': {
            'name': name,
            'pose': [round(spawn_pos[0], 3), round(spawn_pos[1], 3)] if spawn_pos else None,
            'size_xy': [size[0], size[1]],
            'inserted': spawned,
            'insert_after_travel_m': round(math.hypot(spawn_pos[0] - sx, spawn_pos[1] - sy), 2)
            if spawn_pos else None,
        },
        'replans_after_insert': replan_after_spawn,
        'min_body_clearance_m': round(min_clear, 3) if min_clear != float('inf') else None,
        'collision': bool(min_clear < 0) if min_clear != float('inf') else None,
        'max_lateral_deviation_m': round(max_lateral, 3),
        'path_length_m': round(path_len, 2),
        'straight_line_m': round(straight, 2),
        'path_ratio': round(path_len / straight, 2) if straight > 0.5 else None,
        'trajectory': traj,
    }
    if spawned:
        delete_box(node, name)
        time.sleep(2.0)
        clear_costmaps(node)
        time.sleep(1.0)
    print(json.dumps(rec, ensure_ascii=False), flush=True)
    return rec


def goto(node, client, x, y, yaw):
    send = client.send_goal_async(make_goal(node, x, y, yaw))
    rclpy.spin_until_future_complete(node, send, timeout_sec=20.0)
    gh = send.result()
    if gh is None or not gh.accepted:
        return False
    fut = gh.get_result_async()
    t0 = time.time()
    while rclpy.ok() and not fut.done():
        rclpy.spin_once(node, timeout_sec=0.05)
        if time.time() - t0 > 140.0:
            gh.cancel_goal_async()
            return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', choices=['avoid', 'block'], required=True)
    ap.add_argument('--runs', type=int, default=3)
    ap.add_argument('--goal', default='7.0,1.0,1.5708', help='x,y,yaw of the target')
    ap.add_argument('--trigger', type=float, default=0.8, help='travel before inserting')
    ap.add_argument('--lead', type=float, default=2.2, help='insert distance ahead of robot')
    ap.add_argument('--lateral', type=float, default=0.55, help='lateral offset (avoid mode)')
    ap.add_argument('--timeout', type=float, default=120.0)
    ap.add_argument('--return-base', default='7.0,4.0,0.0')
    ap.add_argument('--obstacle', default=None, help='fixed insertion point "x,y"')
    ap.add_argument('--no-return', action='store_true')
    args = ap.parse_args()

    fixed = None
    if args.obstacle:
        fixed = tuple(float(v) for v in args.obstacle.split(','))

    gx, gy, gyaw = [float(v) for v in args.goal.split(',')]
    rx, ry, ryaw = [float(v) for v in args.return_base.split(',')]

    rclpy.init()
    node = R33Node()
    client = ActionClient(node, NavigateToPose, 'navigate_to_pose')
    if not client.wait_for_server(timeout_sec=10.0):
        print('navigate_to_pose not available')
        return
    for _ in range(5):
        rclpy.spin_once(node, timeout_sec=0.3)

    trials = []
    for i in range(1, args.runs + 1):
        print('--- %s trial %d/%d ---' % (args.mode, i, args.runs), flush=True)
        rec = run_trial(node, client, args.mode, i, (gx, gy, gyaw), args, fixed=fixed)
        trials.append(rec)
        if i < args.runs and not args.no_return:
            goto(node, client, rx, ry, ryaw)
            time.sleep(1.0)

    out_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                            '..', '..', 'results'))
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'r33_%s.json' % args.mode)
    ok = sum(1 for t in trials if t.get('success'))
    with open(out_path, 'w') as f:
        json.dump({
            'milestone': 'R3.3',
            'group': args.mode,
            'runs': args.runs,
            'goal': [gx, gy],
            'trials': trials,
            'success_rate': round(ok / len(trials), 3),
        }, f, ensure_ascii=False, indent=2)
    print('saved -> %s' % out_path)
    node.destroy_node()
    rclpy.try_shutdown()


if __name__ == '__main__':
    main()
