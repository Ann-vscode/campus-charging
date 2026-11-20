"""场景加载与配置：数据驱动，改 scenarios/*.yaml 即可改车辆数/停车区/电量。"""
from __future__ import annotations

import os
import yaml
from dataclasses import dataclass, field
from typing import Dict, List


DEFAULT_SCENARIO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scenarios", "campus_basic.yaml",
)


@dataclass
class Vehicle:
    id: str
    zone: str
    slot: int
    x: float
    y: float
    soc: float
    status: str            # parked / low_battery / offline / stale（场景原始）
    online: bool


@dataclass
class Scene:
    scenario_id: str
    name: str
    version: str
    base: tuple             # 基站坐标 (x, y)
    robot_capacity_kwh: float
    robot_initial_soc: float
    move_energy_per_100m: float
    charge_efficiency: float
    zones: List[dict]
    vehicles: List[Vehicle]
    channels: int
    channel_ids: List[str]
    power_kw: float
    transfer_loss: float
    max_per_batch: int
    weights: Dict[str, float]
    target_soc: float
    refill_rule: str
    speed_options: List[int]
    seed: int = 20261118
    low_energy_threshold: float = 20.0   # 仿真假设
    safety_margin: float = 10.0          # 派单保留余量（仿真假设）
    vehicle_cap_kwh: float = 0.5         # 单车电池容量（仿真假设）
    d_max: float = 100.0                 # 打分距离上限（仿真假设）


def load_scenario(path: str | None = None) -> Scene:
    with open(path or DEFAULT_SCENARIO, "r", encoding="utf-8") as f:
        d = yaml.safe_load(f)
    r = d["robot"]
    c = d["charging"]
    s = d["scheduler"]
    sim = d["simulation"]
    vehicles = [Vehicle(
        id=str(v["id"]), zone=v["zone"], slot=int(v["slot"]),
        x=float(v["x"]), y=float(v["y"]), soc=float(v["soc"]),
        status=v["status"], online=bool(v["online"]),
    ) for v in d["vehicles"]]
    return Scene(
        scenario_id="campus-default-v1",
        name=d["meta"]["name"],
        version=str(d["meta"]["version"]),
        base=(float(r["start_base"]["x"]), float(r["start_base"]["y"])),
        robot_capacity_kwh=float(r["battery_capacity_kwh"]),
        robot_initial_soc=float(r["initial_soc"]),
        move_energy_per_100m=float(r["move_energy_per_100m_kwh"]),
        charge_efficiency=float(r["charge_efficiency"]),
        zones=d["zones"],
        vehicles=vehicles,
        channels=int(c["channels"]),
        channel_ids=list(c["channel_ids"]),
        power_kw=float(c["power_kw"]),
        transfer_loss=float(c["transfer_loss"]),
        max_per_batch=int(s["max_per_batch"]),
        weights={k: float(v) for k, v in s["weights"].items()},
        target_soc=float(s["target_soc"]),
        refill_rule=s["refill_rule"],
        speed_options=list(sim["speed_options"]),
    )
