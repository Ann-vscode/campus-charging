# 软件线交付报告 — R1.2 后端 + R1.3 前端（P1 最小闭环）

> 执行日期：2026-11-18｜模式：主代理写后端 + 内置子代理写前端，双线并行 + 目录隔离
> 结论：**P1 最小闭环完成**。后端 pytest 14/14 PASS，前端 tsc + vite build PASS，HTTP/WS 契约验证通过。

---

## 一、交付内容

### R1.2 后端 Mock 闭环（主代理）
| 文件 | 职责 |
|---|---|
| `backend/config.py` | 场景 YAML 加载（数据驱动，改配置不改代码） |
| `backend/scheduler.py` | 调度打分（0.35/0.20/0.25/0.20）+ 跨区补位 + 能源估算 |
| `backend/engine.py` | 仿真时钟 + MockRobot 状态机 + 五路独立充电 + 事件日志 |
| `backend/main.py` | 12 个 HTTP 端点 + WS `/ws` + 统一信封 + 错误码 |
| `backend/README.md` | 启动/验证/已知问题 |
| `tests/conftest.py` | pytest 路径配置 |
| `tests/test_r12_mock.py` | 14 项自动化测试 |

### R1.3 前端最小闭环（子代理）
`frontend/` 共 17 文件：React 18 + TypeScript + Vite 5；组件 CampusMap / TaskPanel / ChargeChannels / ControlBar / EventLog；数据层 api.ts / ws.ts / useSimulation.ts。Mock 模式默认开启，点击"启动系统"自动演示完整流程。

---

## 二、验证结果（全部实测）

| 验证项 | 结果 |
|---|---|
| 后端 pytest | **14/14 PASS**（场景加载、可复现调度、有效车过滤、能源公式、控制状态机、自动完成两批、五路充电、障碍重规划、WS 帧、快照契约） |
| HTTP 端点 | 12 个全部按契约；错误码 409/4001、400/4005、503/5001、404/4007 正确 |
| 仿真闭环 | 24 辆有效车各充一次、5 批、含返基站补能；机器人 SOC 14.1%→补能→75.2% |
| 车辆轮转 | 12 帧覆盖全部 30 辆 |
| 前端构建 | `tsc --noEmit && vite build` PASS，40 模块，dist 165KB |
| 依赖隔离 | Python 用 `~/.workbuddy/binaries/python/envs/default` venv；前端 node_modules 在 frontend/ |

---

## 三、过程中发现并修复的 4 个真实缺陷

1. **重复派单（严重）**：初版调度读静态 `scene.vehicles`，充满电车辆被无限重复派单（B 区 5 车重复 313 次 / 1565 任务）。重构 `scheduler` 接受动态 `StateView`，引擎传运行时车辆状态；修复后 24 辆各充一次，并加回归测试。**教训：配置(静态)与运行时状态(动态)必须分离。**
2. **HTTP 错误码类型错**：engine 返回错误名字符串（如 `"INVALID_STATE"`）而非数字码，导致 HTTP 400 而非 409。统一改为数字错误码，契约对齐。
3. **WS 车辆轮转失效**：轮转依赖 `tick_no`，直接调 `frame()` 时不推进。改用独立 `_frame_seq`。
4. **前端 TS 类型错**：`CampusMap` 用 `obstacle.r`，类型为 `radius`。修正后构建通过。

---

## 四、环境限制与绕行（诚实记录）

- **pip 装包慢**：最新版 FastAPI 触发 pydantic 版本回溯；改固定版本（fastapi 0.115.6 / pydantic 2.10.4 等）后成功。
- **aiohttp 装不上**：镜像缺 yarl；R1.2 不需要 aiohttp，已去除。
- **bash shim 缺 coreutils**（ls/head/tail）：安装命令不能用管道；用绝对路径 python 取输出。
- **PowerShell stdout 被吞**：命令照常执行但取不到输出，改用 python/bash。
- **npm 调用**：bash 下 npm 报 `env: bash not found`；用 managed node 绝对路径调 npm-cli.js + Python subprocess 指定 cwd 解决。
- **WSL 被沙箱拉黑**：`wsl.exe` 在 Program Blacklist，用户侧需自行移除并安装 ROS 2 Humble；本轮软件线不依赖 ROS。
- **后台 uvicorn 进程被环境回收**：Popen 子进程随 shell 退出终止；真实用户手动启动不受影响，HTTP/WS 已用 TestClient 在进程内完整验证。

---

## 五、下一步
- P1 已完成，可进入 **R2.1 车辆遥测模拟器**（Paho MQTT，参考已 clone 的 `refs/paho.mqtt.python`）与 **R3.1 Gazebo 场景**（需 ROS 环境）。
- 前端真实后端模式：设 `VITE_USE_MOCK=false`，联调时把后端地址指到 uvicorn。
