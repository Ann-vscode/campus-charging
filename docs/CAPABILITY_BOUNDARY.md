# 能力边界说明 — 我能直接操控什么 / 需要你做什么

> 背景：用户询问"国内替代 agent 你是否能直接操控"以及"能否直接参考 GitHub 开源代码二次开发"。
> 本文用实测结论明确边界，避免协作误解。日期：2026-11-18。

## 一、三类"agent/工具"的真实关系

| 类别 | 具体对象 | 我能否直接操控 | 当前状态 |
|---|---|---|---|
| **A. 内置子代理** | WorkBuddy 的 general-purpose 子代理 | ✅ 能：我给 prompt、并行启动、收结果、验收 | **已用**：上一轮 3 个（契约线/场景线/工程线） |
| **B. 内置能力/工具** | 联网抓取、git clone、读写文件、跑脚本、图像/视频生成、表格/文档处理等 | ✅ 能：直接调用 | 已用（WebFetch 查 GitHub、git clone 实测，见第三节） |
| **C. 外部商业 agent** | 通义灵码、CodeGeeX、豆包 MarsCode、Claude Code、Codex、v0、Copilot、Kimi API | ❌ **不能**：当前环境没有连接它们的工具/授权 | **未用**：上一轮写进报告的只是"推荐清单"，不是已接入 |

### 关键澄清（重要）
上一轮执行报告里的"国内替代"清单是**给你选型的建议**，不是我已经接通的开关。我**没有**调用过通义灵码/CodeGeeX/豆包 MarsCode/Kimi API，也无法直接向它们派活或收回结果。

## 二、后续正式开工时，C 类工具怎么用？三种方式

1. **你侧使用，结果回灌仓库（最省事、推荐）**
   你在自己的 IDE 里装通义灵码/CodeGeeX/MarsCode，按 `docs/task_cards/` 的任务卡干活，代码提交到同一个 `campus-charging/` 仓库。我从仓库读取、审查、集成。→ 你不需要把结果"贴给我"，**仓库就是交接面**。

2. **配成 MCP / API 让我直接调（进阶）**
   若某个工具提供 MCP server 或开放 API（如 Kimi API），把凭据配置好并接入后，我可以直接调用它。当前**尚未配置**，需要你提供凭据并同意接入。

3. **继续用 A 类内置子代理（零配置）**
   我不依赖任何外部工具，直接用内置子代理按任务卡把代码写出来、跑测试、验收。三条线都可用这种方式推进。→ 这是当前**开箱即用**的路径。

> 结论：你**不必**先把任务布置给外部 agent 再把结果给我。要么直接用我（A 类，现在就能开工），要么你用 C 类工具并把代码提交到仓库我从仓库接手。仓库是唯一事实来源，两种方式都能汇合。

## 三、GitHub 开源代码：实测结论

### 我能做什么
- ✅ 联网检索 / 抓取 GitHub 页面与 README（已实测：`WebFetch` 成功读取 `ros-navigation/navigation2` 主页）
- ✅ `git clone` 把仓库拉到本地工作区（已实测：见下）
- ✅ 阅读源码、提取可复用模块、按项目需要做二次开发与适配
- ✅ 检查许可证与版本，规避合规/依赖风险

### 实测证据（2026-11-18）
1. **抓取验证**：读取了 `ros-navigation/navigation2` GitHub 主页，确认仓库存在、持续维护（覆盖 humble/jazzy/lyrical 多发行版），**`nav2_docking` 目录及 `nav2_docking_core/bt` 组件确实存在**——印证了方案里"可用 Nav2 docking 做自动对接仿真参考"的判断。许可证正文需进一步打开 LICENSE 确认（方案已提示 nav2_docking 为 Apache-2.0）。
2. **克隆验证**：`git clone --depth 1 https://github.com/eclipse-paho/paho.mqtt.python.git` 到 `campus-charging/refs/paho.mqtt.python`，已落盘 24 个条目（含 `src/`、`examples/`、`tests/`、`LICENSE.txt`、`.git`）——这是车辆遥测 MQTT 上报要用的库，可直接二次开发。

### 环境小坑（已绕过，记录备查）
- 本机 bash shim 缺少 `ls/head` 等 coreutils，但 `git` 与绝对路径的 python 可用 → 用 python 做文件检查。
- PowerShell 的 stdout 在此环境会被吞 → 命令照常执行，但用 python/bash 取输出更可靠。

### 复用的边界与注意
- **能读能改能跑**：Python/JS 类库（Paho、FastAPI、ECharts 等）我可本地跑通验证。
- **能读能改但未必能在本机跑**：ROS 2 / Gazebo / Nav2 依赖 Linux + 特定发行版，这台 Windows 机器上通常无法直接运行仿真；但我仍可**读源码、写适配层、生成配置**，把机器人线代码准备好，等你侧 ROS 环境验证。
- **许可证**：复用前逐个检查（Nav2 是多许可证仓库，nav2_docking 子目录 Apache-2.0；Paho 为 EPL/EDL 双许可）。
- **版本一致性**：TurtleBot3 / ros_gz / Gazebo / Nav2 必须同一 ROS 2 发行版，不要混克隆 main 分支编译。

## 四、建议的下一步
- 想要"零配置马上开工"：直接说"开始 R1.2"，我用内置子代理写出后端 Mock 闭环，并从 `refs/paho.mqtt.python` 参考 MQTT 用法。
- 想用外部 agent：按第二节方式 1，你侧用工具、代码提交仓库，我从仓库接手审查集成。
- 想扩大复用：告诉我优先哪个仓库（Nav2 / TurtleBot3 / ECharts 等），我去 clone 到 `refs/` 并产出"可复用模块清单 + 二次开发改造点"。
