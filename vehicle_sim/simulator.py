#!/usr/bin/env python3
"""R2.1 车辆遥测模拟器（仿真数据，非真实车辆）。

把场景 YAML 里的车辆状态，按固定周期以 VehicleTelemetry 结构通过 MQTT 上报，
模拟"车辆 → 平台"的物联网遥测通道。基于已克隆的 refs/paho.mqtt.python 二次开发。

字段严格对齐 contracts/telemetry.json 的 VehicleTelemetry（required 9 项、无额外字段）。
车辆 ID 来自场景配置（如 A01），不写死格式。

用法：
    python -m vehicle_sim.simulator --dry-run                 # 不连 broker，打印一帧样例
    python -m vehicle_sim.simulator --broker 127.0.0.1 --rounds 5 --interval 1
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time

import yaml

try:  # 优先用隔离 venv 安装的 paho；否则从仓库已克隆的 refs 加载（二次开发）
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover - 仅在未 pip install 时触发
    _REFS = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "refs", "paho.mqtt.python", "src",
    )
    if os.path.isdir(_REFS):
        sys.path.insert(0, _REFS)
    import paho.mqtt.client as mqtt

from .topics import vehicle_telemetry_topic, VEHICLE_TELEMETRY_WILDCARD

UTC_FMT = "%Y-%m-%dT%H:%M:%S."
SCENARIO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scenarios", "campus_basic.yaml",
)

# VehicleTelemetry 允许的全部字段（契约 additionalProperties=false）
TELEMETRY_FIELDS = {
    "vehicle_id", "zone", "slot", "x", "y", "soc", "status", "timestamp", "stale",
}
VALID_STATUS = {"PARKED", "SELECTED", "DOCKING", "CHARGING", "CHARGED", "STALE", "OFFLINE"}


def _iso_utc(dt: datetime.datetime) -> str:
    return dt.strftime(UTC_FMT) + f"{dt.microsecond // 1000:03d}Z"


def load_vehicles(path: str | None = None) -> list[dict]:
    """从场景 YAML 读车辆原始字典（数据驱动）。"""
    with open(path or SCENARIO, "r", encoding="utf-8") as f:
        d = yaml.safe_load(f)
    return [dict(v) for v in d["vehicles"]]


def build_telemetry(v: dict, *, tick: int = 0, drift: float = 0.0,
                    now: datetime.datetime | None = None) -> dict | None:
    """由场景车辆构造一帧 VehicleTelemetry。

    - 离线车（online=false / status=offline）不产生遥测 -> 返回 None。
    - stale 样本：上报 status=STALE、stale=true、timestamp 为 120 秒前，模拟陈旧数据。
    - drift>0 时每 tick 轻微掉电，便于端到端观察到数据变化（仿真）。
    """
    if not bool(v.get("online", True)):
        return None
    scene_status = str(v.get("status", "parked")).lower()
    if scene_status == "offline":
        return None
    now = now or datetime.datetime.now(datetime.timezone.utc)
    stale = scene_status == "stale"
    ts = now - datetime.timedelta(seconds=120) if stale else now
    soc = max(0.0, min(100.0, float(v["soc"]) - drift * tick))
    payload = {
        "vehicle_id": str(v["id"]),
        "zone": str(v["zone"]),
        "slot": int(v["slot"]),
        "x": float(v["x"]),
        "y": float(v["y"]),
        "soc": round(soc, 2),
        "status": "STALE" if stale else "PARKED",
        "timestamp": _iso_utc(ts),
        "stale": stale,
    }
    assert set(payload) == TELEMETRY_FIELDS, "字段必须与 telemetry.json 严格一致"
    assert payload["status"] in VALID_STATUS
    return payload


def make_client(client_id: str):
    """兼容 Paho 1.x / 2.x 的构造方式。"""
    if hasattr(mqtt, "CallbackAPIVersion"):
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    return mqtt.Client(client_id=client_id)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="校园共享电动车车辆遥测模拟器（仿真数据）")
    ap.add_argument("--broker", default="127.0.0.1", help="MQTT broker 地址")
    ap.add_argument("--port", type=int, default=1883, help="MQTT broker 端口")
    ap.add_argument("--scenario", default=None, help="场景 YAML 路径（默认 campus_basic.yaml）")
    ap.add_argument("--interval", type=float, default=2.0, help="上报周期（秒）")
    ap.add_argument("--rounds", type=int, default=0, help="上报轮数，0 表示持续运行")
    ap.add_argument("--drift", type=float, default=0.0, help="每轮掉电量（仿真，默认 0）")
    ap.add_argument("--dry-run", action="store_true", help="不连 broker，打印一帧样例后退出")
    args = ap.parse_args(argv)

    vehicles = load_vehicles(args.scenario)
    if args.dry_run:
        emitted = 0
        for v in vehicles:
            p = build_telemetry(v, tick=0)
            if p is not None:
                print(json.dumps(p, ensure_ascii=False))
                emitted += 1
        print(f"[仿真] 车辆总数={len(vehicles)}，本帧上报={emitted}（离线车不上报）；"
              f"topic={VEHICLE_TELEMETRY_WILDCARD}，未连接 broker", file=sys.stderr)
        return 0

    client = make_client(f"vehicle-sim-{os.getpid()}")
    client.connect(args.broker, args.port, 60)
    client.loop_start()
    round_no = 0
    try:
        while args.rounds == 0 or round_no < args.rounds:
            published = 0
            for v in vehicles:
                p = build_telemetry(v, tick=round_no, drift=args.drift)
                if p is None:
                    continue
                client.publish(
                    vehicle_telemetry_topic(p["vehicle_id"]),
                    json.dumps(p, ensure_ascii=False), qos=1, retain=False,
                )
                published += 1
            round_no += 1
            print(f"[仿真] 第 {round_no} 轮：发布 {published} 条 VehicleTelemetry"
                  f"（{len(vehicles) - published} 辆离线未上报）")
            if args.rounds == 0 or round_no < args.rounds:
                time.sleep(args.interval)
    finally:
        client.loop_stop()
        client.disconnect()
    print(f"[仿真] 完成 {round_no} 轮，全部数据为仿真数据。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
