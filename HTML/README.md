# LedgerCrew · HTML 前端（任务流转大屏）

> 作者：Sunset ｜ 所属分支：`sunset`（前端专属开发分支，不作主干）
> 纯 HTML / CSS / JavaScript 实现，无需构建工具，双击即可运行。

## 功能概览

**两个页面**（底部导航互相切换）：
- 🖥️ **作战室**（index.html）：四模块任务流转大屏
- 📊 **仪表盘**（dashboard.html）：全流程数据统计

客户需求下发后，任务依次流经四个模块，每只小猫工位的电脑会播放对应动画：

```
客户接待  →  票据处理  →  数据核对  →  风险与交付
对话气泡     票据扫描OCR   账务比对打勾   风险护盾+交付进度环
```

- 🐱 四只渐变毛发小猫（橘猫/蓝灰猫/奶油猫/玄猫），会眨眼、摇尾、打字、完成后欢呼
- ▶️ 任务下发动画引擎：输入需求点「下发任务」，或直接看自动循环演示
- 📡 可接后端：接口不就绪时自动回退 Mock，页面永不白屏

## 目录结构

```
HTML/
├── index.html          # 作战室（四模块任务流转大屏）
├── dashboard.html      # 仪表盘（KPI / 趋势 / 环形图 / 柱状图 / 任务列表）
├── css/
│   ├── style.css       # 全局样式（小猫插画 / 屏幕动画 / 流转动效）
│   └── dashboard.css   # 仪表盘专用样式
├── js/
│   ├── api.js          # 前端请求层（含 Mock 回退，getDashboard 等）
│   ├── main.js         # 作战室渲染 + 任务流转动画引擎
│   └── dashboard.js    # 仪表盘图表渲染引擎（纯 SVG，无第三方库）
├── api/
│   ├── 接口文档.md      # v1.2 前后端对接契约（交后端同学照做）
│   └── mock-server.js  # 零依赖 Mock 后端
├── preview/            # 效果图截图
└── design-backup/      # 设计迭代备份（母意象版）
```

## 本地运行

方式一：直接双击 `index.html`；
方式二（推荐）：VS Code 装 Live Server 插件 → 右键 `index.html` → Open with Live Server。

## 连接后端（3 步）

```bash
# 1. 先用 Mock 联调（零依赖，只需 Node.js）
node api/mock-server.js

# 2. 在 index.html 中取消注释并填后端地址
#    <script>window.AIWHO_API_BASE = "http://localhost:3000";</script>

# 3. 打开页面，控制台不再出现「回退到内置 Mock」即打通
```

接口契约（REST + WebSocket）见 `api/接口文档.md`。

## 常用调整入口（js/main.js）

| 想改什么 | 位置 |
|---|---|
| 每个模块的工位/名称/配色 | `STAGE_META` / 各模块 stations（来自接口数据） |
| 每模块动画时长 | `runTask()` 里的 `wait(3400)` |
| 小猫配色 | `FUR` 常量 |
| 屏幕动画内容 | `screenHTML()` |
| 自动演示节奏 | `init()` 底部的 `setInterval` |
