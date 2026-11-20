/**
 * 事件日志：按事件类型筛选 + 列表（最新在上）。
 * 全部为仿真模式 · 模拟车辆数据。
 */
import { useState } from 'react';
import type { EventType, TaskEvent } from '../types';
import { EVENT_TYPES, EVENT_TYPE_LABEL, formatSimTime } from '../types';

interface Props {
  events: TaskEvent[];
}

export function EventLog({ events }: Props) {
  const [filter, setFilter] = useState<EventType | 'ALL'>('ALL');
  const shown = filter === 'ALL' ? events : events.filter((e) => e.type === filter);

  return (
    <section className="panel event-log">
      <h2 className="panel-title">
        事件日志 <span className="tag-sim">仿真</span>
        <span className="panel-sub">类型筛选 · 最新在上</span>
      </h2>

      <div className="event-filter">
        <label htmlFor="event-filter-select">筛选类型</label>
        <select
          id="event-filter-select"
          value={filter}
          onChange={(e) => setFilter(e.target.value as EventType | 'ALL')}
        >
          <option value="ALL">全部类型</option>
          {EVENT_TYPES.map((t) => (
            <option key={t} value={t}>{EVENT_TYPE_LABEL[t]}</option>
          ))}
        </select>
        <span className="muted">共 {shown.length} 条（仿真数据）</span>
      </div>

      <ul className="event-list">
        {shown.length === 0 && <li className="muted event-empty">暂无事件，点击「启动系统」开始仿真演示。</li>}
        {shown.map((e) => (
          <li key={e.event_id} className={`event-item ev-${e.type.toLowerCase()}`}>
            <span className="ev-time">{formatSimTime(e.timestamp)}</span>
            <span className="ev-type">{EVENT_TYPE_LABEL[e.type]}</span>
            <span className="ev-vehicle">{e.vehicle_id}</span>
            <span className="ev-msg">{e.message}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
