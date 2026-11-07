# AIWHO WEBHOOK 中台 · 前端功能规格说明书

> 供另一名开发者用**纯 HTML/CSS/JS** 完整复刻该前端。所有字段名、数值、文案均直接取自源码
> （`E:\AI工作\AIWHO-Webhook-中台`，已忽略 node_modules / .next）。

## 0. 架构关键事实（先读）

1. **实际渲染的前端只有 `public/demo.html` 这一个单文件**（1000 行，53KB）。
   `app/route.ts`、`app/dashboard/route.ts`、`app/settings/route.ts` 三个路由 handler 全部返回
   `demoResponse()`（读取 `public/demo.html` 原文返回 `text/html; charset=utf-8`、`Cache-Control: no-store`）。
   即：`GET /`、`GET /dashboard`、`GET /settings` 都是同一份 HTML，**视图由 JS 里 `location.pathname` 决定**。
   `/demo.html` 也可直接下载、双击本地打开（此时用内置数据，无后端）。
2. `components/*.tsx`（React + Tailwind 版本）与 `lib/api.ts` 的 hooks 是**参考实现/接入层**，
   当前没有任何 page.tsx 引用它们。复刻时以 `demo.html` 的实际行为为准，React 版用于对照细节与后端接入方式。
3. 数据层双轨：页面加载后 `hydrate()` 先用**内置演示数据**渲染，再尝试 `GET /api/v1/workspaces`，
   成功则 `adopt()` 整屏换为后端数据（`apiReady = true`）。打不通就一直用内置数据。
4. 后端 API 全部在 `/api/v1` 下（见第三节），演示数据在 `server/store.ts`（内存态，可写、有 SSE 推送）。
5. 设计语言：**夜班值班室 / 机场调度席** —— 冷灰底 + 亮青 `#7ad5ee`（压墨字 `#243e4c`）为主，淡黄 `#fffa8d` 点睛，
   签名元素是 8px「状态灯」小圆点。禁止彩色胶囊、渐变球、跑马灯、呼吸灯。
   配色取自色卡四色（`#4ed7f1` / `#6fe6fc` / `#a8f1ff` / `#fffa8d`）；四色明度偏高，
   所以亮色带只做「面」，压深一档（`--accent`）才做「字与按钮」。页面底色 `--bg` 保持冷灰不动。

---

## 一、页面清单

三个页面共用同一个壳（`.shell`，`height:100vh; min-width:1120px; overflow:hidden`，纵向 flex）：

| 页面 | 路由 | 用途 | 包含区块 |
|---|---|---|---|
| 作战室 | `/`（`state.view="war"`） | 6 个业务域工位总览 | 顶栏 → 实时消息条 → 3×2 工作区面板网格 → 底部导航 + 右下工具条 |
| 仪表盘 | `/dashboard`（`state.view="dash"`） | 全局指标 | 顶栏 → 消息条 → 4 张统计卡 → 消息吞吐折线 + 工位负载排行 → 状态分布 / 各工作区 / 近期异常 |
| 设置 | `/settings`（`state.view="settings"`） | 后端接入说明、回调调试 | 顶栏 → 消息条 → 后端接入卡 → 回调调试卡（`id="webhook"`） → 通用接口表 → 6 张「X 业务接口」表 |

### 壳的公共区块（所有页面都有）

- **顶栏 `.topbar`**：高 60px，`padding:0 24px`，`gap:32px`，白底 + 下边框 `--hairline`。
  - 左：时钟（16px 时钟线icon + `#clock` `HH:mm:ss`，每 1s 刷新）+ 「演示模式」（`lamp lamp-working` + 文字）。
  - 中：Logomark（20×20 SVG）+ 「AIWHO WEBHOOK 中台」（`t-title`，nowrap）。
  - 右：4 组计数（上值下标签，中间 1px×24px 分隔线）：
    `消息` = `EVENTS.length`；`紧急` = critical 事件数（demo.html 中数值恒为 `color:var(--negative)`）；
    `在线工位` = `非 dormant 工位数 / 总工位数`；`响应` = 随机 `8 + floor(random*14)` + `ms`。
    之后 3 个 32px 图标按钮：Wifi（title「连接正常」）、Lock（title「传输已加密」）、设置（→ `go('settings')`）。
    计数为 `—` 时表示数据未就绪（React 版行为；demo.html 在首次 render 就有值）。
- **实时消息条 `.ticker`**：高 48px，圆角 10px，`margin:16px 24px 0`。
  左段：radio 图标 + 「实时消息」（右分隔线）；中段 `#feed`：**最新 6 条**事件横向排列（`gap:24px`，溢出隐藏、**无滚动动画**），
  每条 = 等级灯 + 标题（`t-caption` 主色、nowrap）+ 相对时间（`t-meta`），`title` 悬停显示 detail；
  右段（左分隔线）：「紧急」标签 + 有 critical 时 `lamp lamp-urgent` +「N 条待处理」（`--negative` 色），
  否则 `lamp lamp-dormant` +「无」。
- **主区 `.main`**：`flex:1; overflow-y:auto; padding:16px 24px 96px`，内部 `.view` `max-width:1600px; margin:0 auto`。
- **底部导航 `.bottom-nav`**：`position:fixed; bottom:24px` 居中，白色浮层（`--shadow-float`，圆角 12px，`p:4px`）。
  3 个按钮：作战室（Grid icon）/ 仪表盘（Chart icon）/ 设置（Sliders icon）。
  按钮高 36px、`padding:0 16px`、圆角 8px、字号 14px；激活态 `aria-current="page"`：黑底（`--text-primary`）白字。
- **工具条 `.toolstrip`**：`position:fixed; right:24px; bottom:24px`，同款浮层，3 个 32px 图标按钮：
  ① 负载热力（aria-pressed 切换，激活 = `background:var(--accent-soft); color:var(--accent)`）；
  ② 刷新数据（点击 = `tick()`）；③ 回调调试（→ `go('settings'); location.hash='webhook'`）。

### 页面区块细目

**作战室（war）** — `viewWar()`：
- `.grid3`：`grid-template-columns:repeat(3,1fr); gap:16px` → 6 个工作区面板（3 列 × 2 行）。
- 每个面板 `section.panel.enter`，`animation-delay = min(序号,5)*50ms`：
  - 头 `.panel-head` 高 44px、`padding:0 20px`：工作区名（`t-title`）→ 右侧 `t-meta`「N/M 在线」（spacer 左推）→
    若有 `status==="urgent"` 的工位则追加「N 项待处理」（`--negative` 色；**只数 urgent 工位，不含 critical 事件**）。
  - 体 `.deck.deck-floor`：`flex-wrap; gap:16px; padding:16px; min-height:168px; border-radius:0 0 15px 15px`，
    `.deck` 带 28px 网格底纹（`background-image` 两条 1px `rgba(23,23,23,.035)` 线，`background-size:28px 28px; position:-1px -1px`，底色 `--raised`）。
    内容 = 该区全部工位卡（`.desk`）。

**仪表盘（dash）** — `viewDash()`：
1. `.stat-row`（4 列 grid，gap 16px）四张 `.card.stat`（`padding:20px 24px`）：
   | 卡 | 值（`t-figure-lg`） | 旁注（`.change` mono 12px 灰） |
   |---|---|---|
   | 消息 | `EVENTS.length` | `+4.2% vs 上一小时` |
   | 紧急 | critical 数（值恒 `--negative` 色） | 有 critical 时「未处理」否则「无」 |
   | 在线工位 | `working+idle+urgent / total` | `{dormant 数} 个休眠` |
   | 响应 | `14ms` | `连接正常` |
2. `.row3`（2fr 1fr）：
   - **消息吞吐**卡（`padding:24px`）：标题下 meta「全部工作区合计 · 最近 2 小时 · 每 5 分钟」。
     SVG 折线 `viewBox="0 0 900 320"`，高 320px。数据 24 点（每 5 分钟）：
     `v = max(18, round(220 + sin(i/2.1)*52 + cos(i/4.7)*26 + (23-i)*2.2))`（i=23→0）。
     边距 `PAD={t:16,r:20,b:26,l:20}`；y 值域 = `[min*0.82, max*1.08]`；
     5 条网格线（f=0,.25,.5,.75,1，`#000` 5% 不透明度）+ 底轴（12%）；
     主线 `stroke:var(--accent); stroke-width:2; round 线帽/连接`；末点圆 `r=3.5` accent；
     两端 x 轴时间文字 `shortTime`（`fill:#737373; font-size:11`）。
   - **工位负载**卡：meta「取最高的 6 个工位」。`.bars` 列表（按 load 降序取 6）：
     每行 = 名称（`t-caption`，88px 宽截断）+ 轨道（`height:6px; bg:#e7e6e3; border-radius:999px`，
     填充 `width = load/maxLoad*100%`，色 `#bdbcb9`，**第一名 `var(--accent)`**）+ 值（72px 右对齐 mono `{load}%`）+ 状态文字（52px 右对齐灰 mono）。
3. `.row3b`（3 列等宽）：
   - **状态分布**卡：meta「全部工位」。`.stack` 高 8px、分段间 2px 缝、`flex-grow:count`、色 = 状态灯 hex、首尾段圆角；
     图例 4 行（working/idle/urgent/dormant 固定顺序）：灯 + 名称 + 数量（mono 主色）+ 百分比（44px 右对齐灰，`round(count/total*100)%`），行间细线。
   - **各工作区**卡：meta「吞吐与响应」。6 行：名称 | 随机吞吐 `40+round(random*70)`（mono 主色）| 随机延迟 `120+round(random*180)ms`（52px 右对齐）。
     （**每次重绘都变**，纯演示占位。）
   - **近期异常**卡：meta「warn 与 critical」。取 `level !== "info"` 的事件前 8 条：灯（margin-top 6px）+ 标题（13px，单行省略）+ detail（mono 12px 灰，单行省略）+ `shortTime`（右）。
     无数据时 `.empty`「暂无异常」（32px 上下留白、居中、灰 13px）。

**设置（settings）** — `viewSettings()`，区块顺序：
1. **后端接入**卡（`.card.section`，`padding:24px; margin-bottom:16px`）：
   标题 + 说明「这份演示页的数据写在页面里。接真实后端时把请求指向你的 API base 即可」。
   `.srow` 行（左右两端、`padding:16px 0`、下边框）：
   - 数据来源：副文案 `apiReady ? "已连上后端，状态会写进中台" : "内置演示数据，双击也能跑"`；右侧 `.chip`（mono 12px、`--raised` 底、圆角 6px、`padding:6px 12px`）内含灯 `apiReady ? lamp-working : lamp-dormant` + `apiReady ? "/api/v1" : "内置数据"`。
   - API Base：副文案「替换 apiJSON() 即可整套切换」；chip `/api/v1`。
   - 消息流：副文案「SSE，事件名 feed / snapshot / overview」；chip `text/event-stream`。
   - 完整契约：副文案「接口、字段、幂等与指令映射」；chip `API.md`。
2. **回调调试**卡（`id="webhook"`，被工具条 hash 定位）：
   说明「向消息流写入一条回调，会立刻出现在顶栏和作战室」。
   表单（2 列 grid，gap 16px，标签 `t-meta` 在上、`.control` 在下 margin-top 8px）：
   - 目标工作区 `<select>`：选项「{name} · {key}」×6，默认 `pay`。
   - 等级 `<select>`：`info / warn / critical`，默认 `warn`。
   - 工位 role `<input>`：placeholder `gateway`，默认 `gateway`。
   - 标题 `<input>`：默认「支付回调 5xx 突增」。
   - 详情 `<input>`（跨 2 列）：默认「5 分钟内 37 次失败，渠道 alipay」。
   下方：`.btn-primary`「发送回调」+ 结果文字 `#w-result`（`t-meta`）。
   再下 `pre.code`（mono 12px/24px 行高、`--raised` 底、圆角 8px、`padding:16px 20px`、横向滚动）展示示例请求体：
   ```
   POST /api/v1/workspaces/{key}/webhook
   Content-Type: application/json

   {
     "type": "payment.callback.failed",
     "title": "支付回调 5xx 突增",
     "detail": "5 分钟内 37 次失败，渠道 alipay",
     "level": "critical",
     "agentRole": "gateway",
     "status": "urgent",
     "queue": 4,
     "metrics": { "errorRate": 3.7 },
     "idempotencyKey": "cb-20261106-0911"
   }
   ```
3. **通用接口**卡：表格 `.th`（表头 mono 12px 灰、单元格 mono 12px 主色、说明列 13px sans 灰）7 行：
   `GET /api/v1/system/overview`（顶栏指标）、`GET /api/v1/events`（消息流，支持分页与筛选）、
   `GET /api/v1/events/stream`（SSE 推送 feed / snapshot / overview）、`GET /api/v1/agents`（工位列表）、
   `PATCH /api/v1/agents/:id`（更新状态 / 队列 / 指标）、`GET /api/v1/workspaces`（6 个工作区概览）、
   `GET /api/v1/metrics/dashboard`（仪表盘聚合数据）。
4. **每工作区业务接口**卡 ×6（标题「{工作区名} 业务接口」），各 4 行：
   `GET /api/v1/workspaces/{key}/agents`（本工作区工位）、
   `POST /api/v1/workspaces/{key}/agents/:id/command`（下发指令）、
   `GET /api/v1/workspaces/{key}/metrics`（指标时序）、
   `POST /api/v1/workspaces/{key}/webhook`（业务回调入口）。

---

## 二、组件与功能细节

### 1. TopBar（顶栏，demo.html `.topbar` / `components/TopBar.tsx`）

> **2026-11-07 右上三个按钮的用途调整**：
>
> | 按钮 | 用途 | 实现 |
> |---|---|---|
> | WiFi | **连接状态** | 点开 `.net-pop` 浮层：连接方式 / API Base / 延迟 / 在线工位 / 紧急 / 消息；点别处收起 |
> | 锁 | **界面锁定（防误触）** | `state.uiLocked` 切换；锁定后工位卡与抽屉指令按钮不响应，再点解锁 |
> | 太阳/月亮 | **昼夜切换** | `setTheme()` 写 `localStorage["aiwho.theme"]`，给 `<html>` 挂 `data-theme` |
>
> 原先锁是「传输已加密」的装饰图标、第三个是跳设置（底部导航已有设置，故改用）。

**深色模式**：`[data-theme="dark"]` 整套覆盖 CSS 变量 —— 常规令牌（bg/surface/raised/hairline/text/track/shadow）、
反白元素（`--on-invert`，亮青上压墨字）、滚动条，以及**工位插画配色 `--art-*`**（桌椅转中性灰、剪影压到最深，深底上才读得出）。
插画里的色值都走 `var(--art-*)`（只有接地投影的黑是写死的，跟主题无关），`DEFS_SVG` 的渐变 stop 也用变量 —— 换肤不用改插画。
- 展示：时钟 `HH:mm:ss`（`clockTime()`，每秒 `setInterval`）、演示模式灯、品牌、4 组计数、3 个图标按钮。
- 字段映射（React 版取 `SystemOverview`）：`totalMessages`→消息、`urgent`→紧急、`online`/`agents`→在线工位（显示 `17/18`）、
  `latencyMs`→响应（`null` 显示 `—`，否则 `{latencyMs}ms`）。
- 差异：demo.html 中「紧急」数值**恒为红色**；React 版仅 `overview.urgent > 0` 时着 `--negative`。
  demo.html 的「响应」每次渲染随机 `8–21ms`；React 版来自接口。
- Wifi 按钮 title：`connection === "connected" ? "连接正常" : "连接异常"`（demo.html 固定「连接正常」）。

### 2. Ticker（实时消息条，`components/Ticker.tsx`）
- 取 `events.slice(0, 6)`；事件级灯映射 `LEVEL_LAMP`：`info→lamp-idle`、`warn→lamp-working`、`critical→lamp-urgent`（沿用状态灯，不另起色）。
- 空态：「暂无消息」（`t-meta`）。
- 右段紧急槽：见上。相对时间 `relativeTime(ts, now)` 规则见第三节。
- 刷新：demo.html 每 30s `setInterval(renderFeed, 30000)` 重算相对时间；新事件到达即插队渲染（`pushEvent()` → `renderFeed()`）。

### 3. BottomNav（底部导航，`components/BottomNav.tsx`）
- TABS：`/`「作战室」GridIcon `exact:true`；`/dashboard`「仪表盘」ChartIcon；`/settings`「设置」SlidersIcon。
- 激活判定（React）：exact ? `pathname === href` : `pathname.startsWith(href)`；demo.html 由 `go(view)` 设置 `aria-current="page"`，其余置 `"false"`。
- 点击行为：demo.html `go('war'|'dash'|'settings')` 切视图 + `document.querySelector(".main").scrollTop = 0` + 重绘。

### 4. SideTools / 工具条（`components/SideTools.tsx` / `.toolstrip`）
- 状态 `ToolState { heat: boolean; paused: boolean }`（demo.html 只有 `state.heat`，刷新按钮是手动 `tick()`，无暂停轮询）。
- **heat（负载热力）**：切换后给所有 `.desk` 加 `show-load` 类 → 桌下负载条常显（否则仅 hover 显示）。按钮 `aria-pressed`，激活样式 `bg:var(--accent-soft); color:var(--accent)`。
- **刷新**：`tick()` = 遍历所有非 dormant 工位，`load = clamp(load + round((random-0.5)*10), 4, 98)`，然后 `renderChrome()+renderView()`（负载条宽度**无过渡动画**，直接跳变；React 版注释明确"宽度不参与动画"）。
- **回调调试**：跳 `settings` 视图并 `location.hash='webhook'`。

### 5. PageShell（`components/PageShell.tsx`）
- 作战室之外两页共用壳：`h-screen min-w-[1120px]`、TopBar + 可滚动 main（`px-6 py-6 pb-24`，内容 `max-w-[1600px]`）+ 固定底部导航（`bottom-6`，`z-30`）。
- React 版固定 `demoMode={true}`。

### 6. AgentDesk（工位卡，`components/war-room/AgentDesk.tsx` / `.desk`）
> 2026-11-07 起为**无边框**样式（对照「开发组」示意）：卡片不画框不铺底，名牌浮动居中、状态做成压在插画上的实底胶囊。

- 尺寸：宽 **152px**、`padding:2px 2px 16px`（底部留负载条）、圆角 12px（`--r-card`）、纵向 `gap:2px`；**无边框、背景透明**。hover 让插画 `translateY(-2px)`（150ms），不换底色。
- 结构（自上而下）：
  1. 名牌行 `.desk-top`（高 26px、`position:relative`）：
     - `.queue-badge` 绝对定位 `left:0`、垂直居中，mono 13px `--text-secondary`，仅 `queue > 0` 时渲染。
     - `.nameplate` 绝对定位水平垂直居中（`left:50%; top:50%; translate(-50%,-50%)`），`max-width:calc(100% - 18px)`、`height:24px`、`padding:0 8px`、白底 + `1px --hairline-strong`、圆角 8px（`--r-control`）、mono 12px；名称过长 `text-overflow:ellipsis`（完整名看 `title` / 抽屉）。
  2. 插画容器 `.desk-art-wrap`（`position:relative`）内两件：
     - **工位插画 SVG**（`viewBox="0 0 176 126"`，宽 100%）：**玻璃屏 + 桌板 + 座椅 + 员工剪影 + 桌角状态灯**。屏与剪影压深、桌椅走浅灰白，冷暖靠明度拉开。所有色值走 `--art-*` 变量（明暗两套）。关键几何（可直接照抄坐标）：
       - 玻璃屏：外壳 `rect 42,2 92×44 rx5` 渐变 `d-screen`（`--art-screen-a → --art-screen-b`）；内屏 `rect 47,6 82×36 rx3`（`--art-screen`）+ 玻璃反光 `path M47 6h34L55 42h-8z`（`d-glass`，白 10%→0 斜向）。
       - **工作流程动画**（`working` / `urgent` 才有；`idle` / `dormant` 是静止的四条内容线）：
         屏上是**三条进度条 + 一个工件**：每条进度条 = 轨道 `rect 65,10.5/22.5/34.5 h3 rx1.5`（`--art-line`）+ 填充 `bar-fill`（状态色）；站点圆点 `circle class="station s1/s2/s3" 55,12/24/36 r3.4`（`--art-station`）；工件 `rect class="workpiece" 50,7 10×10 rx3`（状态色）。
         **进度条长度随机**（`barW = 30 + rand(0..36)` 单位，屏宽 82，**全部 > 1/3**），每次重绘重新随机。
         节奏：**每满一条，工件下移一站、该站点亮**，三条都满后淡出重来。
         周期 `4.05s` = 3 站 × `1.35s`，三个元素（进度条 / 工件 / 站点）用同一周期 + `animation-delay` 0 / 1.35s / 2.7s 对齐到站时刻。
         `@keyframes barFill`（`scaleX(0→1)` 占前 1/3 周期）、`flowPiece`（`translateY(0→12→24px)` + 落定 squash `scale 1→1.18→1`）、`stationPulse`（`scale 1→1.3` + 透明度）。
         全部带 `animation-fill-mode: backwards`（延迟期间停在 0% 帧，不会闪一下满条）。
         **`prefers-reduced-motion` 时动画关掉**，三条进度条保持满格、工件常显、站位常亮。
       - 桌板：`rect 14,46 148×18 rx2` 渐变 `d-desk-top`（`--art-desk-a → --art-desk-b`）+ 描边 `--art-stroke`；前沿厚度 `rect 14,63 148×5` 渐变 `d-desk-edge`。
       - 桌腿：`rect 28,68 8×26`、`rect 140,68 8×26`（`--art-desk-edge-a`）。
       - 接地投影：`ellipse cx88 cy110 rx62 ry15` 径向渐变 `d-shadow`（黑 14%→0）。
       - **员工剪影**（`fill: var(--art-figure)`，最深一档）：耳朵 `circle 74,55 r8` / `circle 102,55 r8`、后脑勺 `circle 88,68 r20`、身体 `path M62 95v-6a26 26 0 0 1 52 0v6z`；头顶受光弧 `path M76 61a14 14 0 0 1 22-4`（`--art-hi` 10%，宽 3）。
       - 座椅：**画在剪影之后**，座背 `rect 52,60 72×38 rx15`、扶手 `rect 34,76 20×32 rx10` 与 `rect 122,76 20×32 rx10`，都填渐变 `d-chair`（`--art-chair-a → --art-chair-b`）。
         **三条约束**：① 剪影画在**座椅之前**，浅色椅背盖住深色身体，只露脖子以上的头（露出 12px）—— 看着就是靠在椅背上；② 头顶距屏幕底边留 1px —— 两块深色贴上就糊成一团；③ 身体收在座背的 y 范围（60..98）内，否则会从座背下面露出来。
       - **状态灯**：`circle cx25 cy54 r3.6`，填充 = `var(--st-<status>)`（跟昼夜切换走）+ 左上高光弧（`--art-hi` 55%，1.2 宽）。
       - 共用渐变 defs 全站只写一份（隐藏 `<svg width=0 height=0>` 里，ID：`d-screen / d-glass / d-desk-top / d-desk-edge / d-chair / d-shadow`）。
     - **状态胶囊 `.desk-pill`**：`position:absolute; top:6px; right:2px`、`padding:2px 10px`、圆角 999px、mono 12px、`box-shadow:0 1px 2px rgba(0,0,0,.12)`；底色取 `STATUS_META[status].pill`（= `var(--st-<status>)`）、字色取 `pillInk`（= `var(--st-<status>-ink)`）——**底与字成对**，因为亮青/淡黄这类底子白字看不清。**替代原「状态灯 + 灰字」行**；`pill` 只给工位卡用，`lamp`/`color` 仍给抽屉、图例、图表用，两套互不影响。
  3. **负载条 `.loadbar`**：`position:absolute; left:10px; right:10px; bottom:4px; height:4px; border-radius:999px; background:#e7e6e3`；
     内条 `width: max(load, 3)%`，`background:var(--text-muted)`。
     显隐：默认 `opacity:0`，`.desk:hover` 或 `.show-load`（热力开启）→ `opacity:1`，`transition:opacity .15s`（宽度不参与动画）。
- 交互：整卡 `role="button" tabindex="0"`，click / Enter 打开抽屉 `openDrawer(agent.id)`；`aria-label="{name} · {状态名}"`。

### 7. WorkspacePanel（工作区面板，`components/war-room/WorkspacePanel.tsx` / `.panel`）
- **模块内底 = 全局底色**（`--bg`，不做浮起的白卡，去 `box-shadow`）。
- **标题栏整条铺 `var(--title-bar)`**（淡青 `#e6f8fb`，明暗两套同值），标题文字与 meta 压 `--on-invert` 墨字 `#243e4c`；「N 项待处理」用 `--accent-warn`（`#8f2b26`）。
- `aria-label={workspace.name}`；头部 48px（状态灯 / 名称 / `onlineCount/agentCount 在线` / `urgentCount>0` 时「N 项待处理」）。
- 底板 `.deck-floor`（只留细网格做结构纹理，底 `var(--bg)`）内工位卡按 `agents` 顺序流式排布（`flex-wrap`、**`justify-content:center` 工作台居中**、`gap:16px`、`padding:16px`）。
- 进场动画：`.enter`（opacity 0→1 + `translateY(8px→0)`，380ms `cubic-bezier(.22,1,.36,1)`，`both`），每面板延迟 `min(i,5)*50ms`。

### 8. AgentDrawer（工位抽屉，`components/war-room/AgentDrawer.tsx` / `#drawer`）
- 结构：`.scrim`（全屏 `rgba(0,0,0,.15)`，`z-40`，点击关闭）+ `aside.drawer`（`fixed` 右侧、宽 **384px / max-width:92vw**、白底、左边界线、`--shadow-float`、`z-50`）。
- 动画：`transform:translateX(100%) → translateX(0)`，`visibility:hidden → visible`，`transition:transform .38s var(--ease)`；关闭反之。
- 头部（`padding:20px 24px`）：大灯 `lamp lamp-lg {lamp-状态}`（10px）+ 名称（`t-title`）+ 状态文字（`t-meta`）+ 第二行 `{workspaceName} · {agent.id}`（`t-meta`，margin-top 8px）+ 关闭按钮「×」（32px，字号 20px）。
- 体（`overflow-y:auto; padding:20px 24px`），区块间隔 32px：
  1. 两列数字（`t-figure` 28px）：`负载` = `{load}%`；`待处理` = `{queue}`。
  2. 当前任务：标题「当前任务」（`t-meta`）+ 正文 `currentTask ?? "暂无任务"`（`t-body`）；React 版多一行「最近活跃 {relativeTime(lastActiveAt)}」。
  2.5 **工作轨迹**（2026-11-07 新增，`.trace`，最多 380px 内滚动）：**跟对话一样**按时间正序，每轮一条 `.trace-step`：
     - `.trace-meta`「第 {n} 轮 · {relativeTime}」
     - `.trace-say` 气泡 = 这一轮在干什么（`say`）
     - `.trace-tool` 卡（左缩进 12px、左边框 2px 竖线）= **调用的工具**：`.tool-name`（如 `ledger.lookup`，**不翻译**，是标识符）+ `.tool-args`（入参）+ `.tool-out`（返回）。左边框按 `status` 取色：`ok` 灰、`warn` 主青、`error` 红。
     数据在 `state.traces[agentId]`（种子见 `data.js` 的 `TRACES`，每轮 `{ts, say, tool, input, output, status}`）；接后端后由 `GET /workspaces/{ws}/agents/{id}/trace` 下发。
     **会跟着指令长**：派单追加一轮 `dispatch.accept`、办结追加一轮 `dispatch.complete`。
     **插值要留到渲染时** —— `say` / `output` 存 key + `sayVars`/`outputVars`，渲染时才 `t(say, sayVars)`；写入时就插好值的话切不了语言。
  3. 遥测：`metrics` 的 `Object.entries` 逐行（字段名经 `metricMeta(key).label` 取中文，左 `t-caption` 灰；value 右 `t-num`，单位以 `t-meta` 跟在数值后），`metrics` 为空时显示「暂无遥测」；行间上边框（React 版为下边框、末行无线）。
  4. 下发指令：标题下显示端点提示（React 版：`POST /workspaces/{key}/agents/{id}/command`）；
     输入框 `.control`（placeholder「任务描述，可选」）；6 个按钮 **3 列 grid、gap 8px**：
     | command | 文案 | 样式 |
     |---|---|---|
     | `assign` | 派单 | `btn-primary` |
     | `start` | 启动 | `btn-quiet` |
     | `pause` | 暂停 | `btn-quiet` |
     | `escalate` | 向上汇报 | `btn-quiet` |
     | `ack` | 确认 | `btn-quiet` |
     | `reset` | 复位 | `btn-quiet` |
     按钮在请求中显示「…」并禁用（React 版 `busy`）。
  5. 调用记录（有内容才显示，`hidden` 属性控制）：最多 **5 条**，新记录插最前。
     demo.html 文案：`{HH:mm:ss}  已下发 {cmdLabel(cmd)} 至 {name}`；React 版用后端回执 `{HH:mm:ss}  {result.message}`（经 `localizeCmd` 换成中文指令名），失败时「{time}  失败  {错误信息}」。
- **指令本地效果**（2026-11-07 按业务语义重定义；`applyCommandLocal` + `reactMetrics`）：

  | command | 按钮 | 状态 | 副作用 | 遥测增减 |
  |---|---|---|---|---|
  | `assign` | 派单 | → `working` | **`queue += 1`**；`currentTask = task`（没填则沿用，都没有则「新任务」） | 待办 +1、积压 +2、告警 +1 |
  | `done` | **无按钮**（后端回填） | `queue>0` → `working`，否则 → `idle` | `queue = max(0, queue-1)`；队列清空时 `currentTask = null` | 已办 +1、待办 -1、积压 -2、吞吐 +3、回复 -0.3、达标 +1、错误 -0.2、延迟 -6 |
  | `escalate` | 向上汇报 | → `urgent` | **不加次数**（`queue` 不变） | 紧急 +1、告警 +1 |
  | `on` | 上班 | → `idle` | — | — |
  | `off` | 下班 | → `dormant` | `currentTask = null` | — |
  | `reset` | 复位 | → `idle` | `currentTask = null` | — |
  | `start` / `resume` / `pause` / `ack` | 按钮已不用 | 同旧版 | 仅契约兼容 | — |

  > **「完成」不做按钮，也不由前端模拟**（2026-11-07）：派单后的自动办结是**后端的职责** —— 前端不计时、不猜、不自己收尾。前端只留回填入口 **`onTaskResolved(agentId)`**（`js/api.js`，落本地状态 + 重绘）；后端也可以直接下发 `done` 指令走 `runCommand()`，两条路语义一致。**没有失误分支** —— 工位是智能体，办结一律记成功，`failures`（失败件数）不会因办结而变化。离线演示模式下没有后端，派下去的单会一直停在「工作中」，这是预期行为。
  >
  > **`done` / `on` / `off` 是本项目新增的指令值**，后端 `AgentCommand` 契约需同步扩展。原 7 个值里 `start` / `pause` / `ack` 的按钮已不再使用，语义并入 `assign` / `off` / `on`。
  >
  > 遥测增减规则见 `METRIC_REACT`（`js/api.js`）：**只动该工位已有的字段**（没列出的 key 不变），百分比字段夹在 0–100，其余不小于 0，统一保留 1 位小数。
  共同：`lastActiveAt = now`；写一条消息流事件（level：`escalate→critical`，其余 `info`；
  title `工位「{name}」收到指令 {cmdLabel(cmd)}`；detail = task 或无；source = `{agent.id}`）；清空任务输入框；重开抽屉 + 重绘。
  apiReady 时先 `POST /workspaces/{ws}/agents/{id}/command`（body `{command, task?}`）再本地落状态。
- **回调调试表单行为（`sendWebhook`）**：
  1. 按 `workspace + agentRole` 匹配工位（`find(a => a.workspace===ws && a.role===role)`）。
  2. apiReady 时 `POST /workspaces/{ws}/webhook`，body：
     `{ type:"demo.callback", title, detail, level, agentRole: role||undefined, source:"demo.webhook", idempotencyKey:"dbg-"+Date.now() }`，
     成功后重新拉取 `/events?limit=30` 与 `/workspaces` 整体刷新。
  3. 离线时本地 `pushEvent(ws, level, title, detail, target ? target.id : ws + ".webhook")`；
     若命中工位且 `level==="critical"` → `target.status="urgent"; target.queue+=1`。
  4. 回执（写入 state 后随视图渲染，**不能直接改 DOM**——会被重绘覆盖）：
     命中：`已写入 1 条 · 事件已路由至 {target.name} {后缀}`；
     未命中：`已写入 1 条 · 未匹配到 role「{role}」，落在工作区级 {后缀}`；
     后缀 = apiReady ? `（已写入后端）` : `（内置数据）`。

### 9. icons（`components/icons.tsx` / demo.html `svg.i`）
- 统一规则：**16×16、stroke-width 1.5、`currentColor`、圆头圆角**（lucide 图标集），`aria-hidden`。
- demo.html 内联的 `svg.i` 类：`width/height:16px; stroke:currentColor; fill:none; stroke-width:1.5; stroke-linecap/linejoin:round; flex:none`。
- Logomark：20×20，`rect 1,1 18×18 rx5`（描边 1.5 currentColor，无填充）+ `path M5.5 12.5v-5M10 12.5v-8M14.5 12.5v-3`（三根高低柱，圆头）。
- 图标清单（React 导出名 → 用途）：Clock（时钟）、Wifi、Lock、Settings、Radio（实时消息）、Grid2x2（作战室）、LayoutDashboard（仪表盘）、SlidersHorizontal（设置）、Pointer、Gauge（负载热力）、Database、Server、ShieldCheck、Command、Zap、Moon、Search、ListFilter、RefreshCw（刷新）、Send（回调调试）、Terminal、Bell、Cpu、Square、KeyRound。

### 10. 图表组件（`components/charts/*`，React 版；demo.html 用简化版）
- **ChartCard**：标题（`t-title`）+ meta（`t-meta`）+ 内容；右上「表格/图表」切换按钮（`aria-pressed`，hover `--raised`），
  表格视图 `max-height:320px` 滚动、表头 sticky、首列左对齐其余右对齐（demo.html 无表格切换，可选实现）。
- **LineChart**：内边距 `PAD={top:16,right:20,bottom:26,left:20}`；高 320（主图）。
  y 值域含 `baseline`（默认 0），两端各留 (max-min)*14% 余量；等比像素绘制（`useMeasure` + ResizeObserver 量宽，避免缩放变形）。
  网格 5 线 `#000 5%`；主线 `stroke-width:2` accent（或传入色）；末点 `r=3.5`；
  **悬停**：最近点吸附 → 竖向参考线（`#000 14%`）+ 空心圆点（白底 accent 2px 描边，r=5）+ 顶部浮层（时间 `t-meta` + 数值 `t-num`，圆角 8px、边框 `--hairline`、`--shadow-float`，水平夹在 64px~width-64 之间）。
  可选 `compare` 参考线（`#a3a3a3` 1px 虚线 `3 3`）；`compact` 模式去坐标轴、末点旁直接标值（11px mono 灰）。
- **BarList**：行 = label（88px 截断）+ 6px 轨道（`#e7e6e3`）+ 填充（`max(value/max*100, 3)%`，首条 accent 其余 `#bdbcb9`）+ 值（72px 右，`format(v)+unit`）+ meta（52px 右灰）。
- **StatusStack**：8px 高占比条（分段 `flex-grow:count`、2px 缝、首尾圆角、色=灯 hex、只显示 count>0 的段；
  `role="img"` + `aria-label`「{label} {count}，…」）；图例行（灯 + 名 + 数 + 百分比 44px 右，`(count/total*100).toFixed(0)%`）。
- **useMeasure**：ResizeObserver 量容器像素宽高（差 <0.5px 不更新）。

### 11. 动画与交互总表
| 对象 | 动画 | 时长/曲线 |
|---|---|---|
| 面板进场 `.enter` | opacity 0→1、translateY(8px→0) | 380ms `cubic-bezier(.22,1,.36,1)` both，延迟 `min(i,5)*50ms` |
| 抽屉 | translateX(100%↔0) + visibility | 380ms 同曲线 |
| 按钮按压 `:active` | `transform:scale(.98)` | 140ms |
| 按钮/图标 hover | 背景/前景色 | 140ms |
| 输入框 focus | 边框→accent、`box-shadow:0 0 0 3px var(--accent-soft)` | 140ms |
| 负载条显隐 | 仅 opacity | 150ms（宽度不动画） |
| 工位卡 hover | 插画 `translateY(-2px)`（无边框后不再换底色） | 150ms |
| 状态开关 `.switch`（React 设置页） | 滑块 left 3px↔24px、背景 | 150ms |
| 时钟 | 每 1000ms | — |
| 消息条相对时间重算 | 每 30000ms | — |
| `prefers-reduced-motion: reduce` | `.enter` 动画 none；抽屉无过渡；所有 transition 0.01ms | — |

**明确不做**（源码注释）：呼吸、扩散、漂浮、跑马灯、渐变块、玻璃球、发光点、彩色胶囊。

---

### 12. AI 助手（Marvis 式，本项目新增，非源工程内容）

照 Juniper Mist 的 Marvis 搬的交互：**问它就答（带依据）** + **主动发现卡**（Marvis Actions 式）。页面 `assistant.html`，`body[data-page="assistant"`，底部导航第 4 项。

**布局**：`.assistant` 左右分栏 —— 左 `.chat`（`flex:1`）对话区，右 `.insights`（`flex:0 0 320px`）发现卡。

```
.chat
├─ .chat-head      头像 + 「AI 助手」+「基于 N 个工位的实时数据」
├─ .chat-thread    消息串，可滚动，自动滚到底
│  ├─ .msg.me      用户气泡（深底白字）
│  └─ .msg.bot     助手气泡 + .msg-evidence（依据块）+ .msg-actions（动作按钮）
├─ .chat-suggest   「你可以接着问…」+ .chat-chip 追问按钮
└─ .chat-input     输入框 + 发送钮（Enter 也发送）
```

**三个手感要素**（这是「Marvis 效果」的关键，不是静态卡片）：

1. `.msg-bubble.typing` 三点动画（`@keyframes typing`，5px 圆点 ±2px 上下）—— 提问后立刻出现，600ms 后出答案
2. **回答带依据块** `.msg-evidence`：`.ev-row` = 字段名 + 进度条（`.ev-track`）+ 数值 + 副文本，数字全部来自 `state` 实时计算
3. **答案里有动作** `.msg-actions`（跳 `index.html` / `dashboard.html`）+ **追问 chip** 随答案更新

**意图匹配**（`js/assistant.js` 的 `intentOf(q)`）：关键词 → 9 个意图（busy / queue / urgent / issues / away / recent / overview / help / unknown）。**中英两套词都要收**，注意英文词形 —— `busiest` 不含 `busy`、`problems` 不含 `issue`，漏了就会走到兜底。

**答案现算**（`answer(q)` → `{ text, evidence[], actions[], followups[] }`）：

| 意图 | 数据来源 |
|---|---|
| busy | `state.agents` 按 `load` 降序取前 3 |
| queue | `queue > 0` 按 `queue` 降序 |
| urgent | `status === "urgent"` |
| issues | `state.events` 里 `level !== "info"` |
| away | `idle` + `dormant` |
| overview | `overview()` + 四态计数 |
| recent | `state.events` 前 5 条 |
| help | 静态能力清单 |

**主动发现**（`buildInsights()`，进页面即算）：`urgent` 工位 → `load>85 且 queue>2` → `critical` 事件 → `dormant 超 60 分钟`，每张卡带等级灯、置信度（高/中）、建议动作；无发现显示空状态。

**关键设计**：`.msg.bot` **只存问题 `q`，渲染时调 `answer(q)` 现算** —— 切语言自动换文案，依据块的数字也跟着实时数据走。用户消息存原文（是他说的话，不翻译）。追问 chip 存中文字面量、渲染时 `t()`，`data-ask` 存**翻译后**的文案（否则英文模式下用户气泡会显示中文）。

**不接后端 LLM** —— 规则匹配 + 实时数据计算，与「离线可跑」的既有架构一致。



## 三、数据契约

### 3.1 基础类型（`lib/contract.ts`）

| 类型 | 定义 |
|---|---|
| `WorkspaceKey` | `"dev" \| "ops" \| "pay" \| "support" \| "security" \| "data"` |
| `AgentStatus` | `"working" \| "idle" \| "urgent" \| "dormant"` |
| `EventLevel` | `"info" \| "warn" \| "critical"` |
| `HttpMethod` | `"GET" \| "POST" \| "PUT" \| "PATCH" \| "DELETE"` |

**Agent（工位）**

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 稳定标识，如 `dev.frontend` |
| `workspace` | WorkspaceKey | 所属工作区 |
| `name` | string | 工位名，如「前端」 |
| `role` | string | 机器可读角色，如 `frontend`（webhook 的 `agentRole` 按它匹配） |
| `status` | AgentStatus | 状态灯 |
| `queue` | number | 待处理队列深度；`<=0` 时前端不显示角标 |
| `load` | number | 负载 0–100 |
| `currentTask` | string \| null | 当前任务描述 |
| `lastActiveAt` | string | ISO 时间 |
| `metrics` | Record<string, number> | 各工作区自定义遥测 |

**AgentPatch**：`status? / queue? / load?(0–100) / currentTask?(string\|null) / metrics?(对象，值须为数字)`。

**AgentCommand**：`start | pause | resume | reset | assign | escalate | ack`。

**指令中文文案 `COMMAND_LABEL`**（`js/api.js`，界面文案唯一出处；key 为契约值勿改，只改 value）：

| command | 文案 |
|---|---|
| `assign` | 派单 |
| `start` | 启动 |
| `pause` | 暂停 |
| `resume` | 继续 |
| `escalate` | 向上汇报 |
| `ack` | 确认 |
| `reset` | 复位 |

`cmdLabel(cmd)` 取文案（缺省回退原词）；`localizeCmd(text, cmd)` 把消息里的英文指令名换成中文（后端回执 `message` 也会带 command 原词）。按钮文案、调用记录、消息流 title 三处均走此表。

**遥测字段中文文案 `METRIC_LABEL`**（`js/api.js`，界面文案唯一出处；key 为 `Agent.metrics` 的字段名，勿改 key，只改 value）：

| key | 文案 | 单位 | 归属模块 |
|---|---|---|---|
| `open` | 待办单数 | 单 | 客户接待 |
| `slaRate` | 按时办结率 | % | 客户接待 |
| `avgReply` | 平均响应时长 | 分钟 | 客户接待 |
| `jobs` | 处理件数 | 件 | 票据处理 · 风险与交付 |
| `failures` | 失败件数 | 件 | 票据处理 · 风险与交付 |
| `lagMin` | 积压时长 | 分钟 | 票据处理 · 风险与交付 |
| `tps` | 每秒处理量 | 次/秒 | 数据核对 |
| `errorRate` | 错误率 | % | 数据核对 |
| `p95` | 延迟（95 分位） | 毫秒 | 数据核对 |
| `alerts` | 告警数 | 条 | 风险与交付 |
| `critical` | 严重告警数 | 条 | 风险与交付 |
| `mtta` | 平均受理时长 | 分钟 | 风险与交付 |

`metricMeta(key)` 返回 `{ label, unit }`，未收录的 key 原样显示、单位留空（后端加新指标不影响渲染，只是不翻译）。单位中 `avgReply` / `mtta` 的「分钟」为按量级推断，后端口径不同时改 value 即可。

### 中英切换（i18n）

顶栏左上角 `中文 / 英文` 分段控件（`.lang-switch` / `.lang-opt`，当前语言实心反白），点击 → `setLang(lang)` → 写 `state.lang` + `localStorage["aiwho.lang"]` → `renderAll()` 整屏重绘。三页共用，刷新后保持。

**机制**：源码保持中文原样，渲染时经 `t(src, vars?)`（`js/api.js`）查 `js/i18n.js` 的 `I18N.en`：

- 中文不需要字典 —— 查不到回退原文，所以 `I18N.en` 就是全部英文文案，兼作翻译覆盖清单
- key 必须与源码中文字面量**逐字一致**（含标点、空格、`{var}` 占位）
- 复合句用占位插值：`t("已下发 {cmd} 至 {name}", { cmd, name })` → `Sent {cmd} to {name}`；英文表条目 `"已下发 {cmd} 至 {name}": "Sent {cmd} to {name}"`
- 允许空串翻译（如量词「件」→ `""`），用 `!== undefined` 判定而非真假值
- 后端下发的新文案未收录时回退原文，不崩

**自带翻译的 helper**（调用点因此基本不用改）：`cmdLabel()` / `metricMeta()` / `statusLabel()` / `relativeTime()`。`STATUS_META[s].label` 等 map 的 value 保持中文，英文统一进 `I18N.en`。

**覆盖范围**：界面框架（按钮 / 区块标题 / 底部导航 / 状态名 / `title`·`aria-label`·`placeholder` / 表单 label / 表头）、指令与遥测文案、时间格式、系统消息，以及演示数据（工作区名与描述 / 工位名 / `currentTask` / 消息流事件 title·detail / 接口 summary）。数据在**渲染点**翻译（`esc(t(a.name))`），`js/data.js` 保持中文单一事实源。专有名词保留（星辰科技 → Xingchen Tech，单号 `INV-233`、批次 `SET-20261106-02` 不动）。

`document.title`、`<html lang>`、抽屉 `aria-label` 由 `applyLang()` 跟随切换。调用记录改存结构化字段 `{ ok, ts, cmd, name, message }`，由 `callLogText(c)` 渲染时翻译，切换语言后历史记录同步换语言。

**AgentCommandRequest**：`{ command, task?, params? }`；**AgentCommandResult**：`{ agentId, command, accepted: boolean, status: AgentStatus, message, ts }`。

**WorkspaceMeta**：`{ key, name, accent: string, description, endpoints: ApiEndpoint[] }`；
**ApiEndpoint**：`{ method: HttpMethod, path, summary }`。
**WorkspaceSummary** = WorkspaceMeta + `{ agents: Agent[], agentCount, onlineCount, urgentCount, messageCount, health: 0–100 }`。

**FeedEvent**：`{ id: string（"evt_0001" 格式）, workspace: WorkspaceKey | "system", level: EventLevel, title, detail?, source, ts: ISO }`。
**FeedPage**：`{ items: FeedEvent[], total, urgent（critical 条数）, nextCursor: string | null }`。

**SystemOverview**：`{ totalMessages, urgent, online, agents, latencyMs: number | null, connection: "connected"|"degraded"|"offline", demoMode: boolean, ts }`。

**MetricPoint**：`{ t: ISO, v: number }`；**WorkspaceMetricSeries**：`{ key, name, accent, throughput: MetricPoint[]（消息/5 分钟）, errorRate: MetricPoint[]（0–100 百分比）, latencyP95: MetricPoint[]（毫秒） }`。
**DashboardData**：`{ overview, statusBreakdown: Record<AgentStatus, number>, series: WorkspaceMetricSeries[], topLoad: Agent[], recentCritical: FeedEvent[], generatedAt }`。

**WebhookEnvelope**：`{ type: string（必填，如 "build.finished"）, agentRole?: string, level?: EventLevel, source?, title?, detail?, status?: AgentStatus, queue?, load?, metrics?, data?: unknown（任意业务负载）, idempotencyKey?, ts? }`。
**WebhookAck**：`{ received: number, events: string[], agentIds: string[], ts }`。
**ApiError**：`{ error: { code: string, message: string, details?: unknown } }`。

**BusinessRecord（业务资源）**：`{ id, workspace, kind, title, status: string, level: EventLevel, ts, payload: Record<string, unknown> }`。

### 3.2 状态枚举 → 文案 / 灯 / 颜色（`lib/status.ts`，全站唯一状态表达方式：8px 小圆灯 + 文字，绝不用色块）

| AgentStatus | label | lamp class | 变量 | 用途 |
|---|---|---|---|---|
| `working` | 工作中 | `lamp-working` | `--st-working` | 也用于消息 `warn` 灯 |
| `idle` | 空闲 | `lamp-idle` | `--st-idle` | 也用于消息 `info` 灯 |
| `urgent` | 紧急 | `lamp-urgent` | `--st-urgent` | 也用于消息 `critical` 灯 |
| `dormant` | 休眠 | `lamp-dormant` | `--st-dormant` | 也用于「无紧急」空态灯 |

状态实底（工位卡胶囊、图表分段、插画里的状态点）取 `--st-*`，**字色取配套的 `--st-*-ink`** ——
亮青/淡黄这类底子白字看不清，必须自带墨色。两套变量在 `:root` 与 `[data-theme="dark"]` 各给一套值，
`STATUS_META` 只存 `var(--st-*)` 字符串，JS 里不写死 hex。

`STATUS_ORDER = ["working","idle","urgent","dormant"]`（状态分布图固定此顺序）。

### 3.3 格式化规则（`lib/format.ts` / demo.html 同名函数）
- `relativeTime(ts)`：`<15s`→「刚刚」；`<60s`→「{s} 秒前」；`<60min`→「{m} 分钟前」；`<24h`→「{h} 小时前」；否则「{d} 天前」。
- `clockTime(d)` → `HH:mm:ss`（补零）；`shortTime(ts)` → `HH:mm`。
- `percent(v)` → `{v}%`；`duration(sec)` → `<60`「{s}s」，否则「{m}m{s}s」/「{m}m」；`clamp(v,min,max)`。

### 3.4 API 端点（base `/api/v1`；全部 `Content-Type: application/json; charset=utf-8`，响应 `Cache-Control: no-store`，时间 ISO 8601，新建返回 201，失败 `{error:{code,message,details?}}`）

**全局**

| 方法 | 路径 | 请求 | 响应 |
|---|---|---|---|
| GET | `/system/overview` | — | `SystemOverview` |
| GET | `/events` | query：`limit`（默认 20，最大 100）、`cursor`（上页 `nextCursor`）、`level`、`workspace` | `{ items: FeedEvent[], total, urgent, nextCursor }` |
| POST | `/events` | `{ workspace?, level?, title(必填), detail?, source?（缺省 "api"）, ts? }` | 201 `FeedEvent` |
| GET | `/events/stream` | — | SSE（见 3.5） |
| GET | `/agents` | query：`workspace`、`status` | `{ items: Agent[], total }` |
| GET | `/agents/:id` | — | `Agent`（404 `not_found`） |
| PATCH | `/agents/:id` | `AgentPatch`（status/queue/load 0–100 校验） | 更新后 `Agent` |
| GET | `/workspaces` | — | `{ items: WorkspaceSummary[], total: 6, commonEndpoints: ApiEndpoint[] }` |
| GET | `/metrics/dashboard` | — | `DashboardData` + `workspaces: WorkspaceMeta[]` + `commonEndpoints` |

**工作区通用**（`:key` ∈ 6 个 key）

| 方法 | 路径 | 响应 |
|---|---|---|
| GET | `/workspaces/:key` | `WorkspaceSummary` + `meta: WorkspaceMeta` |
| GET | `/workspaces/:key/agents` | `{ workspace: WorkspaceMeta, items: Agent[], total }` |
| GET | `/workspaces/:key/agents/:agentId` | `Agent` |
| PATCH | `/workspaces/:key/agents/:agentId` | 更新后 `Agent` |
| POST | `/workspaces/:key/agents/:agentId/command` | `AgentCommandResult`（见下） |
| GET | `/workspaces/:key/events` | query `limit`（默认 50，最大 200）、`level`；`{ workspace, items, total }` |
| POST | `/workspaces/:key/events` | `{ title(必填), level?, detail?, source?（缺省 "{key}.api"）, ts? }` → 201 |
| GET | `/workspaces/:key/metrics` | `{ workspace, series: WorkspaceMetricSeries \| null, agentLoad: [{id,name,status,load,queue}], generatedAt }` |
| POST | `/workspaces/:key/webhook` | 见 3.6 |

**指令下发** `POST /workspaces/:key/agents/:agentId/command`，body `{ command, task?, params? }`：
- 非法 command → 400 `validation_error`，`details.allowed` = 7 个命令；工位不存在 → 404。
- 状态映射（后端 `statusAfterCommand`）：`start/resume/assign→working`（assign 有 task 写 `currentTask`）；`pause/reset→idle` 且 `currentTask=null`；`escalate→urgent` 且 `queue+1`；`ack`：`urgent→working` 其余不变，`queue>0` 时 `queue-1`。
- 同时写消息流：`escalate` 落 `critical`，其余 `info`；title `工位「{name}」收到指令 {command}`；source = agentId。
- 响应示例：`{"agentId":"ops.release","command":"assign","accepted":true,"status":"working","message":"已下发 assign 至 发布","ts":"…"}`。

**业务资源**（`:resource` 按工作区限定，跨区 404 `unknown_resource`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/workspaces/:key/:resource` | 列表，query `limit`（默认 50，最大 200）、`status`、`level`；响应 `{ workspace, resource, items: BusinessRecord[], total, actions: string[] }` |
| POST | `/workspaces/:key/:resource` | body `{ id?, title(必填), status?（缺省 "open"）, level?（缺省 info）, payload?, ts? }` → 201 BusinessRecord，id 缺省 `{resource 前 3 字母}_{base36 时间戳}` |
| GET | `/workspaces/:key/:resource/:id` | BusinessRecord |
| PATCH | `/workspaces/:key/:resource/:id` | `{ status?(string), level?(info\|warn\|critical), title?(非空), payload?(对象) }` → 更新后记录（`ts` 刷新） |
| POST | `/workspaces/:key/:resource/:id/:action` | 动作，body 可选（合并进 `payload`）→ `{ record, action, accepted: true, eventId, ts, workspace }` |

资源 → 动作表：`dev: builds(retry,cancel) / deployments(rollback,promote) / commits(—)`；
`ops: incidents(ack,resolve,escalate) / checks(run)`；`pay: transactions(refund) / callbacks(replay) / settlements(reconcile)`；
`support: tickets(assign,close,reopen) / sessions(close,transfer)`；`security: alerts(ack,mute) / audits(—) / scans(run)`；
`data: pipelines(run,pause) / tables(—) / features(publish) / reports(refresh)`。

动作副作用：记录 `status` ← `actionStatus(action)`（ack/run/retry/promote/replay/reconcile/refresh/publish/assign→`processing`；
resolve/close/cancel→`closed`；escalate→`escalated`；rollback→`rolled_back`；pause/mute→`paused`；reopen→`reopened`；
refund→`refunding`；transfer→`transferred`；其余→`updated`），`payload.lastAction = action`；
自动写消息流（title `{记录.title} · {action}`，detail `状态更新为 {新状态}`，source = 记录 id；
level：`escalate→critical`，`cancel/replay→warn`，其余 `info`）。

**错误码**：`not_found`(404)、`validation_error`(400)、`invalid_json`(400)、`unknown_resource`(404)、`unknown_action`(404)、`method_not_allowed`(405，带 `Allow` 头)。

### 3.5 SSE（`GET /api/v1/events/stream`，`text/event-stream; charset=utf-8`，`Cache-Control: no-cache, no-transform`，`X-Accel-Buffering: no`）

| 事件名 | 载荷 | 时机 |
|---|---|---|
| `snapshot` | `{ events: FeedEvent[]（最近 30 条）, overview: SystemOverview }` | 连接建立时一次 |
| `feed` | `FeedEvent` | 每写入一条新消息 |
| `overview` | `SystemOverview` | 每 5 秒 |
| （注释行） | `: ping {Date.now()}` | 每 15 秒保活 |

前端（React `useEventStream`）维护 `{ connected, events（feed 时前插、截断 60 条）, overview }`；
`onopen→connected=true`，`onerror→connected=false`。demo.html 未用 SSE（用 30s 轮询渲染 + 按需 fetch），
纯 HTML 复刻可选实现。

### 3.6 Webhook 语义（`POST /workspaces/:key/webhook`）
- body：单条 `WebhookEnvelope` 或数组批量（≤ 200 条；空数组/非对象/缺 `type` → 400 `validation_error`）。
- `idempotencyKey` 在 **10 分钟窗口**内按 `{key}:{idempotencyKey}` 去重，重复条目跳过。
- 按 `agentRole` 在该工作区找 `role` 匹配的工位；找不到落工作区级（事件 `source` 缺省 `{key}.webhook`）。
- 命中工位且 envelope 带 `status/queue/load/metrics` → 同时 patch 该工位。
- 事件：`level` 缺省 `info`；`title` 缺省用 `type`；`source` 缺省 = agentId ?? `{key}.webhook`；`ts` 缺省服务端当前时间。
- 响应 `WebhookAck { received, events: 事件 id[], agentIds（去重）, ts }`；**全部新写入 → 201，有幂等丢弃 → 200（received < 条数，纯重复时 received=0）**。

---

## 四、设计令牌（本实现 `css/style.css`；源工程是 `app/globals.css` / demo.html `:root`）

> **本项目 2026-11-07 起有意偏离源工程数值**（视觉优化 + 按色卡重排配色，其余实现仍照规格）：
> 配色改**冷灰底 + 青 + 淡黄**（色卡四色 `#4ed7f1` / `#6fe6fc` / `#a8f1ff` / `#fffa8d`），
> 页面底色 `--bg` 与模块底板都用白 `#fbfdfe`；圆角 6/8/10/14；阴影分三级（`shadow-sm/md/float`）。
> 等宽体只留给机器串，按钮 / 表单标签 / 区块标题改无衬线。**下表是本实现的实际值**，不是源工程的。

### 颜色（浅色；`[data-theme="dark"]` 另有一套，见 `css/style.css`）
| 变量 | 值 | 用途 |
|---|---|---|
| `--bg` | `#fbfdfe` | 页面底 + 模块底板（**与 `--surface` 同白**，分隔靠边框与阴影） |
| `--surface` | `#fbfdfe` | 卡片/面板/浮层 |
| `--raised` | `#e9f3f8` | hover 底、chip、deck 底、quiet 按钮 |
| `--hairline` | `rgba(15,82,104,.11)` | 全部细边框 |
| `--hairline-strong` | `rgba(15,82,104,.22)` | 输入框边框、开关边框 |
| `--text-primary` | `#0c2a35` | 主文字 |
| `--text-secondary` | `#3a5c69` | 次级文字 |
| `--text-muted` | `#748f9c` | meta/图标默认色 |
| `--accent` | `#7ad5ee` | 主青**填充**（按钮、选中态、折线主线、第一名条），上压 `--on-invert` 墨字 |
| `--accent-strong` | `#5cc6e6` | 主按钮 hover |
| `--accent-text` | `#0b6c89` | 青当**文字/描边**时的压深版（模块标题、focus 环、按下态图标）——浅底上亮青看不清 |
| `--accent-soft` | `rgba(122,213,238,.32)` | focus 光环、工具按钮激活底 |
| `--accent-tint` | `#a8f1ff` | 淡青（色卡第 3 条）：追问 chip hover |
| `--title-bar` | `#e6f8fb` | 模块标题栏底色（淡青，明暗两套同值） |
| `--accent-warn` | `#8f2b26` | 标题栏上的告警字，明暗同值 |
| `--highlight` | `#fffa8d` | 淡黄（色卡第 4 条）：待办数色块 |
| `--highlight-soft` | `rgba(255,250,141,.5)` | 淡黄软底：演示模式徽标 |
| `--positive` | `#0e8f6e` | 语义正向 |
| `--negative` | `#c2413c` | 紧急/告警文字 |
| `--st-working` / `-ink` | `#7ad5ee` / `#243e4c` | 状态实底 + 字色（**成对**） |
| `--st-idle` / `-ink` | `#5c7c8a` / `#fff` | |
| `--st-urgent` / `-ink` | `#c2413c` / `#fff` | |
| `--st-dormant` / `-ink` | `#d3e0e6` / `#2a4450` | |
| `--lamp-*` | 工作用 `#2fb0d4`（8px 点要压一点密度才在白底上看得见），其余与 `--st-*` 同族 | 8px 状态灯 |
| 图表中性 | `#d3e2e9`（轨道）、`#9db6c1`（填充）、`#87a2ae`（虚线参考）、`--grid-line #175d74` @5%/12%/14%（网格/轴/悬停线） | |
| 按钮 hover | `--accent-strong`（primary）、`--raised`（quiet） | |

**分色规则**：色卡四色明度都偏高，直接当文字会糊在浅底上 ——
**亮青做「面」**（`--accent` 填充，压 `--on-invert #243e4c` 墨字），
**压深做「字」**（`--accent-text`）。
状态实底必须**底与字成对**（`--st-*` + `--st-*-ink`），因为亮青/淡黄这类底子白字看不清；
两套变量在 `:root` 与 `[data-theme="dark"]` 各给一套值，`STATUS_META` 只存 `var(--st-*)` 字符串。

### 字体（权重只用 400 / 500）
- UI：`"IBM Plex Sans","PingFang SC","Microsoft YaHei","Hiragino Sans GB",system-ui,sans-serif`（React 版经 next/font 注入 `--font-ui`；demo.html 走 Google Fonts CDN）。
- 数字/mono：`"IBM Plex Mono",ui-monospace,Consolas,monospace`。
- 字体角色（全站仅此几档）：

| 类 | 字号/行高 | 字体/字重 | 颜色 | 备注 |
|---|---|---|---|---|
| `.t-meta` | 12/16 | mono 400 | `--text-muted` | `letter-spacing:.01em`，`tabular-nums` |
| `.t-caption` | 13/20 | sans 400 | `--text-secondary` | |
| `.t-body` | 14/20 | sans 400 | `--text-primary` | |
| `.t-title` | 16/24 | sans 500 | `--text-primary` | |
| `.t-num` | 16/20 | mono 500 | `--text-primary` | 顶栏计数，tabular |
| `.t-figure` | 28/32 | mono 500 | `--text-primary` | 抽屉大数 |
| `.t-figure-lg` | 32/36 | mono 500 | `--text-primary` | 统计卡大数 |

### 圆角 / 阴影 / 动效
- 圆角：`--r-tag:6px`（名牌/chip/链接钮）、`--r-control:8px`（按钮/输入框/浮层内钮）、`--r-card:12px`（卡/工位/浮层）、`--r-panel:16px`（工作区面板，deck 底部 15px）；灯与轨道 `999px`。
- 阴影：`--shadow-sm: 0 1px 2px rgba(0,0,0,.05)`（卡片）；`--shadow-float: 0 8px 24px rgba(0,0,0,.08)`（底部导航/工具条/抽屉/tooltip）。
- 缓动：`--ease: cubic-bezier(.22,1,.36,1)`（唯一曲线）；时长 140ms（fast）/200ms（mid）/380ms（enter，抽屉同值）/420ms（React `.rise`）。

### 布局尺寸
- 壳：`height:100vh`、`min-width:1120px`；**内容区左右各内缩 10%**（`.shell { padding: 0 10% }`，顶栏/消息条/主区都在这条 80% 带子里，两侧留白各 10%）；顶栏 60px（`padding:0 16px`，左右组 `gap:8px`，标题可收缩省略）；消息条 48px、`margin:16px 24px 0`；主区 `padding:16px 24px 96px`；内容 `max-width:1600px`。工具条 `right: calc(10% + 24px)` 与内容带右缘对齐。
- 作战室网格：3 列 `1fr`，gap 16px；面板头 44px（`padding:0 20px`）；deck `padding:16px`、`min-height:168px`、gap 16px。
- 工位卡：152px 宽、`padding:2px 2px 16px`、**无边框**；负载条 `left:10px; right:10px; bottom:4px; height:4px`。
- 抽屉：384px（max 92vw）；头部 `20px 24px`；body `20px 24px`；区块间距 32px。
- 底部导航/工具条：`bottom:24px`（工具条 `right:24px`）、内边距 4px、gap 4px、按钮 36px 高（图标钮 32×32）。
- 统计卡 `padding:20px 24px`；图表卡 `padding:24px`；设置卡 `padding:24px`、间距 16px。
- 滚动条：`scrollbar-width:thin; scrollbar-color:#d4d4d4 transparent`；webkit 8px、滑块 `#d4d4d4` 圆角、2px 边。

### 无障碍 / 状态类
- `:focus-visible`：`outline:2px solid var(--accent); outline-offset:2px`。
- 状态灯 `.lamp`：8×8、`border-radius:999px`、`box-shadow:inset 0 1px 1px rgba(255,255,255,.45)`；`.lamp-lg` 10×10。
- 开关 `.switch`（React 设置页）：44×24，滑块 16px，`aria-checked` 驱动（true：黑底、滑块 left 24px；false：left 3px）。

---

## 五、演示数据样例

### 5.1 工作区（`server/registry.ts`）
| key | name | accent | description（摘要） | 专属资源 |
|---|---|---|---|---|
| dev | 开发组 | `#64748b` | 前端/后端/移动端 交付工位，构建、联调与版本发布 | builds, deployments, commits |
| ops | 运维组 | `#64748b` | 发布/监控/故障，变更、巡检与应急 | incidents, checks |
| pay | 支付组 | `#64748b` | 网关/结算，支付链路与资金对账 | transactions, callbacks, settlements |
| support | 客服组 | `#64748b` | 工单/在线客服，用户问题与会话 | tickets, sessions |
| security | 安全组 | `#0f9e8e` | SOC/审计，告警处置与操作留痕 | alerts, audits, scans |
| data | 数据组 | `#6d9b1f` | 流水线/数仓/特征/报表，数据链路与产出 | pipelines, tables, features, reports |

### 5.2 工位（18 个，`server/store.ts` SEED_AGENTS；demo.html 内置数据完全相同，另有 `lastActiveMinAgo`）
| id | name | role | status | queue | load | currentTask | metrics |
|---|---|---|---|---|---|---|---|
| dev.frontend | 前端 | frontend | working | 2 | 74 | 重构作战室面板虚拟列表 | `{buildMinutes:6.9, prs:3, errorRate:1.2}` |
| dev.backend | 后端 | backend | idle | 1 | 18 | null | `{buildMinutes:4.1, prs:1, errorRate:0.4}` |
| dev.mobile | 移动端 | mobile | idle | 1 | 22 | null | `{buildMinutes:8.4, prs:1, errorRate:2.1}` |
| dev.workbuddy | WorkBuddy | workbuddy | working | 0 | 61 | 生成回归用例 | `{buildMinutes:2.2, prs:5, errorRate:0.9}` |
| dev.cnb | cnb | cnb | idle | 0 | 9 | null | `{buildMinutes:1.7, prs:0, errorRate:0.2}` |
| ops.release | 发布 | release | **urgent** | 4 | 93 | v2.3.1 灰度回滚确认 | `{pendingChanges:4, failedChanges:1, mttr:17}` |
| ops.monitor | 监控 | monitor | working | 2 | 68 | CPU 持续 88% 归因 | `{pendingChanges:2, failedChanges:0, mttr:6}` |
| ops.trouble | 故障 | trouble | idle | 1 | 14 | null | `{pendingChanges:1, failedChanges:0, mttr:24}` |
| pay.gateway | 网关 | gateway | idle | 1 | 31 | null | `{tps:214, errorRate:0.6, p95:182}` |
| pay.settle | 结算 | settle | working | 2 | 77 | T+1 结算批次核对 | `{tps:41, errorRate:1.4, p95:640}` |
| support.ticket | 工单 | ticket | idle | 1 | 27 | null | `{open:12, slaRate:96, avgReply:8.4}` |
| support.chat | 在线客服 | chat | idle | 1 | 35 | null | `{open:7, slaRate:92, avgReply:3.1}` |
| security.soc | SOC | soc | working | 2 | 82 | 异常登录溯源 | `{alerts:23, critical:2, mtta:4.2}` |
| security.audit | 审计 | audit | idle | 1 | 21 | null | `{alerts:4, critical:0, mtta:11}` |
| data.pipeline | 流水线 | pipeline | idle | 1 | 29 | null | `{jobs:48, failures:1, lagMin:12}` |
| data.warehouse | 数仓 | warehouse | idle | 1 | 24 | null | `{jobs:12, failures:0, lagMin:38}` |
| data.feature | 特征 | feature | working | 2 | 71 | 特征集 v18 新鲜度校验 | `{jobs:9, failures:0, lagMin:4}` |
| data.report | 报表 | report | **dormant** | 0 | 3 | null | `{jobs:3, failures:0, lagMin:240}` |

`lastActiveMinAgo` 依次：1, 12, 26, 2, 41, 0, 1, 33, 8, 3, 15, 5, 1, 22, 11, 19, 2, 184。
demo.html 版的 `lastActiveAt` 随机 `now - 0~30 分钟`。

### 5.3 事件流种子（12 条，倒序即最新在前；id `evt_0001`…`evt_0012`，ts = now - minAgo）
| minAgo | workspace | level | title | detail | source |
|---|---|---|---|---|---|
| 3 | dev | info | 构建耗时 412s | 分支 feature/war-room，较上次 +38s | dev.frontend |
| 12 | ops | info | v2.3.1 发布完成 | 灰度 100%，耗时 6m12s | ops.release |
| 24 | ops | warn | CPU 持续 88% | prod-api-03 已连续 20 分钟高于阈值 | ops.monitor |
| 31 | pay | **critical** | 支付回调 5xx 突增 | 5 分钟内 37 次失败，渠道 alipay | pay.gateway |
| 46 | ops | info | 网关健康检查通过 | 12/12 节点正常 | ops.trouble |
| 58 | security | warn | 异常登录告警 | 同一账号 3 个地区短时登录 | security.soc |
| 72 | data | info | 特征集 v18 产出 | 新鲜度 4 分钟 | data.feature |
| 88 | support | info | 工单 #4821 已流转 | 从待处理转至处理中 | support.ticket |
| 104 | data | warn | 报表任务延迟 | 日活看板落后 240 分钟 | data.report |
| 121 | dev | info | PR #217 合并 | WorkBuddy 自动生成回归用例 | dev.workbuddy |
| 140 | pay | warn | 结算批次差异 2 笔 | 批次 SET-20261106-02 | pay.settle |
| 165 | system | info | 网关健康检查通过 | 全链路探活正常 | system |

### 5.4 业务记录样例（`server/store.ts` BusinessRecord）
`bld_1042`（dev/builds，构建 #1042 · feature/war-room，success，`{durationSec:412, branch:"feature/war-room", commit:"a91f0c2"}`）、
`inc_77`（ops/incidents，故障 INC-77 · 支付回调 5xx，investigating，critical，`{severity:"P1", owner:"ops.release", affected:"pay-callback"}`）、
`cb_551`（pay/callbacks，回调失败 5xx · alipay，failed，critical，`{count:37, code:502, channel:"alipay"}`）、
`tkt_4821`（support/tickets，工单 #4821 · 支付未到账，processing，warn，`{priority:"high", slaMinutes:42, channel:"app"}`）、
`alt_881`（security/alerts，告警 ALT-881 · 异常登录，acked，warn，`{severity:"high", regions:3, asset:"auth-service"}`）、
`rep_07`（data/reports，报表 · 日活看板，delayed，warn，`{lagMin:240, owner:"data.report"}`）等 14 条。

### 5.5 指标序列（`server/store.ts` `series()`）
每个工作区 24 个点、每 5 分钟一个（t 为 ISO）：
`throughput.v = max(4, round((42 + seed*7) * (1 + wobble)))`；
`errorRate.v = max(0, ((1.4 + seed*0.32) * (1 + wobble*1.5)).toFixed(2))`；
`latencyP95.v = round((120 + seed*26) * (1 + wobble*0.7))`；
`wobble = sin((i+seed)/2.1)*0.28 + cos((i+seed)/4.7)*0.18`（seed = 工作区序号 1–6）。

---

## 六、纯 HTML 复刻要点

### 必须实现（P0）
1. **单文件壳 + 三视图切换**：`/`、`/dashboard`、`/settings` 由 `location.pathname` 决定视图（可做成三个 HTML 共用 CSS/JS，或单页 + history/hash 路由）。
2. 顶栏：秒级时钟、4 组计数（消息/紧急/在线工位/响应）、演示模式灯、Wifi/Lock/设置按钮。
3. 消息条：最新 6 条（灯+标题+相对时间）、紧急槽（「N 条待处理」/「无」）、30s 相对时间重算。
4. 作战室：6 面板 3×2 网格、面板头（N/M 在线、N 项待处理）、网格底板、工位卡（名牌胶囊 + queue 数字 + **工位 SVG 插画** + 状态胶囊 + 负载条，**无边框**）。
5. 工位卡 hover/点击/键盘可达（Enter 打开）。
6. 抽屉：滑入动画、scrim、负载/待处理大数、当前任务、遥测表、任务输入、6 指令按钮（本地状态映射 + 调用记录 ≤5 条）、关闭。
7. 仪表盘：4 统计卡、吞吐折线（24 点合成数据 + 网格 + 末点）、工位负载排行（前 6、首条 accent）、状态分布条+图例、各工作区表、近期异常列表。
8. 设置：后端接入 4 行、回调调试表单（默认值见上）+ 发送逻辑（含 role 路由与回执文案）、通用接口表、6 张业务接口表。
9. 底部导航（激活态）与工具条（热力 toggle、刷新 `tick()`、跳 webhook 锚点）。
10. 设计令牌全套照搬（第四节），字体角色、状态灯、焦点环、`prefers-reduced-motion`。

### 可选 / 按需（P1）
- **SSE 实时流**（`EventSource /api/v1/events/stream`，事件 `snapshot/feed/overview`）：demo.html 本身不用；有后端时加上体验更好。
- 图表悬停 tooltip、ChartCard「表格」切换、`compare` 虚线：React 版特性，纯静态演示可省。
- `usePoll` 轮询（React 未实际使用）；如需实时性，30s 重绘 + 手动刷新已够。
- 业务资源 CRUD 页（`/workspaces/:key/:resource` 系列接口）：**当前前端没有任何页面消费它们**，只在设置页列出；纯复刻前端可不做。

### React 特有、可直接丢弃
- hooks（`usePoll`/`useEventStream`/`useMeasure`）、JSX/Tailwind 类名、next/font、next/link、`usePathname`。
- `NEXT_PUBLIC_API_BASE` 注入：纯 JS 里改成常量 `const API_BASE = "/api/v1"`（demo.html 已如此）。

### 接真实后端时
- 所有请求走 `fetch(API_BASE + path, { cache:"no-store", headers:{"content-type":"application/json"} })`，失败解析 `{error:{code,message}}`。
- 启动顺序照抄 demo.html：先内置数据渲染 → `GET /workspaces` 成功则 `adopt()` 重建 WORKSPACES/AGENTS → `GET /events?limit=30` 刷新事件 → 整屏重绘。
- 指令、webhook 在 `apiReady` 时先打接口再落本地（保持离线可用）。

### 细节陷阱（务必注意）
1. demo.html 顶栏「紧急」数值**恒红**；React 版只在 `urgent > 0` 时红 —— 二选一，建议按 React 版（条件上色）。
2. 作战室面板「N 项待处理」只统计 `status === "urgent"` 的工位；而 `WorkspaceSummary.urgentCount`（后端）还包含该区有 critical 事件的情况 —— 本地渲染用前者。
3. 面板在线数 = `status !== "dormant"` 计数；「在线工位」总数同理。
4. 负载条宽度 = `max(load, 3)%`，只做 opacity 过渡，宽度跳变。
5. 「各工作区」卡的吞吐/延迟是随机数，每次重绘变化（演示占位，勿当真实指标）。
6. 「响应」计数 demo 版每次重绘随机 8–21ms。
7. 所有插值进 HTML 的动态文案要 `esc()` 转义（demo.html 有 `esc()` 处理 `& < > "`）。
8. 抽屉打开时 z 序：scrim 40 < drawer 50；底部导航/工具条 z 30。
9. `queue > 0` 才显示工位卡左上角数字；`currentTask` 为空显示「暂无任务」。名牌胶囊与数字同排，`max-width:calc(100% - 18px)` 保证二者不重叠（英文长名靠 `title` / 抽屉看全名）。
10. 事件 id 格式：种子 `evt_0001` 起顺序编号；新事件 demo 版用随机 6 位 base36，后端版 `evt_{递增4位}`。
