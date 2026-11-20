/**
 * 数据源桥接 Hook：
 * - Mock 模式：订阅 MockSimulation，点击启动后自动演完整流程（无后端依赖）。
 * - 真实后端模式：GET 拉初始/轮询任务，WS 推 snapshot/tick 增量更新，控制走 POST。
 * 所有数据均为仿真模式 / 模拟车辆数据。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ApiError, api, createInitialState, deriveChannels, MockSimulation, useMockData,
} from './api';
import { defaultWsUrl, TelemetrySocket, type WsFrame, type WsStatus } from './ws';
import type { SimState } from './types';

export interface SimulationController {
  state: SimState;
  mode: 'mock' | 'backend';
  connection: WsStatus | 'mock';
  error: string | null;
  start: (speed?: number) => void;
  pause: () => void;
  resume: () => void;
  reset: () => void;
  setSpeed: (speed: number) => void;
  addObstacle: () => void;
}

function describeError(e: unknown): string {
  if (e instanceof ApiError) return `${e.code}：${e.message}`;
  if (e instanceof Error) return e.message;
  return '未知错误';
}

export function useSimulation(): SimulationController {
  const [state, setState] = useState<SimState>(createInitialState);
  const [connection, setConnection] = useState<WsStatus | 'mock'>(useMockData ? 'mock' : 'connecting');
  const [error, setError] = useState<string | null>(null);
  const mockRef = useRef<MockSimulation | null>(null);

  useEffect(() => {
    if (useMockData) {
      const mock = new MockSimulation();
      mockRef.current = mock;
      const unsubscribe = mock.subscribe(setState);
      return () => {
        unsubscribe();
        mockRef.current = null;
      };
    }

    let cancelled = false;

    const refreshClockAndTasks = async () => {
      const [scenario, tasks] = await Promise.all([api.getScenario(), api.getTasks()]);
      if (!cancelled) {
        setState((prev) => ({
          ...prev,
          clock: scenario.clock,
          tasks: tasks.tasks,
          channels: deriveChannels(tasks.tasks, prev.vehicles),
        }));
      }
    };

    // 初始 REST 快照
    void (async () => {
      try {
        const [vehicles, robot, tasks, events, scenario] = await Promise.all([
          api.getVehicles(), api.getRobot(), api.getTasks(), api.getEvents(), api.getScenario(),
        ]);
        if (cancelled) return;
        setState((prev) => ({
          ...prev,
          vehicles: vehicles.vehicles,
          robot,
          tasks: tasks.tasks,
          events: events.events,
          channels: deriveChannels(tasks.tasks, vehicles.vehicles),
          clock: scenario.clock,
        }));
      } catch (e) {
        if (!cancelled) setError(describeError(e));
      }
    })();

    // WS 增量推送（按 tick 去重在 ws.ts 内完成）
    const socket = new TelemetrySocket(defaultWsUrl(), {
      onStatus: setConnection,
      onFrame: (frame: WsFrame) => {
        if (frame.type === 'error') {
          setError(frame.message ? `WS ${frame.code ?? ''}：${frame.message}` : 'WebSocket 错误帧');
          return;
        }
        setState((prev) => {
          const next: SimState = { ...prev };
          if (frame.clock) next.clock = frame.clock;
          if (typeof frame.tick === 'number') next.tick = frame.tick;
          let vehiclesChanged = false;
          let eventsChanged = false;

          (frame.messages ?? []).forEach((m) => {
            if (m.type === 'RobotTelemetry') {
              next.robot = m.payload;
            } else if (m.type === 'VehicleTelemetry') {
              const idx = next.vehicles.findIndex((v) => v.vehicle_id === m.payload.vehicle_id);
              if (idx >= 0) {
                const arr = next.vehicles.slice();
                arr[idx] = m.payload;
                next.vehicles = arr;
              } else {
                next.vehicles = [...next.vehicles, m.payload];
              }
              vehiclesChanged = true;
            } else if (m.type === 'TaskEvent') {
              if (!next.events.some((e) => e.event_id === m.payload.event_id)) {
                next.events = [m.payload, ...next.events].slice(0, 500);
                eventsChanged = true;
              }
            }
          });

          if (vehiclesChanged) next.channels = deriveChannels(next.tasks, next.vehicles);
          if (!vehiclesChanged && !eventsChanged && !frame.clock && !frame.messages?.length) return prev;
          return next;
        });
      },
    });
    socket.connect();

    // 任务/通道不在 WS 消息类型内，按契约需轮询 GET /api/tasks
    const poll = window.setInterval(() => {
      void (async () => {
        try {
          const tasks = await api.getTasks();
          if (!cancelled) {
            setState((prev) => ({
              ...prev,
              tasks: tasks.tasks,
              channels: deriveChannels(tasks.tasks, prev.vehicles),
            }));
          }
        } catch { /* 单次轮询失败静默，等待下次 */ }
      })();
      void refreshClockAndTasks().catch(() => { /* 单次轮询失败静默 */ });
    }, 2000);

    return () => {
      cancelled = true;
      window.clearInterval(poll);
      socket.close();
    };
  }, []);

  const runControl = useCallback(async (action: () => Promise<unknown>, refresh: boolean) => {
    if (useMockData) {
      setError(null);
      return;
    }
    try {
      await action();
      setError(null);
      if (refresh) await refreshClockAndTasksOutside();
    } catch (e) {
      setError(describeError(e));
    }
  }, []);

  // 控制后立即回读时钟与任务，保证按钮状态及时更新（真实后端模式）
  async function refreshClockAndTasksOutside(): Promise<void> {
    const [scenario, tasks] = await Promise.all([api.getScenario(), api.getTasks()]);
    setState((prev) => ({
      ...prev,
      clock: scenario.clock,
      tasks: tasks.tasks,
      channels: deriveChannels(tasks.tasks, prev.vehicles),
    }));
  }

  const start = useCallback((speed = 1) => {
    if (useMockData) {
      mockRef.current?.setSpeed(speed);
      mockRef.current?.start();
    } else {
      void runControl(() => api.start({ speed }), true);
    }
  }, [runControl]);

  const pause = useCallback(() => {
    if (useMockData) mockRef.current?.pause();
    else void runControl(() => api.pause(), true);
  }, [runControl]);

  const resume = useCallback(() => {
    if (useMockData) mockRef.current?.resume();
    else void runControl(() => api.resume(), true);
  }, [runControl]);

  const reset = useCallback(() => {
    if (useMockData) mockRef.current?.reset();
    else void runControl(() => api.reset(), true);
  }, [runControl]);

  const setSpeed = useCallback((speed: number) => {
    if (useMockData) mockRef.current?.setSpeed(speed);
    else void runControl(() => api.setSpeed(speed), true);
  }, [runControl]);

  const addObstacle = useCallback(() => {
    if (useMockData) mockRef.current?.addObstacle();
    else void runControl(() => api.addObstacle({ x: 75, y: 30, radius: 1.5 }), false);
  }, [runControl]);

  return {
    state,
    mode: useMockData ? 'mock' : 'backend',
    connection,
    error,
    start,
    pause,
    resume,
    reset,
    setSpeed,
    addObstacle,
  };
}
