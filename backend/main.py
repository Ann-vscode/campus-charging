"""FastAPI 应用：R1.2 后端 Mock 闭环。

契约：contracts/api.md v1.0.0。所有响应统一信封 + simulation:true。
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from .engine import SimulationEngine, now_iso

engine = SimulationEngine()
mqtt_bridge = None   # R2.1：默认 None；CAMPUS_MQTT_ENABLED=1 时在 lifespan 中启用


async def _tick_loop():
    """后台 10 Hz 推进仿真时钟并向所有 WS 订阅者广播 tick。"""
    while True:
        frame = engine.tick()
        dead = []
        for q in list(engine._subscribers):
            try:
                q.put_nowait(frame)
            except asyncio.QueueFull:
                dead.append(q)
            except Exception:
                dead.append(q)
        for q in dead:
            engine._subscribers.discard(q)
        await asyncio.sleep(0.1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mqtt_bridge
    task = asyncio.create_task(_tick_loop())
    # R2.1：可选启用 MQTT 遥测接入，默认关闭，不影响 R1.2 闭环
    if os.environ.get("CAMPUS_MQTT_ENABLED", "0") == "1":
        try:
            from .mqtt_bridge import MqttTelemetryBridge
            mqtt_bridge = MqttTelemetryBridge(engine)
            mqtt_bridge.start()
        except Exception as e:  # broker 不可用时不影响后端主功能
            print(f"[仿真] MQTT 接入启用失败（已降级为纯 Mock）: {e}")
            mqtt_bridge = None
    yield
    task.cancel()
    if mqtt_bridge is not None:
        mqtt_bridge.stop()


app = FastAPI(title="校园共享电动车充电仿真后端（仿真数据）", version="1.0.0", lifespan=lifespan)


def envelope(data=None, code: int = 0, message: str = "OK", http: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=http,
        content={
            "code": code, "message": message, "simulation": True,
            "timestamp": now_iso(), "data": data or {},
        },
    )


ERR_HTTP = {
    4001: 409, 4002: 404, 4003: 404, 4004: 404, 4005: 400,
    4006: 422, 4007: 404, 4008: 400, 5001: 503, 5002: 500, 5003: 409,
}
ERR_MSG = {
    4001: "当前仿真状态不允许该操作", 4005: "非法倍速：仅支持 1/10/60",
    4006: "参数不合法或字段缺失", 4007: "分区不存在（非 A/B/C）",
    4008: "临时障碍参数非法", 5001: "仿真未运行", 5002: "后端内部错误",
}


def err(code: int, msg: str = "", details=None) -> JSONResponse:
    data = {"details": details} if details else {}
    return envelope(data, code=code, message=msg or ERR_MSG.get(code, "错误"), http=ERR_HTTP.get(code, 400))


def ok_exec(result) -> JSONResponse:
    success, code = result
    return envelope({"state": engine_state()}, code=0, message="OK") if success else err(code)


def engine_state() -> str:
    if not engine.running:
        return "IDLE"
    return "PAUSED" if engine.paused else "RUNNING"


# ---------- GET ----------
@app.get("/api/scenario")
def get_scenario():
    return envelope(engine.scenario_data())


@app.get("/api/vehicles")
def get_vehicles(zone: Optional[str] = None, status: Optional[str] = None,
                 limit: int = 100):
    if zone and zone not in ("A", "B", "C"):
        return err(4007)
    vs = list(engine.vehicles.values())
    if zone:
        vs = [v for v in vs if v["zone"] == zone]
    if status:
        vs = [v for v in vs if v["status"] == status]
    return envelope({"total": len(vs), "vehicles": vs[:min(limit, 500)]})


@app.get("/api/robot")
def get_robot():
    from dataclasses import asdict
    return envelope(asdict(engine.robot))


@app.get("/api/tasks")
def get_tasks(status: Optional[str] = None, batch_id: Optional[str] = None,
              limit: int = 100):
    from dataclasses import asdict
    ts = [asdict(t) for t in engine.tasks]
    if status:
        ts = [t for t in ts if t["status"] == status]
    if batch_id:
        ts = [t for t in ts if t["batch_id"] == batch_id]
    return envelope({"total": len(ts), "tasks": ts[:min(limit, 500)]})


@app.get("/api/events")
def get_events(type: Optional[str] = None, limit: int = 100):
    from dataclasses import asdict
    evs = list(engine.events)
    if type:
        evs = [e for e in evs if e["type"] == type]
    return envelope({"total": len(evs), "events": evs[:min(limit, 500)]})


@app.get("/api/mqtt/status")
def get_mqtt_status():
    """R2.1 新增诊断端点：MQTT 遥测接入状态（默认未启用）。"""
    return envelope(mqtt_bridge.status() if mqtt_bridge is not None
                    else {"enabled": False, "simulation": True})


# ---------- POST ----------
@app.post("/api/simulation/start")
def start(body: dict = {}):
    speed = body.get("speed", 1)
    seed = body.get("seed")
    if speed not in engine.scene.speed_options:
        return err(4005)
    ok, code = engine.start(speed=speed, seed=seed)
    if not ok:
        return err(code)
    return envelope({"state": engine_state(), "speed": engine.speed,
                     "sim_time": now_iso(), "seed": engine.seed},
                    message="仿真已启动（仿真数据）")


@app.post("/api/simulation/pause")
def pause():
    ok, code = engine.pause()
    if not ok:
        return err(code)
    return envelope({"state": engine_state(), "sim_time": now_iso()},
                    message="仿真已暂停（仿真数据）")


@app.post("/api/simulation/resume")
def resume():
    ok, code = engine.resume()
    if not ok:
        return err(code)
    return envelope({"state": engine_state(), "sim_time": now_iso()},
                    message="仿真已恢复（仿真数据）")


@app.post("/api/simulation/reset")
def reset():
    engine.reset()
    return envelope({"state": "IDLE", "speed": 1, "sim_time": now_iso()},
                    message="仿真已重置（仿真数据）")


@app.post("/api/simulation/speed")
def set_speed(body: dict):
    if "speed" not in body:
        return err(4006)
    ok, code = engine.set_speed(body["speed"])
    if not ok:
        return err(code)
    return envelope({"speed": engine.speed, "state": engine_state(), "sim_time": now_iso()},
                    message=f"倍速已切换为 {engine.speed}x（仿真数据）")


@app.post("/api/demo/obstacle")
def obstacle(body: dict):
    if "x" not in body or "y" not in body:
        return err(4006)
    radius = body.get("radius", 1.0)
    ttl = body.get("ttl_seconds", 30)
    if radius <= 0:
        return err(4008)
    obs = engine.inject_obstacle(float(body["x"]), float(body["y"]),
                                 float(radius), int(ttl))
    return envelope(obs, message="临时障碍已记录（仿真数据）")


# ---------- WebSocket ----------
@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    engine._subscribers.add(queue)
    try:
        await websocket.send_json(engine.snapshot())
        while True:
            frame = await queue.get()
            await websocket.send_json(frame)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        engine._subscribers.discard(queue)
