# 校园共享电动车移动集群充电仿真系统

> 仿真课程项目 · 多 agent 并行协作 · 含答辩演示
> 本仓库为**仿真环境**，所有车辆、电量、位置与运营数据均为程序生成的**仿真数据**，不接入任何真实车辆或真实运营系统。

---

## 一、项目定位

本项目面向校园场景，仿真一批共享电动车组成的**移动集群**在有限充电桩资源下的充电调度过程。系统通过三类角色协同：车辆仿真产生电量消耗与充电需求、机器人仿真负责移动充电/调度作业、后端平台汇聚遥测并对外提供监控与调度接口，前端看板实时呈现集群状态。

目标是：在**不接触真实车辆**的前提下，验证充电调度策略的可行性与效果。

协作规则见 [AGENTS.md](./AGENTS.md)；任务总览与状态见 [docs/progress.md](./docs/progress.md)。

---

## 二、仿真边界声明

**范围内（IN SCOPE）**

- 车辆电量随行驶里程衰减、低电量触发充电请求的仿真。
- 充电桩占用、排队、调度策略的仿真。
- 移动充电机器人（robot_sim）的路径与作业仿真。
- 遥测数据生成、上报、存储与可视化。
- 调度策略效果的统计与结果输出。

**范围外（OUT OF SCOPE）**

- 接入真实车辆、真实地图、真实支付或真实用户数据。
- 任何面向生产环境的安全、支付、合规能力。
- 真实硬件在环控制（hardware/ 仅保留接口占位与接入约定）。

> 重要：任何数据、截图、演示均为**仿真数据**，不得标注或声称来自真实运营车辆 / 真实校园运营方。

---

## 三、目录结构

```text
campus-charging/
├── AGENTS.md                  # 所有 agent 共同开发规则（单一事实来源入口）
├── README.md                  # 本文件：项目总览与快速启动
├── docker-compose.yml         # 本地 Mosquitto MQTT Broker（仿真环境）
├── docs/                      # 项目文档
│   ├── project_scope.md       # 项目范围与仿真边界（开工必读 ①）
│   └── progress.md            # 进度看板 R0.1→R8.2
├── contracts/                 # 冻结契约（单一事实来源，禁止直接修改）
│   ├── api.md                 # REST / MQTT 主题与消息契约（开工必读 ②）
│   └── telemetry.json         # 遥测数据 schema（开工必读 ③）
├── backend/                   # 后端服务：遥测接入、存储、REST API（后端轨）
├── vehicle_sim/               # 车辆仿真：电量/位置/充电需求（车辆轨）
├── robot_sim/                 # 机器人仿真：移动充电/调度作业（机器人轨）
├── frontend/                  # 前端看板：实时监控与可视化
├── hardware/                  # 硬件接入接口占位（仅约定，不在环）
├── tests/                     # 跨模块集成测试与自动化测试
├── results/                   # 仿真结果、图表与报告输出
└── .github/workflows/ci.yml   # CI 门禁：契约校验/测试/lint/构建
```

各模块的职责、启动方式与约束详见其目录内 `README.md`。

---

## 四、快速启动

### 0. 前置准备

- Python 3.11+、Node.js 20+、Docker（含 docker compose）、Git。
- 首次开工前按 [AGENTS.md](./AGENTS.md) 的"开工前必读顺序"阅读文档。

### 1. 启动 MQTT Broker（仿真环境）

```bash
# 在项目根目录执行，后台启动 Mosquitto，监听 1883，允许匿名（仅仿真）
docker-compose up -d

# 查看运行状态
docker-compose ps

# 停止
docker-compose down
```

> 该 Broker 仅用于本地仿真，允许匿名连接、无 TLS，**禁止用于任何真实或生产场景**。

### 2. 启动后端

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 3. 启动车辆 / 机器人仿真

```bash
# 新开终端
cd vehicle_sim && python main.py       # 车辆仿真

# 另一个终端
cd robot_sim && python main.py         # 机器人仿真
```

### 4. 启动前端

```bash
cd frontend
npm ci
npm run dev
```

> 注：各模块确切命令以其目录内 README 为准；本快速启动为典型链路示例。

---

## 五、三轨并行说明

开发按三条轨并行推进，均依赖**同一份冻结契约**（见 `contracts/`），互不阻塞：

| 轨 | 目录 | 职责 | 交付重点 |
|----|------|------|---------|
| 后端轨 | `backend/` | MQTT 遥测接入、存储、REST API | 稳定的数据入口与查询接口 |
| 车辆仿真轨 | `vehicle_sim/` | 电量衰减、充电需求、位置上报 | 符合 telemetry.json 的遥测流 |
| 机器人仿真轨 | `robot_sim/` | 移动充电路径与调度作业 | 与后端调度的协同接口 |

协作纪律：

- 三轨只在 `contracts/` 定义的边界上对接，**不得改动契约**（见 AGENTS.md 第 3 节）。
- 接口变更需 `[CONTRACT]` 变更 PR + 三轨评审通过。
- 每周三 / 周日为端到端联调窗口（见 AGENTS.md 第 7 节）。
- 进度与依赖实时更新于 [docs/progress.md](./docs/progress.md)。

---

## 六、文档与契约链接

- [docs/project_scope.md](./docs/project_scope.md) — 项目范围与仿真边界（开工必读 ①）
- [docs/progress.md](./docs/progress.md) — 进度看板（R0.1 → R8.2）
- [contracts/api.md](./contracts/api.md) — REST / MQTT 契约（开工必读 ②，冻结）
- [contracts/telemetry.json](./contracts/telemetry.json) — 遥测 schema（开工必读 ③，冻结）
- [AGENTS.md](./AGENTS.md) — 协作规则与任务卡模板

---

## 七、答辩演示链路

演示按"仿真产生数据 → 后端汇聚 → 前端可视化 → 策略对比"的链路展开：

1. **起底座**：`docker-compose up -d` 启动 Mosquitto。
2. **起数据面**：启动 `backend/`，确认订阅遥测主题成功。
3. **起仿真面**：启动 `vehicle_sim/` 与 `robot_sim/`，向后端持续上报仿真遥测。
4. **看板呈现**：启动 `frontend/`，展示车辆电量分布、充电队列、机器人作业状态的实时看板。
5. **策略对比**：通过后端接口切换调度策略，在 `results/` 中展示效果统计与图表。
6. **边界说明**：演示开始即声明全链路为**仿真数据**，并说明项目仿真边界（见第二节）。

> 备份方案：若某一轨现场不可用，可使用 `tests/` 中的预置仿真数据流驱动后端与前端，保证演示链路完整。

---

*最后更新：2026-11-18*
