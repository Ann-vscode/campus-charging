/**
 * WebSocket 客户端（契约 api.md 第 7 节）。
 * - 建连后服务端先推 snapshot，之后每 100ms 一帧 tick（倍速不改变推送频率）。
 * - 帧结构：{type, simulation, timestamp, tick, clock, messages:[{type,payload}]}
 * - 前端按 tick 序号去重；断线指数退避重连并向 UI 提示。
 *
 * 所有数据均为仿真模式 / 模拟车辆数据。
 */
import type { Clock, RobotTelemetry, TaskEvent, VehicleTelemetry } from './types';

export type WsStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

export type WsMessage =
  | { type: 'RobotTelemetry'; payload: RobotTelemetry }
  | { type: 'VehicleTelemetry'; payload: VehicleTelemetry }
  | { type: 'TaskEvent'; payload: TaskEvent };

export interface WsFrame {
  type: 'snapshot' | 'tick' | 'error';
  simulation: boolean;
  timestamp: string;
  tick?: number;
  clock?: Clock;
  messages?: WsMessage[];
  code?: number;
  message?: string;
}

export interface WsHandlers {
  onFrame: (frame: WsFrame) => void;
  onStatus: (status: WsStatus) => void;
}

export function defaultWsUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/ws`;
}

export class TelemetrySocket {
  private ws: WebSocket | null = null;
  private lastTick = -1;
  private retry = 0;
  private reconnectTimer: number | null = null;
  private manualClose = false;

  constructor(
    private readonly url: string,
    private readonly handlers: WsHandlers,
  ) {}

  connect(): void {
    this.manualClose = false;
    this.open();
  }

  private open(): void {
    this.handlers.onStatus('connecting');
    let ws: WebSocket;
    try {
      ws = new WebSocket(this.url);
    } catch {
      this.handlers.onStatus('error');
      this.scheduleReconnect();
      return;
    }
    this.ws = ws;

    ws.onopen = () => {
      this.retry = 0;
      this.lastTick = -1;
      this.handlers.onStatus('connected');
      ws.send(JSON.stringify({
        op: 'subscribe',
        channels: ['robot', 'vehicles', 'tasks', 'events', 'clock'],
      }));
    };

    ws.onmessage = (event: MessageEvent<string>) => {
      let frame: WsFrame;
      try {
        frame = JSON.parse(event.data) as WsFrame;
      } catch {
        return; // 非法 JSON 帧直接忽略，不影响后续 tick
      }

      if (frame.type === 'tick') {
        if (typeof frame.tick === 'number') {
          if (frame.tick <= this.lastTick) return; // 按 tick 去重 + 乱序丢弃
          this.lastTick = frame.tick;
        }
      } else if (frame.type === 'snapshot') {
        this.lastTick = typeof frame.tick === 'number' ? frame.tick : -1;
      }

      this.handlers.onFrame(frame);
    };

    ws.onerror = () => {
      this.handlers.onStatus('error');
    };

    ws.onclose = () => {
      this.ws = null;
      if (!this.manualClose) {
        this.handlers.onStatus('disconnected');
        this.scheduleReconnect();
      }
    };
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer !== null || this.manualClose) return;
    const delay = Math.min(3000, 500 * Math.pow(2, this.retry++));
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.open();
    }, delay);
  }

  close(): void {
    this.manualClose = true;
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }
  }
}
