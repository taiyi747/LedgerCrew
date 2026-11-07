/* ============================================================
   数据层：状态 + 双轨接入（内置数据 / /api/v1 后端）
   契约与 E:\AI工作\AIWHO-Webhook-中台 的 lib/contract.ts 一致
   ============================================================ */

const API_BASE = window.AIWHO_API_BASE || "/api/v1";

/* ---------- 状态枚举 → 灯 / 色 / 文案 ----------
   lamp/color 给状态点与图表用（全局一致）；
   pill 只给作战室工位卡上的状态胶囊用（参考图样式：实底 + 白字） */
const STATUS_META = {
  working: { label: "工作中", lamp: "lamp-working", color: "#c2410c", pill: "#e8963c" },
  idle:    { label: "空闲",   lamp: "lamp-idle",    color: "#737373", pill: "#5b8def" },
  urgent:  { label: "紧急",   lamp: "lamp-urgent",  color: "#b91c1c", pill: "#c0392b" },
  dormant: { label: "休眠",   lamp: "lamp-dormant", color: "#c9c7c4", pill: "#8e8d89" },
};
const STATUS_ORDER = ["working", "idle", "urgent", "dormant"];

const LEVEL_META = {
  info:     { lamp: "lamp-idle" },
  warn:     { lamp: "lamp-working" },
  critical: { lamp: "lamp-urgent" },
};

/* ---------- 指令枚举 → 中文文案（界面唯一出处） ----------
   key = AgentCommand，与后端契约一致，勿改 key，只改 value。
   done / on / off 是本项目新增的语义（完成 / 上班 / 下班），后端契约需同步扩展。
   start / pause / resume / ack 契约里仍有，但按钮已不用（语义并入 assign/on/off）。 */
const COMMAND_LABEL = {
  assign:   "派单",
  done:     "完成",
  escalate: "向上汇报",
  on:       "上班",
  off:      "下班",
  reset:    "复位",
  /* 以下仅契约兼容，按钮不用 */
  start:    "启动",
  pause:    "暂停",
  resume:   "继续",
  ack:      "确认",
};
function cmdLabel(command) {
  return t(COMMAND_LABEL[command] || command);
}
/* 把消息里的英文指令名换成本地文案（后端回执 message 也会带 command 原词） */
function localizeCmd(text, command) {
  return String(text).split(command).join(cmdLabel(command));
}

/* ---------- 中英切换 ----------
   t(src, vars?)：按 state.lang 查 js/i18n.js 的 I18N.en，查不到回退原文。
   英文表的 key 必须与源码中文字面量逐字一致；{var} 占位在调用处插值。 */
function t(src, vars) {
  let s = src;
  if (state.lang === "en" && I18N.en[src] !== undefined) s = I18N.en[src];
  if (vars) for (const k in vars) s = s.split("{" + k + "}").join(vars[k]);
  return s;
}
function readLang() {
  try { return localStorage.getItem("aiwho.lang") === "en" ? "en" : "zh"; } catch (err) { return "zh"; }
}
function setLang(lang) {
  state.lang = lang === "en" ? "en" : "zh";
  try { localStorage.setItem("aiwho.lang", state.lang); } catch (err) {}
  renderAll();  // app.js：整屏重绘（含抽屉、document.title）
}
function statusLabel(status) {
  return t(STATUS_META[status] ? STATUS_META[status].label : status);
}

/* ---------- 遥测字段 → 中文文案（界面唯一出处） ----------
   key = Agent.metrics 的字段名，与后端契约一致，勿改 key，只改 value。
   按业务模块分组；同一 key 在不同工作区含义相同（jobs/failures/lagMin 复用）。
   没收录的 key 原样显示，后端加新指标不影响渲染。 */
const METRIC_LABEL = {
  /* 客户接待 */
  open:      { label: "待办单数",     unit: "单" },
  slaRate:   { label: "按时办结率",   unit: "%" },
  avgReply:  { label: "平均响应时长", unit: "分钟" },
  /* 票据处理 · 风险与交付（归档） */
  jobs:      { label: "处理件数",     unit: "件" },
  failures:  { label: "失败件数",     unit: "件" },
  lagMin:    { label: "积压时长",     unit: "分钟" },
  /* 数据核对 */
  tps:       { label: "每秒处理量",   unit: "次/秒" },
  errorRate: { label: "错误率",       unit: "%" },
  p95:       { label: "延迟（95 分位）", unit: "毫秒" },
  /* 风险与交付 */
  alerts:    { label: "告警数",       unit: "条" },
  critical:  { label: "严重告警数",   unit: "条" },
  mtta:      { label: "平均受理时长", unit: "分钟" },
};
function metricMeta(key) {
  const m = METRIC_LABEL[key] || { label: key, unit: "" };
  return { label: t(m.label), unit: t(m.unit) };
}

/* ---------- 遥测随指令增减 ----------
   派单 → 待办/积压/告警上调；完成 → 已办上调、待办/积压下调、效率类小幅变好；
   向上汇报 → 紧急/告警上调。只动该工位已有的字段，未列出的 key 不变。
   百分比字段夹在 0–100，其余不小于 0，统一保留 1 位小数。 */
const METRIC_REACT = {
  assign:   { open: 1, lagMin: 2, alerts: 1 },
  done:     { jobs: 1, open: -1, lagMin: -2, tps: 3, avgReply: -0.3, slaRate: 1, errorRate: -0.2, p95: -6 },
  escalate: { critical: 1, alerts: 1 },
};
function reactMetrics(agent, command) {
  const delta = METRIC_REACT[command];
  if (!delta || !agent.metrics) return;
  for (const key in delta) {
    if (!(key in agent.metrics)) continue;
    const meta = METRIC_LABEL[key];
    let v = Number(agent.metrics[key]) + delta[key];
    v = meta && meta.unit === "%" ? Math.min(100, Math.max(0, v)) : Math.max(0, v);
    agent.metrics[key] = Math.round(v * 10) / 10;
  }
}

/* ---------- 全局状态 ---------- */
const state = {
  workspaces: WORKSPACES.map((w) => ({ ...w })),
  agents: AGENTS.map((a) => ({ ...a, metrics: { ...a.metrics } })),
  events: EVENTS.map((e) => ({ ...e })),
  traces: Object.fromEntries(Object.entries(TRACES).map(([k, v]) => [k, [...v]])),
  apiReady: false,
  latencyMs: 8 + Math.floor(Math.random() * 14), // demo：8–21ms
  showLoad: false,
  calls: {},          // agentId -> 调用记录（≤5）
  webhookResult: "",  // 回调调试回执
  eventSeq: 12,
  lang: readLang(),   // "zh" | "en"，三页共用 localStorage["aiwho.lang"]
  theme: readTheme(), // "light" | "dark"，三页共用 localStorage["aiwho.theme"]
  uiLocked: false,    // 界面锁定（防误触）：锁定后工位卡与指令按钮不响应
};

function readTheme() {
  try { return localStorage.getItem("aiwho.theme") === "dark" ? "dark" : "light"; } catch (err) { return "light"; }
}
function setTheme(theme) {
  state.theme = theme === "dark" ? "dark" : "light";
  try { localStorage.setItem("aiwho.theme", state.theme); } catch (err) {}
  renderAll();
}
function toggleLock() {
  state.uiLocked = !state.uiLocked;
  renderAll();
}

/* ---------- 格式化（规格书） ---------- */
function relativeTime(iso) {
  const s = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 15) return t("刚刚");
  if (s < 60) return t("{s} 秒前", { s });
  const m = Math.floor(s / 60);
  if (m < 60) return t("{m} 分钟前", { m });
  const h = Math.floor(m / 60);
  if (h < 24) return t("{h} 小时前", { h });
  return t("{d} 天前", { d: Math.floor(h / 24) });
}
function clockTime(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
function shortTime(iso) {
  const d = new Date(iso);
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}`;
}
function durationText(seconds) {
  const m = Math.floor(seconds / 60), s = seconds % 60;
  return m > 0 ? `${m}m${s}s` : `${s}s`;
}
function esc(str) {
  return String(str ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

/* ---------- 事件写入（本地） ---------- */
function pushEvent({ title, detail, level = "info", source, workspace }) {
  state.eventSeq += 1;
  const id = "evt_" + Math.random().toString(36).slice(2, 8);
  state.events.unshift({
    id,
    workspace: workspace || "system",
    level,
    title,
    detail: detail || "",
    source: source || "api",
    ts: new Date().toISOString(),
  });
  return id;
}

/* ---------- 汇总计算 ---------- */
function overview() {
  const online = state.agents.filter((a) => a.status !== "dormant").length;
  return {
    totalMessages: state.events.length,
    urgent: state.events.filter((e) => e.level === "critical").length,
    online,
    agents: state.agents.length,
    latencyMs: state.apiReady ? state.latencyMs : state.latencyMs,
    connection: state.apiReady ? "connected" : "connected",
    demoMode: !state.apiReady,
    ts: new Date().toISOString(),
  };
}
function workspaceSummary(key) {
  const meta = state.workspaces.find((w) => w.key === key);
  const agents = state.agents.filter((a) => a.workspace === key);
  return {
    ...meta,
    agents,
    agentCount: agents.length,
    onlineCount: agents.filter((a) => a.status !== "dormant").length,
    urgentCount: agents.filter((a) => a.status === "urgent").length,
    messageCount: state.events.filter((e) => e.workspace === key).length,
    health: Math.max(10, Math.round(100 - agents.reduce((s, a) => s + (a.status === "urgent" ? 22 : a.status === "working" ? 4 : 0), 0) / Math.max(agents.length, 1))),
  };
}

/* ---------- 后端接入（可选） ---------- */
async function apiJSON(path, options) {
  const res = await fetch(API_BASE + path, {
    cache: "no-store",
    headers: { "content-type": "application/json" },
    ...(options || {}),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function hydrate() {
  try {
    const body = await apiJSON("/workspaces");
    if (body && Array.isArray(body.items) && body.items.length) {
      state.workspaces = body.items.map((w) => ({
        key: w.key, name: w.name, accent: w.accent, description: w.description || "",
        endpoints: w.endpoints || [],
      }));
      state.agents = body.items.flatMap((w) => (w.agents || []).map((a) => ({ ...a })));
      state.apiReady = true;
    }
    const ev = await apiJSON("/events?limit=30");
    if (ev && Array.isArray(ev.items)) state.events = ev.items;
    return true;
  } catch (err) {
    state.apiReady = false; // 内置数据继续跑，离线可演示
    return false;
  }
}

/* ---------- 指令：先打后端，再本地落（离线可跑） ----------
   start/resume/assign → working（assign 写 currentTask）
   pause/reset → idle 且 currentTask=null
   escalate → urgent 且 queue+1
   ack：urgent→working 其余不变；queue>0 时 -1
*/
async function runCommand(agentId, command, task) {
  const agent = state.agents.find((a) => a.id === agentId);
  if (!agent) return { ok: false, message: t("工位不存在") };

  if (state.apiReady) {
    try {
      const body = await apiJSON(`/workspaces/${agent.workspace}/agents/${agent.id}/command`, {
        method: "POST",
        body: JSON.stringify({ command, task: task || undefined }),
      });
      applyCommandLocal(agent, command, task);
      return {
        ok: true,
        message: body.message ? localizeCmd(body.message, command) : t("已下发 {cmd} 至 {name}", { cmd: cmdLabel(command), name: t(agent.name) }),
      };
    } catch (err) {
      return { ok: false, message: t("失败 {msg}", { msg: err.message }) };
    }
  }

  applyCommandLocal(agent, command, task);
  return { ok: true, message: t("已下发 {cmd} 至 {name}", { cmd: cmdLabel(command), name: t(agent.name) }) };
}

/* ---------- 工作轨迹：追加一轮 ----------
   每轮 = 这一轮在干什么（say）+ 调用的工具（tool/input）+ 返回（output）。
   按时间正序，跟对话一样；接后端后改由 GET .../trace 下发。 */
function pushTrace(agentId, step) {
  (state.traces[agentId] = state.traces[agentId] || []).push({
    ts: new Date().toISOString(),
    status: "ok",
    ...step,
  });
}

/* ---------- 后端办结回填入口 ----------
   派单后的「自动完成」是**后端的职责**：前端不计时、不模拟、不猜。
   后端办结后通过任一通道告诉前端即可，两条路：
     ① 下发指令  POST /workspaces/{ws}/agents/{id}/command  { command: "done" }
        → 走 runCommand()，与派单同一套语义；
     ② 调用本函数 onTaskResolved(agentId) —— 只落本地状态 + 重绘。
   没有失误分支：工位是智能体，办结一律记成功（failures 不因办结变化）。
   离线演示模式下没有后端，任务不会自己收尾 —— 这是预期行为。 */
function onTaskResolved(agentId) {
  const agent = state.agents.find((a) => a.id === agentId);
  if (!agent) return false;
  applyCommandLocal(agent, "done");
  renderAll();
  return true;
}

function applyCommandLocal(agent, command, task) {
  switch (command) {
    case "assign":                       // 派单：接活 + 任务量 +1 + 转工作中
      agent.status = "working";
      agent.currentTask = task || agent.currentTask || "新任务";
      agent.queue += 1;
      pushTrace(agent.id, {
        say: "接到派单，开始处理",
        tool: "dispatch.accept",
        input: `queue=${agent.queue}`,
        output: "已排入队列",
      });
      break;
    case "done":                         // 完成：任务量 -1，清空队列才转空闲
      agent.queue = Math.max(0, agent.queue - 1);
      agent.status = agent.queue > 0 ? "working" : "idle";
      if (agent.queue === 0) agent.currentTask = null;
      pushTrace(agent.id, {
        say: "本轮办结",
        tool: "dispatch.complete",
        input: `queue=${agent.queue}`,
        // 存 key + 参数，渲染时才 t() 插值 —— 写入时插好值就换不了语言了
        output: agent.queue > 0 ? "队列还有 {n} 件" : "队列已清空",
        outputVars: agent.queue > 0 ? { n: agent.queue } : undefined,
      });
      break;
    case "escalate":                     // 向上汇报：只标紧急，不加次数
      agent.status = "urgent";
      break;
    case "on":                           // 上班：空闲
      agent.status = "idle";
      break;
    case "off":                          // 下班：休眠
      agent.status = "dormant";
      agent.currentTask = null;
      break;
    /* —— 以下为契约里仍有的老命令，按钮已不用，保留兼容 —— */
    case "start":
    case "resume":
      agent.status = "working";
      break;
    case "pause":
    case "reset":
      agent.status = "idle";
      agent.currentTask = null;
      break;
    case "ack":
      if (agent.status === "urgent") agent.status = "working";
      if (agent.queue > 0) agent.queue -= 1;
      break;
    default:
      break;
  }
  reactMetrics(agent, command);          // 遥测随派单/完成/汇报增减
  agent.lastActiveAt = new Date().toISOString();
  pushEvent({
    title: t("工位「{name}」收到指令 {cmd}", { name: t(agent.name), cmd: cmdLabel(command) }),
    detail: task || "",
    level: command === "escalate" ? "critical" : "info",
    source: agent.id,
    workspace: agent.workspace,
  });
}

/* ---------- 回调调试 sendWebhook ----------
   按 workspace + role 匹配工位；命中且 critical → urgent、queue+1
*/
async function sendWebhook({ workspace, level, role, title, detail }) {
  const suffix = state.apiReady ? t("（已写入后端）") : t("（内置数据）");

  if (state.apiReady) {
    try {
      await apiJSON(`/workspaces/${workspace}/webhook`, {
        method: "POST",
        body: JSON.stringify({
          type: "demo.callback",
          title, detail, level,
          agentRole: role || undefined,
          source: "demo.webhook",
          idempotencyKey: "dbg-" + Date.now(),
        }),
      });
      await hydrate();
    } catch (err) {
      return { ok: false, message: `失败 ${err.message}` };
    }
  }

  const agent = state.agents.find((a) => a.workspace === workspace && a.role === role);
  pushEvent({
    title,
    detail,
    level,
    source: agent ? agent.id : `${workspace}.webhook`,
    workspace,
  });
  if (agent && level === "critical") {
    agent.status = "urgent";
    agent.queue += 1;
    agent.lastActiveAt = new Date().toISOString();
  }

  return {
    ok: true,
    message: agent
      ? t("已写入 1 条 · 事件已路由至 {name} {suffix}", { name: t(agent.name), suffix })
      : t("已写入 1 条 · 未匹配到 role「{role}」，落在工作区级 {suffix}", { role, suffix }),
  };
}

/* ---------- 刷新：非休眠工位负载抖动（工具条刷新钮） ---------- */
function jitterLoads() {
  state.agents.forEach((a) => {
    if (a.status !== "dormant") {
      a.load = Math.min(98, Math.max(4, a.load + Math.round((Math.random() - 0.5) * 10)));
    }
  });
}
