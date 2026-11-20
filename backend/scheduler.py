"""充电批次调度器（R2.2）+ 能源模型（R2.3）核心逻辑。

严格实现 contracts/simulation_params.md 第 2/5/6 节。
关键：调度读取"动态车辆状态视图" view（vid -> {soc,status,online,stale,x,y,zone}），
不再读静态 scene.vehicles——否则已充满车辆会被无限重复派单。
"""
from __future__ import annotations

import math
from typing import Dict, List, Tuple

from .config import Scene, Vehicle

SCENE_TO_CONTRACT = {
    "parked": "PARKED", "low_battery": "PARKED",
    "offline": "OFFLINE", "stale": "STALE",
}

# 车辆状态视图：vid -> dict(soc, status, online, stale, x, y, zone, slot)
StateView = Dict[str, dict]


def static_view(scene: Scene) -> StateView:
    return {
        v.id: {"soc": v.soc, "status": SCENE_TO_CONTRACT.get(v.status, "PARKED"),
               "online": v.online, "stale": v.status == "stale",
               "x": v.x, "y": v.y, "zone": v.zone, "slot": v.slot}
        for v in scene.vehicles
    }


def distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def zone_averages(scene: Scene, view: StateView) -> Dict[str, float]:
    acc: Dict[str, List[float]] = {}
    for vid, v in view.items():
        if v["online"] and not v["stale"] and v["status"] != "OFFLINE":
            acc.setdefault(v["zone"], []).append(v["soc"])
    return {z: sum(s) / len(s) for z, s in acc.items() if s}


def is_effective(vid: str, scene: Scene, view: StateView) -> bool:
    v = view[vid]
    return (v["online"] and not v["stale"]
            and v["status"] in ("PARKED",)   # 已选/充电中/充满的不再入选
            and v["soc"] < scene.target_soc - 1e-6)


def score_vehicle(vid: str, scene: Scene, view: StateView,
                  robot_pos, robot_soc: float, zone_avg: Dict[str, float]) -> float:
    v = view[vid]
    w = scene.weights
    s_low = 1 - v["soc"] / 100
    s_avg = 1 - zone_avg.get(v["zone"], v["soc"]) / 100
    d = distance(robot_pos, (v["x"], v["y"]))
    s_dist = max(0.0, 1 - d / scene.d_max)
    s_robot = robot_soc / 100
    return (w["low_soc"] * s_low + w["avg_soc"] * s_avg
            + w["distance"] * s_dist + w["robot_energy"] * s_robot)


def select_batch(scene: Scene, view: StateView, robot_pos, robot_soc: float,
                 zone_focus: str | None = None) -> List[str]:
    """按打分选一批车辆 ID（≤5）；先本区，不足跨区补齐，按 score 降序。"""
    zone_avg = zone_averages(scene, view)
    effective = [vid for vid in view if is_effective(vid, scene, view)]

    def ranked(pool: List[str]) -> List[str]:
        scored = [(score_vehicle(vid, scene, view, robot_pos, robot_soc, zone_avg), vid)
                  for vid in pool]
        scored.sort(key=lambda t: (-round(t[0], 9), t[1]))   # 同分 vid 字典序
        return [vid for _, vid in scored]

    selected: List[str] = []
    if zone_focus:
        selected = ranked([v for v in effective if view[v]["zone"] == zone_focus])[:scene.max_per_batch]

    if len(selected) < scene.max_per_batch:
        chosen = set(selected)
        others = [v for v in effective if v not in chosen]
        if zone_focus:
            centers = {}
            for z in scene.zones:
                zs = [v for v in scene.vehicles if v.zone == z["id"]]
                if zs:
                    centers[z["id"]] = (sum(x.x for x in zs) / len(zs),
                                        sum(x.y for x in zs) / len(zs))
            zone_order = sorted(
                {view[v]["zone"] for v in others},
                key=lambda z: distance(robot_pos, centers.get(z, (1e9, 1e9))),
            )
            for z in zone_order:
                for vid in ranked([v for v in others if view[v]["zone"] == z]):
                    if len(selected) >= scene.max_per_batch:
                        break
                    if vid not in chosen:
                        selected.append(vid)
                        chosen.add(vid)
        else:
            selected = ranked(others)[:scene.max_per_batch]
    return selected


def estimate_batch_energy(scene: Scene, batch: List[str], view: StateView, robot_pos) -> float:
    pos = robot_pos
    e_move = 0.0
    for vid in batch:
        v = view[vid]
        e_move += scene.move_energy_per_100m * distance(pos, (v["x"], v["y"])) / 100
        pos = (v["x"], v["y"])
    e_move += scene.move_energy_per_100m * distance(pos, scene.base) / 100
    e_store_total = 0.0
    for vid in batch:
        e_need = (scene.target_soc - view[vid]["soc"]) / 100 * scene.vehicle_cap_kwh
        e_store_total += max(0.0, e_need / (scene.charge_efficiency * (1 - scene.transfer_loss)))
    return e_move + e_store_total


def available_energy_kwh(scene: Scene, robot_soc: float) -> float:
    return max(0.0, robot_soc - scene.safety_margin) / 100 * scene.robot_capacity_kwh


def can_dispatch(scene: Scene, batch: List[str], view: StateView,
                 robot_pos, robot_soc: float) -> bool:
    return bool(batch) and estimate_batch_energy(scene, batch, view, robot_pos) <= available_energy_kwh(scene, robot_soc)
