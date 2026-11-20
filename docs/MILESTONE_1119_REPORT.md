# 里程碑报告 2026-11-19 — 软件线收尾 + 机器人线启动

> 全部为仿真数据，非真实车辆数据。

## 一、本轮完成的三件大事

### 1. WSL2 + ROS 2 Humble 打通（环境里程碑）
用户侧完成安装：WSL 3.0.5.0 / Ubuntu-22.04.5 / ROS 2 Humble（282 包装、273 可用）/ rviz2、rqt_gui、turtlesim / colcon、rosdep（清华镜像）。**关键变化：助手侧黑名单已解除，我现在可直接调用 WSL 执行命令**（`wsl.exe -d Ubuntu-22.04 -e bash -lc ...`），实测 `ROS_DISTRO=humble`、273 包、内核 6.18.58.1。

由此我又装齐了仿真依赖：`turtlebot3`、`turtlebot3_gazebo`、`gazebo_ros`（Gazebo 11.10.2 classic）、`nav2_bringup`、`nav2_bt_navigator`、`ros_gz_bridge`。**机器人线从此可以自写、自跑、自验证，不再需要用户代跑。**

### 2. 软件线收尾（R2.2 / R2.3 + 一个真 bug 修复）
- **R2.2 调度器验收**：27 用例 PASS（可复现性、权重主导、每批≤5、有效性过滤、跨区补位、打分公式、能源守门）。
- **R2.3 能源模型验收**：14 用例 PASS（移动能耗、五路独立充电、目标 SOC80%、返基站阈值、闭环可复现）。
- **修复一个真实 bug — 倍速能耗偏差**：原引擎用 `speed*dt` 扣能，未按实际里程截断，高倍速下能耗被放大（10x 时首段耗电 3.05%，实际应 0.3053%）。改为按实际位移积分后，1x/10x/60x 全部 **0.3053%**，与契约公式一致。全量回归 **72/72 PASS**。
- 详单见 `docs/R22_R23_ACCEPTANCE.md`（含第 7 节修复记录）。

### 3. R3.1 Gazebo 场景与机器人模型
- `robot_sim/worlds/campus.world`：SDF 1.6 场景，A 蓝/B 绿/C 橙三停车区（12/10/8 车位）、5 充电桩、基站台座、路障、俯视相机；坐标与 `campus_basic.yaml` 按 1:10 缩放对齐。
- `robot_sim/urdf/campus_robot.urdf.xacro`：自包含差速机器人（base_link+双轮+caster+laser），含差速驱动/IMU/激光 plugin。
- `robot_sim/launch/spawn_campus.launch.py`：gzserver/gzclient + xacro + robot_state_publisher + 延迟 spawn 到基站 (7.0,4.0,0.1)。
- **WSL 实测（助手亲自复现）**：headless 启动成功，`Successfully spawned entity [campus_robot]`，`/cmd_vel`、`/odom`、`/scan`、`/imu` 四话题齐全，无致命错误。

## 二、验证总表

| 项目 | 结果 |
|---|---|
| 全量 pytest（R1.2+R2.1+R2.2+R2.3） | **72/72 PASS** |
| 倍速能耗一致性 | 1x/10x/60x 均 0.3053%，与公式一致 |
| R3.1 Gazebo headless | spawn 成功，4 关键话题齐全，0 致命错误 |
| WSL 跨机路径读写 | `/mnt/c/.../campus-charging` 可读可写，双端同一份文件 |

## 三、跨机器协作约定
- 项目唯一目录：`C:\Users\lenovo\WorkBuddy\plan phase\campus-charging\`（WSL 视角 `/mnt/c/Users/lenovo/WorkBuddy/plan phase/campus-charging`），双端同一份文件，无需同步。
- Windows 侧：后端/前端/算法/测试（隔离 venv `C:\Users\lenovo\.workbuddy\binaries\python\envs\default`）。
- WSL 侧：ROS/Gazebo/Nav2 仿真；启动前 `source /opt/ros/humble/setup.bash`，路径含空格需加引号。
- WSL 输出 UTF-16LE，从 Windows 侧读取需用 `utf-16-le` 解码（判断第二字节是否为 0）。

## 四、下一步（按顺序）
- **R3.2 Nav2 点到点导航**：三区各≥3 次重复导航，验证定位与路径跟踪。
- **R3.3 动态路障与重规划**：绕障 + 完全阻断两组记录。
- **R5.1 Nav2 接入（含降级）**：把真实 Nav2 桥接到后端，保留 MockRobot 保底答辩。
- 可选：R4.x 前端完整页面打磨、R6.x 实体 Demo。

## 五、已知限制（诚实列出）
- 机器人在不同倍速下跑相同仿真时长，完成任务数略有差异（如 speed=1 完成 20 辆、speed=60 完成 15 辆）——状态机离散步长特性，不影响能耗正确性与单批闭环。
- 跨区补位的 `TASK_ASSIGNED` 事件 message 未标注来源分区（问题 2），待 R4/P5 一并处理。
- 机器人模型为自包含简化差速车，未用 TurtleBot3 原始 mesh（安装包仅含 `.urdf` 无 `.urdf.xacro`），保证 spawn 优先。
