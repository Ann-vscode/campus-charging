/**
 * 全局类型定义 —— 与 contracts/api.md / telemetry.json / state_machines.md 对齐。
 * 注意：本系统所有数据均为「仿真模式 / 模拟车辆数据」，非真实车辆数据。
 */

export type Zone = 'A' | 'B' | 'C';
export type Point2D = [number, number];

export type ClockState = 'IDLE' | 'RUNNING' | 'PAUSED';

/** 车辆状态（契约固定枚举，不得增删） */
export type VehicleStatus =
  | 'PARKED' | 'SELECTED' | 'DOCKING' | 'CHARGING'
  | 'CHARGED' | 'STALE' | 'OFFLINE';

/** 机器人状态（契约固定枚举，不得增删） */
export type RobotStatus =
  | 'IDLE' | 'NAVIGATING' | 'REPLANNING' | 'DOCKING'
  | 'CHARGING' | 'RETURNING' | 'RECHARGING' | 'FAULT';

/** 充电通道状态（契约固定枚举，不得增删） */
export type ChannelStatus = 'EMPTY' | 'CONNECTING' | 'CHARGING' | 'DONE' | 'FAULT';

/** 任务状态（契约固定枚举） */
export type TaskStatus = 'PENDING' | 'NAVIGATING' | 'DOCKING' | 'CHARGING' | 'COMPLETED' | 'FAILED';

/** 事件类型（契约固定枚举） */
export type EventType =
  | 'SIM_STARTED' | 'SIM_PAUSED' | 'SIM_RESUMED' | 'SIM_RESET' | 'SPEED_CHANGED'
  | 'BATCH_CREATED' | 'TASK_ASSIGNED' | 'DOCK_OK' | 'DOCK_FAIL' | 'CHARGE_DONE'
  | 'VEHICLE_DEPARTED' | 'OBSTACLE_DETECTED' | 'REPLAN_TRIGGERED' | 'LOW_ENERGY'
  | 'RETURN_BASE' | 'RECHARGE_DONE' | 'FAULT';

export const EVENT_TYPES: EventType[] = [
  'SIM_STARTED', 'SIM_PAUSED', 'SIM_RESUMED', 'SIM_RESET', 'SPEED_CHANGED',
  'BATCH_CREATED', 'TASK_ASSIGNED', 'DOCK_OK', 'DOCK_FAIL', 'CHARGE_DONE',
  'VEHICLE_DEPARTED', 'OBSTACLE_DETECTED', 'REPLAN_TRIGGERED', 'LOW_ENERGY',
  'RETURN_BASE', 'RECHARGE_DONE', 'FAULT',
];

export interface Clock {
  sim_time: string;
  speed: number;
  state: ClockState;
}

/** 车辆遥测（telemetry.json: VehicleTelemetry） */
export interface VehicleTelemetry {
  vehicle_id: string;
  zone: Zone;
  slot: number;
  x: number;
  y: number;
  soc: number;
  status: VehicleStatus;
  stale: boolean;
  timestamp: string;
}

/** 机器人遥测（telemetry.json: RobotTelemetry） */
export interface RobotTelemetry {
  robot_id: string;
  x: number;
  y: number;
  heading: number;
  speed: number;
  soc: number;
  status: RobotStatus;
  planned_path: Point2D[];
  traveled_path: Point2D[];
  timestamp: string;
}

/** 任务事件（telemetry.json: TaskEvent） */
export interface TaskEvent {
  event_id: string;
  type: EventType;
  batch_id: string;
  vehicle_id: string;
  message: string;
  timestamp: string;
}

/** 任务（api.md 4.4） */
export interface Task {
  task_id: string;
  batch_id: string;
  vehicle_id: string;
  zone: Zone;
  channel: number;
  status: TaskStatus;
  progress: number;
  created_at: string;
  updated_at: string;
}

/** 充电通道（前端展示模型，由任务/车辆派生或 Mock 引擎直接给出） */
export interface Channel {
  id: string;
  index: number;
  status: ChannelStatus;
  vehicle_id: string | null;
  soc: number;
  progress: number;
}

/** 场景配置（api.md 4.1） */
export interface Scenario {
  scenario_id: string;
  name: string;
  version: string;
  clock: Clock;
  zones: string[];
  vehicles: { total: number; by_zone: Record<string, number> };
  robot: { robot_id: string; battery_capacity_kwh: number };
  charging_channels: number;
  seed: number;
}

/** 前端统一视图状态 */
export interface SimState {
  tick: number;
  clock: Clock;
  vehicles: VehicleTelemetry[];
  robot: RobotTelemetry;
  tasks: Task[];
  channels: Channel[];
  events: TaskEvent[];
}

/** 仿真静态障碍（来自 campus_basic.yaml） */
export interface Obstacle {
  x: number;
  y: number;
  radius: number;
}

// ---------------- 展示映射（中文标签 + 投影友好状态色） ----------------

export const VEHICLE_STATUS_LABEL: Record<VehicleStatus, string> = {
  PARKED: '停放', SELECTED: '已选中', DOCKING: '对接中', CHARGING: '充电中',
  CHARGED: '已充满', STALE: '数据陈旧', OFFLINE: '离线',
};

export const VEHICLE_STATUS_COLOR: Record<VehicleStatus, string> = {
  PARKED: '#90a4ae', SELECTED: '#ffb300', DOCKING: '#ab47bc',
  CHARGING: '#29b6f6', CHARGED: '#2e7d32', STALE: '#ef6c00', OFFLINE: '#37474f',
};

export const ROBOT_STATUS_LABEL: Record<RobotStatus, string> = {
  IDLE: '待命', NAVIGATING: '导航中', REPLANNING: '重规划中', DOCKING: '对接中',
  CHARGING: '充电中', RETURNING: '返基站中', RECHARGING: '基站补能中', FAULT: '故障',
};

export const CHANNEL_STATUS_LABEL: Record<ChannelStatus, string> = {
  EMPTY: '空闲', CONNECTING: '连接中', CHARGING: '充电中', DONE: '已完成', FAULT: '故障',
};

export const CHANNEL_STATUS_COLOR: Record<ChannelStatus, string> = {
  EMPTY: '#546e7a', CONNECTING: '#ffb300', CHARGING: '#29b6f6', DONE: '#2e7d32', FAULT: '#e53935',
};

export const TASK_STATUS_LABEL: Record<TaskStatus, string> = {
  PENDING: '待执行', NAVIGATING: '导航中', DOCKING: '对接中', CHARGING: '充电中',
  COMPLETED: '已完成', FAILED: '失败',
};

export const CLOCK_STATE_LABEL: Record<ClockState, string> = {
  IDLE: '未启动 / 待命', RUNNING: '运行中', PAUSED: '已暂停',
};

export const EVENT_TYPE_LABEL: Record<EventType, string> = {
  SIM_STARTED: '仿真启动', SIM_PAUSED: '仿真暂停', SIM_RESUMED: '仿真恢复',
  SIM_RESET: '仿真复位', SPEED_CHANGED: '倍速变更', BATCH_CREATED: '批次创建',
  TASK_ASSIGNED: '任务派发', DOCK_OK: '对接成功', DOCK_FAIL: '对接失败',
  CHARGE_DONE: '充电完成', VEHICLE_DEPARTED: '车辆离位',
  OBSTACLE_DETECTED: '障碍检测', REPLAN_TRIGGERED: '触发重规划',
  LOW_ENERGY: '低电量', RETURN_BASE: '返回基站', RECHARGE_DONE: '补能完成', FAULT: '故障',
};

/** 电量颜色：绿色 ≥50%，橙色 20%~50%，红色 <20%（投影清晰） */
export function socColor(soc: number): string {
  if (soc < 20) return '#e53935';
  if (soc < 50) return '#fb8c00';
  return '#2e9e5b';
}

/** 时间本地化展示（传输与存储仍为 UTC ISO 8601） */
export function formatSimTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString('zh-CN', { hour12: false });
}
