#!/usr/bin/env python3
"""R3.2 acceptance test - repeat point-to-point navigation 3 times per zone.

Each trial sends one nav2 NavigateToPose goal, records the start `pose,
the arrival error and the wall-clock duration, then writes a JSON log that
can be quoted in the milestone report.

Run (Gazebo + nav2 already up):
    python3 robot_sim/scripts/nav2_r32_test.py
"""
import json
import math
import os
import time

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import Odometry

ZONES = [
    ("A 区", 1.50, 1.00, math.pi / 2),
    ("B 区", 7.00, 1.00, math.pi / 2),
    ("C 区", 12.50, 1.00, math.pi / 2),
]
RUNS_PER_ZONE = 3
STATUS_SUCCEEDED = 4


class TrialNode(Node):
    def __init__(self):
        super().__init__('r32_nav_trial')
        self.odom_xy = (float('nan'), float('nan'))
        self.create_subscription(Odometry, '/odom', self.on_odom, 10)

    def on_odom(self, msg):
        p = msg.pose.pose.position
        self.odom_xy = (p.x, p.y)


def navigate(node, client, x, y, yaw, timeout=150.0):
    goal = NavigateToPose.Goal()
    goal.pose.header.frame_id = 'map'
    goal.pose.header.stamp = node.get_clock().now().to_msg()
    goal.pose.pose.position.x = float(x)
    goal.pose.pose.position.y = float(y)
    goal.pose.pose.orientation.z = math.sin(yaw / 2.0)
    goal.pose.pose.orientation.w = math.cos(yaw / 2.0)

    send = client.send_goal_async(goal)
    rclpy.spin_until_future_complete(node, send, timeout_sec=30.0)
    gh = send.result()
    if gh is None or not gh.accepted:
        return False, 'rejected', 0.0

    t0 = time.time()
    res = gh.get_result_async()
    rclpy.spin_until_future_complete(node, res, timeout_sec=timeout)
    elapsed = time.time() - t0
    if res.result() is None:
        gh.cancel_goal_async()
        return False, 'timeout', elapsed
    status = res.result().status
    return status == STATUS_SUCCEEDED, 'status=%d' % status, elapsed


def main():
    rclpy.init()
    node = TrialNode()
    client = ActionClient(node, NavigateToPose, 'navigate_to_pose')
    if not client.wait_for_server(timeout_sec=10.0):
        print('navigate_to_pose not available')
        return

    for _ in range(5):
        rclpy.spin_once(node, timeout_sec=0.3)

    trials = []
    for run in range(1, RUNS_PER_ZONE + 1):
        for name, x, y, yaw in ZONES:
            sx, sy = node.odom_xy
            ok, detail, elapsed = navigate(node, client, x, y, yaw)
            rclpy.spin_once(node, timeout_sec=0.2)
            ex, ey = node.odom_xy
            err = math.hypot(ex - x, ey - y)
            rec = {
                'run': run,
                'zone': name,
                'goal': [x, y],
                'start': [round(sx, 3), round(sy, 3)],
                'end': [round(ex, 3), round(ey, 3)],
                'arrival_error_m': round(err, 3),
                'elapsed_s': round(elapsed, 1),
                'success': bool(ok),
                'detail': detail,
            }
            trials.append(rec)
            print(json.dumps(rec, ensure_ascii=False), flush=True)

    out_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                            '..', '..', 'results'))
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'r32_nav_trials.json')
    with open(out_path, 'w') as f:
        json.dump({
            'milestone': 'R3.2',
            'runs_per_zone': RUNS_PER_ZONE,
            'trials': trials,
            'success_rate': round(sum(1 for t in trials if t['success']) / len(trials), 3),
            'max_arrival_error_m': round(max(t['arrival_error_m'] for t in trials), 3),
        }, f, ensure_ascii=False, indent=2)
    print('saved -> %s' % out_path)
    node.destroy_node()
    rclpy.try_shutdown()


if __name__ == '__main__':
    main()