"""仿真引擎：仿真时钟 + MockRobot 状态机 + 五路充电 + 事件日志（R1.2 核心）。

- 后端是唯一仿真时钟源（api.md 第 2 节）。
- MockRobot 依次经过 IDLE→NAVIGATING→DOCKING→CHARGING→离开→RETURNING→RECHARGING。
- 所有数据为仿真数据。
"""
from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from .config import Scene, Vehicle, load_scenario
from . import scheduler as sch

UTC_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"
_PLATFORM_BUSY = {"SELECTED", "DOCKING", "CHARGING", "CHARGED"}


def now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime(UTC_FMT)[:-3] + "Z"


@dataclass
class Channel:
    id: str
    state: str = "EMPTY"          # EMPTY/CONNECTING/CHARGING/DONE/FAULT
    vehicle_id: Optional[str] = None
    progress: float = 0.0
    e_need: float = 0.0
    t_total: float = 0.0         # 充电总时长（仿真秒）
    t_elapsed: float = 0.0


@dataclass
class Task:
    task_id: str
    batch_id: str
    vehicle_id: str
    zone: str
    channel: int
    status: str = "PENDING"      # PENDING/NAVIGATING/DOCKING/CHARGING/COMPLETED/FAILED
    progress: float = 0.0
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Robot:
    robot_id: str
    x: float
    y: float
    heading: float = 0.0
    speed: float = 0.0
    soc: float = 100.0
    status: str = "IDLE"
    planned_path: List[list] = field(default_factory=list)
    traveled_path: List[list] = field(default_factory=list)


class SimulationEngine:
    def __init__(self, scene: Optional[Scene] = None):
        self.scene = scene or load_scenario()
        self._lock = threading.RLock()
        self._subscribers: set = set()   # asyncio Queue 集合（在 main 中注册）
        self.reset(seed=self.scene.seed)

    # ---------- 生命周期 ----------
    def reset(self, seed: Optional[int] = None):
        with self._lock:
            s = self.scene
            self.seed = seed if seed is not None else s.seed
            self.running = False
            self.paused = False
            self.speed = 1
            self.sim_time_ms = 0
            self.tick_no = 0
            self._task_seq = 0
            self._batch_seq = 0
            self._event_seq = 0
            self._obs_seq = 0
            self.events: deque = deque(maxlen=1000)
            self.tasks: List[Task] = []
            self.obstacles: List[dict] = []
            self.vehicles: Dict[str, dict] = {}
            for v in s.vehicles:
                self.vehicles[v.id] = {
                    "vehicle_id": v.id, "zone": v.zone, "slot": v.slot,
                    "x": v.x, "y": v.y, "soc": v.soc,
                    "status": sch.SCENE_TO_CONTRACT.get(v.status, "PARKED"),
                    "stale": v.status == "stale",
                    "online": v.online,
                    "timestamp": now_iso(),
                }
            self.robot = Robot(s.robot_id if hasattr(s, "robot_id") else "R01",
                               s.base[0], s.base[1], soc=s.robot_initial_soc)
            self.channels: List[Channel] = [
                Channel(id=cid) for cid in s.channel_ids
            ]
            # MockRobot 运行状态
            self._phase = "IDLE"           # IDLE/TO_ZONE/DOCKING/CHARGING/DEPART/RETURN/RECHARGE
            self._phase_t = 0.0
            self._phase_dur = 0.0
            self._active_batch: List[str] = []
            self._batch_zone: Optional[str] = None
            self._need_recharge = False

    def upsert_vehicle_telemetry(self, payload: dict) -> bool:
        """写入一条 MQTT 车辆遥测（R2.1）。未知 vehicle_id 返回 False。

        平台正在服务的车辆（SELECTED/DOCKING/CHARGING/CHARGED）只刷新时间戳，
        不用上报值覆盖 soc —— 此时平台侧充电结果是权威，避免双写互相覆盖。
        OFFLINE/STALE 原样写入，供调度器 is_effective 过滤。
        """
        with self._lock:
            vid = payload.get("vehicle_id")
            if vid is None or vid not in self.vehicles:
                return False
            v = self.vehicles[vid]
            st = payload["status"]
            v["timestamp"] = payload["timestamp"]
            if v["status"] in _PLATFORM_BUSY and st == "PARKED":
                return True  # 平台服务中，忽略车辆侧陈旧 soc
            v["soc"] = float(payload["soc"])
            v["x"] = float(payload["x"])
            v["y"] = float(payload["y"])
            v["stale"] = bool(payload["stale"])
            v["status"] = st
            v["online"] = st != "OFFLINE"
            return True

    def start(self, speed: int = 1, seed: Optional[int] = None):
        with self._lock:
            if self.running:
                return False, 4001            # INVALID_STATE
            if seed is not None:
                self.reset(seed=seed)
            self.speed = speed if speed in self.scene.speed_options else 1
            self.running = True
            self.paused = False
            self._emit("SIM_STARTED", message="仿真已启动（仿真数据）")
            return True, 0

    def pause(self):
        with self._lock:
            if not self.running:
                return False, 5001            # SIM_NOT_RUNNING
            if self.paused:
                return False, 4001            # INVALID_STATE
            self.paused = True
            self._emit("SIM_PAUSED", message="仿真已暂停（仿真数据）")
            return True, 0

    def resume(self):
        with self._lock:
            if not self.running:
                return False, 5001            # SIM_NOT_RUNNING
            if not self.paused:
                return False, 4001            # INVALID_STATE
            self.paused = False
            self._emit("SIM_RESUMED", message="仿真已恢复（仿真数据）")
            return True, 0

    def set_speed(self, speed: int):
        with self._lock:
            if speed not in self.scene.speed_options:
                return False, 4005            # INVALID_SPEED
            self.speed = speed
            self._emit("SPEED_CHANGED", message=f"倍速切换为 {speed}x（仿真数据）")
            return True, 0

    # ---------- 事件 ----------
    def _emit(self, event_type: str, batch_id: str = "", vehicle_id: str = "", message: str = ""):
        self._event_seq += 1
        ev = {
            "event_id": f"E-{self._event_seq:06d}",
            "type": event_type,
            "batch_id": batch_id,
            "vehicle_id": vehicle_id,
            "message": message or f"{event_type}（仿真数据）",
            "timestamp": now_iso(),
        }
        self.events.append(ev)

    # ---------- 时钟推进（由后台任务每 100ms 调用） ----------
    BASE_TICK_MS = 100            # 10 Hz，倍速不改变频率
    SIM_SEC_PER_TICK = 0.5        # 1x 时每 tick 推进的仿真秒（仿真假设）

    def tick(self) -> Optional[dict]:
        with self._lock:
            self.tick_no += 1
            dt_sim = self.SIM_SEC_PER_TICK * self.speed
            if self.running and not self.paused:
                self.sim_time_ms += int(dt_sim * 1000)
                self._advance(dt_sim)
            return self.frame()

    def _advance(self, dt: float):
        """推进 MockRobot 状态机与五路充电。"""
        s = self.scene
        r = self.robot
        ph = self._phase

        if ph == "IDLE":
            # 选取一个批次：优先机器人当前所在区/最近区；使用动态车辆视图
            nearest_zone = self._nearest_zone((r.x, r.y))
            batch = sch.select_batch(s, self.vehicles, (r.x, r.y), r.soc,
                                     zone_focus=nearest_zone)
            if not batch:
                return
            if not sch.can_dispatch(s, batch, self.vehicles, (r.x, r.y), r.soc):
                self._need_recharge = True
                self._enter("RETURN", message="预计储能不足，先返回基站补能（仿真数据）")
                return
            self._batch_seq += 1
            self._batch_zone = nearest_zone
            self._active_batch = list(batch)   # batch 现为 vid 列表
            self._emit("BATCH_CREATED", batch_id=f"B-{self._batch_seq:04d}",
                       message=f"创建批次 B-{self._batch_seq:04d}，{len(batch)} 辆（仿真数据）")
            # 分配通道并建立任务
            for i, vid in enumerate(batch):
                self._task_seq += 1
                tid = f"T-{self._task_seq:04d}"
                bid = f"B-{self._batch_seq:04d}"
                t = Task(tid, bid, vid, self.vehicles[vid]["zone"], i + 1,
                         status="PENDING", created_at=now_iso(), updated_at=now_iso())
                self.tasks.append(t)
                self.vehicles[vid]["status"] = "SELECTED"
                self._emit("TASK_ASSIGNED", batch_id=bid, vehicle_id=vid,
                           message=f"任务 {tid} 分配给机器人 R01（仿真数据）")
            # 计算到首个目标的路径
            target = self.vehicles[batch[0]]
            r.planned_path = [[r.x, r.y], [target["x"], target["y"]]]
            self._enter("TO_ZONE", duration=self._path_len(r.planned_path) / s_base_speed(),
                        message=f"机器人前往 {nearest_zone} 区（仿真数据）")

        elif ph == "TO_ZONE":
            self._phase_t += dt
            r.speed = s_base_speed()
            frac = min(1.0, self._phase_t / max(0.001, self._phase_dur))
            old_x, old_y = r.x, r.y
            if r.planned_path and len(r.planned_path) >= 2:
                a, b = r.planned_path[0], r.planned_path[-1]
                r.x = a[0] + (b[0] - a[0]) * frac
                r.y = a[1] + (b[1] - a[1]) * frac
                r.heading = __import__("math").degrees(__import__("math").atan2(b[1]-a[1], b[0]-a[0]))
            # 移动扣能：按本 tick 实际位移积分（与倍速无关，R2.3 修复）
            self._consume_move_energy(old_x, old_y)
            if frac >= 1.0:
                r.speed = 0.0
                self._enter("DOCKING", duration=1.0, message="机器人到达，开始对接（仿真数据）")

        elif ph == "DOCKING":
            self._phase_t += dt
            if self._phase_t >= self._phase_dur:
                # 逐车对接：正常成功（重试/跳过为 R5.2 内容，此处 Mock 全部成功）
                for tid in self._active_batch:
                    t = self._find_task_by_vehicle(tid)
                    if t and t.status == "PENDING":
                        t.status = "DOCKING"
                        t.updated_at = now_iso()
                        self.vehicles[tid]["status"] = "DOCKING"
                        self._emit("DOCK_OK", batch_id=t.batch_id, vehicle_id=tid,
                                   message=f"车辆 {tid} 对接成功（仿真数据）")
                self._start_charging()
                self._enter("CHARGING", message="五路开始独立充电（仿真数据）")

        elif ph == "CHARGING":
            all_done = True
            p_bat = s.power_kw * (1 - s.transfer_loss)   # kW
            for ch in self.channels:
                if ch.state == "CHARGING":
                    all_done = False
                    ch.t_elapsed += dt
                    ch.progress = min(1.0, ch.t_elapsed / max(0.001, ch.t_total))
                    v = self.vehicles.get(ch.vehicle_id)
                    t = self._find_task_by_vehicle(ch.vehicle_id)
                    if v and t:
                        delivered_kwh = p_bat * (dt / 3600.0)
                        v["soc"] = min(s.target_soc, v["soc"] + delivered_kwh / s.vehicle_cap_kwh * 100)
                        t.progress = ch.progress
                        t.status = "CHARGING"
                        t.updated_at = now_iso()
                        # 机器人储能扣减（储能侧）
                        p_store = s.power_kw / s.charge_efficiency
                        self.robot.soc = max(
                            0.0,
                            self.robot.soc - (p_store * (dt / 3600.0)) / s.robot_capacity_kwh * 100,
                        )
                    if ch.progress >= 1.0:
                        ch.state = "DONE"
                        if v:
                            v["soc"] = s.target_soc
                            v["status"] = "CHARGED"
                        if t:
                            t.status = "COMPLETED"
                            t.progress = 1.0
                            t.updated_at = now_iso()
                        self._emit("CHARGE_DONE", batch_id=t.batch_id if t else "",
                                   vehicle_id=ch.vehicle_id,
                                   message=f"车辆 {ch.vehicle_id} 充电至目标 SOC {s.target_soc:.0f}%（仿真数据）")
            if all_done:
                self._enter("DEPART", duration=1.0, message="整批完成，机器人离开（仿真数据）")

        elif ph == "DEPART":
            self._phase_t += dt
            if self._phase_t >= self._phase_dur:
                for vid in self._active_batch:
                    v = self.vehicles.get(vid)
                    if v:
                        v["status"] = "CHARGED"
                    self._emit("VEHICLE_DEPARTED", vehicle_id=vid,
                               message=f"车辆 {vid} 已完成充电（仿真数据）")
                self._active_batch = []
                for ch in self.channels:
                    ch.state = "EMPTY"
                    ch.vehicle_id = None
                    ch.progress = 0.0
                if self.robot.soc <= s.low_energy_threshold:
                    self._need_recharge = True
                if self._need_recharge:
                    self._enter("RETURN", message="电量偏低，返回基站（仿真数据）")
                else:
                    self._enter("IDLE", message="返回待命，准备下一批（仿真数据）")

        elif ph == "RETURN":
            self._phase_t += dt
            r.speed = s_base_speed()
            frac = min(1.0, self._phase_t / max(0.001, self._phase_dur))
            old_x, old_y = r.x, r.y
            if r.planned_path and len(r.planned_path) >= 2:
                a, b = r.planned_path[0], r.planned_path[-1]
                r.x = a[0] + (b[0] - a[0]) * frac
                r.y = a[1] + (b[1] - a[1]) * frac
            # 移动扣能：按本 tick 实际位移积分（与倍速无关，R2.3 修复）
            self._consume_move_energy(old_x, old_y)
            if frac >= 1.0:
                r.speed = 0.0
                self._emit("RETURN_BASE", message="机器人到达基站（仿真数据）")
                if self.robot.soc <= s.low_energy_threshold or self._need_recharge:
                    self._enter("RECHARGE", message="开始基站补能（仿真数据）")
                else:
                    self._need_recharge = False
                    self._enter("IDLE", message="返回待命（仿真数据）")

        elif ph == "RECHARGE":
            self._phase_t += dt
            # 补能速率：3.5 kW / 效率，按容量折算
            p = s.power_kw / s.charge_efficiency
            self.robot.soc = min(100.0, self.robot.soc + (p * (dt / 3600.0)) / s.robot_capacity_kwh * 100)
            if self.robot.soc >= 99.5:
                self.robot.soc = 100.0
                self._need_recharge = False
                self._emit("RECHARGE_DONE", message="机器人补能完成（仿真数据）")
                self._enter("IDLE", message="补能完成，恢复待命（仿真数据）")

    def _enter(self, phase: str, duration: float = 0.0, message: str = ""):
        """状态迁移；message 仅作为可选的状态变更记录事件。"""
        self._phase = phase
        self._phase_t = 0.0
        self._phase_dur = duration
        self.robot.status = {
            "IDLE": "IDLE", "TO_ZONE": "NAVIGATING", "DOCKING": "DOCKING",
            "CHARGING": "CHARGING", "DEPART": "NAVIGATING",
            "RETURN": "RETURNING", "RECHARGE": "RECHARGING",
        }.get(phase, phase)

    def _start_charging(self):
        s = self.scene
        p_bat = s.power_kw * (1 - s.transfer_loss)
        for i, vid in enumerate(self._active_batch):
            ch = self.channels[i]
            v = self.vehicles[vid]
            e_need = (s.target_soc - v["soc"]) / 100 * s.vehicle_cap_kwh
            t_total = e_need / p_bat * 3600 if p_bat > 0 else 0
            ch.state = "CHARGING"
            ch.vehicle_id = vid
            ch.e_need = e_need
            ch.t_total = t_total
            ch.t_elapsed = 0.0
            ch.progress = 0.0
            t = self._find_task_by_vehicle(vid)
            if t:
                t.status = "CHARGING"
                t.updated_at = now_iso()

    def _find_task_by_vehicle(self, vid: str) -> Optional[Task]:
        for t in reversed(self.tasks):
            if t.vehicle_id == vid and t.status not in ("COMPLETED", "FAILED"):
                return t
        return None

    def _nearest_zone(self, pos) -> str:
        centers = {}
        for z in self.scene.zones:
            vs = [v for v in self.scene.vehicles if v.zone == z["id"]]
            if vs:
                centers[z["id"]] = (sum(v.x for v in vs) / len(vs), sum(v.y for v in vs) / len(vs))
        return min(centers, key=lambda z: sch.distance(pos, centers[z])) if centers else "A"

    def _consume_move_energy(self, old_x: float, old_y: float):
        """按本 tick 的实际位移扣减机器人储能（R2.3 修复）。

        位移由插值后的位置差决定，而非 speed*dt —— 后者在高倍速下会越过终点
        仍按整段 dt 扣能，导致能耗随倍速放大、与契约 §2.2 的"按里程"模型不符。
        """
        s = self.scene
        r = self.robot
        import math
        moved = math.hypot(r.x - old_x, r.y - old_y)
        if moved <= 0:
            return
        r.soc = max(
            0.0,
            r.soc - (s.move_energy_per_100m * moved / 100) / s.robot_capacity_kwh * 100,
        )

    @staticmethod
    def _path_len(path) -> float:
        if len(path) < 2:
            return 0.0
        return sch.distance(tuple(path[0]), tuple(path[-1]))

    def inject_obstacle(self, x, y, radius, ttl_seconds):
        with self._lock:
            self._obs_seq += 1
            from datetime import datetime, timedelta, timezone
            exp = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).strftime(UTC_FMT)[:-3] + "Z"
            obs = {
                "obstacle_id": f"O-{self._obs_seq:06d}", "x": x, "y": y,
                "radius": radius, "expires_at": exp,
            }
            self.obstacles.append(obs)
            self._emit("OBSTACLE_DETECTED", message=f"临时障碍 O-{self._obs_seq:06d} 已注入（仿真数据）")
            reaction = "IDLE"
            if self._phase == "TO_ZONE":
                self._emit("REPLAN_TRIGGERED", message="检测到临时障碍，触发重新规划（仿真数据）")
                reaction = "REPLANNING"
            obs["robot_reaction"] = reaction
            return obs

    # ---------- 快照 / WS 帧 ----------
    def frame(self) -> dict:
        with self._lock:
            r = self.robot
            msgs = [{
                "type": "RobotTelemetry",
                "payload": {
                    "robot_id": r.robot_id, "x": round(r.x, 3), "y": round(r.y, 3),
                    "heading": round(r.heading, 2), "speed": round(r.speed, 3),
                    "soc": round(r.soc, 2), "status": r.status,
                    "planned_path": r.planned_path, "traveled_path": r.traveled_path,
                    "timestamp": now_iso(),
                },
            }]
            # 每帧推 5 辆，按帧序号轮转，覆盖全部 30 辆
            self._frame_seq = getattr(self, "_frame_seq", 0) + 1
            all_v = list(self.vehicles.values())
            n = len(all_v)
            offset = (self._frame_seq * 5) % n if n else 0
            for i in range(min(5, n)):
                v = all_v[(offset + i) % n]
                msgs.append({
                    "type": "VehicleTelemetry",
                    "payload": {k: v[k] for k in
                                ("vehicle_id", "zone", "slot", "x", "y", "soc", "status", "stale", "timestamp")},
                })
            recent = list(self.events)[-5:]
            for ev in recent:
                msgs.append({"type": "TaskEvent", "payload": ev})
            return {
                "type": "tick", "simulation": True, "timestamp": now_iso(),
                "tick": self.tick_no,
                "clock": {"sim_time": now_iso(), "speed": self.speed,
                          "state": "RUNNING" if self.running and not self.paused
                          else "PAUSED" if self.paused else "IDLE"},
                "messages": msgs,
            }

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "type": "snapshot", "simulation": True, "timestamp": now_iso(),
                "vehicles": list(self.vehicles.values()),
                "robot": asdict(self.robot),
                "tasks": [asdict(t) for t in self.tasks],
                "events": list(self.events),
            }

    def scenario_data(self) -> dict:
        s = self.scene
        return {
            "scenario_id": s.scenario_id, "name": s.name, "version": s.version,
            "clock": {"source": "backend", "speed": self.speed,
                      "sim_time": now_iso(),
                      "running": self.running and not self.paused,
                      "state": "RUNNING" if self.running and not self.paused
                      else "PAUSED" if self.paused else "IDLE"},
            "zones": [z["id"] for z in s.zones],
            "vehicles": {"total": len(s.vehicles),
                         "by_zone": {z["id"]: sum(1 for v in s.vehicles if v.zone == z["id"])
                                     for z in s.zones}},
            "robot": {"robot_id": "R01", "battery_capacity_kwh": s.robot_capacity_kwh},
            "charging_channels": s.channels,
            "seed": self.seed,
        }


def s_base_speed() -> float:
    """机器人仿真移动速度（单位/仿真秒），仿真假设。"""
    return 3.0
