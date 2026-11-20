# robot_sim — 校园共享电动车移动集群充电仿真系统（R3.1 / R3.2 / R3.3）

> **仿真声明**：本模块所有场景、坐标、机器人、充电站、电量与遥测数据均为**仿真生成（simulated）**，不代表任何真实车辆、真实运营数据或真实校园设施。禁止将本模块输出标注为真实数据。

本目录覆盖机器人线三个阶段：**R3.1 Gazebo 场景与机器人模型**、**R3.2 Nav2 点到点导航**、**R3.3 动态路障与重规划**（含可点面板手动放路障）。基于 Ubuntu 22.04 + ROS 2 Humble + Gazebo classic 11.10.2 + WSL2。

---

## 1. 文件清单

| 文件 | 作用 |
|------|------|
| `worlds/campus.world` | SDF 1.6 场景：灰色场地地面、A/B/C 三色停车区（12/10/8 车位）、5 个充电桩、基站台座、静态路障、俯视 GUI 相机、ODE 物理 |
| `urdf/campus_robot.urdf.xacro` | 自包含简化差速机器人：base_link + 左右轮 + 万向轮 + 激光 link；含差速驱动、IMU、激光雷达插件；每个 link 均有 inertial + collision |
| `launch/spawn_campus.launch.py` | 启动 gzserver + gzclient，加载 world，运行 robot_state_publisher，把机器人 spawn 到基站 (7.0, 4.0, 0.1) |
| `scripts/make_campus_map.py` | 从 `worlds/campus.world` 的几何直接生成静态地图（不依赖 SLAM），输出 320×160 px、0.05 m/px 的 PGM |
| `maps/campus_map.pgm` / `maps/campus_map.yaml` | R3.2 静态地图（0=占据 / 254=自由），由上一脚本生成，可复现 |
| `config/nav2_campus_params.yaml` | Nav2 参数：RPP 控制器、NavFn 规划器、全局/局部 costmap（吃 `/scan`）等 |
| `launch/nav2_campus.launch.py` | 起 map_server + static `map→odom` + 官方 `navigation_launch.py`，一键拉起整套 Nav2 |
| `scripts/goal_panel.py` | tkinter 面板：**可点小地图**（左键放路障 / 右键撤销）+ 3 m 雷达虚线圈 + 6 个目的地按钮 + 取消/停车 + 实时位姿与状态（替代 rviz 拖箭头） |
| `scripts/nav2_r32_test.py` | R3.2 验收脚本：A/B/C 三区各 3 次重复导航，结果落盘 `results/r32_nav_trials.json` |
| `scripts/nav2_r33_test.py` | R3.3 验收脚本：导航途中动态插入路障（`/spawn_entity`），记录轨迹、重规划次数、最小间隙、是否碰撞；两组场景 `--mode avoid / block` |
| `scripts/plot_r33.py` | 合并两组记录为 `results/r33_obstacle_trials.json` 并画出轨迹对比图 `results/figs/r33_obstacle_trials.png` |
| `scripts/plot_ui_demo.py` | 把面板手动放路障那一次的 `/odom` 轨迹画成图 `results/figs/ui_obstacle_demo.png` |
| `README.md` | 本说明 |

---

## 2. 启动（在 WSL2 中执行）

```bash
# 路径含空格，务必加引号
cd "/mnt/c/Users/lenovo/WorkBuddy/plan phase/campus-charging"

source /opt/ros/humble/setup.bash
export TURTLEBOT3_MODEL=burger   # launch 文件内部也会设置

# 带界面（WSLg，DISPLAY=:0）
ros2 launch robot_sim/launch/spawn_campus.launch.py

# 无界面 / 仅服务端验证
ros2 launch robot_sim/launch/spawn_campus.launch.py gui:=false
```

启动后另开一个终端检查话题：

```bash
source /opt/ros/humble/setup.bash
ros2 topic list | grep -E '(cmd_vel|odom|imu|scan)'
ros2 topic echo /odom --once

# 让仿真机器人动一下（仿真指令）
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist \
  '{linear: {x: 0.2}, angular: {z: 0.0}}'
```

> 注意：手动 `pub /cmd_vel` 与 Nav2 会抢同一个速度话题，跑导航时不要发；反之跑完手动指令后要先让车停下再起 Nav2。

### 2.1 R3.2 导航（Nav2）

**启动顺序固定**：先 Gazebo 场景，等约 45 秒场景稳定，再起 Nav2（等约 28 秒生命周期节点全部 active），最后起面板。

```bash
# 终端 1：校园场景（已跑起来就不用重复）
ros2 launch robot_sim/launch/spawn_campus.launch.py

# 终端 2：Nav2（map_server + static map→odom + 官方 navigation_launch）
ros2 launch robot_sim/launch/nav2_campus.launch.py

# 终端 3：一键发目标点面板（鼠标点按钮，不需要敲命令，也不需要 rviz）
ros2 run robot_sim goal_panel.py      # 或 python3 robot_sim/scripts/goal_panel.py
```

面板上 6 个目的地按钮（与验收脚本完全一致，yaw 除基站外均为 +90°）：

| 按钮 | 世界坐标 (x, y, yaw) |
|------|----------------------|
| A 区 | (1.5, 1.0, π/2) |
| B 区 | (7.0, 1.0, π/2) |
| C 区 | (12.5, 1.0, π/2) |
| 基站 | (7.0, 4.0, 0.0) |
| A 区门口 | (2.0, 4.0, π/2) |
| C 区门口 | (12.0, 4.0, π/2) |

命令行等价方式（不点面板时）：

```bash
ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose \
  "{pose: {header: {frame_id: map}, pose: {position: {x: 1.5, y: 1.0}, orientation: {z: 0.707, w: 0.707}}}}"
```

检查 Nav2 是否健康（六个节点都应为 `active`）：

```bash
for n in map_server planner_server controller_server bt_navigator behavior_server velocity_smoother; do
  ros2 lifecycle get /$n
done
```

### 2.2 R3.3 动态路障与重规划（验收用）

两个场景组都用 `/spawn_entity` 在**机器人行驶途中**插入路障，再用 `/delete_entity` 撤除，全程不需要人工点击 Gazebo 的 Insert：

```bash
# 组 1 绕障：0.5×0.5 m 橙色方块插在 (7.0, 2.4)，目标 B 区 (7.0, 1.0)，3 次
python3 robot_sim/scripts/nav2_r33_test.py --mode avoid --runs 3 \
  --goal 7.0,1.0,1.5708 --obstacle 7.0,2.4 --trigger 0.8 --timeout 100

# 组 2 完全阻断：16.4×0.3 m 隔墙插在 y=2.4 贯穿全场，目标 B 区，2 次
python3 robot_sim/scripts/nav2_r33_test.py --mode block --runs 2 \
  --goal 7.0,1.0,1.5708 --obstacle 8.0,2.4 --trigger 0.8 --timeout 90

# 汇总 + 出图
python3 robot_sim/scripts/plot_r33.py
```

验收结论（2026-11-20 实测，详见 `results/r33_obstacle_trials.json`）：

| 组 | 次数 | 到达目标 | 最小体表间隙 | 碰撞 | 平均重规划 | 结论 |
|---|---|---|---|---|---|---|
| 绕障 avoid | 3 | **3/3** | 0.08 m | 0 | 34.7 次 | 检测→重规划→绕行→到达 |
| 完全阻断 block | 2 | **0/2** | 0.16 m | 0 | 88.5 次 | 无可行路径，90 s 窗口内被挡在北侧 |

> `--trigger 0.8` 表示机器人先走 0.8 m（已经离开基站、Nav2 正在跟踪路径）后才放入路障，这样记录里才有"先有路径、再被打断"的证据；`replans_after_insert` 统计插入之后 `/plan` 的更新次数。

### 2.3 可点面板：手动放路障（演示 / 看得见的绕障）

脚本 `robot_sim/scripts/goal_panel.py`（窗口标题 `校园充电 R3.3 - 一键导航 + 放路障`）把"放路障"做成鼠标操作，全程不用敲命令：

1. 小地图上**左键点一下** = 在那个世界坐标放一个 0.5×0.5×0.6 m 橙色方块（`/spawn_entity`，实体名 `ui_obs_<n>`）；
2. 再点 6 个目的地按钮之一发目标 → 车规划时就把方块当障碍绕开；
3. 右键 /「撤销上一个」撤掉最近一个，「清除全部路障」清场。

| 项 | 说明 |
|---|---|
| 小地图 | 16 m × 8 m 场地，24 px/m；画出 A/B/C 三区、黄墙、红柱、基站方块、5 根充电桩 |
| 蓝色虚线圈 | 激光雷达量程 3 m（与 `campus_robot.urdf.xacro` 的 `max 3.0` 对齐） |
| 圈内放 | 立刻进 costmap，出发即绕开 |
| 圈外放 | 超过 3 m 看不见，车开到 3 m 内才被 `/scan` 发现并触发重规划 |
| 放置校验 | 场地内 0.3 ≤ x ≤ 15.7、0.3 ≤ y ≤ 7.7；距车 ≥ 0.8 m；与已有路障 ≥ 0.65 m |
| 单实例 | `/tmp/goal_panel.pid` 锁，重复启动会直接退出（两个重叠窗口会让点击串窗口） |
| 线程模型 | Tk 回调只往 `queue` 塞命令，`create_timer(0.1, pump)` 在 rclpy 线程发服务/动作，避免 Tk 与 ROS 抢线程 |

实测（2026-11-20，`results/figs/ui_obstacle_demo.gif` / `.png`）：车在基站 (6.85, 3.95)，小地图点 (7.0, 2.62) 放路障，再点「B 区」→ 车向左绕到 x≈5 附近再折回，终点误差 0.182 m，最小体表间隙 0.93 m，路径 5.1 m（直线 2.9 m），面板状态显示"已到达目标（场上有 1 个路障，已避开）"。

```bash
# 面板（Gazebo + nav2 起来后）
bash /home/ubuntu/run_goal_panel.sh      # 日志 /tmp/panel.log
# 复盘出图（需要当时录的 /odom 轨迹 csv）
python3 robot_sim/scripts/plot_ui_demo.py /tmp/ui_run.csv
```

---

## 3. Windows ↔ WSL 路径映射

| 环境 | 路径 |
|------|------|
| Windows | `C:\Users\lenovo\WorkBuddy\plan phase\campus-charging\robot_sim\` |
| WSL2 | `/mnt/c/Users/lenovo/WorkBuddy/plan phase/campus-charging/robot_sim/` |

> 注意路径包含空格，所有 shell 命令都要用引号包裹。源码在 Windows 侧用 Write 编辑，在 WSL 侧直接读取运行，两侧同一份文件。

---

## 4. 坐标规格（场景 → Gazebo，缩放 1:10）

| 对象 | 场景坐标 | Gazebo 世界坐标 |
|------|----------|-----------------|
| 基站 | (70, 40) | (7.0, 4.0) |
| A 停车区 | x[0,30] y[0,20] | x[0,3] y[0,2]，12 车位（蓝色） |
| B 停车区 | x[50,90] y[0,20] | x[5,9] y[0,2]，10 车位（绿色） |
| C 停车区 | x[110,140] y[0,20] | x[11,14] y[0,2]，8 车位（橙色） |
| 5 个充电桩 | 基站旁一排 | x = 6.0/6.2/6.4/6.6/6.8, y = 4.5（颜色 1~5 区分编号） |
| 场地地面 | — | 约 16 m × 8 m，中心 (8, 4) |

充电桩编号用**颜色 + model 名称**（`charging_pile_1`~`charging_pile_5`）标识，SDF 1.6 无原生文本几何。

机器人初始 spawn 位姿：位置 (7.0, 4.0, 0.1)，朝向 0（基站位置，**仿真**）。

---

## 5. 关键 ROS 话题（均为仿真）

| 话题 | 类型 | 来源 |
|------|------|------|
| `/cmd_vel` | `geometry_msgs/Twist` | 差速驱动插件订阅（速度指令） |
| `/odom` | `nav_msgs/Odometry` | 差速驱动插件发布 |
| `/imu` | `sensor_msgs/Imu` | IMU 传感器插件 |
| `/scan` | `sensor_msgs/LaserScan` | 激光雷达插件 |
| `/robot_description` | `std_msgs/String` | robot_state_publisher / xacro |
| `/tf`, `/tf_static` | `tf2_msgs/TFMessage` | robot_state_publisher |

---

## 6. 已实现 / 未实现

**已实现（R3.1）**
- [x] Gazebo 场景与三色停车区、充电桩、基站、路障、俯视相机
- [x] 自包含差速机器人模型（含碰撞/惯性，避免 Gazebo 报错）
- [x] 差速驱动 `/cmd_vel` → `/odom`、IMU、激光雷达插件
- [x] ROS 2 launch 一键启动（Gazebo server/client + spawn）
- [x] WSL 实测：world/urdf XML 校验、Gazebo 加载、机器人 spawn、话题检查（结果见任务报告）

**已实现（R3.2 Nav2 点到点导航）**
- [x] 静态地图 `campus_map.pgm`（16 m×8 m 场地，0.05 m/px，从 world 几何生成，可复现）
- [x] 全局/局部 costmap 吃 `/scan`，NavFn 规划器 + Regulated Pure Pursuit 控制器（限速 0.22 m/s）
- [x] 一键发目标点面板（6 目的地 + 取消/停车 + 实时位姿与状态），鼠标操作，无需敲命令
- [x] 验收脚本：A/B/C 三区各 3 次重复导航，**9/9 成功**，成功率 1.0，最大到达误差 0.191 m（明细见 `results/r32_nav_trials.json`）
- [x] 修复机器人碰撞盒贴地导致的速度衰减/自偏航 bug（原文件备份为 `campus_robot.urdf.xacro.bak`）

**已实现（R3.3 动态路障与重规划）**
- [x] 运行期动态插入/撤除路障（`/spawn_entity` + `/delete_entity`，不用手工点 Insert），插入时机可配置（默认车先走 0.8 m）
- [x] 绕障组 3/3 到达，最小体表间隙 0.08 m，**0 碰撞**，插入后平均 34.7 次全局重规划
- [x] 完全阻断组 0/2 到达（16.4 m 隔墙），规划器持续 `failed to create plan`，90 s 观察窗口内车辆被挡在北侧、**0 碰撞**
- [x] 轨迹/间隙/重规划次数自动记录，一键出图 `results/figs/r33_obstacle_trials.png`

**未实现（后续任务）**
- [ ] **真 SLAM / 重定位**：R3.2 用仿真里程计 + 静态 `map→odom` 恒等变换定位，未启用 AMCL（见第 7 节）
- [ ] **真·动态避障**：R3.3 的路障是"中途静态插入"，不是会移动的行人/车辆；移动障碍追踪属后续增强
- [ ] 停车场车位状态与充电桩状态接入后端契约（仿真数据发布）
- [ ] 与 `backend/` 的 MQTT / REST 联调
- [ ] A/B 两线（机器人线 + 后端线）联调，见 R5.1

---

## 7. 已知问题 / 限制

- 机器人为**自包含简化模型**（长方体 + 圆柱轮），未使用 TurtleBot3 burger 的精细网格；原因是 ROS 安装中 `turtlebot3_description` 只提供 `turtlebot3_burger.urdf`，并无任务描述中的 `turtlebot3_burger.urdf.xacro`，优先保证可成功 spawn。
- 充电桩编号以颜色和 model 名标识，Gazebo 11 的 SDF 1.6 无原生文字标签。
- 本环境未安装 `libgazebo_ros_laser.so`，激光雷达改用 ROS 2 Humble 自带的 `libgazebo_ros_ray_sensor.so`，发布 `/scan`（`sensor_msgs/LaserScan`，约 10 Hz）。
- `gazebo_ros` 自动计算的 `GAZEBO_MODEL_PATH` 不含系统内置模型，launch 中显式加入 `/usr/share/gazebo-11/models` 并禁用在线模型库，否则 `model://ground_plane` / `model://sun` 会卡在联网查询导致 `/spawn_entity` 迟迟不可用。
- launch 通过 TimerAction 延迟 5 秒 spawn；世界加载在本机可能额外耗时约 20 秒，spawn 完成前 `/cmd_vel`、`/odom` 等话题不会注册，属正常现象。
- WSL 无音频设备时 gzserver 会打印 ALSA `Unknown PCM default` 警告，不影响仿真；WSLg（`DISPLAY=:0`）下 GUI 模式已实测可启动。
- 所有数据均为仿真数据；R3.3 动态避障与真 SLAM 尚未实现，请勿用于真实导航或真实调度结论。
- **R3.2 的定位口径（对官方 bringup 的有意偏离）**：不启用 AMCL，改用仿真里程计（diff_drive 插件发布 `odom→base_link`）+ 静态 `map→odom` 恒等变换。理由是仿真里程计无漂移、演示不可崩；代价是**不能对外宣称"SLAM 建图/重定位"**。对外表述应为"自主点到点导航 + 里程计定位"，真 SLAM/重定位留给 R3.3+。
- **R3.2 的避障口径**：只做"静态地图 + costmap 命中即重规划"，不具备"动态障碍物实时绕行"的演示能力，该口径属 R3.3。
- `regulated pure pursuit` 的 `use_collision_detection` 已关闭（`false`）：开启时在 0.22 m/s 低速下会误报 `collision ahead` 导致目标 ABORTED；避障仍由 costmap 膨胀层承担。
- 中断导航测试会残留 `/cmd_vel` 把车开出场外；重跑前需 kill gzserver/gzclient/nav2/残余 `ros2 topic pub`，再按"场景 → Nav2 → 面板"顺序重启。
- 面板/滑杆类手动速度工具不得与 Nav2 同时存在，否则抢 `/cmd_vel`。
- **R3.3 的间隙口径**：绕障时规划器沿膨胀层边界走，机器人中心到障碍表面的最近距离 ≈ `inflation_radius 0.28`；按车体半宽 0.15 m 计，实体间隙 ≈ 0.08~0.19 m。这是参数决定的"最近通过距离"，不是撞上了——`collision` 字段另算，两组均为 false。
- **R3.3 的阻断口径**：完全阻断组的"未到达"是 90 s 观察窗口内判定（脚本取消目标），日志里 `GridBased: failed to create plan` 反复出现，可作规划器无解的证据；不要把它说成"行为树自动 ABORT"。
- 反复插入同名路障时 `/spawn_entity` 可能返回失败（残留同名实体未清），脚本会记 `inserted: false` 并在下一轮 `clear_costmaps`；此时该次记录无效，需要重跑。
- 轨迹图用 matplotlib（WSL 侧 3.5.1），因该环境无 CJK 字体，图内文字为英文；中文说明见 `docs/` 与本文档。

---

> 任务号：R3.1 + R3.2　|　归属：机器人仿真 agent　|　允许改动范围：仅 `robot_sim/`
