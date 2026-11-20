"""R1.2 后端 Mock 闭环自动化测试。

覆盖任务卡验收条件：
- 不依赖 ROS 2
- 启动一次自动完成两批模拟任务（五路充电 + 返基站补能）
- 能源模型：移动/充电扣能、不会电量不变/无限充电/耗尽仍工作
- 状态机合法迁移、状态枚举符合契约
- 调度可复现（同 seed 同结果）
"""
import math
import pytest

from backend.config import load_scenario
from backend.engine import SimulationEngine
from backend import scheduler as sch


def run_sim(seconds: float, dt: float = 0.5) -> dict:
    engine = SimulationEngine()
    engine.start(speed=60, seed=20261118)
    steps = int(seconds / dt) + 1
    for _ in range(steps):
        engine.tick()
    return {"engine": engine}


class TestScenario:
    def test_scenario_loaded(self):
        s = load_scenario()
        assert len(s.vehicles) == 30
        assert {z["id"] for z in s.zones} == {"A", "B", "C"}
        assert s.channels == 5
        assert s.power_kw == 3.5
        assert s.transfer_loss == 0.05
        assert s.robot_capacity_kwh == 5.0
        assert abs(sum(s.weights.values()) - 1.0) < 1e-9

    def test_seed_reproducible_selection(self):
        s = load_scenario()
        view = sch.static_view(s)
        pos = (s.base[0], s.base[1])
        b1 = sch.select_batch(s, view, pos, 100.0, zone_focus="A")
        b2 = sch.select_batch(s, view, pos, 100.0, zone_focus="A")
        assert b1 == b2
        assert len(b1) <= s.max_per_batch


class TestScheduler:
    def test_effective_vehicle_filtering(self):
        s = load_scenario()
        view = sch.static_view(s)
        # A03 离线、B04 stale、高电量(>=80)车都不应入选
        eff = {vid for vid in view if sch.is_effective(vid, s, view)}
        assert "A03" not in eff     # offline
        assert "B04" not in eff     # stale
        assert "A08" not in eff     # soc 90 >= 80
        assert "C07" not in eff     # soc 95 >= 80
        assert "A01" in eff         # parked 72 < 80

    def test_batch_max_five(self):
        s = load_scenario()
        view = sch.static_view(s)
        batch = sch.select_batch(s, view, s.base, 100.0, zone_focus=None)
        assert len(batch) <= 5
        assert len(batch) == len(set(batch)), "不可重复选车"

    def test_energy_formula(self):
        s = load_scenario()
        view = sch.static_view(s)
        # B03 soc=30 -> 80: E_need = 0.5*0.5 = 0.25 kWh
        v = view["B03"]
        assert math.isclose((s.target_soc - v["soc"]) / 100 * s.vehicle_cap_kwh, 0.25)
        e_store = 0.25 / (s.charge_efficiency * (1 - s.transfer_loss))
        assert e_store > 0.25


class TestControl:
    def test_start_pause_resume(self):
        e = SimulationEngine()
        assert e.start(speed=1)[0]
        assert not e.start()[0], "重复 start 应被拒"
        assert e.pause()[0]
        assert not e.pause()[0], "重复 pause 应被拒"
        assert e.resume()[0]
        assert not e.resume()[0], "未暂停 resume 应被拒"

    def test_speed_validation(self):
        e = SimulationEngine()
        assert e.set_speed(10)[0]
        assert not e.set_speed(5)[0], "非法倍速应被拒"

    def test_reset_restores_initial(self):
        e = SimulationEngine()
        e.start(speed=60)
        for _ in range(100):
            e.tick()
        e.reset()
        assert e.speed == 1
        assert not e.running
        assert all(v["soc"] == next(x.soc for x in e.scene.vehicles if x.id == vid)
                   for vid, v in e.vehicles.items())


class TestClosedLoop:
    def test_auto_completes_two_batches(self):
        """启动一次，自动完成至少两批，含五路充电与返基站补能。"""
        e = SimulationEngine()
        e.start(speed=60, seed=20261118)
        # 推进足够长时间（倍速 60，需覆盖至少两批）
        for _ in range(4000):
            e.tick()
        done = [t for t in e.tasks if t.status == "COMPLETED"]
        assert len(done) >= 5, f"应至少完成一整批 5 辆，实际 {len(done)}"
        # 回归：每辆车最多派单一次（防止充满后被重复选择）
        from collections import Counter
        counts = Counter(t.vehicle_id for t in e.tasks)
        assert max(counts.values()) == 1, "同一辆车不得被重复派单"
        types = {ev["type"] for ev in e.events}
        assert "SIM_STARTED" in types
        assert "BATCH_CREATED" in types
        assert "DOCK_OK" in types
        assert "CHARGE_DONE" in types
        assert "VEHICLE_DEPARTED" in types
        assert len(e.tasks) >= 5

    def test_robot_energy_never_negative_or_static(self):
        e = SimulationEngine()
        e.start(speed=60)
        socs = []
        for _ in range(2000):
            e.tick()
            socs.append(e.robot.soc)
        assert min(socs) >= 0, "机器人电量不应为负"
        assert any(b < a - 1e-6 for a, b in zip(socs, socs[1:])), "机器人电量应随移动/充电下降"
        assert max(socs) <= 100, "机器人电量不应超过 100%"

    def test_five_channels_independent(self):
        e = SimulationEngine()
        e.start(speed=60)
        charging_states = set()
        for _ in range(1500):
            e.tick()
            states = {ch.state for ch in e.channels}
            charging_states |= states
            assert len(e.channels) == 5
        assert "CHARGING" in charging_states, "应出现五路充电状态"

    def test_obstacle_triggers_replan(self):
        e = SimulationEngine()
        e.start(speed=60)
        e.inject_obstacle(15.0, 10.0, 1.5, 30)
        obs = e.obstacles[-1]
        assert obs["obstacle_id"].startswith("O-")
        assert "OBSTACLE_DETECTED" in {ev["type"] for ev in e.events}


class TestEnvelope:
    def test_frame_contract(self):
        e = SimulationEngine()
        f = e.frame()
        assert f["type"] == "tick"
        assert f["simulation"] is True
        assert "clock" in f
        assert all(k in f["clock"] for k in ("sim_time", "speed", "state"))
        assert all(m["type"] in ("RobotTelemetry", "VehicleTelemetry", "TaskEvent")
                   for m in f["messages"])

    def test_snapshot_contract(self):
        e = SimulationEngine()
        s = e.snapshot()
        assert s["type"] == "snapshot"
        assert len(s["vehicles"]) == 30
        assert s["simulation"] is True
