/* ============================================================
   AI 助手（Marvis 式）—— 纯逻辑，不含渲染
   两块能力：你问它答（answer，带依据块），以及主动发现（buildInsights）。
   答案全部从 state 的实时数据现算，不接后端 LLM —— 与「离线可跑」一致。
   文案一律走 t()，中英双语；key 与中文字面量逐字一致。
   ============================================================ */

state.chat = {
  messages: [],     // { role:"me", text } 或 { role:"bot", q } —— bot 只存问题，渲染时现算
  suggestions: [],  // 输入框上方的追问 chip（存中文字面量，渲染时 t()）
  typing: false,
  seeded: false,
  focus: false,
};

/* ---------- 建议问题（追问 chip 的池子） ---------- */
const CHAT_SUGGESTIONS = [
  "哪个工位现在最忙？",
  "有什么异常吗？",
  "哪些工位积压了？",
  "有紧急的工位吗？",
  "谁现在空闲？",
  "整体情况怎么样？",
  "最近有什么消息？",
  "你能帮我做什么？",
];

/* ---------- 意图识别：关键词 → 意图 ----------
   中英两套词都要收；英文注意词形（busiest 不含 busy、problems 不含 issue）。 */
function intentOf(q) {
  const s = String(q || "").toLowerCase();
  const has = (...ws) => ws.some((w) => s.includes(w));
  if (has("帮助", "你能", "能做", "怎么用", "能帮我", "help", "what can")) return "help";
  if (has("最忙", "负载", "忙", "压力", "busy", "busiest", "workload", "load", "pressure")) return "busy";
  if (has("积压", "待处理", "队列", "排队", "backlog", "queue", "pending", "waiting")) return "queue";
  if (has("紧急", "报警", "告警", "urgent", "alert")) return "urgent";
  if (has("异常", "问题", "报错", "故障", "error", "issue", "problem", "wrong")) return "issues";
  if (has("空闲", "休眠", "下班", "没在", "闲置", "idle", "dormant", "away", "off duty")) return "away";
  if (has("最近", "消息", "事件", "动态", "recent", "event", "update", "latest")) return "recent";
  if (has("在线", "概况", "整体", "状态", "多少", "online", "status", "overview", "everything", "overall")) return "overview";
  return "unknown";
}

/* 证据行：{ label, value, sub?, bar? }，bar 0–100 画成小进度条 */
function ev(label, value, opts) {
  return { label, value, ...(opts || {}) };
}

/* ---------- 回答：按意图从实时数据现算 ---------- */
function answer(q) {
  const intent = intentOf(q);
  const byLoad = [...state.agents].sort((x, y) => y.load - x.load);
  const byQueue = [...state.agents].filter((a) => a.queue > 0).sort((x, y) => y.queue - x.queue);
  const urgent = state.agents.filter((a) => a.status === "urgent");
  const issues = state.events.filter((e) => e.level !== "info");
  const idle = state.agents.filter((a) => a.status === "idle");
  const dormant = state.agents.filter((a) => a.status === "dormant");
  const ov = overview();

  switch (intent) {
    case "busy": {
      const top = byLoad.slice(0, 3);
      return {
        text: t("现在最忙的是「{name}」，负载 {load}%。", { name: t(top[0].name), load: top[0].load }),
        evidence: top.map((a) => ev(t(a.name), a.load + "%", { bar: a.load, sub: statusLabel(a.status) })),
        actions: [{ label: t("查看工位负载"), href: "dashboard.html" }],
        followups: ["哪些工位积压了？", "有紧急的工位吗？"],
      };
    }

    case "queue": {
      if (!byQueue.length) {
        return {
          text: t("现在没有积压，所有工位队列都是空的。"),
          followups: ["哪个工位现在最忙？", "整体情况怎么样？"],
        };
      }
      const top = byQueue.slice(0, 3);
      return {
        text: t("待处理最多的是「{name}」，积压 {queue} 件。", { name: t(top[0].name), queue: top[0].queue }),
        evidence: top.map((a) => ev(t(a.name), t("{n} 件", { n: a.queue }), { sub: statusLabel(a.status) })),
        actions: [{ label: t("查看工位负载"), href: "dashboard.html" }],
        followups: ["有紧急的工位吗？", "最近有什么消息？"],
      };
    }

    case "urgent": {
      if (!urgent.length) {
        return {
          text: t("目前没有紧急工位，都还撑得住。"),
          followups: ["哪些工位积压了？", "有什么异常吗？"],
        };
      }
      return {
        text: t("有 {n} 个工位处于紧急状态。", { n: urgent.length }),
        evidence: urgent.map((a) => ev(t(a.name), statusLabel(a.status), {
          sub: a.currentTask ? t(a.currentTask) : t("暂无任务"),
        })),
        actions: [{ label: t("去作战室看"), href: "index.html" }],
        followups: ["有什么异常吗？", "哪些工位积压了？"],
      };
    }

    case "issues": {
      if (!issues.length) {
        return {
          text: t("最近没有异常，一切正常。"),
          followups: ["最近有什么消息？", "哪个工位现在最忙？"],
        };
      }
      return {
        text: t("最近有 {n} 条异常，最严重的是「{title}」。", {
          n: issues.length,
          title: t(issues[0].title),
        }),
        evidence: issues.slice(0, 4).map((e) => ev(t(e.title), relativeTime(e.ts), {
          sub: e.detail ? t(e.detail) : "",
        })),
        actions: [{ label: t("去仪表盘看"), href: "dashboard.html" }],
        followups: ["有紧急的工位吗？", "哪些工位积压了？"],
      };
    }

    case "away": {
      const list = [...idle, ...dormant];
      if (!list.length) {
        return {
          text: t("所有工位都在忙，没有空闲或休眠的。"),
          followups: ["哪个工位现在最忙？", "整体情况怎么样？"],
        };
      }
      return {
        text: t("{idle} 个空闲，{dormant} 个休眠。", { idle: idle.length, dormant: dormant.length }),
        evidence: list.map((a) => ev(t(a.name), statusLabel(a.status), { sub: relativeTime(a.lastActiveAt) })),
        actions: [{ label: t("去作战室看"), href: "index.html" }],
        followups: ["哪个工位现在最忙？", "整体情况怎么样？"],
      };
    }

    case "recent": {
      const items = state.events.slice(0, 5);
      return {
        text: t("最近 {n} 条消息：", { n: items.length }),
        evidence: items.map((e) => ev(t(e.title), relativeTime(e.ts), {
          sub: e.detail ? t(e.detail) : "",
        })),
        actions: [{ label: t("去仪表盘看"), href: "dashboard.html" }],
        followups: ["有什么异常吗？", "整体情况怎么样？"],
      };
    }

    case "overview": {
      const counts = {};
      STATUS_ORDER.forEach((s) => (counts[s] = state.agents.filter((a) => a.status === s).length));
      return {
        text: t("{total} 个工位里 {online} 个在线。", { total: ov.agents, online: ov.online }),
        evidence: STATUS_ORDER.map((s) => ev(statusLabel(s), counts[s], {
          bar: Math.round((counts[s] / Math.max(ov.agents, 1)) * 100),
        })),
        actions: [{ label: t("去作战室看"), href: "index.html" }, { label: t("去仪表盘看"), href: "dashboard.html" }],
        followups: ["哪个工位现在最忙？", "最近有什么消息？"],
      };
    }

    case "help":
      return {
        text: t("我可以帮你盯这些工位的实时状态。"),
        evidence: [
          ev(t("负载与忙闲"), t("哪个工位最忙")),
          ev(t("积压与队列"), t("哪些工位积压了")),
          ev(t("异常与紧急"), t("有什么异常吗")),
          ev(t("人员在岗"), t("谁现在空闲")),
        ],
        followups: ["哪个工位现在最忙？", "有什么异常吗？", "整体情况怎么样？"],
      };

    default:
      return {
        text: t("这个问题我还拿不准。你可以问我工位的忙闲、积压、异常或者整体情况。"),
        followups: ["哪个工位现在最忙？", "有什么异常吗？", "整体情况怎么样？"],
      };
  }
}

/* ---------- 主动发现（Marvis Actions 式） ----------
   进页面即算；每张卡：等级灯 + 标题 + 说明 + 置信度 + 建议动作。 */
function buildInsights() {
  const out = [];
  const since = (a) => Math.round((Date.now() - new Date(a.lastActiveAt).getTime()) / 60000);

  state.agents.filter((a) => a.status === "urgent").forEach((a) => {
    out.push({
      level: "critical",
      title: t("「{name}」状态紧急", { name: t(a.name) }),
      detail: a.currentTask ? t(a.currentTask) : t("待处理 {n} 件", { n: a.queue }),
      confidence: t("高"),
      action: { label: t("去作战室看"), href: "index.html" },
    });
  });

  state.agents.filter((a) => a.load > 85 && a.queue > 2).forEach((a) => {
    out.push({
      level: "warn",
      title: t("「{name}」过载且积压", { name: t(a.name) }),
      detail: t("负载 {load}%，待处理 {n} 件，建议分流", { load: a.load, n: a.queue }),
      confidence: t("高"),
      action: { label: t("查看工位负载"), href: "dashboard.html" },
    });
  });

  const crit = state.events.filter((e) => e.level === "critical");
  if (crit.length) {
    out.push({
      level: "critical",
      title: t("{n} 条紧急消息待处理", { n: crit.length }),
      detail: t(crit[0].title),
      confidence: t("中"),
      action: { label: t("去仪表盘看"), href: "dashboard.html" },
    });
  }

  state.agents.filter((a) => a.status === "dormant" && since(a) > 60).forEach((a) => {
    out.push({
      level: "info",
      title: t("「{name}」休眠较久", { name: t(a.name) }),
      detail: t("已 {min} 分钟没有动作", { min: since(a) }),
      confidence: t("中"),
      action: { label: t("去作战室看"), href: "index.html" },
    });
  });

  return out;
}
