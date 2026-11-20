# R2.1 车辆遥测模拟器 — 交付报告

> 全部为仿真数据，非真实车辆数据。 ｜ 完成日期：2026-11-18 ｜ 负责人：阿岚（主代理）

## 一、做了什么

把"车辆 → 平台"的物联网遥测通道补齐：车辆模拟器按契约上报，后端可选接入，写入引擎动态视图供调度使用。基于仓库已克隆的 `refs/paho.mqtt.python` 二次开发（EPL/EDL 双许可）。

## 二、交付文件

| 文件 | 说明 |
|------|------|
| `vehicle_sim/simulator.py` | 模拟器：`build_telemetry()` 构造严格 9 字段契约帧；离线不上报；stale 样本；drift；CLI |
| `vehicle_sim/topics.py` | Topic 约定：`campus/v1/sim/vehicles/{id}/telemetry`（`/sim/` 标识仿真） |
| `vehicle_sim/e2e_check.py` | 本机端到端自检：进程内 amqtt broker，发布→订阅全链路 |
| `vehicle_sim/README.md` | 启动命令、行为约定、后端对接 |
| `backend/mqtt_bridge.py` | 接入层：订阅 wildcard、轻量校验 + jsonschema 精校、平台权威保护、诊断计数 |
| `backend/engine.py` | 新增 `upsert_vehicle_telemetry()`（双写保护） |
| `backend/main.py` | 可选启用（`CAMPUS_MQTT_ENABLED=1`）+ `GET /api/mqtt/status` |
| `contracts/telemetry.json` | 修正 vehicle_id 描述：`V-A-001` → 数据驱动 `A01`（仅描述，不动结构） |
| `tests/test_r21_telemetry.py` | 17 项测试 |
| `docs/task_cards/R2.1-车辆遥测模拟器.md` | 任务卡 |

## 三、验证结果（全部实测）

- **pytest 31/31 PASS**（R1.2 的 14 项 + R2.1 的 17 项）
- **E2E PASS**：进程内 MQTT broker，发布 29 帧全部送达，jsonschema 校验通过（离线 A03 正确排除）
- **HTTP 回归 PASS**：6 个端点（含新增 `/api/mqtt/status`）在 websockets 14.1→15.0.1 升级后仍正常
- **遥测注入 PASS**：A03 保持 OFFLINE、B04 stale=true，调度器 `is_effective` 均正确排除；A01 有效入选
- **契约 JSON 合法**：无 `V-A-001` 残留，ID 示例统一为 A01

## 四、关键设计决策

1. **双写冲突 → 平台权威原则**：车辆侧遥测与平台侧充电都会写 `soc`。若车辆处于 SELECTED/DOCKING/CHARGING/CHARGED（平台服务中），接入层只刷新时间戳，**不用车辆上报值覆盖 soc**，避免"车辆报旧电量把平台充电结果冲掉"。
2. **默认关闭、按需启用**：`CAMPUS_MQTT_ENABLED=0` 时 `mqtt_bridge=None`，R1.2 纯 Mock 闭环完全不受影响；broker 不可用也只降级不影响主功能。
3. **契约描述缝隙修复**：`telemetry.json` 原把车辆 ID 写死为 `V-A-001`，与数据驱动的 `A01` 冲突。改为"格式由场景配置决定，如 A01"——不改字段结构，只消除歧义（符合 contracts 变更治理：非破坏性描述修正）。
4. **仿真隔离**：topic 带 `/sim/`、broker 用独立端口 18830、所有消息标注仿真——与任何真实车辆接入物理隔离。

## 五、依赖与复用

- `paho-mqtt==2.1.0`（基于克隆的 `refs/paho.mqtt.python`，EPL/EDL）— MQTT 客户端
- `amqtt==0.11.0`（MIT）— 纯 Python broker，本机 E2E 无需 Docker
- `jsonschema==4.23.0` — 契约精校（缺失时降级为轻量校验，不阻断仿真）

> 注意：安装 amqtt 使 `websockets` 14.1→15.0.1、`click` 8.5.1→8.1.8。已做 HTTP 回归验证，R1.2 端点正常。

## 六、下一步

- **R2.2 充电批次调度器** / **R2.3 能源模型**：逻辑已在 R1.2 的 `scheduler.py`/`engine.py` 中实现，可独立提取验收。
- **R3.1 Gazebo 场景**：需用户侧 WSL2 + ROS 2 Humble 环境；代码可先备。
