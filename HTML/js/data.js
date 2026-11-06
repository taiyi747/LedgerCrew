/* ============================================================
   内置演示数据（精简版：4 大业务模块）
   客户接待 → 票据处理 → 数据核对 → 风险与交付
   后续新增模块：在 WORKSPACES / AGENTS / EVENTS 各加一条即可
   后端接入成功后由 js/api.js 的 adopt() 整体替换
   ============================================================ */

const WORKSPACES = [
  {
    key: "reception", name: "客户接待", accent: "#64748b",
    description: "客户需求受理与合同登记",
    endpoints: [
      { method: "GET",  path: "/api/v1/workspaces/reception/agents", summary: "工位列表" },
      { method: "POST", path: "/api/v1/workspaces/reception/agents/:id/command", summary: "下发指令" },
      { method: "GET",  path: "/api/v1/workspaces/reception/metrics", summary: "工作区指标" },
      { method: "POST", path: "/api/v1/workspaces/reception/webhook", summary: "业务回调" },
    ],
  },
  {
    key: "ticketing", name: "票据处理", accent: "#64748b",
    description: "票据录入与票面审核",
    endpoints: [
      { method: "GET",  path: "/api/v1/workspaces/ticketing/agents", summary: "工位列表" },
      { method: "POST", path: "/api/v1/workspaces/ticketing/agents/:id/command", summary: "下发指令" },
      { method: "GET",  path: "/api/v1/workspaces/ticketing/metrics", summary: "工作区指标" },
      { method: "POST", path: "/api/v1/workspaces/ticketing/webhook", summary: "业务回调" },
    ],
  },
  {
    key: "reconcile", name: "数据核对", accent: "#64748b",
    description: "账务比对与差异复核",
    endpoints: [
      { method: "GET",  path: "/api/v1/workspaces/reconcile/agents", summary: "工位列表" },
      { method: "POST", path: "/api/v1/workspaces/reconcile/agents/:id/command", summary: "下发指令" },
      { method: "GET",  path: "/api/v1/workspaces/reconcile/metrics", summary: "工作区指标" },
      { method: "POST", path: "/api/v1/workspaces/reconcile/webhook", summary: "业务回调" },
    ],
  },
  {
    key: "delivery", name: "风险与交付", accent: "#0f9e8e",
    description: "风险评估与交付归档",
    endpoints: [
      { method: "GET",  path: "/api/v1/workspaces/delivery/agents", summary: "工位列表" },
      { method: "POST", path: "/api/v1/workspaces/delivery/agents/:id/command", summary: "下发指令" },
      { method: "GET",  path: "/api/v1/workspaces/delivery/metrics", summary: "工作区指标" },
      { method: "POST", path: "/api/v1/workspaces/delivery/webhook", summary: "业务回调" },
    ],
  },
];

/* ---------- 8 个工位（每模块 2 岗） ---------- */
const AGENTS = [
  { id: "reception.intake", workspace: "reception", name: "需求受理", role: "intake", status: "working", queue: 2, load: 74, currentTask: "受理「星辰科技」3 月票据核对需求", lastActiveAt: minutesAgo(2), metrics: { open: 12, slaRate: 96, avgReply: 8.4 } },
  { id: "reception.contract", workspace: "reception", name: "合同登记", role: "contract", status: "idle", queue: 1, load: 18, currentTask: null, lastActiveAt: minutesAgo(9), metrics: { open: 5, slaRate: 99, avgReply: 3.1 } },

  { id: "ticketing.entry", workspace: "ticketing", name: "票据录入", role: "entry", status: "working", queue: 2, load: 68, currentTask: "Q1 发票批量录入（128 张）", lastActiveAt: minutesAgo(3), metrics: { jobs: 128, failures: 2, lagMin: 6 } },
  { id: "ticketing.review", workspace: "ticketing", name: "票面审核", role: "review", status: "urgent", queue: 4, load: 93, currentTask: "票面异常复核（金额不符 2 笔）", lastActiveAt: minutesAgo(1), metrics: { jobs: 96, failures: 2, lagMin: 12 } },

  { id: "reconcile.compare", workspace: "reconcile", name: "账务比对", role: "compare", status: "working", queue: 2, load: 71, currentTask: "3 月账务比对", lastActiveAt: minutesAgo(2), metrics: { tps: 214, errorRate: 0.6, p95: 182 } },
  { id: "reconcile.diff", workspace: "reconcile", name: "差异复核", role: "diff", status: "idle", queue: 1, load: 24, currentTask: null, lastActiveAt: minutesAgo(11), metrics: { tps: 42, errorRate: 1.1, p95: 240 } },

  { id: "delivery.risk", workspace: "delivery", name: "风险评估", role: "risk", status: "working", queue: 1, load: 66, currentTask: "交付前风险评估 · #R-0621", lastActiveAt: minutesAgo(2), metrics: { alerts: 23, critical: 1, mtta: 4.2 } },
  { id: "delivery.archive", workspace: "delivery", name: "交付归档", role: "archive", status: "dormant", queue: 0, load: 3, currentTask: null, lastActiveAt: minutesAgo(104), metrics: { jobs: 3, failures: 0, lagMin: 240 } },
];

/* ---------- 12 条事件种子（minAgo 为距今分钟数） ---------- */
const EVENTS = [
  { id: "evt_0001", workspace: "reception", level: "info", title: "需求受理完成 · 「星辰科技」3 月票据核对", detail: "已生成工单，进入票据处理", source: "reception.intake", ts: minutesAgo(3) },
  { id: "evt_0002", workspace: "ticketing", level: "info", title: "票据批量 OCR 识别完成 128 张", detail: "识别准确率 98.7%", source: "ticketing.entry", ts: minutesAgo(8) },
  { id: "evt_0003", workspace: "ticketing", level: "critical", title: "票面异常 · 金额不符 2 笔", detail: "INV-233 与流水差 ¥40，INV-241 缺凭证", source: "ticketing.review", ts: minutesAgo(12) },
  { id: "evt_0004", workspace: "reconcile", level: "info", title: "账务比对一致率 99.2%", detail: "128 笔中 2 笔转差异复核", source: "reconcile.compare", ts: minutesAgo(18) },
  { id: "evt_0005", workspace: "reconcile", level: "warn", title: "差异 1 项待说明", detail: "批次 SET-20261106-02 差 ¥40", source: "reconcile.diff", ts: minutesAgo(24) },
  { id: "evt_0006", workspace: "delivery", level: "info", title: "风险评估通过 · 报告生成中", detail: "#R-0621 风险项 0，进入交付", source: "delivery.risk", ts: minutesAgo(31) },
  { id: "evt_0007", workspace: "delivery", level: "info", title: "交付归档完成 #R-0621", detail: "报告与凭证已归档", source: "delivery.archive", ts: minutesAgo(46) },
  { id: "evt_0008", workspace: "reception", level: "info", title: "合同登记完成 · 蓝海传媒", detail: "服务期 2026 全年", source: "reception.contract", ts: minutesAgo(58) },
  { id: "evt_0009", workspace: "ticketing", level: "warn", title: "票据录入积压 42 张", detail: "队列持续增长，建议分流", source: "ticketing.entry", ts: minutesAgo(72) },
  { id: "evt_0010", workspace: "delivery", level: "info", title: "报表任务完成", detail: "月度对账报表已推送", source: "delivery.archive", ts: minutesAgo(88) },
  { id: "evt_0011", workspace: "reception", level: "info", title: "需求受理完成 · 星火教育 Q1 发票", detail: "已进入票据处理队列", source: "reception.intake", ts: minutesAgo(104) },
  { id: "evt_0012", workspace: "system", level: "info", title: "全链路探活正常", detail: "4 个工作区 8 个工位在线", source: "system", ts: minutesAgo(165) },
];

/* ---------- 工作轨迹（每一轮干什么 + 调了什么工具） ----------
   跟对话一样按时间正序排：叙述 → 工具调用 → 返回结果。
   演示种子；接后端后由 GET /workspaces/{ws}/agents/{id}/trace 下发。
   say = 这一轮在干什么；tool/input/output = 调用的工具、入参、返回。 */
const TRACES = {
  "reception.intake": [
    { ts: minutesAgo(58), say: "受理「星辰科技」3 月票据核对需求", tool: "ticket.create", input: "customer=星辰科技", output: "工单 T-20261106-01 已建", status: "ok" },
    { ts: minutesAgo(41), say: "调取客户合同与服务范围", tool: "contract.fetch", input: "customer=星辰科技", output: "CT-2026-031，含 3 月票据核对", status: "ok" },
    { ts: minutesAgo(26), say: "把需求拆成票据录入与账务比对两段，派给下游", tool: "dispatch.route", input: "to=ticketing.entry,reconcile.compare", output: "已派 2 个工位", status: "ok" },
    { ts: minutesAgo(2),  say: "跟进工单进度，票据已进入比对阶段", tool: "ticket.status", input: "id=T-20261106-01", output: "进度 60%", status: "ok" },
  ],

  "reception.contract": [
    { ts: minutesAgo(88), say: "登记「蓝海传媒」2026 年度服务合同", tool: "contract.register", input: "customer=蓝海传媒", output: "CT-2026-032 已入库", status: "ok" },
    { ts: minutesAgo(71), say: "核对服务期与计费条款", tool: "clause.check", input: "id=CT-2026-032", output: "服务期 2026 全年，无异常", status: "ok" },
    { ts: minutesAgo(58), say: "归档合同原件并同步到计费系统", tool: "archive.push", input: "id=CT-2026-032", output: "已归档并同步", status: "ok" },
    { ts: minutesAgo(9),  say: "登记「星火教育」Q1 发票服务合同", tool: "contract.register", input: "customer=星火教育", output: "CT-2026-033 已入库", status: "ok" },
  ],

  "ticketing.entry": [
    { ts: minutesAgo(52), say: "批量 OCR 识别 Q1 发票 128 张", tool: "ocr.batch", input: "files=128", output: "识别 128 张，准确率 98.7%", status: "ok" },
    { ts: minutesAgo(37), say: "补录缺失的抬头与税号", tool: "field.fill", input: "missing=12", output: "补齐 12 张", status: "ok" },
    { ts: minutesAgo(19), say: "送票面审核", tool: "dispatch.route", input: "to=ticketing.review", output: "已派票面审核", status: "ok" },
    { ts: minutesAgo(3),  say: "继续录入新到的 42 张票据", tool: "ocr.batch", input: "files=42", output: "队列增长中", status: "warn" },
  ],

  "ticketing.review": [
    { ts: minutesAgo(46), say: "复核票面异常（金额不符 2 笔）", tool: "invoice.compare", input: "batch=Q1", output: "INV-233 差 ¥40，INV-241 缺凭证", status: "warn" },
    { ts: minutesAgo(31), say: "比对流水找差异来源", tool: "ledger.lookup", input: "invoice=INV-233", output: "与流水差 ¥40", status: "warn" },
    { ts: minutesAgo(18), say: "查 INV-241 的原始凭证", tool: "receipt.find", input: "invoice=INV-241", output: "未找到凭证", status: "error" },
    { ts: minutesAgo(12), say: "把差异转人工说明", tool: "escalate.human", input: "items=2", output: "已转差异复核", status: "ok" },
  ],

  "reconcile.compare": [
    { ts: minutesAgo(44), say: "比对 3 月账务 128 笔", tool: "ledger.match", input: "period=2026-03,count=128", output: "一致率 99.2%", status: "ok" },
    { ts: minutesAgo(29), say: "抽出 2 笔不一致的入账", tool: "diff.extract", input: "period=2026-03", output: "2 笔转差异复核", status: "warn" },
    { ts: minutesAgo(18), say: "输出比对结果报表", tool: "report.generate", input: "type=monthly-match", output: "月度比对报表已生成", status: "ok" },
  ],

  "reconcile.diff": [
    { ts: minutesAgo(33), say: "核查批次 SET-20261106-02 的差异", tool: "batch.trace", input: "batch=SET-20261106-02", output: "差 ¥40", status: "warn" },
    { ts: minutesAgo(24), say: "查该批次的入账凭证", tool: "receipt.find", input: "batch=SET-20261106-02", output: "找到 3 张凭证", status: "ok" },
    { ts: minutesAgo(11), say: "汇总差异说明草稿", tool: "report.draft", input: "items=1", output: "草稿已出，待人工确认", status: "ok" },
  ],

  "delivery.risk": [
    { ts: minutesAgo(64), say: "对 #R-0621 做交付前风险扫描", tool: "risk.scan", input: "id=R-0621", output: "风险项 0", status: "ok" },
    { ts: minutesAgo(43), say: "校验交付物完整性", tool: "artifact.check", input: "id=R-0621", output: "报告与凭证齐备", status: "ok" },
    { ts: minutesAgo(31), say: "出具风险评估结论", tool: "report.generate", input: "id=R-0621", output: "结论已出，进入交付", status: "ok" },
  ],

  "delivery.archive": [
    { ts: minutesAgo(104), say: "归档 #R-0621 的报告与凭证", tool: "archive.push", input: "id=R-0621", output: "已归档", status: "ok" },
    { ts: minutesAgo(88), say: "生成月度对账报表", tool: "report.generate", input: "type=monthly", output: "报表已推送", status: "ok" },
    { ts: minutesAgo(46), say: "同步到计费系统", tool: "billing.sync", input: "period=2026-03", output: "已同步", status: "ok" },
  ],
};

/* ---------- 通用接口（设置页表格） ---------- */
const COMMON_ENDPOINTS = [
  { method: "GET",   path: "/api/v1/system/overview", summary: "顶栏指标" },
  { method: "GET",   path: "/api/v1/events", summary: "消息流（分页/筛选）" },
  { method: "GET",   path: "/api/v1/events/stream", summary: "SSE 实时流" },
  { method: "GET",   path: "/api/v1/agents", summary: "全部工位" },
  { method: "PATCH", path: "/api/v1/agents/:id", summary: "更新工位状态" },
  { method: "GET",   path: "/api/v1/workspaces", summary: "工作区汇总" },
  { method: "GET",   path: "/api/v1/metrics/dashboard", summary: "仪表盘数据" },
];

/* ---------- 工具函数 ---------- */
function minutesAgo(m) {
  return new Date(Date.now() - m * 60000).toISOString();
}

/* 吞吐折线：24 点合成公式（规格书仪表盘·消息吞吐） */
function throughputSeries() {
  const pts = [];
  for (let i = 0; i < 24; i++) {
    pts.push(Math.max(18, Math.round(220 + Math.sin(i / 2.1) * 52 + Math.cos(i / 4.7) * 26 + (23 - i) * 2.2)));
  }
  return pts;
}
