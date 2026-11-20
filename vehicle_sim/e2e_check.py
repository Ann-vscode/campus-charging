#!/usr/bin/env python3
"""R2.1 端到端联调自检（本机，无需 Docker/Mosquitto）。

流程：进程内启动 amqtt broker(1883) → 起一个订阅者统计消息 → 用 Paho 客户端
按 vehicle_sim.build_telemetry 发布 30 辆车 → 校验订阅者收到的消息数量/字段/schema。

这是"车辆 → broker → 平台"链路的可复现验证，全部为仿真数据。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from amqtt.broker import Broker  # noqa: E402
from vehicle_sim.simulator import (  # noqa: E402
    TELEMETRY_FIELDS, build_telemetry, load_vehicles, make_client,
)
from vehicle_sim.topics import VEHICLE_TELEMETRY_WILDCARD  # noqa: E402

HOST, PORT = "127.0.0.1", 18830  # 避开默认 1883，防止与用户环境冲突


def _broker_config():
    return {
        "listeners": {
            "default": {"type": "tcp", "bind": f"{HOST}:{PORT}", "max_connections": 20},
        },
        "sys_interval": 0,
        "auth": {"allow-anonymous": True, "plugins": []},
        "topic-check": {"enabled": False},
    }


async def run_check() -> int:
    broker = Broker(_broker_config())
    await broker.start()
    received = []
    ready = asyncio.Event()

    sub = make_client("e2e-subscriber")

    def on_connect(client, userdata, flags, rc, *args):
        client.subscribe(VEHICLE_TELEMETRY_WILDCARD, qos=1)

    def on_message(client, userdata, msg):
        received.append(json.loads(msg.payload.decode("utf-8")))

    sub.on_connect = on_connect
    sub.on_message = on_message
    sub.connect(HOST, PORT, 60)
    sub.loop_start()
    await asyncio.sleep(0.8)  # 等订阅建立

    pub = make_client("e2e-publisher")
    pub.connect(HOST, PORT, 60)
    pub.loop_start()
    vehicles = load_vehicles()
    expected = 0
    for v in vehicles:
        p = build_telemetry(v)
        if p is None:
            continue
        topic = f"campus/v1/sim/vehicles/{p['vehicle_id']}/telemetry"
        pub.publish(topic, json.dumps(p, ensure_ascii=False), qos=1)
        expected += 1
    # 等消息全部送达
    for _ in range(30):
        if len(received) >= expected:
            break
        await asyncio.sleep(0.1)
    await asyncio.sleep(0.3)
    pub.loop_stop(); pub.disconnect()
    sub.loop_stop(); sub.disconnect()
    await broker.shutdown()

    # 校验
    print(f"E2E expected={expected} received={len(received)}")
    assert len(received) == expected, f"收到 {len(received)} 条，预期 {expected} 条"
    assert all(set(m) == TELEMETRY_FIELDS for m in received), "字段必须严格匹配契约"
    ids = {m["vehicle_id"] for m in received}
    assert "A03" not in ids, "离线车不应上报"
    assert "A01" in ids
    try:
        import jsonschema
        defn = json.load(open(os.path.join(ROOT, "contracts", "telemetry.json"),
                              encoding="utf-8"))["definitions"]["VehicleTelemetry"]
        validator = jsonschema.Draft7Validator(defn)
        for m in received:
            errs = list(validator.iter_errors(m))
            assert not errs, f"契约校验失败 {m['vehicle_id']}: {[e.message for e in errs]}"
        print("E2E jsonschema validation: PASS")
    except ImportError:
        print("E2E jsonschema: skipped (not installed)")
    print("E2E RESULT: PASS — 车辆→broker→平台订阅链路完整（仿真数据）")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_check()))
