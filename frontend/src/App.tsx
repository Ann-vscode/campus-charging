/**
 * 主监控页面装配（R1.3 最小闭环）。
 * 页面顶部显著标注「仿真模式 · 模拟车辆数据」。
 */
import { useState } from 'react';
import { CampusMap } from './components/CampusMap';
import { ChargeChannels } from './components/ChargeChannels';
import { ControlBar } from './components/ControlBar';
import { EventLog } from './components/EventLog';
import { TaskPanel } from './components/TaskPanel';
import type { Obstacle } from './types';
import { useSimulation } from './useSimulation';

export default function App() {
  const sim = useSimulation();
  const [obstacles, setObstacles] = useState<Obstacle[]>([]);

  const handleObstacle = () => {
    sim.addObstacle();
    setObstacles((prev) => [...prev, { x: 75, y: 30, radius: 1.5 }]);
  };

  const handleReset = () => {
    sim.reset();
    setObstacles([]);
  };

  return (
    <div className="app">
      <header className="app-header">
        <div className="title-block">
          <h1>校园共享电动车移动集群充电仿真系统</h1>
          <div className="subtitle">监控平台 · R1.3 前端最小闭环</div>
        </div>
        <div className="mode-banner">仿真模式 · 模拟车辆数据</div>
        <div className="header-meta">
          <span>数据源：<b>{sim.mode === 'mock' ? '内置 Mock' : '真实后端'}</b></span>
          <span>场景：campus_basic.yaml（30 辆 / 5 路通道）</span>
        </div>
      </header>

      {sim.error && (
        <div className="error-banner" role="alert">
          提示：{sim.error}（若未启动后端，请保持默认 Mock 模式或在 .env.local 中设置 VITE_USE_MOCK=true）
        </div>
      )}

      <main className="dashboard">
        <div className="slot-map">
          <CampusMap
            vehicles={sim.state.vehicles}
            robot={sim.state.robot}
            tasks={sim.state.tasks}
            obstacles={obstacles}
          />
        </div>

        <div className="slot-right">
          <TaskPanel
            tasks={sim.state.tasks}
            vehicles={sim.state.vehicles}
            robot={sim.state.robot}
            clock={sim.state.clock}
          />
          <ChargeChannels channels={sim.state.channels} />
        </div>

        <div className="slot-control">
          <ControlBar
            clock={sim.state.clock}
            tick={sim.state.tick}
            connection={sim.connection}
            mode={sim.mode}
            onStart={() => sim.start(sim.state.clock.speed)}
            onPause={sim.pause}
            onResume={sim.resume}
            onReset={handleReset}
            onSpeed={sim.setSpeed}
            onObstacle={handleObstacle}
          />
        </div>

        <div className="slot-events">
          <EventLog events={sim.state.events} />
        </div>
      </main>

      <footer className="app-footer">
        本系统为课程项目仿真演示，所有车辆、机器人、电量、路径、事件均为
        <b> 仿真模式 · 模拟车辆数据</b>，非真实车辆数据。
      </footer>
    </div>
  );
}
