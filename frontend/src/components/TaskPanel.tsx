/**
 * 右侧任务面板：当前任务、目标 5 车、机器人状态与电量、本批进度 x/5。
 * 全部为仿真模式 · 模拟车辆数据。
 */
import type { Clock, RobotTelemetry, Task, VehicleTelemetry } from '../types';
import {
  CLOCK_STATE_LABEL, ROBOT_STATUS_LABEL, TASK_STATUS_LABEL,
  VEHICLE_STATUS_LABEL, formatSimTime, socColor,
} from '../types';

interface Props {
  tasks: Task[];
  vehicles: VehicleTelemetry[];
  robot: RobotTelemetry;
  clock: Clock;
}

export function TaskPanel({ tasks, vehicles, robot, clock }: Props) {
  const completed = tasks.filter((t) => t.status === 'COMPLETED').length;
  const current = tasks.find((t) => t.status !== 'COMPLETED' && t.status !== 'FAILED');
  const currentVehicle = current
    ? vehicles.find((v) => v.vehicle_id === current.vehicle_id)
    : undefined;

  return (
    <section className="panel task-panel">
      <h2 className="panel-title">
        任务面板 <span className="tag-sim">仿真</span>
        <span className="panel-sub">批次 B-0001 · 模拟数据</span>
      </h2>

      <div className="batch-progress">
        <div>
          <span className="label">本批进度</span>
          <span className="progress-big">{completed}<small>/5</small></span>
        </div>
        <div className="progress-track large">
          <div className="progress-fill" style={{ width: `${completed / 5 * 100}%` }} />
        </div>
        <div className="clock-line">
          仿真时钟 {formatSimTime(clock.sim_time)} · {CLOCK_STATE_LABEL[clock.state]} · {clock.speed}x
        </div>
      </div>

      <h3 className="block-title">当前任务</h3>
      {current ? (
        <div className="current-task">
          <div className="ct-row"><b>{current.task_id}</b> · 通道 CH{current.channel}</div>
          <div className="ct-row">目标车辆 <b>{current.vehicle_id}</b>（{current.zone} 区）</div>
          <div className="ct-row">任务状态 <span className="badge blue">{TASK_STATUS_LABEL[current.status]}</span></div>
          {currentVehicle && (
            <div className="ct-row">车辆电量
              <span className="soc-pill" style={{ background: socColor(currentVehicle.soc) }}>
                {currentVehicle.soc}%
              </span>
              <span className="badge">{VEHICLE_STATUS_LABEL[currentVehicle.status]}</span>
            </div>
          )}
          <div className="progress-track">
            <div className="progress-fill" style={{ width: `${Math.round(current.progress * 100)}%` }} />
          </div>
          <div className="ct-row muted">充电进度 {Math.round(current.progress * 100)}%</div>
        </div>
      ) : (
        <div className="empty-box">本批任务已完成 / 尚未派发（仿真数据）</div>
      )}

      <h3 className="block-title">目标车辆（5 辆）</h3>
      <ul className="target-list">
        {tasks.length === 0 && <li className="muted">等待启动系统…</li>}
        {tasks.map((t) => {
          const v = vehicles.find((item) => item.vehicle_id === t.vehicle_id);
          return (
            <li key={t.task_id} className={t.status === 'COMPLETED' ? 'done' : ''}>
              <span className="tid">{t.vehicle_id}</span>
              <span className="tzone">{t.zone} 区</span>
              <span className="soc-pill" style={{ background: socColor(v?.soc ?? 0) }}>{v?.soc ?? 0}%</span>
              <span className="badge">{TASK_STATUS_LABEL[t.status]}</span>
            </li>
          );
        })}
      </ul>

      <h3 className="block-title">机器人 R01</h3>
      <div className="robot-box">
        <div className="ct-row">
          状态 <span className="badge cyan">{ROBOT_STATUS_LABEL[robot.status]}</span>
        </div>
        <div className="ct-row">储能 SOC <b>{Math.round(robot.soc)}%</b></div>
        <div className="progress-track">
          <div className="progress-fill robot" style={{ width: `${robot.soc}%` }} />
        </div>
        <div className="ct-row muted">位置 ({robot.x.toFixed(1)}, {robot.y.toFixed(1)}) · 朝向 {Math.round(robot.heading)}°</div>
      </div>
    </section>
  );
}
