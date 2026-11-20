#!/usr/bin/env python3
"""R3.2 / R3.3 - one-click navigation panel with a clickable mini-map.

Two jobs in one window, so the whole demo needs no terminal typing:

1. 一键发目标点：七个按钮直接把 nav2 NavigateToPose 目标发出去。
2. 手动放路障：在小地图上点一下，就在那个世界坐标放一个橙色路障
   （/spawn_entity），机器人出发前或途中都可以放；点「撤销」或
   「清除全部」把路障撤掉（/delete_entity）。

小地图上那条虚线圈 = 激光雷达 3 m 量程：圈内的路障会被立刻"看见"，
规划时就会绕开；圈外的要等车开到 3 m 内才会被发现并触发重规划。

Run (inside WSL, Gazebo + nav2 already up):
    source /opt/ros/humble/setup.bash
    python3 robot_sim/scripts/goal_panel.py
"""
import math
import os
import queue
import threading
import time
import tkinter as tk

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import Odometry
from gazebo_msgs.srv import SpawnEntity, DeleteEntity
from geometry_msgs.msg import Pose

DESTINATIONS = [
    ("A 区 (蓝 12 位)", 1.50, 1.00, math.pi / 2),
    ("B 区 (绿 10 位)", 7.00, 1.00, math.pi / 2),
    ("C 区 (橙 8 位)", 12.50, 1.00, math.pi / 2),
    ("基站", 7.00, 4.00, 0.0),
    ("A 区门口", 2.00, 4.00, 0.0),
    ("C 区门口", 12.00, 4.00, 0.0),
]

STATUS_SUCCEEDED = 4
OBS_SIZE = 0.5          # m, temporary obstacle footprint
LIDAR_RANGE = 3.0       # m, must match campus_robot.urdf.xacro

BG = '#1e2430'
FG = '#ffffff'


def obstacle_sdf(name, size=OBS_SIZE, height=0.6):
    return """<?xml version="1.0"?>
<sdf version="1.6">
  <model name="%s">
    <static>true</static>
    <pose>0 0 0 0 0 0</pose>
    <link name="link">
      <visual name="visual">
        <geometry><box><size>%.2f %.2f %.2f</size></box></geometry>
        <material><ambient>0.95 0.35 0.1 1</ambient><diffuse>0.95 0.35 0.1 1</diffuse></material>
      </visual>
      <collision name="collision">
        <geometry><box><size>%.2f %.2f %.2f</size></box></geometry>
      </collision>
    </link>
  </model>
</sdf>""" % (name, size, size, height, size, size, height)


class Panel(Node):
    def __init__(self):
        super().__init__('campus_goal_panel')
        self.client = ActionClient(self, NavigateToPose, 'navigate_to_pose')
        self.spawn_cli = self.create_client(SpawnEntity, '/spawn_entity')
        self.del_cli = self.create_client(DeleteEntity, '/delete_entity')

        self.gh = None
        self.status = '待命 - 选一个目的地'
        self.pose = (0.0, 0.0, 0.0)
        self.obstacles = []          # [(name, x, y)]
        self.obs_count = 0
        self.commands = queue.Queue()

        self.create_subscription(Odometry, '/odom', self.on_odom, 10)
        self.create_timer(0.1, self.pump)

    # ---------- ROS callbacks ----------
    def on_odom(self, msg):
        p = msg.pose.pose.position
        q = msg.pose.pose.orientation
        self.pose = (p.x, p.y, 2.0 * math.atan2(q.z, q.w))

    def pump(self):
        """Run UI-thread service requests on the rclpy executor thread."""
        while True:
            try:
                cmd = self.commands.get_nowait()
            except queue.Empty:
                break
            if cmd[0] == 'spawn':
                self._spawn(*cmd[1:])
            elif cmd[0] == 'delete':
                self._delete(cmd[1])
            elif cmd[0] == 'goal':
                self._goto(*cmd[1:])

    def _spawn(self, name, x, y):
        req = SpawnEntity.Request()
        req.name = name
        req.xml = obstacle_sdf(name)
        req.initial_pose = Pose()
        req.initial_pose.position.x = float(x)
        req.initial_pose.position.y = float(y)
        req.initial_pose.position.z = 0.3
        req.reference_frame = 'world'
        fut = self.spawn_cli.call_async(req)
        fut.add_done_callback(lambda f, n=name, x=x, y=y: self._on_spawned(f, n, x, y))

    def _on_spawned(self, fut, name, x, y):
        try:
            ok = bool(fut.result() and fut.result().success)
        except Exception:
            ok = False
        if ok:
            self.obstacles.append((name, x, y))
            d = math.hypot(x - self.pose[0], y - self.pose[1])
            if d <= LIDAR_RANGE:
                self.status = '已放路障 (%.1f, %.1f)：车能直接看见，会绕开' % (x, y)
            else:
                self.status = ('已放路障 (%.1f, %.1f)：距车 %.1f m 超过雷达 3 m，'
                               '车开到 3 m 内才会发现并绕行' % (x, y, d))
        else:
            self.status = '路障没放成功（同名模型残留？先「清除全部」再试）'

    def _delete(self, name):
        req = DeleteEntity.Request()
        req.name = name
        self.del_cli.call_async(req)

    def add_obstacle(self, x, y):
        if not (0.3 <= x <= 15.7 and 0.3 <= y <= 7.7):
            self.status = '点到场外了：路障只能放在 16 m x 8 m 场地内'
            return None
        rx, ry, _ = self.pose
        if math.hypot(x - rx, y - ry) < 0.8:
            self.status = '离车太近（<0.8 m），换个位置放'
            return None
        for _, ox, oy in self.obstacles:
            if math.hypot(x - ox, y - oy) < OBS_SIZE + 0.15:
                self.status = '和已有路障重叠了，往旁边挪一点'
                return None
        self.obs_count += 1
        name = 'ui_obs_%d' % self.obs_count
        self.commands.put(('spawn', name, x, y))
        return name

    def delete_last(self):
        if not self.obstacles:
            self.status = '场上没有可撤销的路障'
            return
        name, x, y = self.obstacles.pop()
        self.commands.put(('delete', name))
        self.status = '已撤销路障 (%.1f, %.1f)' % (x, y)

    def clear_obstacles(self):
        while self.obstacles:
            name, _, _ = self.obstacles.pop()
            self.commands.put(('delete', name))
        self.status = '已清除全部路障'

    # ---------- navigation ----------
    def goto(self, x, y, yaw, label):
        if self.gh is not None:
            self.status = '上一个目标还在执行，先「取消」再下发'
            return
        if not self.client.wait_for_server(timeout_sec=3.0):
            self.status = 'navigate_to_pose 还没上线（nav2 没起来？）'
            return
        self.status = '规划中 -> %s' % label
        self.commands.put(('goal', x, y, yaw, label))

    def _goto(self, x, y, yaw, label):
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = 'map'
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = float(x)
        goal.pose.pose.position.y = float(y)
        goal.pose.pose.orientation.z = math.sin(yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(yaw / 2.0)
        self._leaps = len(self.obstacles)
        self.client.send_goal_async(goal).add_done_callback(self.on_goal_response)

    def on_goal_response(self, future):
        gh = future.result()
        if not gh or not gh.accepted:
            self.status = '目标被拒绝（目标点可能在障碍里）'
            return
        self.gh = gh
        self.status = '执行中 ...'
        gh.get_result_async().add_done_callback(self.on_result)

    def on_result(self, future):
        status = future.result().status
        if status == STATUS_SUCCEEDED:
            n = getattr(self, '_leaps', len(self.obstacles))
            self.status = ('已到达目标（场上有 %d 个路障，已避开）' % n) if n else '已到达目标'
        else:
            self.status = '失败或被取消 (status=%d)' % status
        self.gh = None

    def cancel(self):
        if self.gh is None:
            self.status = '当前没有正在执行的目标'
            return
        self.gh.cancel_goal_async()
        self.status = '已请求取消'


class MiniMap:
    """16 m x 8 m field drawn as a canvas; click = drop an obstacle."""
    SCALE = 24           # px per metre
    PAD = 8
    W = int(16 * SCALE) + 2 * PAD
    H = int(8 * SCALE) + 2 * PAD

    def __init__(self, master, panel):
        self.panel = panel
        self._last_click = 0.0
        self.canvas = tk.Canvas(master, width=self.W, height=self.H,
                                bg='#2a2f3a', highlightthickness=0)
        self.canvas.bind('<Button-1>', self.on_click)
        self.canvas.bind('<Button-3>', lambda e: panel.delete_last())

    # world <-> pixel
    def px(self, x):
        return self.PAD + x * self.SCALE

    def py(self, y):
        return self.H - self.PAD - y * self.SCALE

    def m2w(self, cx, cy):
        return ((cx - self.PAD) / float(self.SCALE),
                (self.H - self.PAD - cy) / float(self.SCALE))

    def on_click(self, event):
        # 一次物理点击偶尔会被 X 侧重复投递两次，这里按时间去抖
        now = time.monotonic()
        print('[canvas] click px=(%d,%d) dt=%.2f' % (event.x, event.y, now - self._last_click),
              flush=True)
        if now - self._last_click < 0.35:
            return
        self._last_click = now
        x, y = self.m2w(event.x, event.y)
        self.panel.add_obstacle(round(x, 2), round(y, 2))

    # ---------- drawing ----------
    def draw(self, pose, obstacles):
        c = self.canvas
        c.delete('all')
        c.create_rectangle(self.px(0), self.py(8), self.px(16), self.py(0),
                           fill='#8f8f8f', outline='#555555')
        for label, x0, x1, color in (('A', 0, 3, '#2f6fd0'), ('B', 5, 9, '#2aa845'),
                                     ('C', 11, 14, '#ef8a1f')):
            c.create_rectangle(self.px(x0), self.py(2), self.px(x1), self.py(0),
                               fill=color, outline='white')
            c.create_text(self.px((x0 + x1) / 2.0), self.py(1), text=label,
                          fill='white', font=('DejaVu Sans', 10, 'bold'))
        for wx in (4.3, 10.0):
            c.create_rectangle(self.px(wx - 0.05), self.py(3.8), self.px(wx + 0.05),
                               self.py(2.0), fill='#d8cc3a', outline='')
        for px_, py_ in ((3.5, 6.0), (9.5, 6.0), (14.5, 6.0)):
            c.create_rectangle(self.px(px_ - 0.1), self.py(py_ + 0.1),
                               self.px(px_ + 0.1), self.py(py_ - 0.1),
                               fill='#a83232', outline='')
        c.create_rectangle(self.px(6.4), self.py(4.6), self.px(7.6), self.py(3.4),
                           fill='#1a1a5e', outline='white')
        for i, color in enumerate(['#e33', '#3cf', '#3c3', '#ed2', '#a5f']):
            cx = 6.0 + 0.2 * i
            c.create_oval(self.px(cx - 0.06), self.py(4.56), self.px(cx + 0.06),
                          self.py(4.44), fill=color, outline='')

        for idx, (_, x, y) in enumerate(obstacles):
            c.create_rectangle(self.px(x - OBS_SIZE / 2), self.py(y + OBS_SIZE / 2),
                               self.px(x + OBS_SIZE / 2), self.py(y - OBS_SIZE / 2),
                               fill='#f04a12', outline='white', width=1)
            c.create_text(self.px(x), self.py(y), text=str(idx + 1), fill='white',
                          font=('DejaVu Sans', 7, 'bold'))

        # 3 m lidar ring
        rx, ry, _ = pose
        r = LIDAR_RANGE * self.SCALE
        c.create_oval(self.px(rx) - r, self.py(ry) - r, self.px(rx) + r, self.py(ry) + r,
                      outline='#7fd3ff', dash=(3, 4), width=1)
        # robot
        c.create_oval(self.px(rx) - 5, self.py(ry) - 5, self.px(rx) + 5, self.py(ry) + 5,
                      fill='#22e0ff', outline='black')


def main():
    # 单实例保护：同时开两个面板会出现两个重叠窗口、点击串到别的窗口上
    pidfile = '/tmp/goal_panel.pid'
    try:
        old = int(open(pidfile).read().strip())
        os.kill(old, 0)
        print('另一份面板已在运行 (pid=%d)，本次退出' % old, flush=True)
        return
    except Exception:
        pass
    open(pidfile, 'w').write(str(os.getpid()))

    rclpy.init()
    node = Panel()

    root = tk.Tk()
    root.title('校园充电 R3.3 - 一键导航 + 放路障')
    root.geometry('444x624+828+48')
    root.configure(bg=BG)
    root.attributes('-topmost', True)

    tk.Label(root, text='① 点地图放路障   ② 点目的地', fg=FG, bg=BG,
             font=('DejaVu Sans', 13, 'bold')).pack(pady=(10, 2))
    hint = tk.Label(root, text='放好路障再出发，车会自己绕开它（行进中也能放）',
                    fg='#9ee6a6', bg=BG, font=('DejaVu Sans', 9))
    hint.pack()
    hint2 = tk.Label(root, text='虚线圈 = 雷达 3 m：圈内立刻看见，圈外靠近才发现',
                     fg='#7fd3ff', bg=BG, font=('DejaVu Sans', 9))
    hint2.pack(pady=(0, 2))

    mm = MiniMap(root, node)
    mm.canvas.pack(pady=(6, 2))

    pose_label = tk.Label(root, text='位姿: --', fg='#8fd3ff', bg=BG,
                          font=('DejaVu Sans', 9))
    pose_label.pack(pady=(0, 4))

    obsbar = tk.Frame(root, bg=BG)
    obsbar.pack(fill='x', padx=16, pady=(0, 4))
    tk.Button(obsbar, text='撤销上一个', height=1, bg='#5a6270', fg='white', relief='flat',
              font=('DejaVu Sans', 9), command=node.delete_last).pack(side='left', expand=True,
                                                                     fill='x', padx=3)
    tk.Button(obsbar, text='清除全部路障', height=1, bg='#8a4a20', fg='white', relief='flat',
              font=('DejaVu Sans', 9), command=node.clear_obstacles).pack(side='left', expand=True,
                                                                       fill='x', padx=3)

    frame = tk.Frame(root, bg=BG)
    frame.pack(padx=14, pady=2, fill='both')
    for idx, (label, x, y, yaw) in enumerate(DESTINATIONS):
        tk.Button(frame, text=label, height=2, bg='#2f6fed', fg='white',
                  activebackground='#1b4fc0', font=('DejaVu Sans', 10, 'bold'),
                  relief='flat',
                  command=lambda l=label, x=x, y=y, ya=yaw: node.goto(x, y, ya, l)
                  ).grid(row=idx // 2, column=idx % 2, padx=4, pady=4, sticky='nsew')
    frame.grid_columnconfigure(0, weight=1)
    frame.grid_columnconfigure(1, weight=1)

    tk.Button(root, text='取消 / 停车', height=1, bg='#b3382c', fg='white', relief='flat',
              font=('DejaVu Sans', 10, 'bold'), command=node.cancel
              ).pack(fill='x', padx=18, pady=(4, 4))

    status_label = tk.Label(root, text='待命', fg='#ffe08a', bg=BG, wraplength=400,
                            justify='left', font=('DejaVu Sans', 9))
    status_label.pack(padx=14, pady=(2, 8))

    def refresh():
        px, py, pyaw = node.pose
        pose_label.config(text='位姿: x=%.2f y=%.2f yaw=%.2f  路障 %d 个'
                          % (px, py, pyaw, len(node.obstacles)))
        status_label.config(text=node.status)
        mm.draw(node.pose, node.obstacles)
        root.after(300, refresh)

    refresh()
    root.bind_all('<Button-1>',
                  lambda e: print('[click] widget=%s xy=(%d,%d) root=(%d,%d)'
                                  % (e.widget, e.x, e.y, e.x_root, e.y_root), flush=True))
    threading.Thread(target=rclpy.spin, args=(node,), daemon=True).start()

    try:
        root.mainloop()
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
