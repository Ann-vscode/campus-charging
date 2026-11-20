"""R2.3 机器人能源模型——独立验收测试（全部为仿真数据）。

验收对象：backend/engine.py 的能源模型 / 五路充电 / 返基站逻辑 / _phase 状态机。
本测试为独立可复现验收，不改动任何业务代码；所有数值断言引用 scene 或契约常量。
文件顶部把项目根加入 sys.path（参考 tests/conftest.py）。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import math
from collections import Counter

import pytest

from backend.config import load_scenario
from backend.engine import SimulationEngine, s_base_speed
from backend import scheduler as sch

# 契约 contracts/simulation_params.md 第 1/2/4/8 节（给定基线 + 仿真假设）
CONTRACT = {
    "robot_capacity_kwh": 5.0,      # 给定基线：机器人储能 5.0 kWh
    "move_energy_per_100m": 0.05,   # 给定基线：0.05 kWh/100m
    "charge_efficiency": 0.95,      # 给定基线
    "power_kw": 3.5,                # 给定基线：单路额定功率
    "transfer_loss": 0.05,          # 给定基线：传输损耗系数
    "channels": 5,                  # 给定基线：五路
    "max_per_batch": 5,             # 给定基线：每批 ≤5
    "target_soc": 80.0,             # 给定基线：目标 SOC
    "vehicle_cap_kwh": 0.5,         # 仿真假设：单车电池容量
    "d_max": 100.0,                 # 仿真假设：距离归一化上限
    "low_energy_threshold": 20.0,   # 仿真假设：低电量返基站阈值
    "safety_margin": 10.0,          # 仿真假设：派单安全余量
}
CONTRACT_WEIGHTS = {"low_soc": 0.35, "avg_soc": 0.20,
                    "distance": 0.25, "robot_energy": 0.20}


@pytest.fixture(scope="module")
def scene():
    return load_scenario()


def _run(seed, ticks=12000):
    """跑固定 seed 的仿真闭环，返回 (engine, 任务签名, 事件签名)。"""
    e = SimulationEngine()
    e.start(speed=60, seed=seed)
    for _ in range(ticks):
        e.tick()
    task_sig = [(t.vehicle_id, t.status, t.batch_id) for t in e.tasks]
    event_sig = [(ev["type"], ev["batch_id"], ev["vehicle_id"]) for ev in e.events]
    return e, task_sig, event_sig


class TestContractParams:
    """参数来自契约：所有数值取自 scene，与 simulation_params.md 核对。"""

    def test_scene_matches_contract(self, scene):
        for key, expected in CONTRACT.items():
            assert getattr(scene, key) == expected, f"{key} 与契约不一致"
        assert scene.weights == CONTRACT_WEIGHTS
        assert math.isclose(sum(scene.weights.values()), 1.0, abs_tol=1e-9)


class TestMoveEnergy:
    """移动能耗：E_move = 0.05·D/100 kWh，按 5.0kWh 容量折算 SOC 下降。"""

    def test_move_energy_formula_per_100m(self, scene):
        D = 100.0
        e_move = scene.move_energy_per_100m * D / 100.0
        assert math.isclose(e_move, CONTRACT["move_energy_per_100m"], abs_tol=1e-9)
        soc_drop = e_move / scene.robot_capacity_kwh * 100.0
        assert math.isclose(soc_drop, 1.0, abs_tol=1e-9), "100m 应降 1% SOC（5.0kWh 容量）"

    def test_per_tick_deduction_uses_formula(self, scene):
        # 实测 TO_ZONE 阶段：每 tick 按 speed·dt 的位移折算扣能，验证能耗率/容量换算正确。
        e = SimulationEngine()
        e.start(speed=1, seed=scene.seed)
        while e._phase != "TO_ZONE":
            e.tick()
        dt = SimulationEngine.SIM_SEC_PER_TICK * e.speed
        moved = s_base_speed() * dt
        expected = (scene.move_energy_per_100m * moved / 100.0) \
                   / scene.robot_capacity_kwh * 100.0
        checked = 0
        while e._phase == "TO_ZONE" and checked < 3:
            before = e.robot.soc
            e.tick()
            assert math.isclose(before - e.robot.soc, expected, abs_tol=1e-9), \
                "移动扣能应使用 0.05kWh/100m 并按 5.0kWh 折算"
            checked += 1
        assert checked >= 1


class TestFiveChannelCharging:
    """五路独立充电：3.5kW/路、损耗0.05、效率0.95。"""

    def test_channel_energy_and_duration_formula(self, scene):
        e = SimulationEngine()
        e.start(speed=1, seed=scene.seed)
        while e._phase != "CHARGING":
            e.tick()
        active = [c for c in e.channels if c.state == "CHARGING"]
        assert len(active) == scene.channels == 5, "应五路并发充电"
        p_bat = scene.power_kw * (1 - scene.transfer_loss)
        for ch in active:
            v = e.vehicles[ch.vehicle_id]
            e_need = (scene.target_soc - v["soc"]) / 100.0 * scene.vehicle_cap_kwh
            assert math.isclose(ch.e_need, e_need, abs_tol=1e-9)
            assert math.isclose(ch.t_total, ch.e_need / p_bat * 3600.0, abs_tol=1e-6), \
                "充电时长 = E_need / (P_ch·(1-损耗))"

    def test_store_energy_formula(self, scene):
        # E_store = E_need / (η·(1-λ))，验证储能侧消耗大于交付车辆电量
        e_need = (scene.target_soc - 30.0) / 100.0 * scene.vehicle_cap_kwh
        e_store = e_need / (scene.charge_efficiency * (1 - scene.transfer_loss))
        assert e_store > e_need
        assert math.isclose(e_store, e_need / (0.95 * 0.95), abs_tol=1e-9)

    def test_per_tick_power_accounting_five_channels(self, scene):
        # 实测 1 tick：五路各自向车辆交付 P_bat，并各自从机器人储能扣 P_store。
        e = SimulationEngine()
        e.start(speed=1, seed=scene.seed)
        while e._phase != "CHARGING":
            e.tick()
        active = [c for c in e.channels if c.state == "CHARGING"]
        n = len(active)
        assert n == scene.channels
        dt = SimulationEngine.SIM_SEC_PER_TICK * e.speed
        p_bat = scene.power_kw * (1 - scene.transfer_loss)
        p_store = scene.power_kw / scene.charge_efficiency

        before_soc = {c.vehicle_id: e.vehicles[c.vehicle_id]["soc"] for c in active}
        robot_before = e.robot.soc
        e.tick()
        for ch in active:
            vid = ch.vehicle_id
            delta = e.vehicles[vid]["soc"] - before_soc[vid]
            exp = min(scene.target_soc - before_soc[vid],
                      p_bat * (dt / 3600.0) / scene.vehicle_cap_kwh * 100.0)
            assert math.isclose(delta, exp, abs_tol=1e-6), "单车 SOC 增量应等于 P_bat 折算值"
        # 机器人储能总扣 = 并发通道数 × 单路 P_store 折算（效率在储能侧一次性折算）
        exp_robot = n * p_store * (dt / 3600.0) / scene.robot_capacity_kwh * 100.0
        assert math.isclose(robot_before - e.robot.soc, exp_robot, abs_tol=1e-6), \
            "五路并发时机器人储能扣减应为单路的 5 倍"

    def test_five_channels_have_distinct_vehicles(self, scene):
        e = SimulationEngine()
        e.start(speed=1, seed=scene.seed)
        while e._phase != "CHARGING":
            e.tick()
        vids = [c.vehicle_id for c in e.channels if c.state == "CHARGING"]
        assert len(vids) == 5 == len(set(vids))


class TestTargetSOC:
    """充电目标 SOC=80%：到目标即停，不超额。"""

    def test_charge_stops_at_target(self, scene):
        e, _, _ = _run(scene.seed)
        for t in e.tasks:
            if t.status == "COMPLETED":
                assert math.isclose(e.vehicles[t.vehicle_id]["soc"], scene.target_soc,
                                    abs_tol=1e-9), "完成充电的车辆应恰好停在目标 SOC"
        assert any(ev["type"] == "CHARGE_DONE" for ev in e.events)


class TestReturnToBase:
    """返基站阈值：SOC≤阈值触发 RETURN，回基站 RECHARGE，补满恢复 IDLE。"""

    def test_threshold_triggers_return_and_full_recharge(self, scene):
        e = SimulationEngine()
        e.start(speed=60, seed=scene.seed)
        # 构造白盒前提：令机器人在 DEPART 阶段电量低于阈值
        e._active_batch = []
        e._need_recharge = False
        for ch in e.channels:
            ch.state = "EMPTY"
            ch.vehicle_id = None
        e._phase = "DEPART"
        e._phase_t = 0.0
        e._phase_dur = 1.0
        e.robot.soc = scene.low_energy_threshold - 0.1

        e.tick()
        assert e._phase == "RETURN", "SOC≤阈值应触发 RETURN"
        assert e.robot.status == "RETURNING"
        e.tick()
        assert e._phase == "RECHARGE", "到达基站后应转 RECHARGE"
        assert e.robot.status == "RECHARGING"
        types = {ev["type"] for ev in e.events}
        assert "RETURN_BASE" in types

        for _ in range(500):
            e.tick()
            if e._phase == "IDLE":
                break
        assert e._phase == "IDLE", "补满后应恢复待命"
        assert math.isclose(e.robot.soc, 100.0, abs_tol=1e-9), "应补满至 100%"
        assert e._need_recharge is False
        assert "RECHARGE_DONE" in {ev["type"] for ev in e.events}

    def test_closed_loop_recharge_then_resume_dispatch(self, scene):
        e, _, _ = _run(scene.seed)
        events = list(e.events)
        types = {ev["type"] for ev in events}
        assert "RETURN_BASE" in types
        assert "RECHARGE_DONE" in types
        # 返基站补能完成后仍有新批次创建，证明恢复派单
        ri = next(i for i, ev in enumerate(events) if ev["type"] == "RECHARGE_DONE")
        assert any(ev["type"] == "BATCH_CREATED" for ev in events[ri + 1:]), \
            "补能完成后应继续派单"


class TestClosedLoop:
    """完整闭环可复现：24 辆有效车各充一次，包含关键事件。"""

    def test_full_loop_is_reproducible(self, scene):
        _, tasks1, events1 = _run(scene.seed)
        _, tasks2, events2 = _run(scene.seed)
        assert tasks1 == tasks2, "同 seed 应产生完全相同的任务序列"
        assert events1 == events2, "同 seed 应产生完全相同的事件序列"

    def test_all_effective_vehicles_charged_exactly_once(self, scene):
        e, _, _ = _run(scene.seed)
        view = sch.static_view(scene)
        effective = {vid for vid in view if sch.is_effective(vid, scene, view)}
        assert len(effective) == 24, "标准场景应有 24 辆有效车（仿真数据）"
        completed = {t.vehicle_id for t in e.tasks if t.status == "COMPLETED"}
        assert completed == effective, "24 辆有效车应各完成一次充电"
        counts = Counter(t.vehicle_id for t in e.tasks)
        assert max(counts.values()) == 1, "同一辆车不得被重复派单"

    def test_key_event_types_present(self, scene):
        e, _, _ = _run(scene.seed)
        types = {ev["type"] for ev in e.events}
        for key in ("SIM_STARTED", "BATCH_CREATED", "TASK_ASSIGNED", "DOCK_OK",
                    "CHARGE_DONE", "VEHICLE_DEPARTED", "RETURN_BASE", "RECHARGE_DONE"):
            assert key in types, f"事件 {key} 应在闭环中出现"

    def test_energy_never_out_of_range(self, scene):
        e = SimulationEngine()
        e.start(speed=60, seed=scene.seed)
        socs = []
        for _ in range(2000):
            e.tick()
            socs.append(e.robot.soc)
        assert min(socs) >= 0.0, "机器人电量不应为负"
        assert max(socs) <= 100.0, "机器人电量不应超过 100%"
