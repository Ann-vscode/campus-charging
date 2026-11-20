/**
 * 五路充电通道卡片。每张卡片独立渲染：单路对接失败/故障只影响本卡片，
 * 不会遮挡或破坏其他通道（强制要求）。全部为仿真模式 · 模拟数据。
 */
import type { Channel } from '../types';
import { CHANNEL_STATUS_COLOR, CHANNEL_STATUS_LABEL } from '../types';

interface Props {
  channels: Channel[];
}

export function ChargeChannels({ channels }: Props) {
  // 契约固定 5 路；不足时补空卡，保证布局始终是 5 张且互不遮挡
  const cards: Channel[] = Array.from({ length: 5 }, (_, i): Channel =>
    channels[i] ?? {
      id: `CH${i + 1}`, index: i + 1, status: 'EMPTY',
      vehicle_id: null, soc: 0, progress: 0,
    },
  );

  return (
    <section className="panel channels-panel">
      <h2 className="panel-title">
        五路充电通道 <span className="tag-sim">仿真</span>
        <span className="panel-sub">各路独立状态机</span>
      </h2>

      <div className="channel-grid">
        {cards.map((c) => (
          <article key={c.id} className={`channel-card ch-${c.status.toLowerCase()}`}>
            <div className="ch-head">
              <b className="ch-id">{c.id}</b>
              <span className="badge" style={{ background: CHANNEL_STATUS_COLOR[c.status] }}>
                {CHANNEL_STATUS_LABEL[c.status]}
              </span>
            </div>
            <div className="ch-vehicle">{c.vehicle_id ?? '— 空闲 —'}</div>
            <div className="ch-soc">SOC <b>{Math.round(c.soc)}%</b></div>
            <div className="progress-track">
              <div
                className="progress-fill"
                style={{ width: `${Math.round(c.progress * 100)}%`, background: CHANNEL_STATUS_COLOR[c.status] }}
              />
            </div>
            <div className="ch-footer">
              <span>进度</span><b>{Math.round(c.progress * 100)}%</b>
            </div>
          </article>
        ))}
      </div>

      <p className="hint">各通道独立运行；单车对接失败或通道故障不会影响其他通道（仿真数据）。</p>
    </section>
  );
}
