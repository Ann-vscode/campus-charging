"""R2.1 后端 MQTT 遥测接入层（仿真链路，默认关闭）。

订阅 vehicle_sim 发布的 VehicleTelemetry，经 schema 校验后写入 engine 的动态车辆视图。
不修改 api.md 契约：默认 CAMPUS_MQTT_ENABLED=0 时完全不影响 R1.2 闭环。

设计要点：
- 平台正在服务的车（SELECTED/DOCKING/CHARGING/CHARGED）只刷新时间戳，不用上报值覆盖 soc，
  避免车辆侧遥测与平台侧充电结果互相覆盖 —— 此时平台是权威。
- 上报的 OFFLINE / STALE 会被调度器 is_effective 正确过滤。
"""
from __future__ import annotations

import json
import os
import threading

try:
    import paho.mqtt.client as mqtt
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("缺少 paho-mqtt，请在隔离 venv 安装 paho-mqtt==2.1.0") from exc

TOPIC_PREFIX = "campus/v1/sim"
VEHICLE_TELEMETRY_WILDCARD = f"{TOPIC_PREFIX}/vehicles/+/telemetry"

DEFAULT_HOST = os.environ.get("CAMPUS_MQTT_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("CAMPUS_MQTT_PORT", "1883"))

REQUIRED_FIELDS = {
    "vehicle_id", "zone", "slot", "x", "y", "soc", "status", "timestamp", "stale",
}
VALID_STATUS = {"PARKED", "SELECTED", "DOCKING", "CHARGING", "CHARGED", "STALE", "OFFLINE"}
_PLATFORM_BUSY = {"SELECTED", "DOCKING", "CHARGING", "CHARGED"}


def _make_client(client_id: str):
    if hasattr(mqtt, "CallbackAPIVersion"):
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    return mqtt.Client(client_id=client_id)


class MqttTelemetryBridge:
    def __init__(self, engine, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                 topic: str = VEHICLE_TELEMETRY_WILDCARD, client_id: str = "campus-backend"):
        self.engine = engine
        self.host, self.port, self.topic = host, port, topic
        self._client = _make_client(client_id)
        self._client.on_message = self._on_message
        self._client.on_connect = self._on_connect
        self._running = False
        self._lock = threading.Lock()
        self.received = 0
        self.rejected = 0
        self.last_error = ""
        self._validator = None

    # ---------- Paho 回调 ----------
    def _on_connect(self, client, userdata, flags, rc, *args):
        client.subscribe(self.topic, qos=1)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception as e:
            self._reject(f"非法 JSON: {str(e)[:120]}")
            return
        errs = self._validate(payload)
        if errs:
            self._reject(errs[0])
            return
        if self.engine.upsert_vehicle_telemetry(payload):
            with self._lock:
                self.received += 1
        else:
            self._reject("未知 vehicle_id（不在当前场景）")

    # ---------- 校验 ----------
    def _validate(self, payload) -> list[str]:
        if not isinstance(payload, dict):
            return ["payload 不是 JSON 对象"]
        missing = REQUIRED_FIELDS - set(payload)
        if missing:
            return [f"缺少字段 {sorted(missing)}"]
        extra = set(payload) - REQUIRED_FIELDS
        if extra:
            return [f"额外字段 {sorted(extra)}（契约 additionalProperties=false）"]
        if payload["status"] not in VALID_STATUS:
            return [f"非法 status {payload['status']}"]
        soc = payload.get("soc")
        if not isinstance(soc, (int, float)) or not 0 <= soc <= 100:
            return ["soc 必须是 0-100 的数值"]
        st = payload.get("stale")
        if not isinstance(st, bool):
            return ["stale 必须是布尔值"]
        # 有 jsonschema 时用权威定义二次精校（可选依赖）
        if self._validator is None:
            self._validator = self._load_validator()
        if self._validator is not None:
            errs = list(self._validator.iter_errors(payload))
            if errs:
                return [e.message for e in errs[:2]]
        return []

    @staticmethod
    def _load_validator():
        try:
            import jsonschema
            root_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "contracts", "telemetry.json",
            )
            with open(root_path, "r", encoding="utf-8") as f:
                schema = json.load(f)
            return jsonschema.Draft7Validator(schema["definitions"]["VehicleTelemetry"])
        except Exception:
            return None  # jsonschema 缺失时仍用上面的轻量校验，不阻断仿真

    def _reject(self, reason: str):
        with self._lock:
            self.rejected += 1
            self.last_error = reason

    # ---------- 生命周期 ----------
    def start(self):
        if self._running:
            return
        self._client.connect(self.host, self.port, 60)
        self._client.loop_start()
        self._running = True

    def stop(self):
        if self._running:
            self._client.loop_stop()
            self._client.disconnect()
            self._running = False

    def status(self) -> dict:
        with self._lock:
            return {
                "enabled": True,
                "connected": bool(self._client.is_connected()),
                "topic": self.topic,
                "broker": f"{self.host}:{self.port}",
                "received": self.received,
                "rejected": self.rejected,
                "last_error": self.last_error,
                "simulation": True,
            }
