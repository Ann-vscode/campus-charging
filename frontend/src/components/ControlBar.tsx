/**
 * 控制条：启动 / 暂停 / 恢复 / 复位 / 倍速 1x·10x·60x / 添加临时路障。
 * 按钮按 clock.state 禁用，不出现无响应死按钮。全部为仿真模式。
 */
import type { Clock } from '../types';
import { CLOCK_STATE_LABEL, formatSimTime } from '../types';

type ConnectionLabel = string;

interface Props {
  clock: Clock;
  tick: number;
  connection: ConnectionLabel;
  mode: 'mock' | 'backend';
  onStart: () => void;
  onPause: () => void;
  onResume: () => void;
  onReset: () => void;
  onSpeed: (speed: number) => void;
  onObstacle: () => void;
}

export function ControlBar({
  clock, tick, connection, mode, onStart, onPause, onResume, onReset, onSpeed, onObstacle,
}: Props) {
  const isIdle = clock.state === 'IDLE';
  const isRunning = clock.state === 'RUNNING';
  const isPaused = clock.state === 'PAUSED';

  return (
    <section className="panel control-bar">
      <div className="control-group">
        <button className="btn btn-primary" onClick={onStart} disabled={isRunning}>
          启动系统
        </button>
        <button className="btn" onClick={onPause} disabled={!isRunning}>
          暂停
        </button>
        <button className="btn" onClick={onResume} disabled={!isPaused}>
          恢复
        </button>
        <button className="btn" onClick={onReset} disabled={isIdle && tick === 0}>
          复位
        </button>
        <button className="btn btn-warn" onClick={onObstacle}>
          添加临时路障
        </button>
      </div>

      <div className="control-group control-speed">
        <span className="control-label">倍速</span>
        {[1, 10, 60].map((s) => (
          <button
            key={s}
            className={`btn btn-speed ${clock.speed === s ? 'active' : ''}`}
            onClick={() => onSpeed(s)}
          >
            {s}x
          </button>
        ))}
      </div>

      <div className="control-status">
        <span className={`status-dot ${connection}`} />
        {mode === 'mock' ? 'Mock 数据源' : `WS ${connection}`} · tick {tick}
        <br />
        <span className="muted">{CLOCK_STATE_LABEL[clock.state]} · 仿真时钟 {formatSimTime(clock.sim_time)}</span>
      </div>
    </section>
  );
}
