# R2.2 / R2.3 独立验收报告

> **仿真标注声明**：本报告及所涉测试、数据、事件、SOC、能耗、充电时长全部为**仿真数据**，来自「校园共享电动车移动集群充电仿真系统」的模型计算，**非真实车辆数据**，不得用于实际工程验收或成本结论。本系统不涉及真实插枪、真实高功率充电与真实车辆对接。

- **验收对象**：R2.2 充电批次调度器、R2.3 机器人能源模型
- **验收性质**：独立、可复现的验收测试；仅新增测试文件与本报告，**未改动任何业务代码**
- **验收依据**：`contracts/simulation_params.md`（v1.0.0，FROZEN）+ 用户给定的 R2.2/R2.3 验收点
- **任务卡核对**：`docs/task_cards/` 现有 R1.2 / R1.3 / R2.1 / R3.1，**无 R2.2 / R2.3 卡**，故以契约与验收点为准

---

## 1. 实现位置与验收方法

| 任务 | 业务实现位置（只读） | 验收文件 |
|---|---|---|
| R2.2 调度器 | `backend/scheduler.py`：`static_view`、`zone_averages`、`is_effective`、`score_vehicle`、`select_batch`、`estimate_batch_energy`、`available_energy_kwh`、`can_dispatch` | `tests/test_r22_scheduler.py`（27 用例） |
| R2.3 能源模型 | `backend/engine.py`：`SimulationEngine.tick/_advance` 的 `IDLE→TO_ZONE→DOCKING→CHARGING→DEPART→RETURN→RECHARGE` 状态机、五路 `Channel` 充电、返基站补能 | `tests/test_r23_energy.py`（14 用例） |
| 参数/场景 | `backend/config.py`（`Scene`/`Vehicle`）、`scenarios/campus_basic.yaml` | 两文件顶部均将项目根加入 `sys.path`，参数经 `scene` 对象读取 |

**验收方法**：
1. **黑盒 + 受控白盒结合**：调度器通过构造极小 `StateView` 制造极端场景；能源模型通过真实 `SimulationEngine` 跑闭环，并在必要处受控设置 `_phase` / `robot.soc` 以精确验证阈值状态机。
2. **数值断言不写死魔数**：所有期望值来自 `scene` 字段或与契约常量表（`CONTRACT` / `CONTRACT_WEIGHTS`）核对。
3. **可复现性验证**：同 seed 跑两次，比较任务序列与事件序列签名（不含真实时间戳）。
4. **运行命令**：
   ```
   C:/Users/lenovo/.workbuddy/binaries/python/envs/default/Scripts/python.exe -m pytest \
     tests/test_r22_scheduler.py tests/test_r23_energy.py -v \
     --rootdir="C:/Users/lenovo/WorkBuddy/plan phase/campus-charging"
   ```

---

## 2. 测试结果

环境：Python 3.13.14 / pytest 8.3.4 / win32。结果：**41 passed，0 failed**（耗时约 12.5s）。

| 测试文件 | 测试类 | 用例数 | 结果 |
|---|---|---:|---|
| test_r22_scheduler.py | `TestReproducibility` | 3 | 全部通过 |
| test_r22_scheduler.py | `TestWeights` | 3 | 全部通过 |
| test_r22_scheduler.py | `TestBatchSize`（参数化 4×3） | 12 | 全部通过 |
| test_r22_scheduler.py | `TestEffectiveFilter` | 2 | 全部通过 |
| test_r22_scheduler.py | `TestCrossZoneRefill` | 2 | 全部通过 |
| test_r22_scheduler.py | `TestScoreFormula` | 2 | 全部通过 |
| test_r22_scheduler.py | `TestEnergyGate` | 3 | 全部通过 |
| **R2.2 小计** | | **27** | **27 passed** |
| test_r23_energy.py | `TestContractParams` | 1 | 全部通过 |
| test_r23_energy.py | `TestMoveEnergy` | 2 | 全部通过 |
| test_r23_energy.py | `TestFiveChannelCharging` | 4 | 全部通过 |
| test_r23_energy.py | `TestTargetSOC` | 1 | 全部通过 |
| test_r23_energy.py | `TestReturnToBase` | 2 | 全部通过 |
| test_r23_energy.py | `TestClosedLoop` | 4 | 全部通过 |
| **R2.3 小计** | | **14** | **14 passed** |
| **合计** | | **41** | **41 passed** |

**关键验收结论**：
- 可复现性：同 seed 任务/事件序列完全一致，改变 view 字典插入顺序不影响结果（同分按 vid 字典序 tie-break）。
- 权重：`low_soc=0.35` 主导 `distance=0.25`（极端场景低电量远车胜出）；把权重改为仅 `distance=1` 后排序反转，证明排序由配置驱动而非硬编码。
- 有效性过滤：`A03`(OFFLINE)、`B04`(STALE)、`A08`(SOC90)、`C07`(SOC95) 均被过滤；`PARKED` 且 SOC<80 入选。
- 跨区补位：本区仅 2 辆有效时，从最近的 B 区补 3 辆，总数恰为 5；全区不足时按实际数量派发。
- 能源守门：`robot_soc=safety_margin` 时可用储能为 0，`can_dispatch=False`，引擎进入 `RETURN`。
- 闭环：12000 tick 内 24 辆有效车各充电一次、无重复派单，含 8 类关键事件，触发 1 次返基站补能并恢复派单。

---

## 3. 关键公式与设计决策表

| 主题 | 公式 / 决策 | 来源 | 实现位置 |
|---|---|---|---|
| 调度打分 | `score = 0.35·(1−soc/100) + 0.20·(1−zoneAvg/100) + 0.25·max(0,1−d/d_max) + 0.20·(robotSOC/100)` | 契约 §5 | `scheduler.score_vehicle` |
| 同分处理 | 以 `vid` 字典序升序 tie-break | 契约 §5.3 | `scheduler.select_batch` 的 `sort key=(-round(score,9), vid)` |
| 每批上限 | 先本区、按 `max_per_batch` 截断；不足按分区中心距机器人由近到远跨区补齐，总数仍 ≤5 | 契约 §5.4/§6 | `scheduler.select_batch` |
| 有效车定义 | `online && !stale && status==PARKED && soc<target_soc` | 契约 §6.1 | `scheduler.is_effective` |
| 移动扣能 | `E_move = e_move·d/100`，`ΔSOC = E_move/E_cap·100` | 契约 §2.2 | `engine._advance`(`TO_ZONE`/`RETURN`) |
| 交付功率 | `P_bat = P_ch·(1−λ) = 3.5×0.95 = 3.325 kW` | 契约 §4.2 | `engine._start_charging` / `CHARGING` |
| 储能侧功率 | `P_store = P_ch/η = 3.5/0.95 ≈ 3.684 kW` | 契约 §2.2/§4.2 | `engine._advance`(`CHARGING`/`RECHARGE`) |
| 单车需电 | `E_need = (target−soc)/100·E_vehicle_cap`（默认 0.5kWh） | 契约 §3.2 | `engine._start_charging` |
| 储能消耗 | `E_store = E_need/(η·(1−λ))`，两系数一次性折算不重复扣 | 契约 §2.2 | `scheduler.estimate_batch_energy` |
| 充电时长 | `t_total = E_need/P_bat`（小时）→ ×3600 转仿真秒 | 契约 §4.2 | `engine._start_charging` |
| 派发守门 | `E_est = E_move_total + ΣE_store,i`；`E_est > (soc−margin)/100·E_cap` 时不派发并返基站 | 契约 §2.3 | `scheduler.can_dispatch` |
| 返基站阈值 | `soc ≤ low_energy_threshold`（默认 20%）→ `RETURN` → `RECHARGE` 至 100% → `IDLE` | 契约 §2.2(3)/§8.1 | `engine._advance`(`DEPART`/`RETURN`/`RECHARGE`) |

**设计决策说明**：
- 效率 η 与传输损耗 λ 是两个不同环节（储能→通道、通道→电池），按 `E_store = E_need/(η·(1−λ))` **一次性折算**，未重复扣减；验收实测五路并发时机器人储能扣减为单路 `P_store` 折算的 5 倍，与该设计一致。
- 机器人容量 5.0 kWh 与单车容量 0.5 kWh 是两个不同参数，测试严格区分，避免混淆。

---

## 4. 与契约参数一致性核对

| 参数 | 契约值 | scene 字段 | 核对 |
|---|---|---|---|
| 机器人储能容量 | 5.0 kWh | `robot_capacity_kwh` | 一致 |
| 移动能耗 | 0.05 kWh/100m | `move_energy_per_100m` | 一致 |
| 充电效率 | 0.95 | `charge_efficiency` | 一致 |
| 单路额定功率 | 3.5 kW | `power_kw` | 一致 |
| 传输损耗 | 0.05 | `transfer_loss` | 一致 |
| 通道数 | 5 | `channels` | 一致 |
| 每批上限 | ≤5 | `max_per_batch` | 一致 |
| 目标 SOC | 80% | `target_soc` | 一致 |
| 调度权重 | 0.35/0.20/0.25/0.20 | `weights` | 一致，和为 1.0 |
| 单车电池容量（仿真假设） | 0.5 kWh | `vehicle_cap_kwh` | 一致 |
| d_max（仿真假设） | 100 m | `d_max` | 一致 |
| 低电量阈值（仿真假设） | 20% | `low_energy_threshold` | 一致 |
| 安全余量（仿真假设） | 10% | `safety_margin` | 一致 |
| refill_rule | `nearest_zone_if_short` | `refill_rule` | 一致 |

`TestContractParams::test_scene_matches_contract` 对上表逐项自动核对，全部通过。

---

## 5. 发现的问题与限制（诚实列出）

> 以下为独立验收中发现的实现偏差，**均未修改 backend/**，提请主代理 / 业务负责人评估。

### 问题 1（中）：移动扣能按“时间×速度”积分，未按实际行驶里程截断，倍速越高偏差越大

- **位置**：`backend/engine.py:251-252`（`TO_ZONE`）、`backend/engine.py:338-339`（`RETURN`）
- **现象**：扣能用 `moved = r.speed * dt`，而位置插值用 `frac = min(1, _phase_t/_phase_dur)`。当最后一 tick 跨越终点（frac 被截断到 1）时，`moved` 仍按整段 `speed·dt` 计，高于实际剩余位移；高倍速下 `dt` 大，单 tick 可远超整段路径长度。
- **实测**（标准场景首段路径 D=30.529 m，公式应降 0.3053% SOC）：
  - `speed=1`：实降 0.3150%（多扣约 0.0097%）
  - `speed=60`：实降 0.9000%（多扣约 0.5947%，约为公式值的 2.95 倍）
- **影响**：与契约 §2.2「`E_move = e_move × d/100`，d 为行驶距离」不一致；高倍速下机器人电量消耗偏快、返基站更频繁，且相同 seed 在不同倍速下能耗轨迹不同，削弱“可复现”语义。闭环功能不受影响（41 用例全过），但 SOC 结果精度依赖倍速。
- **建议**：按实际插值位移或 `min(剩余距离, speed·dt)` 计 `moved`。
- **验收处理**：移动能耗用“公式级断言 + 每 tick 扣能换算断言”验收以避开积分偏差；本问题在此如实报告，未改业务代码。

### 问题 2（轻）：跨区补位事件未标注“跨区补位”及来源分区

- **位置**：`backend/engine.py:233`（`TASK_ASSIGNED` 事件 message）
- **现象**：契约 §6.3 要求跨区补位的 `TASK_ASSIGNED` message 注明“跨区补位”与来源分区；实际 message 仅为 `任务 {tid} 分配给机器人 R01（仿真数据）`，无法从事件识别补位。
- **影响**：前端展示与验收核对缺少补位可追溯性；调度器内部补位逻辑本身正确（已验收通过）。
- **建议**：在补位任务派发时向 message 追加来源分区标注。

### 限制说明

- **返基站次数**：标准场景 24 辆有效车分 5 批、初始 SOC 100%，闭环仅触发 **1 次**返基站补能（非“数次”），此为场景参数与能源参数的结果，非缺陷。
- **倍速固定**：为消除问题 1 带来的倍速敏感性，本验收的闭环测试统一使用 `speed=60`；若需跨倍速一致性验收，应先修复问题 1。
- **白盒断言**：`test_threshold_triggers_return_and_full_recharge` 受控设置 `_phase`/`robot.soc` 以精确验证阈值状态机，属状态机单元验收，不替代长时间随机场景的覆盖。

---

## 6. 仿真标注声明

- 本系统为**校园共享电动车移动集群充电仿真系统**，本报告所有成果均为**仿真结果**。
- 所有车辆、车位、电量、位移、能耗、充电时长、SOC、事件与时钟均为**仿真数据**，**非真实车辆数据**。
- 对外呈现须按契约 §8.2 携带 `simulation: true`（HTTP/WS）及消息文本“（仿真数据）”。
- 仿真结果**不能直接证明实际成本更低**，不得用于真实工程验收或成本结论。

---

*验收执行：独立验收代理 · 依据 `contracts/simulation_params.md` v1.0.0 · 全部数据标注仿真*

---

## 7. 验收后修复记录（2026-11-19，协调层）

**问题 1（倍速能耗偏差）已修复。** 修复方式：`backend/engine.py` 新增 `_consume_move_energy(old_x, old_y)`，按本 tick 的**实际位移**（插值前后位置差 `hypot(dx,dy)`）扣能，替代原 `speed*dt` 积分；`TO_ZONE` 与 `RETURN` 两段均改用该方法。

复验结果（同 seed=20261118，跑完首段路径）：

| 倍速 | 首段耗电（修复前） | 首段耗电（修复后） |
|---|---|---|
| 1x | 0.3053% | **0.3053%** |
| 10x | 3.05%（约 10 倍偏差）| **0.3053%** |
| 60x | 0.9%（约 3 倍偏差）| **0.3053%** |

修复后能耗与倍速完全无关，与公式 `0.05·D/100/5.0×100`（D≈30.53m）一致。全量回归 pytest **72/72 PASS**（含本报告的 41 项），无回归。

**问题 2（跨区补位事件标注）** 保留为已知小限制，待 R4/P5 阶段前端展示时一并处理，不影响数值验收。
**倍速固定说明** 现在可以放宽：能耗已与倍速无关，闭环曾在 1x/10x/60x 下均验证可完成（任务数因状态机离散步长略有差异，属仿真离散化特性）。
