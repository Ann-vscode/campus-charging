# API 契约（HTTP + WebSocket）

- **契约版本**：`v1.0.0`
- **状态**：FROZEN（冻结，作为「接口宪法」；变更规则见第 8 节）
- **适用范围**：校园共享电动车移动集群充电**仿真**系统（非真实部署）
- **契约 Owner**：Kimi（系统负责人）
- **消费方**：后端线（Codex）、机器人线（Claude Code）、前端线（v0 + Codex）
- **汇合点**：P5，三条线仅通过本契约与 `telemetry.json` / `state_machines.md` / `simulation_params.md` 对接

> 本文件定义的所有数据均为**仿真数据，非真实车辆数据**。所有响应体必须携带 `simulation: true` 标识。

---

## 1. 通用约定

### 1.1 基础地址与编码

- 协议：`http`（本地/内网演示），WebSocket 为 `ws`。
- 请求/响应编码：`application/json; charset=utf-8`。
- 所有时间戳：**UTC ISO 8601**，格式 `YYYY-MM-DDTHH:mm:ss.sssZ`（例如 `2026-11-18T09:30:00.000Z`）。前端展示可本地化，但**传输与存储一律 UTC**。

### 1.2 统一响应信封

所有 HTTP 端点（含错误）使用统一信封：

```json
{
  "code": 0,
  "message": "OK",
  "simulation": true,
  "timestamp": "2026-11-18T09:30:00.000Z",
  "data": {}
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | integer | 业务码，`0` 表示成功；非 0 见第 9 节错误码表 |
| `message` | string | 人类可读信息；错误信息须为中文 |
| `simulation` | boolean | **恒为 `true`**，标识仿真数据 |
| `timestamp` | string | 服务端生成响应的 UTC 时间（ISO 8601） |
| `data` | object | 业务负载；错误时可为空对象或含 `details` |

> 请求体字段缺失或类型错误由框架返回 `HTTP 422`，其业务语义码对应 `4006 INVALID_PARAMETER`；实现方应在 `code` 中回填 `4006` 以保持一致。

### 1.3 分页 / 过滤

- `GET /api/vehicles`、`GET /api/tasks`、`GET /api/events` 支持 `limit`（默认 100，最大 500）与 `since`（ISO 8601，仅返回该时刻之后的记录）。
- 过滤参数非法不报错，返回空集；但 `zone` 非 `A/B/C` 时返回 `4007 ZONE_NOT_FOUND`。

---

## 2. 仿真时钟源定义（强制，原方案缺口 O3）

> 本节为**强制契约**。三端联调出现时间对不上时，一律以本节为准。

### 2.1 唯一时钟源

- **后端（FastAPI 进程）是唯一的仿真时钟源**。`sim_time` 由后端权威维护并推进。
- 前端**不得**自行推进仿真时间，只按 WebSocket 推送渲染。
- 机器人线（Gazebo / Nav2 / `robot_sim`）的物理时间由后端经接口/MQTT 下发倍速指令对齐；机器人线上报的遥测时间戳须换算到同一 `sim_time` 坐标系。

### 2.2 倍速

- 合法倍速集合：**`1`、`10`、`60`**（整数，单位 x）。
- 倍速**只能**通过 `POST /api/simulation/speed` 设置，请求体 `{"speed": 10}`。
- 后端按倍速推进仿真时间：`dt_sim = dt_base × speed`。
- 倍速设置对正在运行的仿真**立即生效**；在 `reset` 后倍速恢复为 `1x`（除非 start/reset 时显式传入）。

### 2.3 WS 推送节奏

- WebSocket 以固定 **10 Hz（每 100 ms 一个 tick）** 推送，倍速**不改变**推送频率，只改变每个 tick 的 `dt_sim`。
- 每个 tick 的消息体必须携带 `clock.sim_time`（当前仿真时间）与 `clock.speed`。
- 消息批量下发（见第 7 节），前端按 `tick` 序号去重、节流渲染。

### 2.4 时间对齐规则

| 层 | 角色 | 时间行为 |
|---|---|---|
| 后端 | **权威时钟源** | 生成 `sim_time`、按倍速推进、生成所有时间戳 |
| 机器人线 | 从属 | 接收后端倍速指令，上报遥测使用统一 `sim_time` 坐标系 |
| 前端 | 展示层 | 仅渲染 WS 推送的 `sim_time`，不本地推进 |

所有时间戳格式：`UTC ISO 8601`（`...Z` 结尾）。

---

## 3. 端点总表

| # | 方法 | 路径 | 说明 | 成功 HTTP |
|---|---|---|---|---|
| 1 | GET | `/api/scenario` | 获取当前场景配置与时钟状态 | 200 |
| 2 | GET | `/api/vehicles` | 获取车辆遥测列表 | 200 |
| 3 | GET | `/api/robot` | 获取机器人遥测 | 200 |
| 4 | GET | `/api/tasks` | 获取任务列表 | 200 |
| 5 | GET | `/api/events` | 获取事件日志 | 200 |
| 6 | POST | `/api/simulation/start` | 启动仿真 | 200 |
| 7 | POST | `/api/simulation/pause` | 暂停仿真 | 200 |
| 8 | POST | `/api/simulation/resume` | 恢复仿真 | 200 |
| 9 | POST | `/api/simulation/reset` | 重置仿真 | 200 |
| 10 | POST | `/api/simulation/speed` | 设置倍速（1/10/60） | 200 |
| 11 | POST | `/api/demo/obstacle` | 注入临时障碍（演示用） | 200 |
| 12 | WS | `/ws` | 遥测/事件/时钟推送通道 | 101 |

---

## 4. 查询端点（GET）

### 4.1 GET `/api/scenario`

- **请求参数**：无。
- **响应示例（200）**：

```json
{
  "code": 0,
  "message": "OK",
  "simulation": true,
  "timestamp": "2026-11-18T09:30:00.000Z",
  "data": {
    "scenario_id": "campus-default-v1",
    "name": "校园共享电动车移动集群充电仿真-默认场景",
    "version": "1.0.0",
    "clock": {
      "source": "backend",
      "speed": 1,
      "sim_time": "2026-11-18T09:30:00.000Z",
      "running": false,
      "state": "IDLE"
    },
    "zones": ["A", "B", "C"],
    "vehicles": { "total": 30, "by_zone": { "A": 12, "B": 10, "C": 8 } },
    "robot": { "robot_id": "R01", "battery_capacity_kwh": 5.0 },
    "charging_channels": 5,
    "seed": 20261118
  }
}
```

- **状态码**：`200` 成功；`5002` → `500` 内部错误。

### 4.2 GET `/api/vehicles`

- **请求参数（query）**：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `zone` | string | 否 | 过滤分区，枚举 `A` / `B` / `C` |
| `status` | string | 否 | 过滤车辆状态（见 4.2.1） |
| `since` | string | 否 | ISO 8601，仅返回此后更新的车辆 |
| `limit` | integer | 否 | 默认 100，最大 500 |

- **车辆状态枚举（固定，不得增删）**：`PARKED`、`SELECTED`、`DOCKING`、`CHARGING`、`CHARGED`、`STALE`、`OFFLINE`。
- **响应示例（200）**：

```json
{
  "code": 0,
  "message": "OK",
  "simulation": true,
  "timestamp": "2026-11-18T09:30:00.000Z",
  "data": {
    "total": 2,
    "vehicles": [
      {
        "vehicle_id": "V-A-001",
        "zone": "A",
        "slot": 3,
        "x": 12.5,
        "y": 8.0,
        "soc": 34.0,
        "status": "PARKED",
        "stale": false,
        "timestamp": "2026-11-18T09:29:58.000Z"
      },
      {
        "vehicle_id": "V-B-004",
        "zone": "B",
        "slot": 1,
        "x": 41.2,
        "y": 15.7,
        "soc": 79.5,
        "status": "CHARGED",
        "stale": false,
        "timestamp": "2026-11-18T09:29:59.000Z"
      }
    ]
  }
}
```

- **状态码**：`200` 成功；`4007` → `404` 非法 `zone`。

### 4.3 GET `/api/robot`

- **请求参数**：无。
- **机器人状态枚举（固定，不得增删）**：`IDLE`、`NAVIGATING`、`REPLANNING`、`DOCKING`、`CHARGING`、`RETURNING`、`RECHARGING`、`FAULT`。
- **响应示例（200）**：

```json
{
  "code": 0,
  "message": "OK",
  "simulation": true,
  "timestamp": "2026-11-18T09:30:00.000Z",
  "data": {
    "robot_id": "R01",
    "x": 18.4,
    "y": 9.2,
    "heading": 90.0,
    "speed": 0.6,
    "soc": 82.0,
    "status": "NAVIGATING",
    "planned_path": [[18.4, 9.2], [20.0, 9.2], [22.5, 10.0]],
    "traveled_path": [[10.0, 6.0], [14.2, 7.5], [18.4, 9.2]],
    "timestamp": "2026-11-18T09:29:59.000Z"
  }
}
```

- **状态码**：`200` 成功；`4004` → `404` 机器人不存在。

### 4.4 GET `/api/tasks`

- **请求参数（query）**：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `status` | string | 否 | 过滤任务状态（见下） |
| `batch_id` | string | 否 | 按批次过滤 |
| `since` | string | 否 | ISO 8601 |
| `limit` | integer | 否 | 默认 100，最大 500 |

- **任务状态枚举（固定）**：`PENDING`、`NAVIGATING`、`DOCKING`、`CHARGING`、`COMPLETED`、`FAILED`。
- **响应示例（200）**：

```json
{
  "code": 0,
  "message": "OK",
  "simulation": true,
  "timestamp": "2026-11-18T09:30:00.000Z",
  "data": {
    "total": 1,
    "tasks": [
      {
        "task_id": "T-0001",
        "batch_id": "B-0001",
        "vehicle_id": "V-A-001",
        "zone": "A",
        "channel": 1,
        "status": "CHARGING",
        "progress": 0.6,
        "created_at": "2026-11-18T09:28:00.000Z",
        "updated_at": "2026-11-18T09:29:59.000Z"
      }
    ]
  }
}
```

- **状态码**：`200` 成功；`5002` → `500` 内部错误。

### 4.5 GET `/api/events`

- **请求参数（query）**：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `type` | string | 否 | 事件类型过滤（见下） |
| `since` | string | 否 | ISO 8601 |
| `limit` | integer | 否 | 默认 100，最大 500 |

- **事件类型 `type` 枚举（固定）**：`SIM_STARTED`、`SIM_PAUSED`、`SIM_RESUMED`、`SIM_RESET`、`SPEED_CHANGED`、`BATCH_CREATED`、`TASK_ASSIGNED`、`DOCK_OK`、`DOCK_FAIL`、`CHARGE_DONE`、`VEHICLE_DEPARTED`、`OBSTACLE_DETECTED`、`REPLAN_TRIGGERED`、`LOW_ENERGY`、`RETURN_BASE`、`RECHARGE_DONE`、`FAULT`。
- **响应示例（200）**：

```json
{
  "code": 0,
  "message": "OK",
  "simulation": true,
  "timestamp": "2026-11-18T09:30:00.000Z",
  "data": {
    "total": 2,
    "events": [
      {
        "event_id": "E-000001",
        "type": "TASK_ASSIGNED",
        "batch_id": "B-0001",
        "vehicle_id": "V-A-001",
        "message": "任务 T-0001 分配给机器人 R01（仿真数据）",
        "timestamp": "2026-11-18T09:28:01.000Z"
      },
      {
        "event_id": "E-000002",
        "type": "CHARGE_DONE",
        "batch_id": "B-0001",
        "vehicle_id": "V-A-001",
        "message": "车辆 V-A-001 充电至目标 SOC 80%（仿真数据）",
        "timestamp": "2026-11-18T09:29:59.000Z"
      }
    ]
  }
}
```

- **状态码**：`200` 成功。

---

## 5. 仿真控制端点（POST）

> 所有 POST 端点请求体为空对象 `{}` 时表示使用默认值；字段缺失/类型错误返回 `4006` / HTTP `422`。

### 5.1 POST `/api/simulation/start`

- **请求体（可选）**：

```json
{ "speed": 1, "seed": 20261118 }
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `speed` | integer | 否 | 初始倍速，枚举 `1/10/60`，默认 `1` |
| `seed` | integer | 否 | 随机种子（车辆离线/低电量模拟），保证可复现 |

- **响应示例（200）**：

```json
{
  "code": 0,
  "message": "仿真已启动（仿真数据）",
  "simulation": true,
  "timestamp": "2026-11-18T09:30:00.000Z",
  "data": {
    "state": "RUNNING",
    "speed": 1,
    "sim_time": "2026-11-18T09:30:00.000Z",
    "seed": 20261118
  }
}
```

- **状态码**：`200` 成功；`4001` → `409` 已在运行（`INVALID_STATE`）；`4005` → `400` 非法倍速；`4006` → `422` 参数错误。

### 5.2 POST `/api/simulation/pause`

- **请求体**：`{}`（无字段）。
- **响应示例（200）**：

```json
{
  "code": 0,
  "message": "仿真已暂停（仿真数据）",
  "simulation": true,
  "timestamp": "2026-11-18T09:31:00.000Z",
  "data": { "state": "PAUSED", "sim_time": "2026-11-18T09:31:00.000Z" }
}
```

- **状态码**：`200` 成功；`5001` → `503` 仿真未运行；`4001` → `409` 已暂停。

### 5.3 POST `/api/simulation/resume`

- **请求体**：`{}`。
- **响应示例（200）**：

```json
{
  "code": 0,
  "message": "仿真已恢复（仿真数据）",
  "simulation": true,
  "timestamp": "2026-11-18T09:32:00.000Z",
  "data": { "state": "RUNNING", "sim_time": "2026-11-18T09:32:00.000Z" }
}
```

- **状态码**：`200` 成功；`5001` → `503` 仿真未启动；`4001` → `409` 非暂停态不可恢复。

### 5.4 POST `/api/simulation/reset`

- **请求体**：`{}`。
- **行为**：停止仿真并将车辆/机器人/任务/事件恢复到初始场景；倍速恢复 `1x`；`sim_time` 归零到场景起始时刻。
- **响应示例（200）**：

```json
{
  "code": 0,
  "message": "仿真已重置（仿真数据）",
  "simulation": true,
  "timestamp": "2026-11-18T09:33:00.000Z",
  "data": { "state": "IDLE", "speed": 1, "sim_time": "2026-11-18T09:00:00.000Z" }
}
```

- **状态码**：`200` 成功（任意状态均允许 reset）；`5002` → `500` 内部错误。

### 5.5 POST `/api/simulation/speed`

- **请求体**：

```json
{ "speed": 10 }
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `speed` | integer | 是 | 枚举 `1` / `10` / `60` |

- **响应示例（200）**：

```json
{
  "code": 0,
  "message": "倍速已切换为 10x（仿真数据）",
  "simulation": true,
  "timestamp": "2026-11-18T09:34:00.000Z",
  "data": { "speed": 10, "state": "RUNNING", "sim_time": "2026-11-18T09:34:00.000Z" }
}
```

- **状态码**：`200` 成功；`4005` → `400` 倍速非法；`4006` → `422` 字段缺失/类型错误。

### 5.6 POST `/api/demo/obstacle`

- **说明**：演示用。向机器人线注入一个**临时障碍**；若机器人处于 `NAVIGATING`，将触发 `REPLANNING` 并记 `REPLAN_TRIGGERED` 事件。仅 Mock/仿真有效。
- **请求体**：

```json
{ "x": 15.0, "y": 10.0, "radius": 1.5, "ttl_seconds": 30 }
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `x` | number | 是 | 障碍中心 x 坐标（场景单位） |
| `y` | number | 是 | 障碍中心 y 坐标 |
| `radius` | number | 否 | 影响半径，默认 `1.0`，须 > 0 |
| `ttl_seconds` | integer | 否 | 存活时长（仿真秒），默认 `30` |

- **响应示例（200）**：

```json
{
  "code": 0,
  "message": "临时障碍已记录（仿真数据）",
  "simulation": true,
  "timestamp": "2026-11-18T09:35:00.000Z",
  "data": {
    "obstacle_id": "O-000001",
    "x": 15.0,
    "y": 10.0,
    "radius": 1.5,
    "expires_at": "2026-11-18T09:35:30.000Z",
    "robot_reaction": "REPLANNING"
  }
}
```

- **状态码**：`200` 成功；`4008` → `400` 障碍参数非法；`4006` → `422` 字段缺失/类型错误。

---

## 6. 仿真状态语义（后端 `clock.state`）

| state | 含义 | 可迁移到 |
|---|---|---|
| `IDLE` | 未启动 / 已重置 | `RUNNING`（start） |
| `RUNNING` | 正在按倍速推进 | `PAUSED`（pause）、`IDLE`（reset） |
| `PAUSED` | 时钟冻结 | `RUNNING`（resume）、`IDLE`（reset） |

> 该状态仅描述**仿真时钟**，与机器人/车辆/通道状态机（见 `state_machines.md`）相互独立。

---

## 7. WebSocket `/ws`

### 7.1 连接

- 端点：`ws://<host>/ws`，握手成功返回 HTTP `101`。
- 建连后服务端立即推送一帧 `snapshot`（当前全部车辆 + 机器人 + 未完成任务的快照）。

### 7.2 客户端 → 服务端（可选订阅）

```json
{ "op": "subscribe", "channels": ["robot", "vehicles", "tasks", "events", "clock"] }
```

- `channels` 可选值：`robot` / `vehicles` / `tasks` / `events` / `clock`；不发送则默认订阅全部。
- `op` 另支持 `unsubscribe`（同样带 `channels`）。

### 7.3 服务端 → 客户端（每 tick 推送）

帧结构（**批量**，含时钟）：

```json
{
  "type": "tick",
  "simulation": true,
  "timestamp": "2026-11-18T09:30:00.100Z",
  "tick": 1234,
  "clock": {
    "sim_time": "2026-11-18T09:30:00.100Z",
    "speed": 10,
    "state": "RUNNING"
  },
  "messages": [
    { "type": "RobotTelemetry", "payload": { "robot_id": "R01", "x": 18.4, "y": 9.2, "heading": 90.0, "speed": 0.6, "soc": 82.0, "status": "NAVIGATING", "planned_path": [[18.4,9.2],[20.0,9.2]], "traveled_path": [[10.0,6.0],[18.4,9.2]], "timestamp": "2026-11-18T09:30:00.100Z" } },
    { "type": "VehicleTelemetry", "payload": { "vehicle_id": "V-A-001", "zone": "A", "slot": 3, "x": 12.5, "y": 8.0, "soc": 55.0, "status": "CHARGING", "stale": false, "timestamp": "2026-11-18T09:30:00.100Z" } },
    { "type": "TaskEvent", "payload": { "event_id": "E-000002", "type": "CHARGE_DONE", "batch_id": "B-0001", "vehicle_id": "V-A-001", "message": "车辆 V-A-001 充电至目标 SOC 80%（仿真数据）", "timestamp": "2026-11-18T09:30:00.100Z" } }
  ]
}
```

- `type` 取值：`snapshot` | `tick` | `error`。
- `messages[].type` 取值：`RobotTelemetry` | `VehicleTelemetry` | `TaskEvent`，其 `payload` **必须符合 `telemetry.json` 对应 Schema**。
- 前端按 `tick` 序号去重并节流渲染；`clock` 字段为强制字段，缺省即视为契约违规。
- 错误帧示例：`{ "type": "error", "simulation": true, "timestamp": "...", "code": 4005, "message": "非法倍速" }`。

---

## 8. 接口变更治理（强制，原方案缺口 O4 / O8）

> **`contracts/` 是「接口宪法」**：本目录内四个文件冻结后，任何改动都必须走本节流程。三条开发线只认版本化契约，不得私改。

### 8.1 版本规则

- 采用语义化版本 `MAJOR.MINOR.PATCH`，当前 `v1.0.0`。
- **破坏性变更（breaking）** → `MAJOR` 升级（如 `v2.0.0`）。包括但不限于：
  - 状态枚举新增/删除/改名（机器人、车辆、通道、任务、事件类型）；
  - 遥测字段新增必填项、删除、改名、类型变更；
  - API 路径变更、HTTP 方法变更、请求/响应结构不兼容变更；
  - 错误码语义变更。
- **向后兼容的新增**（新增可选字段、新增端点、新增事件类型）→ `MINOR` 升级（如 `v1.1.0`）。
- **文档澄清 / 修复错别字 / 示例修正** → `PATCH` 升级（如 `v1.0.1`）。

### 8.2 变更流程（缺一不可）

1. **变更 PR**：提交到 `contracts/r1-1` 分支，说明变更点、影响范围、迁移方案。
2. **版本号更新**：同步更新本文件头、`telemetry.json` 的 `x-version`、相关文档版本。
3. **三轨评审**：后端线（Codex）、机器人线（Claude Code）、前端线（v0/Codex）各出 1 名评审人；**Kimi 作为契约 Owner 终审**。避免单点瓶颈。
4. **向后兼容期**：`MAJOR` 变更必须提供 **≥ 1 个迭代周期**的兼容期——旧版本端点/字段继续可用，新旧并行运行，三轨完成迁移后方可下线旧版。
5. **CI 门禁**：变更须通过接口契约测试（对照 `contracts/` 校验）方可合入 `main`。
6. **通知三轨**：合入后在 `docs/progress.md` 记录版本变更与迁移截止日。

### 8.3 冻结纪律

- 未走完 8.2 流程的改动一律视为**契约违规**，CI 应拒绝合入。
- 各线不得在自身目录内「兼容」非版本化字段；发现契约缺口应提变更 PR，由 Kimi 统一裁决。

---

## 9. 统一错误码表

| `code` | HTTP | 名称 | 含义 | 典型触发 |
|---|---|---|---|---|
| `0` | 200 | `OK` | 成功 | 正常响应 |
| `4001` | 409 | `INVALID_STATE` | 当前仿真状态不允许该操作 | 重复 start / 非 PAUSED 时 resume |
| `4002` | 404 | `VEHICLE_NOT_FOUND` | 车辆不存在 | 指定 `vehicle_id` 无效 |
| `4003` | 404 | `TASK_NOT_FOUND` | 任务不存在 | 指定 `task_id` 无效 |
| `4004` | 404 | `ROBOT_NOT_FOUND` | 机器人不存在 | 机器人未初始化 |
| `4005` | 400 | `INVALID_SPEED` | 倍速非 `1/10/60` | `POST /api/simulation/speed` 传 `5` |
| `4006` | 400 / 422 | `INVALID_PARAMETER` | 参数不合法或字段缺失/类型错误 | 请求体缺 `speed` |
| `4007` | 404 | `ZONE_NOT_FOUND` | 分区不存在（非 `A/B/C`） | `?zone=D` |
| `4008` | 400 | `OBSTACLE_INVALID` | 临时障碍参数非法 | `radius <= 0` |
| `5001` | 503 | `SIM_NOT_RUNNING` | 仿真未运行 | 未 start 就 pause/resume/speed |
| `5002` | 500 | `INTERNAL_ERROR` | 后端内部错误 | 未预期异常 |
| `5003` | 409 | `CHANNEL_UNAVAILABLE` | 充电通道不可用 | 五路全占用时派发 |

> 错误响应示例：
>
> ```json
> {
>   "code": 4005,
>   "message": "非法倍速：仅支持 1/10/60",
>   "simulation": true,
>   "timestamp": "2026-11-18T09:36:00.000Z",
>   "data": { "details": { "speed": 5 } }
> }
> ```

---

## 10. 版本变更记录

| 版本 | 日期 | 说明 |
|---|---|---|
| `v1.0.0` | 2026-11-18 | 首版冻结：12 个端点 + WS；补齐仿真时钟源（O3）、变更治理（O4）、错误码；统一状态枚举与仿真标注。 |
