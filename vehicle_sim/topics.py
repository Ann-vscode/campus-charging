"""R2.1 MQTT Topic 约定（仿真专用）。

所有 topic 带 /sim/ 段，明确标识仿真链路，与真实车辆接入隔离。
"""
TOPIC_PREFIX = "campus/v1/sim"


def vehicle_telemetry_topic(vehicle_id: str) -> str:
    """单车遥测 topic：campus/v1/sim/vehicles/{vehicle_id}/telemetry"""
    return f"{TOPIC_PREFIX}/vehicles/{vehicle_id}/telemetry"


VEHICLE_TELEMETRY_WILDCARD = f"{TOPIC_PREFIX}/vehicles/+/telemetry"
