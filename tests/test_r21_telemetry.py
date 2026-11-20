"""R2.1 车辆遥测单元测试：payload 契约一致性 / 引擎写入 / 桥接校验。

不依赖 MQTT broker，可在依赖未就绪时先验证核心逻辑。
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from types import SimpleNamespace

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.engine import SimulationEngine  # noqa: E402
from backend.mqtt_bridge import MqttTelemetryBridge  # noqa: E402
from vehicle_sim.simulator import (  # noqa: E402
    TELEMETRY_FIELDS, build_telemetry, load_vehicles,
)


def _contract_schema():
    with open(os.path.join(ROOT, "contracts", "telemetry.json"), encoding="utf-8") as f:
        return json.load(f)


class TestSimulatorPayload:
    def test_fields_exactly_match_contract(self):
        v = load_vehicles()[0]
        p = build_telemetry(v)
        assert set(p) == TELEMETRY_FIELDS, "字段必须与 telemetry.json 严格一致"
        assert p["vehicle_id"] == "A01", "车辆 ID 来自场景，非写死格式"

    def test_contract_schema_validation(self):
        jsonschema = pytest.importorskip("jsonschema")
        defn = _contract_schema()["definitions"]["VehicleTelemetry"]
        validator = jsonschema.Draft7Validator(defn)
        for v in load_vehicles():
            p = build_telemetry(v)
            if p is not None:
                errs = list(validator.iter_errors(p))
                assert not errs, f"{v['id']} 违反契约: {[e.message for e in errs]}"

    def test_offline_vehicle_emits_nothing(self):
        vs = {v["id"]: v for v in load_vehicles()}
        assert build_telemetry(vs["A03"]) is None, "离线车不上报遥测"
        assert build_telemetry(vs["A01"]) is not None

    def test_stale_sample_is_flagged(self):
        vs = {v["id"]: v for v in load_vehicles()}
        p = build_telemetry(vs["B04"])
        assert p["status"] == "STALE"
        assert p["stale"] is True

    def test_drift_lowers_soc(self):
        v = load_vehicles()[0]
        p0 = build_telemetry(v, tick=0, drift=0.5)
        p5 = build_telemetry(v, tick=5, drift=0.5)
        assert p5["soc"] < p0["soc"]

    def test_timestamp_is_utc_iso(self):
        p = build_telemetry(load_vehicles()[0],
                            now=datetime.datetime(2026, 11, 18, 9, 30, 0,
                                                  tzinfo=datetime.timezone.utc))
        assert p["timestamp"] == "2026-11-18T09:30:00.000Z"


class TestEngineUpsert:
    def setup_method(self):
        self.e = SimulationEngine()

    def _payload(self, vid="A01", soc=33.0, status="PARKED"):
        return {
            "vehicle_id": vid, "zone": "A", "slot": 1, "x": 5.0, "y": 5.0,
            "soc": soc, "status": status,
            "timestamp": "2026-11-18T09:30:00.000Z", "stale": status == "STALE",
        }

    def test_unknown_vehicle_rejected(self):
        assert self.e.upsert_vehicle_telemetry(self._payload("ZZZ")) is False

    def test_updates_soc_and_position(self):
        assert self.e.upsert_vehicle_telemetry(self._payload(soc=33.0)) is True
        v = self.e.vehicles["A01"]
        assert v["soc"] == 33.0 and v["x"] == 5.0 and v["status"] == "PARKED"

    def test_platform_busy_not_overridden(self):
        # 平台正在给 A01 充电：车辆侧陈旧 soc 不应覆盖平台结果
        self.e.vehicles["A01"]["status"] = "CHARGING"
        self.e.vehicles["A01"]["soc"] = 77.0
        ok = self.e.upsert_vehicle_telemetry(self._payload(soc=10.0))
        assert ok is True
        assert self.e.vehicles["A01"]["soc"] == 77.0, "平台服务中应保留平台侧 soc"

    def test_offline_and_stale_written_for_filtering(self):
        self.e.upsert_vehicle_telemetry(self._payload("A01", status="OFFLINE"))
        assert self.e.vehicles["A01"]["status"] == "OFFLINE"
        assert self.e.vehicles["A01"]["online"] is False
        self.e.upsert_vehicle_telemetry(self._payload("B04", status="STALE"))
        assert self.e.vehicles["B04"]["stale"] is True


class TestBridgeValidation:
    def setup_method(self):
        self.bridge = MqttTelemetryBridge(SimulationEngine())

    def _valid(self):
        return {
            "vehicle_id": "A01", "zone": "A", "slot": 1, "x": 5.0, "y": 5.0,
            "soc": 42.0, "status": "PARKED",
            "timestamp": "2026-11-18T09:30:00.000Z", "stale": False,
        }

    def test_valid_payload_passes(self):
        assert self.bridge._validate(self._valid()) == []

    def test_missing_field_rejected(self):
        p = self._valid(); del p["soc"]
        assert any("缺少字段" in e for e in self.bridge._validate(p))

    def test_extra_field_rejected(self):
        p = self._valid(); p["hack"] = 1
        assert any("额外字段" in e for e in self.bridge._validate(p))

    def test_bad_status_rejected(self):
        p = self._valid(); p["status"] = "BOGUS"
        assert any("非法 status" in e for e in self.bridge._validate(p))

    def test_bad_soc_rejected(self):
        p = self._valid(); p["soc"] = 101
        assert any("soc" in e for e in self.bridge._validate(p))

    def test_on_message_updates_engine(self):
        p = self._valid(); p["soc"] = 55.0
        msg = SimpleNamespace(payload=json.dumps(p).encode("utf-8"))
        self.bridge._on_message(None, None, msg)
        assert self.bridge.received == 1
        assert self.bridge.engine.vehicles["A01"]["soc"] == 55.0

    def test_on_message_rejects_malformed_json(self):
        msg = SimpleNamespace(payload=b"not json")
        self.bridge._on_message(None, None, msg)
        assert self.bridge.rejected == 1
