/**
 * 校园示意地图（SVG）：基站 / A B C 停车区 / 车位 / 车辆编号与电量颜色 /
 * 机器人位置与朝向 / 规划路径与已走路径 / 静态与临时障碍。
 * 全部为仿真模式 · 模拟车辆数据。
 */
import type { Obstacle, Point2D, RobotTelemetry, Task, VehicleTelemetry } from '../types';
import { socColor, VEHICLE_STATUS_COLOR, VEHICLE_STATUS_LABEL } from '../types';

const SCALE = 10;
const px = (n: number): number => n * SCALE;
const toPoints = (pts: Point2D[]): string => pts.map((p) => `${px(p[0])},${px(p[1])}`).join(' ');

const ZONES = [
  { id: 'A', name: 'A 停车区', x: 0, y: 0, w: 30, h: 20 },
  { id: 'B', name: 'B 停车区', x: 50, y: 0, w: 40, h: 20 },
  { id: 'C', name: 'C 停车区', x: 110, y: 0, w: 30, h: 20 },
];

const STATIC_OBSTACLES = [
  { x: 40, y: 10, r: 2, label: '花坛' },
  { x: 100, y: 12, r: 3, label: '建筑' },
  { x: 105, y: 30, r: 0.5, label: '灯柱' },
];

interface Props {
  vehicles: VehicleTelemetry[];
  robot: RobotTelemetry;
  tasks: Task[];
  obstacles?: Obstacle[];
}

export function CampusMap({ vehicles, robot, tasks, obstacles = [] }: Props) {
  const targetIds = new Set(tasks.filter((t) => t.status !== 'COMPLETED').map((t) => t.vehicle_id));

  return (
    <section className="panel map-panel">
      <h2 className="panel-title">
        校园示意地图 <span className="tag-sim">仿真</span>
        <span className="panel-sub">坐标来自 campus_basic.yaml · 模拟车辆数据</span>
      </h2>

      <div className="map-wrap">
        <svg className="campus-map" viewBox="0 0 1460 500" role="img" aria-label="校园仿真示意地图">
          <rect x="0" y="0" width="1460" height="500" rx="12" fill="#0f1a2d" />

          {/* 停车区 */}
          {ZONES.map((z) => (
            <g key={z.id}>
              <rect
                x={px(z.x)} y={px(z.y)} width={px(z.w)} height={px(z.h)}
                rx="10" fill="#142b45" stroke="#3d76ad" strokeWidth="2"
              />
              <text x={px(z.x) + 12} y={px(z.y) + 26} fill="#9cc9ff" fontSize="17" fontWeight="700">
                {z.name}
              </text>
            </g>
          ))}

          {/* 车位 */}
          {vehicles.map((v) => (
            <rect
              key={`slot-${v.vehicle_id}`}
              x={px(v.x) - 14} y={px(v.y) - 14} width="28" height="28" rx="5"
              fill="none" stroke="#33506e" strokeWidth="1.5"
            />
          ))}

          {/* 静态障碍 */}
          {STATIC_OBSTACLES.map((o) => (
            <g key={o.label}>
              <circle
                cx={px(o.x)} cy={px(o.y)} r={px(o.r)}
                fill="#ff9800" fillOpacity="0.16" stroke="#ff9800" strokeWidth="2" strokeDasharray="6 4"
              />
              <text x={px(o.x)} y={px(o.y) - px(o.r) - 6} textAnchor="middle" fontSize="12" fill="#ffb74d">
                {o.label}（仿真）
              </text>
            </g>
          ))}

          {/* 临时路障 */}
          {obstacles.map((o, i) => (
            <g key={`tmp-${i}`}>
              <circle
                cx={px(o.x)} cy={px(o.y)} r={px(o.radius)}
                fill="#e53935" fillOpacity="0.28" stroke="#ff5252" strokeWidth="3"
              />
              <text x={px(o.x)} y={px(o.y) - px(o.radius) - 8} textAnchor="middle" fontSize="13" fontWeight="700" fill="#ff8a80">
                临时路障
              </text>
            </g>
          ))}

          {/* 已走路径 / 规划路径 */}
          {robot.traveled_path.length > 1 && (
            <polyline points={toPoints(robot.traveled_path)} fill="none" stroke="#4be3a6" strokeWidth="4" strokeLinejoin="round" />
          )}
          {robot.planned_path.length > 1 && (
            <polyline
              points={toPoints(robot.planned_path)} fill="none" stroke="#8fbaff"
              strokeWidth="4" strokeDasharray="10 8" strokeLinejoin="round"
            />
          )}

          {/* 充电基站 */}
          <g>
            <circle cx={px(70)} cy={px(40)} r="22" fill="#ffca28" stroke="#fff8e1" strokeWidth="3" />
            <text x={px(70)} y={px(40) + 6} textAnchor="middle" fontSize="15" fontWeight="800" fill="#4e3700">基站</text>
          </g>

          {/* 车辆：填充色=电量，描边色=状态；目标车辆加白色高亮环 */}
          {vehicles.map((v) => {
            const cx = px(v.x);
            const cy = px(v.y);
            const targeted = targetIds.has(v.vehicle_id);
            return (
              <g key={v.vehicle_id}>
                <title>{`${v.vehicle_id} · ${VEHICLE_STATUS_LABEL[v.status]} · SOC ${v.soc}%（仿真数据）`}</title>
                {targeted && <circle cx={cx} cy={cy} r="17" fill="none" stroke="#ffffff" strokeWidth="2.5" />}
                <circle
                  cx={cx} cy={cy} r="11"
                  fill={socColor(v.soc)}
                  stroke={VEHICLE_STATUS_COLOR[v.status]}
                  strokeWidth="4"
                />
                <text x={cx} y={cy - 18} textAnchor="middle" fontSize="12" fontWeight="700" fill="#e8f2ff">
                  {v.vehicle_id}
                </text>
              </g>
            );
          })}

          {/* 机器人：三角形指向 heading 方向 */}
          <g transform={`translate(${px(robot.x)} ${px(robot.y)}) rotate(${robot.heading})`}>
            <polygon points="20,0 -14,12 -14,-12" fill="#29b6f6" stroke="#e1f5fe" strokeWidth="2.5" />
          </g>
          <text x={px(robot.x)} y={px(robot.y) + 32} textAnchor="middle" fontSize="13" fontWeight="800" fill="#7dd3fc">
            {robot.robot_id} · {Math.round(robot.soc)}%
          </text>
        </svg>
      </div>

      <div className="map-legend">
        <span><i style={{ background: '#2e9e5b' }} />电量 ≥50%</span>
        <span><i style={{ background: '#fb8c00' }} />20%~50%</span>
        <span><i style={{ background: '#e53935' }} />&lt;20%</span>
        <span><i className="ring" />本批目标车辆</span>
        <span><i className="line-solid" />已走路径</span>
        <span><i className="line-dash" />规划路径</span>
        <span className="legend-note">全部为仿真模式 · 模拟车辆数据</span>
      </div>
    </section>
  );
}
