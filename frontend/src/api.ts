/**
 * HTTP API 封装 + Mock 数据源。
 *
 * - 真实后端模式：统一解包 {code,message,simulation,timestamp,data} 信封，非 0 code 抛 ApiError。
 * - Mock 模式（默认）：内置 campus_basic.yaml 的 30 辆车与 5 路通道，
 *   点击「启动系统」后由 MockSimulation 自动推进整条流程，无需后端。
 *
 * 所有数据均为仿真模式 / 模拟车辆数据。
 */
import type {
  Channel, ChannelStatus, Clock, EventType, RobotTelemetry, Scenario, SimState,
  Task, TaskEvent, TaskStatus, VehicleStatus, VehicleTelemetry, Zone,
} from './types';

// ---------------------------------------------------------------------------
// 1. 统一响应信封与 HTTP 客户端
// ---------------------------------------------------------------------------

export interface Envelope<T> {
  code: number;
  message: string;
  simulation: boolean;
  timestamp: string;
  data: T;
}

export class ApiError extends Error {
  readonly code: number;
  constructor(code: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
  }
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(5002, '无法连接到仿真后端（请检查服务是否启动，或改用 Mock 模式）');
  }

  let envelope: Envelope<T>;
  try {
    envelope = (await response.json()) as Envelope<T>;
  } catch {
    throw new ApiError(5002, `HTTP ${response.status} 响应不是合法的 JSON 信封`);
  }

  if (!envelope || typeof envelope.code !== 'number' || envelope.code !== 0) {
    throw new ApiError(envelope?.code ?? 5002, envelope?.message ?? `HTTP ${response.status} 请求失败`);
  }
  return envelope.data;
}

function query(params: Record<string, string | number | undefined>): string {
  const usp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') usp.set(k, String(v));
  });
  const s = usp.toString();
  return s ? `?${s}` : '';
}

export type ListParams = {
  limit?: number;
  since?: string;
  zone?: Zone;
  status?: string;
  type?: string;
  batch_id?: string;
};

export const api = {
  getScenario: () => http<Scenario>('/api/scenario'),
  getVehicles: (p: ListParams = {}) =>
    http<{ total: number; vehicles: VehicleTelemetry[] }>(`/api/vehicles${query(p)}`),
  getRobot: () => http<RobotTelemetry>('/api/robot'),
  getTasks: (p: ListParams = {}) =>
    http<{ total: number; tasks: Task[] }>(`/api/tasks${query(p)}`),
  getEvents: (p: ListParams = {}) =>
    http<{ total: number; events: TaskEvent[] }>(`/api/events${query(p)}`),

  start: (body: { speed?: number; seed?: number } = {}) =>
    http('/api/simulation/start', { method: 'POST', body: JSON.stringify(body) }),
  pause: () => http('/api/simulation/pause', { method: 'POST', body: '{}' }),
  resume: () => http('/api/simulation/resume', { method: 'POST', body: '{}' }),
  reset: () => http('/api/simulation/reset', { method: 'POST', body: '{}' }),
  setSpeed: (speed: number) =>
    http('/api/simulation/speed', { method: 'POST', body: JSON.stringify({ speed }) }),
  addObstacle: (body: { x: number; y: number; radius?: number; ttl_seconds?: number } = { x: 75, y: 30, radius: 1.5 }) =>
    http('/api/demo/obstacle', { method: 'POST', body: JSON.stringify(body) }),
};

/** Mock 开关：默认开启（纯静态预览即可演示全流程）；设置 VITE_USE_MOCK=false 切换真实后端。 */
export const useMockData: boolean = import.meta.env.VITE_USE_MOCK !== 'false';

// ---------------------------------------------------------------------------
// 2. Mock 数据（来自 scenarios/campus_basic.yaml，全部为仿真数据）
// ---------------------------------------------------------------------------

interface SeedVehicle {
  id: string; zone: Zone; slot: number; x: number; y: number;
  soc: number; st: string; online: boolean;
}

const SEED_VEHICLES: SeedVehicle[] = [
  { id: 'A01', zone: 'A', slot: 1, x: 5, y: 5, soc: 72, st: 'parked', online: true },
  { id: 'A02', zone: 'A', slot: 2, x: 13, y: 5, soc: 35, st: 'low_battery', online: true },
  { id: 'A03', zone: 'A', slot: 3, x: 21, y: 5, soc: 88, st: 'offline', online: false },
  { id: 'A04', zone: 'A', slot: 4, x: 29, y: 5, soc: 61, st: 'parked', online: true },
  { id: 'A05', zone: 'A', slot: 5, x: 5, y: 11, soc: 22, st: 'low_battery', online: true },
  { id: 'A06', zone: 'A', slot: 6, x: 13, y: 11, soc: 79, st: 'parked', online: true },
  { id: 'A07', zone: 'A', slot: 7, x: 21, y: 11, soc: 45, st: 'parked', online: true },
  { id: 'A08', zone: 'A', slot: 8, x: 29, y: 11, soc: 90, st: 'parked', online: true },
  { id: 'A09', zone: 'A', slot: 9, x: 5, y: 17, soc: 15, st: 'low_battery', online: true },
  { id: 'A10', zone: 'A', slot: 10, x: 13, y: 17, soc: 68, st: 'parked', online: true },
  { id: 'A11', zone: 'A', slot: 11, x: 21, y: 17, soc: 53, st: 'parked', online: true },
  { id: 'A12', zone: 'A', slot: 12, x: 29, y: 17, soc: 8, st: 'low_battery', online: true },

  { id: 'B01', zone: 'B', slot: 1, x: 54, y: 6, soc: 77, st: 'parked', online: true },
  { id: 'B02', zone: 'B', slot: 2, x: 62, y: 6, soc: 41, st: 'parked', online: true },
  { id: 'B03', zone: 'B', slot: 3, x: 70, y: 6, soc: 30, st: 'low_battery', online: true },
  { id: 'B04', zone: 'B', slot: 4, x: 78, y: 6, soc: 85, st: 'stale', online: true },
  { id: 'B05', zone: 'B', slot: 5, x: 86, y: 6, soc: 64, st: 'parked', online: true },
  { id: 'B06', zone: 'B', slot: 6, x: 54, y: 14, soc: 19, st: 'low_battery', online: true },
  { id: 'B07', zone: 'B', slot: 7, x: 62, y: 14, soc: 92, st: 'parked', online: true },
  { id: 'B08', zone: 'B', slot: 8, x: 70, y: 14, soc: 56, st: 'parked', online: true },
  { id: 'B09', zone: 'B', slot: 9, x: 78, y: 14, soc: 48, st: 'parked', online: true },
  { id: 'B10', zone: 'B', slot: 10, x: 86, y: 14, soc: 5, st: 'low_battery', online: true },

  { id: 'C01', zone: 'C', slot: 1, x: 114, y: 6, soc: 81, st: 'parked', online: true },
  { id: 'C02', zone: 'C', slot: 2, x: 122, y: 6, soc: 12, st: 'low_battery', online: true },
  { id: 'C03', zone: 'C', slot: 3, x: 130, y: 6, soc: 70, st: 'parked', online: true },
  { id: 'C04', zone: 'C', slot: 4, x: 138, y: 6, soc: 38, st: 'parked', online: true },
  { id: 'C05', zone: 'C', slot: 5, x: 114, y: 14, soc: 60, st: 'parked', online: true },
  { id: 'C06', zone: 'C', slot: 6, x: 122, y: 14, soc: 27, st: 'low_battery', online: true },
  { id: 'C07', zone: 'C', slot: 7, x: 130, y: 14, soc: 95, st: 'parked', online: true },
  { id: 'C08', zone: 'C', slot: 8, x: 138, y: 14, soc: 44, st: 'parked', online: true },
];

const SCENARIO_START_MS = Date.parse('2026-11-18T09:00:00.000Z');
const TARGET_IDS = ['B10', 'A12', 'C02', 'A09', 'B06'];
const TARGET_SEED_SOC = TARGET_IDS.map((id) => SEED_VEHICLES.find((v) => v.id === id)?.soc ?? 0);
const TOTAL_STEPS = 15;
const SPEED_INTERVAL: Record<number, number> = { 1: 900, 10: 450, 60: 220 };

const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

function seedStatus(v: SeedVehicle): VehicleStatus {
  if (!v.online || v.st === 'offline') return 'OFFLINE';
  if (v.st === 'stale') return 'STALE';
  return 'PARKED';
}

export function createInitialState(): SimState {
  const ts = new Date(SCENARIO_START_MS).toISOString();
  return {
    tick: 0,
    clock: { sim_time: ts, speed: 1, state: 'IDLE' },
    vehicles: SEED_VEHICLES.map((v) => ({
      vehicle_id: v.id, zone: v.zone, slot: v.slot, x: v.x, y: v.y, soc: v.soc,
      status: seedStatus(v), stale: v.st === 'stale', timestamp: ts,
    })),
    robot: {
      robot_id: 'R01', x: 70, y: 40, heading: 0, speed: 0, soc: 100, status: 'IDLE',
      planned_path: [], traveled_path: [], timestamp: ts,
    },
    tasks: [],
    channels: Array.from({ length: 5 }, (_, i) => ({
      id: `CH${i + 1}`, index: i + 1, status: 'EMPTY' as ChannelStatus,
      vehicle_id: null, soc: 0, progress: 0,
    })),
    events: [],
  };
}

// ---------------------------------------------------------------------------
// 3. Mock 仿真引擎：点击一次「启动系统」自动演完整流程
//    选车 → 派单导航 → 对接 → 五路并行充电 → 完成 → 车辆离位 → 返基站 → 待命
// ---------------------------------------------------------------------------

type Listener = (state: SimState) => void;

export class MockSimulation {
  private state: SimState = createInitialState();
  private listeners = new Set<Listener>();
  private timer: number | null = null;
  private step = 0;
  private eventSeq = 0;
  private replan = 0;

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    listener(this.state);
    return () => { this.listeners.delete(listener); };
  }

  getState(): SimState { return this.state; }

  private emit(): void {
    this.listeners.forEach((listener) => listener(this.state));
  }

  private stopTimer(): void {
    if (this.timer !== null) {
      window.clearInterval(this.timer);
      this.timer = null;
    }
  }

  private schedule(): void {
    this.stopTimer();
    const ms = SPEED_INTERVAL[this.state.clock.speed] ?? 900;
    this.timer = window.setInterval(() => this.advance(), ms);
  }

  private ev(s: SimState, type: EventType, vehicleId: string, text: string): TaskEvent {
    this.eventSeq += 1;
    return {
      event_id: `E-${String(this.eventSeq).padStart(6, '0')}`,
      type,
      batch_id: 'B-0001',
      vehicle_id: vehicleId,
      message: `${text}（仿真数据）`,
      timestamp: s.clock.sim_time,
    };
  }

  private pushEvents(s: SimState, ...events: TaskEvent[]): void {
    s.events = [...events.slice().reverse(), ...s.events].slice(0, 500);
  }

  /** 推进一个预设阶段（所有状态迁移均遵循 state_machines.md 联动规则）。 */
  private advance(): void {
    const s = clone(this.state);
    this.step += 1;
    const speed = s.clock.speed;
    s.tick = this.step;
    s.clock.sim_time = new Date(SCENARIO_START_MS + this.step * 1000 * speed).toISOString();

    const setVehicle = (id: string, status: VehicleStatus, soc?: number) => {
      const v = s.vehicles.find((item) => item.vehicle_id === id);
      if (v) {
        v.status = status;
        if (soc !== undefined) v.soc = soc;
        v.stale = false;
        v.timestamp = s.clock.sim_time;
      }
    };
    const setTask = (id: string, status: TaskStatus, progress?: number) => {
      const t = s.tasks.find((item) => item.vehicle_id === id);
      if (t) {
        t.status = status;
        if (progress !== undefined) t.progress = progress;
        t.updated_at = s.clock.sim_time;
      }
    };
    const setChannel = (idx: number, status: ChannelStatus, vehicleId: string | null, soc: number, progress: number) => {
      const c = s.channels[idx - 1];
      if (c) {
        c.status = status;
        c.vehicle_id = vehicleId;
        c.soc = soc;
        c.progress = progress;
      }
    };

    // 临时路障触发的 REPLANNING 在本步恢复为 NAVIGATING 后继续原流程
    if (this.replan > 0) {
      this.replan -= 1;
      s.robot.status = 'NAVIGATING';
    }

    if (this.step === 1) {
      s.clock.state = 'RUNNING';
      TARGET_IDS.forEach((id) => {
        const v = s.vehicles.find((item) => item.vehicle_id === id);
        if (v) { v.status = 'SELECTED'; v.stale = false; v.timestamp = s.clock.sim_time; }
      });
      s.tasks = TARGET_IDS.map((id, i) => {
        const zone = s.vehicles.find((v) => v.vehicle_id === id)?.zone ?? 'A';
        return {
          task_id: `T-${String(i + 1).padStart(4, '0')}`, batch_id: 'B-0001', vehicle_id: id,
          zone, channel: i + 1, status: 'PENDING' as TaskStatus,
          progress: 0, created_at: s.clock.sim_time, updated_at: s.clock.sim_time,
        };
      });
      s.channels.forEach((c, i) => {
        c.status = 'CONNECTING';
        c.vehicle_id = TARGET_IDS[i];
        c.soc = TARGET_SEED_SOC[i];
        c.progress = 0;
      });
      this.pushEvents(s,
        this.ev(s, 'SIM_STARTED', '—', '仿真已启动'),
        this.ev(s, 'BATCH_CREATED', '—', '创建批次 B-0001，选中 5 辆低电量车辆'),
      );
    } else if (this.step === 2) {
      s.robot.status = 'NAVIGATING';
      s.robot.speed = 0.8;
      s.robot.heading = 68;
      s.robot.planned_path = [[70, 40], [74, 28], [78, 14], [78, 6]];
      s.robot.traveled_path = [[70, 40]];
      TARGET_IDS.forEach((id) => setTask(id, 'NAVIGATING'));
      this.pushEvents(s, ...TARGET_IDS.map((id) =>
        this.ev(s, 'TASK_ASSIGNED', id, `车辆 ${id} 任务已分配给机器人 R01`)));
    } else if (this.step === 3) {
      s.robot.x = 74; s.robot.y = 28; s.robot.heading = 72;
      s.robot.traveled_path = [[70, 40], [74, 28]];
    } else if (this.step === 4) {
      s.robot.x = 78; s.robot.y = 14; s.robot.heading = 90;
      s.robot.traveled_path = [[70, 40], [74, 28], [78, 14]];
    } else if (this.step === 5) {
      s.robot.x = 78; s.robot.y = 6; s.robot.speed = 0; s.robot.status = 'DOCKING';
      s.robot.traveled_path = [[70, 40], [74, 28], [78, 14], [78, 6]];
      // 集群对接：5 辆车统一 SELECTED → DOCKING（V8），下一步统一 DOCKING → CHARGING（V9）
      TARGET_IDS.forEach((id) => {
        setVehicle(id, 'DOCKING');
        setTask(id, 'DOCKING');
      });
    } else if (this.step === 6) {
      s.robot.status = 'CHARGING';
      TARGET_IDS.forEach((id, i) => {
        setVehicle(id, 'CHARGING');
        setTask(id, 'CHARGING', 0.05);
        setChannel(i + 1, 'CHARGING', id, TARGET_SEED_SOC[i], 0.05);
      });
      this.pushEvents(s, ...TARGET_IDS.map((id) =>
        this.ev(s, 'DOCK_OK', id, `车辆 ${id} 对接成功，充电通道已连接`)));
    } else if (this.step >= 7 && this.step <= 10) {
      const p = this.step === 7 ? 0.2 : this.step === 8 ? 0.45 : this.step === 9 ? 0.7 : 0.95;
      TARGET_IDS.forEach((id, i) => {
        const soc = Math.round(TARGET_SEED_SOC[i] + (80 - TARGET_SEED_SOC[i]) * p);
        setVehicle(id, 'CHARGING', soc);
        setTask(id, 'CHARGING', p);
        setChannel(i + 1, 'CHARGING', id, soc, p);
      });
      s.robot.soc = Math.max(20, s.robot.soc - 2);
    } else if (this.step === 11) {
      s.robot.status = 'RETURNING';
      s.robot.speed = 0.8;
      s.robot.heading = 270;
      s.robot.planned_path = [[78, 6], [70, 20], [70, 40]];
      TARGET_IDS.forEach((id, i) => {
        setVehicle(id, 'CHARGED', 80);
        setTask(id, 'COMPLETED', 1);
        setChannel(i + 1, 'DONE', id, 80, 1);
      });
      this.pushEvents(s, ...TARGET_IDS.map((id) =>
        this.ev(s, 'CHARGE_DONE', id, `车辆 ${id} 充电完成，SOC 达到目标值 80%`)));
    } else if (this.step === 12) {
      TARGET_IDS.forEach((id, i) => {
        setVehicle(id, 'PARKED', 80);
        setChannel(i + 1, 'EMPTY', null, 0, 0);
      });
      this.pushEvents(s, ...TARGET_IDS.map((id) =>
        this.ev(s, 'VEHICLE_DEPARTED', id, `车辆 ${id} 离位，车位与通道已释放`)));
    } else if (this.step === 13) {
      s.robot.x = 70; s.robot.y = 20; s.robot.heading = 270;
      s.robot.traveled_path = [[70, 40], [74, 28], [78, 14], [78, 6], [70, 20]];
    } else if (this.step === 14) {
      s.robot.x = 70; s.robot.y = 40; s.robot.status = 'IDLE';
      s.robot.speed = 0; s.robot.soc = 100; s.robot.planned_path = [];
      this.pushEvents(s, this.ev(s, 'RETURN_BASE', 'R01', '机器人 R01 已返回充电基站'));
    } else if (this.step === 15) {
      s.clock.state = 'IDLE';
      s.clock.speed = 1;
    }

    this.state = s;
    this.emit();
    if (this.step >= TOTAL_STEPS) this.stopTimer();
  }

  // ---- 控制（与 POST /api/simulation/* 一一对应） ----

  start(speed = 1): void {
    if (this.timer !== null) return;
    if (this.step >= TOTAL_STEPS) this.reset();
    this.state.clock.speed = speed;
    this.state.clock.state = 'RUNNING';
    this.emit();
    this.schedule();
  }

  pause(): void {
    if (this.state.clock.state !== 'RUNNING') return;
    this.stopTimer();
    const s = clone(this.state);
    s.clock.state = 'PAUSED';
    this.pushEvents(s, this.ev(s, 'SIM_PAUSED', '—', '仿真已暂停'));
    this.state = s;
    this.emit();
  }

  resume(): void {
    if (this.state.clock.state !== 'PAUSED') return;
    const s = clone(this.state);
    s.clock.state = 'RUNNING';
    this.pushEvents(s, this.ev(s, 'SIM_RESUMED', '—', '仿真已恢复'));
    this.state = s;
    this.emit();
    this.schedule();
  }

  reset(): void {
    this.stopTimer();
    this.step = 0;
    this.eventSeq = 0;
    this.replan = 0;
    this.state = createInitialState();
    this.emit();
  }

  setSpeed(speed: number): void {
    if (![1, 10, 60].includes(speed)) return;
    const wasRunning = this.timer !== null;
    const s = clone(this.state);
    s.clock.speed = speed;
    if (wasRunning) {
      this.pushEvents(s, this.ev(s, 'SPEED_CHANGED', '—', `仿真倍速切换为 ${speed}x`));
    }
    this.state = s;
    this.emit();
    if (wasRunning) this.schedule();
  }

  addObstacle(): void {
    const s = clone(this.state);
    this.pushEvents(s,
      this.ev(s, 'OBSTACLE_DETECTED', 'R01', '检测到临时路障（75, 30）'),
      this.ev(s, 'REPLAN_TRIGGERED', 'R01', '机器人触发路径重规划'),
    );
    if (s.robot.status === 'NAVIGATING') {
      s.robot.status = 'REPLANNING';
      this.replan = 2;
    }
    this.state = s;
    this.emit();
  }
}

/** Mock 模式下由任务与车辆派生通道状态（真实后端模式在 useSimulation 中复用此逻辑）。 */
export function deriveChannels(tasks: Task[], vehicles: VehicleTelemetry[]): Channel[] {
  const latest: Record<number, Task> = {};
  tasks.forEach((t) => {
    const cur = latest[t.channel];
    if (!cur || t.updated_at >= cur.updated_at) latest[t.channel] = t;
  });
  return Array.from({ length: 5 }, (_, i) => {
    const t = latest[i + 1];
    const v = t ? vehicles.find((item) => item.vehicle_id === t.vehicle_id) : undefined;
    let status: ChannelStatus = 'EMPTY';
    if (t) {
      if (t.status === 'PENDING' || t.status === 'NAVIGATING' || t.status === 'DOCKING') status = 'CONNECTING';
      else if (t.status === 'CHARGING') status = 'CHARGING';
      else if (t.status === 'COMPLETED') status = 'DONE';
      else if (t.status === 'FAILED') status = 'FAULT';
    }
    return {
      id: `CH${i + 1}`, index: i + 1, status,
      vehicle_id: t?.vehicle_id ?? null, soc: v?.soc ?? 0, progress: t?.progress ?? 0,
    };
  });
}
