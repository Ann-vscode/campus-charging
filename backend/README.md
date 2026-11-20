# 后端 R1.2 — Mock 闭环（FastAPI）

> 校园共享电动车移动集群充电**仿真**系统后端。所有数据为仿真数据，非真实车辆数据。
> 契约：`contracts/api.md` v1.0.0｜参数：`contracts/simulation_params.md`

## 本轮实现范围（R1.2）
- ✅ 12 个 HTTP 端点 + WS `/ws`，统一信封 + `simulation:true` + 完整错误码
- ✅ **MockRobot** 不依赖 ROS 2：IDLE→NAVIGATING→DOCKING→CHARGING→DEPART→RETURNING→RECHARGING 状态机
- ✅ 五路独立充电：每路独立进度，单车完成不影响其他通道
- ✅ 调度打分（R2.2 逻辑）+ 能源模型（R2.3 逻辑）：移动/充电扣能、派单可行性校验、低电量返基站
- ✅ 后端唯一仿真时钟源，倍速 1/10/60，10Hz WS 推送
- ✅ 数据驱动：改 `scenarios/campus_basic.yaml` 即可改车辆数/电量/停车区

## 启动
```bash
# 依赖（隔离环境）
pip install fastapi uvicorn pydantic pytest httpx websockets pyyaml

# 启动服务
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
# 打开 http://localhost:8000/docs 看 Swagger
```

## 快速验证闭环
```bash
# 1. 启动
curl -X POST http://localhost:8000/api/simulation/start -H "Content-Type: application/json" -d '{"speed":60,"seed":20261118}'
# 2. 等几秒，看任务/事件
curl http://localhost:8000/api/tasks
curl http://localhost:8000/api/events
# 3. 看机器人
curl http://localhost:8000/api/robot
```

## 测试
```bash
pytest tests/test_r12_mock.py -v
```
覆盖：场景加载、调度可复现、有效车辆过滤、能源公式、控制状态机、自动完成两批、五路独立充电、WS 帧契约、障碍重规划。

## 目录
- `config.py` — 场景 YAML 加载（数据驱动）
- `scheduler.py` — 调度打分 + 跨区补位 + 能源估算（R2.2/R2.3）
- `engine.py` — 仿真引擎：时钟 + MockRobot + 五路充电 + 事件
- `main.py` — FastAPI 端点 + WS

## 已知问题 / 未完成（按任务卡诚实记录）
1. **对接重试/失败跳过**（R5.2）：当前 Mock 全部对接成功；重试与连续失败跳过逻辑留到 P5 集成阶段。
2. **真实 MQTT 车辆遥测**（R2.1）：当前车辆数据从 YAML 加载，周期上报与离线/过期模拟在 R2.1 实现（Paho 参考见 `refs/paho.mqtt.python`）。
3. **车辆电量方向**：Mock 中车辆 SOC 单调上升至 80%（充电需求），未模拟车辆行驶耗电（车辆不自动驾驶，符合冻结边界）。
4. **仿真时间压缩**：`SIM_SEC_PER_TICK=0.5`（1x 时每 100ms tick 推进 0.5 仿真秒），为让答辩演示可在数秒内跑完；倍速 60x 下更快。此为仿真假设，可配置。
5. **WS 车辆轮转**：每 tick 推 5 辆，按 tick 轮转覆盖 30 辆；前端若需每辆高频刷新可调整。

## 仿真标注
所有 HTTP 响应含 `"simulation": true`，事件消息含「（仿真数据）」字样，符合方案"仿真数据必须明确标注"的冻结边界。
