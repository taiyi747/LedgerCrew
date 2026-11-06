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
