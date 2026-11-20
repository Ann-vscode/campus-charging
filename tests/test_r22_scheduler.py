"""R2.2 充电批次调度器——独立验收测试（全部为仿真数据）。

验收对象：backend/scheduler.py（打分 / is_effective / select_batch / can_dispatch / zone_averages）。
本测试为独立可复现验收，不改动任何业务代码；所有数值断言引用 scene 或契约常量。
参考 tests/conftest.py：文件顶部把项目根加入 sys.path。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import math
from dataclasses import replace

import pytest

from backend.config import load_scenario
from backend.engine import SimulationEngine
from backend import scheduler as sch

# 契约 contracts/simulation_params.md 第 1/5 节给定基线（仿真参数）
CONTRACT_WEIGHTS = {
    "low_soc": 0.35,
    "avg_soc": 0.20,
    "distance": 0.25,
    "robot_energy": 0.20,
}


@pytest.fixture(scope="module")
def scene():
    return load_scenario()


@pytest.fixture(scope="module")
def view(scene):
    return sch.static_view(scene)


def _make_view(**overrides):
    """构造一辆仿真候选车的 view 条目，缺省为有效 PARKED 车。"""
    base = {"soc": 50.0, "status": "PARKED", "online": True, "stale": False,
            "x": 0.0, "y": 0.0, "zone": "A", "slot": 1}
    base.update(overrides)
    return base


class TestReproducibility:
    """可复现性：相同 seed + 相同场景，select_batch 多次结果完全一致。"""

    def test_same_view_repeated_calls_identical(self, scene, view):
        pos = scene.base
        b1 = sch.select_batch(scene, view, pos, 100.0, zone_focus=None)
        b2 = sch.select_batch(scene, view, pos, 100.0, zone_focus=None)
        b3 = sch.select_batch(scene, view, pos, 100.0, zone_focus=None)
        assert b1 == b2 == b3, "同场景多次调度必须完全一致（仿真可复现）"

    def test_dict_insertion_order_does_not_change_result(self, scene, view):
        # 同分以 vid 字典序 tie-break，故打乱 view 插入顺序不应影响结果
        reversed_view = dict(reversed(list(view.items())))
        pos = scene.base
        assert sch.select_batch(scene, view, pos, 100.0, zone_focus="A") == \
               sch.select_batch(scene, reversed_view, pos, 100.0, zone_focus="A")

    def test_zone_focus_repeated_calls_identical(self, scene, view):
        pos = scene.base
        r1 = sch.select_batch(scene, view, pos, 100.0, zone_focus="B")
        r2 = sch.select_batch(scene, view, pos, 100.0, zone_focus="B")
        assert r1 == r2


class TestWeights:
    """权重正确性：低 SOC 主导；权重来自场景配置而非硬编码。"""

    def test_weights_from_scene_match_contract(self, scene):
        assert scene.weights == CONTRACT_WEIGHTS
        assert math.isclose(sum(scene.weights.values()), 1.0, abs_tol=1e-9)

    def test_low_soc_weight_dominates_distance(self, scene):
        # 极端场景：V_LOW 电量极低但远在 d_max，V_NEAR 电量稍高但就在机器人脚下。
        # low_soc 权重 0.35 > distance 权重 0.25，故极低电量者应胜出。
        pos = scene.base
        vw = {
            "V_LOW": _make_view(soc=0.0, x=pos[0] + scene.d_max, y=pos[1], zone="A"),
            "V_NEAR": _make_view(soc=79.0, x=pos[0], y=pos[1], zone="A"),
        }
        za = sch.zone_averages(scene, vw)
        s_low = sch.score_vehicle("V_LOW", scene, vw, pos, 100.0, za)
        s_near = sch.score_vehicle("V_NEAR", scene, vw, pos, 100.0, za)
        assert s_low > s_near, "0.35·low_soc 应压过 0.25·distance"
        assert sch.select_batch(scene, vw, pos, 100.0, zone_focus=None)[0] == "V_LOW"

    def test_ranking_driven_by_configured_weights(self, scene):
        # 把权重改为仅 distance=1，排序应反转，证明打分由配置权重驱动
        pos = scene.base
        vw = {
            "V_LOW": _make_view(soc=0.0, x=pos[0] + scene.d_max, y=pos[1], zone="A"),
            "V_NEAR": _make_view(soc=79.0, x=pos[0], y=pos[1], zone="A"),
        }
        dist_only = replace(scene, weights={"low_soc": 0.0, "avg_soc": 0.0,
                                            "distance": 1.0, "robot_energy": 0.0})
        assert sch.select_batch(dist_only, vw, pos, 100.0, zone_focus=None)[0] == "V_NEAR"


class TestBatchSize:
    """每批 ≤ max_per_batch（≤5）。"""

    @pytest.mark.parametrize("zone_focus", [None, "A", "B", "C"])
    @pytest.mark.parametrize("robot_soc", [10.0, 50.0, 100.0])
    def test_batch_never_exceeds_max(self, scene, view, zone_focus, robot_soc):
        batch = sch.select_batch(scene, view, scene.base, robot_soc, zone_focus=zone_focus)
        assert len(batch) <= scene.max_per_batch
        assert len(batch) == len(set(batch)), "同一批不得出现重复车辆"


class TestEffectiveFilter:
    """有效性过滤：OFFLINE / STALE / SOC≥目标 不入选；PARKED 且 SOC<目标 入选。"""

    def test_invalid_vehicles_excluded(self, scene, view):
        eff = {vid for vid in view if sch.is_effective(vid, scene, view)}
        assert "A03" not in eff, "OFFLINE 车 A03 应被过滤"
        assert "B04" not in eff, "STALE 车 B04 应被过滤"
        assert "A08" not in eff, "SOC=90≥80 的 A08 应被过滤"
        assert "C07" not in eff, "SOC=95≥80 的 C07 应被过滤"
        assert "A01" in eff, "PARKED 且 SOC<80 的 A01 应入选"
        assert "A06" in eff, "PARKED 且 SOC<80 的 A06 应入选"

    def test_batch_excludes_invalid(self, scene, view):
        batch = sch.select_batch(scene, view, scene.base, 100.0, zone_focus=None)
        for bad in ("A03", "B04", "A08", "C07"):
            assert bad not in batch


class TestCrossZoneRefill:
    """跨区补位：本区有效车不足 5 时从邻近区补齐，总数仍 ≤5。"""

    def test_refill_from_nearest_zone_when_local_short(self, scene, view):
        # 契约第 6 节：本区不足按分区中心到机器人距离由近到远补位
        assert scene.refill_rule == "nearest_zone_if_short"
        local_view = dict(view)
        for vid in local_view:
            if local_view[vid]["zone"] == "A" and vid not in ("A01", "A05"):
                local_view[vid] = dict(local_view[vid], status="CHARGED", soc=scene.target_soc)

        local_eff = [v for v in local_view
                     if sch.is_effective(v, scene, local_view) and local_view[v]["zone"] == "A"]
        assert len(local_eff) == 2, "构造前提：本区仅 2 辆有效车"

        batch = sch.select_batch(scene, local_view, scene.base, 100.0, zone_focus="A")
        assert len(batch) <= scene.max_per_batch
        assert len(batch) == scene.max_per_batch, "全区有效车充足时应补满到上限"
        assert set(local_eff).issubset(set(batch)), "本区有效车应全部入选"
        refilled = [v for v in batch if v not in local_eff]
        assert refilled, "应发生跨区补位"
        # 基站(70,40) 距 B 区中心最近，补位应来自 B 区
        assert all(local_view[v]["zone"] == "B" for v in refilled), "应从最近的 B 区补位"

    def test_no_overflow_when_total_short(self, scene, view):
        # 全区有效车不足 5 时，按实际数量派发，不得虚构车辆
        tiny = dict(view)
        for vid in tiny:
            if vid not in ("A01", "A05"):
                tiny[vid] = dict(tiny[vid], status="CHARGED", soc=scene.target_soc)
        batch = sch.select_batch(scene, tiny, scene.base, 100.0, zone_focus="A")
        assert len(batch) == 2 <= scene.max_per_batch


class TestScoreFormula:
    """打分公式：score = 0.35·S_lowSOC + 0.20·S_avgSOC + 0.25·S_dist + 0.20·S_robot。"""

    def test_score_matches_formula(self, scene, view):
        pos = scene.base
        robot_soc = 63.0
        za = sch.zone_averages(scene, view)
        for vid in ("A01", "B03", "C08"):
            v = view[vid]
            expected = (scene.weights["low_soc"] * (1 - v["soc"] / 100.0)
                        + scene.weights["avg_soc"] * (1 - za.get(v["zone"], v["soc"]) / 100.0)
                        + scene.weights["distance"]
                        * max(0.0, 1 - sch.distance(pos, (v["x"], v["y"])) / scene.d_max)
                        + scene.weights["robot_energy"] * (robot_soc / 100.0))
            actual = sch.score_vehicle(vid, scene, view, pos, robot_soc, za)
            assert math.isclose(actual, expected, abs_tol=1e-9), f"{vid} 打分与公式不一致"

    def test_batch_order_matches_score_desc(self, scene, view):
        pos = scene.base
        robot_soc = 100.0
        batch = sch.select_batch(scene, view, pos, robot_soc, zone_focus=None)
        za = sch.zone_averages(scene, view)
        scores = [sch.score_vehicle(vid, scene, view, pos, robot_soc, za) for vid in batch]
        # score 降序（同分已被 vid 字典序 tie-break）
        for a, b in zip(scores, scores[1:]):
            assert a + 1e-9 >= b, "批次排序应与 score 降序一致"


class TestEnergyGate:
    """can_dispatch 能源守门：余能不足返回 False，并触发返基站。"""

    def test_can_dispatch_false_when_energy_insufficient(self, scene, view):
        pos = scene.base
        batch = sch.select_batch(scene, view, pos, 100.0, zone_focus="A")
        assert batch
        # robot_soc 等于安全余量 → 可用储能为 0 → 任何非空批次都不可派发
        assert sch.available_energy_kwh(scene, scene.safety_margin) == 0.0
        assert sch.can_dispatch(scene, batch, view, pos, scene.safety_margin) is False

    def test_can_dispatch_true_when_energy_sufficient(self, scene, view):
        pos = scene.base
        one = ["B03"]
        assert sch.can_dispatch(scene, one, view, pos, scene.robot_initial_soc) is True

    def test_low_energy_triggers_return_phase(self, scene):
        e = SimulationEngine()
        e.start(speed=60, seed=scene.seed)
        e.robot.soc = scene.safety_margin  # 余能不足
        e.tick()
        assert e._phase == "RETURN", "预计储能不足时应先返基站"
        assert e.robot.status == "RETURNING"
