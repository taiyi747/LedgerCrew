/**
 * AIWHO WEBHOOK 中台 · 前端数据层（v1.1）
 *
 * - 对接后端：在 index.html 中（本文件之前）配置：
 *     <script>window.AIWHO_API_BASE = "http://localhost:3000";</script>
 * - 后端未就绪 / 请求失败时自动回退到内置 Mock，页面永不白屏。
 * - 接口契约见 api/接口文档.md。
 *
 * 业务流程：客户接待 → 票据处理 → 数据核对 → 风险与交付
 */
(function () {
  "use strict";

  const API_BASE = (window.AIWHO_API_BASE || "").replace(/\/$/, "");

  /* ---------- 内置 Mock（与 mock-server.js 数据一致） ---------- */
  const now = Date.now();
  const minsAgo = (m) => new Date(now - m * 60000).toISOString();

  const MOCK = {
    overview: {
      totalTasks: 12,
      processing: 2,
      delivered: 17,
      avgCycleMinutes: null,
    },
    messages: {
      list: [
        { id: "msg_001", text: "任务 #T018 需求受理完成",   level: "blue",  source: "reception", occurredAt: minsAgo(26) },
        { id: "msg_002", text: "票据批量 OCR 识别完成",     level: "amber", source: "ticketing", occurredAt: minsAgo(24) },
        { id: "msg_003", text: "账务比对一致率 99.2%",      level: "teal",  source: "reconcile", occurredAt: minsAgo(21) },
        { id: "msg_004", text: "任务 #T017 交付报告已归档", level: "green", source: "delivery",  occurredAt: minsAgo(18) },
        { id: "msg_005", text: "风险评估规则库已更新",      level: "green", source: "delivery",  occurredAt: minsAgo(12) },
      ],
      total: 12,
      nextCursor: null,
    },
    alerts: { list: [], total: 0 },
    groups: {
      list: [
        {
          id: "grp_reception", name: "客户接待", accent: "blue", columns: 1,
          stations: [
            { id: "st_intake",   name: "需求受理" },
            { id: "st_contract", name: "合同登记" },
          ],
        },
        {
          id: "grp_ticketing", name: "票据处理", accent: "amber", columns: 1,
          stations: [
            { id: "st_entry",  name: "票据录入" },
            { id: "st_review", name: "票面审核" },
          ],
        },
        {
          id: "grp_reconcile", name: "数据核对", accent: "teal", columns: 1,
          stations: [
            { id: "st_compare", name: "账务比对" },
            { id: "st_diff",    name: "差异复核" },
          ],
        },
        {
          id: "grp_delivery", name: "风险与交付", accent: "green", columns: 1,
          stations: [
            { id: "st_risk",     name: "风险评估" },
            { id: "st_archiver", name: "交付归档" },
          ],
        },
      ],
      total: 4,
    },
  };

  /* ---------- 请求封装 ---------- */
  async function request(path, fallback, options) {
    try {
      const res = await fetch(API_BASE + path, Object.assign({
        headers: { Accept: "application/json" },
      }, options || {}));
      if (!res.ok) throw new Error("HTTP " + res.status);
      const body = await res.json();
      if (body.code !== 0) throw new Error("业务错误: " + body.message);
      return body.data;
    } catch (err) {
      if (fallback !== undefined) {
        console.warn("[api] " + path + " 请求失败，回退到内置 Mock —", err.message);
        return fallback;
      }
      throw err;
    }
  }

  /* ---------- 仪表盘 Mock（按时间范围缩放演示数据） ---------- */
  function mockDashboard(range) {
    const factor = range === "today" ? 0.3 : range === "30d" ? 3.6 : 1;
    const scale = (n) => Math.max(1, Math.round(n * factor));

    const labels = range === "today"
      ? ["09:00", "11:00", "13:00", "15:00", "17:00", "19:00", "21:00"]
      : range === "30d"
        ? ["第1周", "第2周", "第3周", "第4周", "第5周", "第6周", "第7周"]
        : ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

    return {
      kpis: [
        { label: "总任务",  value: scale(128), unit: "",    delta: "+12%",  vs: "较上期", deltaType: "up",   color: "blue",  spark: [8, 12, 10, 16, 14, 20, 24] },
        { label: "已交付",  value: scale(117), unit: "",    delta: "+9%",   vs: "较上期", deltaType: "up",   color: "green", spark: [6, 10, 9, 14, 13, 18, 22] },
        { label: "处理中",  value: scale(6),   unit: "",    delta: "并行处理", vs: "4 个模块", deltaType: "warn", color: "amber", spark: [2, 3, 2, 5, 4, 6, 6] },
        { label: "平均时效", value: 42, unit: "min", delta: "↓ 8min", vs: "更快", deltaType: "down", color: "teal",  spark: [58, 55, 52, 50, 47, 45, 42] },
        { label: "异常率",  value: "1.2", unit: "%",  delta: "↓ 0.4%", vs: "更稳", deltaType: "down", color: "red",   spark: [2.1, 1.9, 1.8, 1.6, 1.5, 1.3, 1.2] },
      ],
      trend: {
        labels,
        received: [12, 18, 15, 22, 28, 24, 31].map(scale),
        delivered: [9, 15, 14, 19, 25, 22, 29].map(scale),
      },
      status: {
        done: scale(117),
        doing: scale(6),
        todo: scale(3),
        err: scale(2),
      },
      modules: [
        { name: "客户接待", accent: "blue",  count: scale(132), avgMinutes: 12 },
        { name: "票据处理", accent: "amber", count: scale(214), avgMinutes: 28 },
        { name: "数据核对", accent: "teal",  count: scale(198), avgMinutes: 22 },
        { name: "风险与交付", accent: "green", count: scale(121), avgMinutes: 15 },
      ],
      verify: { checked: scale(1284), pending: scale(12), failed: scale(3) },
      recent: [
        { id: "T0128", requirement: "为客户「星辰科技」核对 3 月票据并出具交付报告", module: "风险与交付", status: "done",  duration: "41 分钟",  createdAt: "今天 15:32" },
        { id: "T0127", requirement: "「蓝海传媒」2 月流水差异复核与说明",           module: "数据核对",  status: "doing", duration: "进行中 18 分钟", createdAt: "今天 14:58" },
        { id: "T0126", requirement: "「星火教育」Q1 发票批量录入与票面审核",        module: "票据处理",  status: "doing", duration: "进行中 26 分钟", createdAt: "今天 14:21" },
        { id: "T0125", requirement: "「云间科技」合同票据归档",                    module: "风险与交付", status: "done",  duration: "35 分钟",  createdAt: "今天 11:47" },
        { id: "T0124", requirement: "「新锐设计」报销单核验（金额不符 2 笔）",      module: "数据核对",  status: "err",   duration: "已挂起",   createdAt: "今天 10:16" },
        { id: "T0123", requirement: "「明远贸易」客户建档与需求受理",              module: "客户接待",  status: "todo",  duration: "待开始",   createdAt: "今天 09:40" },
      ],
    };
  }

  let localTaskSeq = 100;

  /* ---------- 对外接口 ---------- */
  window.API = {
    /** 顶部统计 */
    getOverview: () => request("/api/v1/overview", MOCK.overview),
    /** 实时消息流 */
    getMessages: (limit) => request("/api/v1/messages?limit=" + (limit || 20), MOCK.messages),
    /** 风险告警 */
    getAlerts: () => request("/api/v1/alerts", MOCK.alerts),
    /** 四大模块与工位 */
    getGroups: () => request("/api/v1/groups", MOCK.groups),

    /** 仪表盘统计（range: today / 7d / 30d） */
    getDashboard: (range) => request("/api/v1/dashboard?range=" + (range || "7d"), mockDashboard(range || "7d")),

    /**
     * 下发客户任务
     * @param {string} requirement 客户需求描述
     * @returns {Promise<{id:string, stage:string}>}
     */
    submitTask: (requirement) => request("/api/v1/tasks", {
      id: "T0" + (++localTaskSeq),
      stage: "grp_reception",
      requirement: requirement,
      createdAt: new Date().toISOString(),
    }, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ requirement: requirement }),
    }),
  };
})();
