# 前端监控平台（R1.3 最小闭环）

校园共享电动车移动集群充电仿真系统 · 前端监控页面。
**所有数据均为「仿真模式 · 模拟车辆数据」，非真实车辆数据。**

技术栈：React 18 + TypeScript + Vite 5。

---

## 1. 启动命令

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 `http://localhost:5173`。

其他命令：

```bash
npm run build     # tsc 类型检查 + 生产构建
npm run preview   # 预览构建产物
```

> 本轮未执行 `npm install`，只交付源码与 `package.json`。

---

## 2. Mock 模式（默认，推荐答辩使用）

- `src/api.ts` 中 `useMockData` 默认值为 `true`（仅当环境变量 `VITE_USE_MOCK === 'false'` 时才关闭）。
- 无需后端、无需 WebSocket，纯静态预览即可演示全流程。
- Mock 数据来自 `scenarios/campus_basic.yaml`：30 辆车（A/B/C 三区）、5 路充电通道、机器人起点 (70, 40)、低电量目标车 B10/A12/C02/A09/B06。
- **演示方式**：点击一次「启动系统」，页面自动演进：
  选车 → 派单/导航 → 到达对接 → 五路充电 → 充电完成 → 车辆离位 → 返基站 → 系统待命。
  全程无需人工点击确认。
- 控制条上的 暂停 / 恢复 / 复位 / 倍速（1x / 10x / 60x）/ 添加临时路障 均可真实改变 Mock 流程状态，无死按钮。
  - 导航中注入临时路障：机器人进入 `REPLANNING`，记录 `OBSTACLE_DETECTED` + `REPLAN_TRIGGERED` 事件，随后恢复导航。
- Mock 引擎内部按 15 个预设阶段推进，阶段间隔随倍速变化（1x≈900ms、10x≈450ms、60x≈220ms），便于投影演示。

---

## 3. 切换到真实后端

在 `frontend/` 下创建 `.env.local`：

```env
VITE_USE_MOCK=false
```

然后重启 `npm run dev`，并启动后端服务（约定同源 `http://<host>`，WebSocket 为 `ws://<host>/ws`）。

切换后的数据通路：

- **初始快照**：`GET /api/scenario`、`/api/vehicles`、`/api/robot`、`/api/tasks`、`/api/events`。
- **实时推送**：`src/ws.ts` 连接 `/ws`，建连订阅全部 channel；处理 `snapshot` / `tick` / `error` 帧，按 `tick` 序号去重；断线指数退避重连（最长 3s）并在控制条显示连接状态。
- **任务轮询**：任务与通道状态不在 WS 消息类型内，按契约以 `GET /api/tasks` 每 2s 轮询，通道状态由任务 + 车辆派生。
- **控制**：`POST /api/simulation/start|pause|resume|reset|speed`、`POST /api/demo/obstacle`。
- **信封解包**：`src/api.ts` 统一检查 `{code,message,simulation,timestamp,data}`，`code !== 0` 抛出 `ApiError(code, message)` 并显示在页面顶部提示条。

---

## 4. 目录结构

```
frontend/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── README.md
└── src/
    ├── main.tsx
    ├── App.tsx                 # 页面装配 + 顶部仿真标识
    ├── api.ts                  # HTTP 信封解包 / 错误处理 / useMockData / Mock 引擎
    ├── ws.ts                   # WebSocket 客户端（snapshot/tick/error、去重、重连）
    ├── useSimulation.ts        # Mock/真实后端数据源桥接 Hook
    ├── types.ts                # 契约枚举、类型、中文标签与状态色
    ├── styles.css              # 大字号、投影友好样式
    └── components/
        ├── CampusMap.tsx       # SVG 地图：基站/停车区/车位/车辆/机器人/路径/障碍
        ├── TaskPanel.tsx       # 当前任务、目标 5 车、机器人状态电量、进度 x/5
        ├── ChargeChannels.tsx  # 五路通道卡片（单路失败不影响其他）
        ├── ControlBar.tsx      # 启动/暂停/恢复/复位/倍速/临时路障
        └── EventLog.tsx        # 事件类型筛选与列表
```

---

## 5. 已实现 / 未实现

### 已实现

- [x] React + TS + Vite 工程骨架与构建脚本
- [x] 页面顶部与地图、面板的「仿真模式 · 模拟车辆数据」标注
- [x] SVG 校园示意地图：基站、A/B/C 停车区、车位、车辆编号与电量颜色、状态描边、机器人位置与朝向、规划/已走路径、静态与临时障碍
- [x] 任务面板：当前任务、目标 5 车、机器人状态与电量、本批进度 x/5
- [x] 五路充电通道卡片，独立状态渲染（单路失败不遮其他）
- [x] 控制条：启动/暂停/恢复/复位/倍速 1x·10x·60x/添加临时路障，按状态禁用按钮
- [x] 事件日志：17 类事件筛选，中文标签，最新在上
- [x] HTTP 统一信封解包 + 错误码提示（`ApiError`）
- [x] WebSocket 客户端：snapshot/tick/error、tick 去重、断线重连提示
- [x] Mock 模式：无后端一键自动演完整流程
- [x] 大字号、高对比状态色，适配答辩电脑与投影

### 未实现 / 已知问题

- [ ] 未执行 `npm install` 与构建验证（按要求跳过，需使用者本地安装依赖）。
- [ ] 真实后端 `/api/tasks` 与 WS tick 的联动仅按契约实现，未与后端实机联调。
- [ ] P4 阶段的精细路径动画、动态障碍物理避让、车位级 3D 效果不在本轮范围。
- [ ] 契约 `telemetry.json` 示例中的车辆 ID 为 `V-A-001` 格式，而场景 YAML 与实际演示使用 `A01/B04/C08`；前端按任务要求采用 YAML 格式，真实后端若输出 `V-A-001` 仍可作为字符串 ID 正常渲染（不影响状态机与颜色逻辑）。
- [ ] Mock 流程中 5 路充电为并行推进（演示「五路充电」效果），与真实后端按任务逐车推进的节奏可能不同；真实后端模式以后端推送为准。
- [ ] 组件级自动化测试与界面截图未包含在本轮交付。

---

## 6. 边界声明

本轮只新增/修改了 `frontend/` 目录下的文件；未改动 `contracts/`、`backend/`、`docs/` 或任何其他目录，未编写后端代码，未修改 API 契约。
