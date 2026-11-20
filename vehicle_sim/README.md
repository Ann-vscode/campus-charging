# 车辆遥测模拟器（R2.1）

> ⚠️ **全部为仿真数据，非真实车辆数据。** 车辆 ID 来自场景配置（基础场景形如 A01/B04/C08），不写死格式。

把 `scenarios/campus_basic.yaml` 里的 30 辆车，按周期以 `VehicleTelemetry` 结构通过 MQTT 上报，模拟"车辆 → 平台"的物联网遥测通道。基于仓库内已克隆的 `refs/paho.mqtt.python` 二次开发（`import paho` 优先用隔离 venv 安装版，未安装时自动回退到 refs 源码）。

## 文件

| 文件 | 说明 |
|---|---|
| `simulator.py` | 模拟器主体：`build_telemetry()` 构造契约帧 + MQTT 发布循环 |
| `topics.py` | Topic 约定：`campus/v1/sim/vehicles/{id}/telemetry`（`/sim/` 明确仿真） |
| `e2e_check.py` | 本机端到端自检：进程内起 amqtt broker，验证发布→订阅全链路 |

## 依赖（隔离 venv）

```bash
pip install paho-mqtt==2.1.0 amqtt==0.11.0 jsonschema==4.23.0
```

## 使用

```bash
# 1. 不连 broker，打印一帧样例（校验字段契约）
python -m vehicle_sim.simulator --dry-run

# 2. 连本机 broker（docker-compose up -d 起的 Mosquitto），上报 5 轮
python -m vehicle_sim.simulator --broker 127.0.0.1 --port 1883 --rounds 5 --interval 1

# 3. 持续上报（掉电模拟，每轮 -0.5%，便于观察数据变化）
python -m vehicle_sim.simulator --rounds 0 --interval 2 --drift 0.5

# 4. 本机端到端自检（无需 Docker，进程内 broker）
python -m vehicle_sim.e2e_check
```

## 行为约定

- **离线车**（`online:false` / `status:offline`，如 A03）**不上报**遥测。
- **陈旧样本**（`status:stale`，如 B04）上报 `status=STALE`、`stale=true`、时间戳为 120 秒前，用于测试平台过滤逻辑。
- 每帧严格匹配 `contracts/telemetry.json` 的 `VehicleTelemetry`（9 个字段、`additionalProperties=false`）。
- 调度打分所需的电量、坐标均来自场景配置，改 YAML 即可，无需改代码。

## 与后端的对接

后端默认 **不启用** MQTT 接入（`backend/main.py` 中 `mqtt_bridge=None`），R1.2 的 Mock 闭环完全不受影响。要接入真实遥测：

```bash
CAMPUS_MQTT_ENABLED=1 CAMPUS_MQTT_HOST=127.0.0.1 CAMPUS_MQTT_PORT=1883 \
  uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

后端通过 `backend/mqtt_bridge.py` 订阅 wildcard topic，校验后写入 `engine.vehicles` 动态视图：
- 平台正在服务的车（SELECTED/DOCKING/CHARGING/CHARGED）只刷时间戳，不被车辆侧陈旧 soc 覆盖（平台权威，避免双写冲突）。
- OFFLINE/STALE 原样写入，供 `scheduler.is_effective` 过滤。
- 诊断端点 `GET /api/mqtt/status` 可查接入状态、收发计数、最近错误。

## 已实现 / 未实现

- ✅ 数据驱动上报、离线/陈旧样本、契约严格字段、drift 观察、E2E 自检
- ✅ MQTT 接入层（含 jsonschema 二次校验、平台权威保护）
- ⏳ 真实奥约厂商接口（**不在本项目范围**）
- ⏳ TLS/鉴权（仿真 broker 允许匿名，**禁止用于真实接入**）
