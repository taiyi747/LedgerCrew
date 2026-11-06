/**
 * AIWHO WEBHOOK 中台 · Mock 后端 v1.1（零依赖，仅需 Node.js）
 *
 * 启动：  node api/mock-server.js        （默认 http://localhost:3000）
 * 换端口： PORT=8080 node api/mock-server.js
 *
 * 业务流程：客户接待 → 票据处理 → 数据核对 → 风险与交付
 * 实现了 api/接口文档.md 中的全部 REST 接口，数据结构与文档一致，
 * 后端同学可直接以本文件的 DATA 作为造数参考。
 */

const http = require("http");
const { URL } = require("url");

const PORT = Number(process.env.PORT || 3000);

/* ============ 造数（时间按启动时刻动态生成） ============ */
const now = Date.now();
const minsAgo = (m) => new Date(now - m * 60000).toISOString();

const DATA = {
  overview: {
    totalTasks: 12,
    processing: 2,
    delivered: 17,
    avgCycleMinutes: null,
  },

  messages: [
    { id: "msg_001", text: "任务 #T018 需求受理完成",   level: "blue",  source: "reception", occurredAt: minsAgo(26) },
    { id: "msg_002", text: "票据批量 OCR 识别完成",     level: "amber", source: "ticketing", occurredAt: minsAgo(24) },
    { id: "msg_003", text: "账务比对一致率 99.2%",      level: "teal",  source: "reconcile", occurredAt: minsAgo(21) },
    { id: "msg_004", text: "任务 #T017 交付报告已归档", level: "green", source: "delivery",  occurredAt: minsAgo(18) },
    { id: "msg_005", text: "风险评估规则库已更新",      level: "green", source: "delivery",  occurredAt: minsAgo(12) },
    { id: "msg_006", text: "任务 #T016 已交付",         level: "green", source: "delivery",  occurredAt: minsAgo(8)  },
    { id: "msg_007", text: "新客户「星辰科技」已建档",   level: "blue",  source: "reception", occurredAt: minsAgo(5)  },
    { id: "msg_008", text: "票据影像归档完成",          level: "amber", source: "ticketing", occurredAt: minsAgo(2)  },
  ],

  alerts: [
    // 联调风险区域时可打开
    // { id: "alert_001", title: "差异复核超时 1 单", level: "warn", createdAt: new Date(now - 1800e3).toISOString(), resolved: false },
  ],

  /* 四大模块（顺序即流程顺序），stations = 模块内的小猫工位 */
  groups: [
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
};

/* ============ 任务模拟（POST /tasks 后按流程自动推进） ============ */
const STAGE_ORDER = ["grp_reception", "grp_ticketing", "grp_reconcile", "grp_delivery"];
const STAGE_SECONDS = 30; // 每个模块模拟处理 30 秒
let taskSeq = 100;
const TASKS = {};

function createTask(requirement) {
  const id = "T0" + (++taskSeq);
  TASKS[id] = {
    id,
    requirement,
    createdAt: new Date().toISOString(),
  };
  return id;
}

function taskView(id) {
  const t = TASKS[id];
  if (!t) return null;
  const elapsed = (Date.now() - new Date(t.createdAt).getTime()) / 1000;
  const idx = Math.min(Math.floor(elapsed / STAGE_SECONDS), STAGE_ORDER.length - 1);
  const done = elapsed >= STAGE_SECONDS * STAGE_ORDER.length;
  return {
    id: t.id,
    requirement: t.requirement,
    createdAt: t.createdAt,
    stage: STAGE_ORDER[idx],
    done,
  };
}

/* ============ 路由 ============ */
const ROUTES = {
  "/api/v1/overview": () => DATA.overview,
  "/api/v1/messages": (url) => {
    const limit = Math.min(Number(url.searchParams.get("limit")) || 20, 100);
    return { list: DATA.messages.slice(0, limit), total: DATA.messages.length, nextCursor: null };
  },
  "/api/v1/alerts": () => {
    const list = DATA.alerts.filter((a) => !a.resolved);
    return { list, total: list.length };
  },
  "/api/v1/groups": () => ({ list: DATA.groups, total: DATA.groups.length }),
};

function envelope(data) {
  return JSON.stringify({ code: 0, message: "ok", data, ts: new Date().toISOString() });
}
function envelopeErr(code, message) {
  return JSON.stringify({ code, message, data: null, ts: new Date().toISOString() });
}

http
  .createServer((req, res) => {
    const url = new URL(req.url, `http://${req.headers.host}`);
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Headers", "Authorization, Content-Type");
    res.setHeader("Content-Type", "application/json; charset=utf-8");

    if (req.method === "OPTIONS") {
      res.writeHead(204).end();
      return;
    }

    // POST /api/v1/tasks —— 下发客户任务
    if (req.method === "POST" && url.pathname === "/api/v1/tasks") {
      let body = "";
      req.on("data", (c) => (body += c));
      req.on("end", () => {
        let requirement = "";
        try { requirement = JSON.parse(body).requirement || ""; } catch (e) {}
        const id = createTask(requirement);
        res.writeHead(200);
        res.end(envelope(taskView(id)));
        console.log(`[200] POST /api/v1/tasks -> ${id}`);
      });
      return;
    }

    // GET /api/v1/tasks/:id —— 查询任务进度
    const taskMatch = url.pathname.match(/^\/api\/v1\/tasks\/(\w+)$/);
    if (req.method === "GET" && taskMatch) {
      const view = taskView(taskMatch[1]);
      res.writeHead(view ? 200 : 404);
      res.end(view ? envelope(view) : envelopeErr(404, "任务不存在"));
      console.log(`[${view ? 200 : 404}] GET ${url.pathname}`);
      return;
    }

    const handler = ROUTES[url.pathname];
    if (req.method === "GET" && handler) {
      res.writeHead(200);
      res.end(envelope(handler(url)));
      console.log(`[200] ${req.method} ${url.pathname}${url.search}`);
      return;
    }

    res.writeHead(404);
    res.end(envelopeErr(404, "接口不存在"));
    console.log(`[404] ${req.method} ${url.pathname}`);
  })
  .listen(PORT, () => {
    console.log(`✅ Mock API 已启动: http://localhost:${PORT}`);
    console.log("   GET  /api/v1/overview | /api/v1/messages | /api/v1/alerts | /api/v1/groups");
    console.log("   POST /api/v1/tasks   | GET /api/v1/tasks/:id");
  });
