/* ============ AIWHO WEBHOOK 中台 · 渲染与任务流转引擎 ============
 * 业务流程：客户接待 → 票据处理 → 数据核对 → 风险与交付
 *
 * 数据来自 js/api.js（window.API）：
 *   后端就绪 → 接口数据；后端未就绪 → 内置 Mock，页面照常演示。
 * 契约见 api/接口文档.md
 */

/* ---------- 模块元信息（顺序即流程顺序） ---------- */
const STAGE_META = {
  grp_reception: {
    screen: "chat",
    working: "受理需求",
    doneLog: "需求受理完成，工单已建立",
    logColor: "blue",
  },
  grp_ticketing: {
    screen: "scan",
    working: "处理票据",
    doneLog: "票据录入与票面审核完成",
    logColor: "amber",
  },
  grp_reconcile: {
    screen: "compare",
    working: "核对数据",
    doneLog: "账务核对一致，差异已复核",
    logColor: "teal",
  },
  grp_delivery: {
    screen: "shield",
    working: "风险交付",
    doneLog: "风险评估通过，交付报告已归档",
    logColor: "green",
  },
};

/* ---------- 各模块的小猫配色 ---------- */
const FUR = {
  blue:  { fur1: "#F6B26B", fur2: "#E89B4E", belly: "#FFE9CE" }, // 橘猫
  amber: { fur1: "#A9B6C8", fur2: "#8C9BB0", belly: "#E7EDF4" }, // 蓝灰猫
  teal:  { fur1: "#EFE3D4", fur2: "#D9C7B2", belly: "#FBF6EF" }, // 奶油猫
  green: { fur1: "#5B6472", fur2: "#47505D", belly: "#C9D2DE" }, // 玄猫
};

/* ============ 小猫 SVG（渐变毛发 / 表情 / 尾巴 / 打字爪） ============ */
function catSVG(accent) {
  const f = FUR[accent] || FUR.blue;
  return `
  <svg class="cat" viewBox="0 0 200 190"
       style="--fur1:${f.fur1};--fur2:${f.fur2};--belly:${f.belly}">
    <!-- 尾巴 -->
    <path class="tail fur-dark" d="M150 172 Q192 160 180 116"
          fill="none" stroke="${f.fur2}" stroke-width="15" stroke-linecap="round"/>
    <!-- 身体 -->
    <path class="body-grp">
      <path class="fur" d="M60 178 Q56 112 100 110 Q144 112 140 178 Z"/>
      <ellipse class="belly" cx="100" cy="154" rx="27" ry="24"/>
      <!-- 爪子 -->
      <ellipse class="paw paw-l fur-dark" cx="80" cy="176" rx="13" ry="9"/>
      <ellipse class="paw paw-r fur-dark" cx="120" cy="176" rx="13" ry="9"/>
    </path>
    <!-- 头 -->
    <g class="head-grp">
      <!-- 耳朵 -->
      <path class="fur" d="M62 52 L56 12 L92 38 Z"/>
      <path class="fur" d="M138 52 L144 12 L108 38 Z"/>
      <path class="inner-ear" d="M66 48 L62 22 L86 40 Z"/>
      <path class="inner-ear" d="M134 48 L138 22 L114 40 Z"/>
      <!-- 脸 -->
      <ellipse class="fur" cx="100" cy="72" rx="41" ry="38"/>
      <!-- 虎斑纹 -->
      <path class="fur-dark" d="M88 38 Q92 30 96 38 Q92 34 88 38" opacity=".7"/>
      <path class="fur-dark" d="M104 38 Q108 30 112 38 Q108 34 104 38" opacity=".7"/>
      <!-- 眼睛 -->
      <g class="eyes">
        <ellipse class="eye-white" cx="82" cy="70" rx="9.5" ry="11"/>
        <ellipse class="eye-white" cx="118" cy="70" rx="9.5" ry="11"/>
        <circle class="pupil" cx="83" cy="71.5" r="5.6"/>
        <circle class="pupil" cx="119" cy="71.5" r="5.6"/>
        <circle class="glint" cx="85.6" cy="68" r="2.1"/>
        <circle class="glint" cx="121.6" cy="68" r="2.1"/>
      </g>
      <!-- 腮红 -->
      <ellipse cx="66" cy="88" rx="8" ry="5" fill="#f79e9e" opacity=".5"/>
      <ellipse cx="134" cy="88" rx="8" ry="5" fill="#f79e9e" opacity=".5"/>
      <!-- 口鼻 -->
      <ellipse class="belly" cx="100" cy="90" rx="21" ry="14"/>
      <path class="nose" d="M100 81 l6 4.5 -6 5 -6 -5 z"/>
      <path class="line" d="M100 90.5 q-5 6 -10 1.5"/>
      <path class="line" d="M100 90.5 q5 6 10 1.5"/>
      <!-- 胡须 -->
      <path class="line" d="M74 84 L52 78" opacity=".5"/>
      <path class="line" d="M74 91 L51 91" opacity=".5"/>
      <path class="line" d="M126 84 L148 78" opacity=".5"/>
      <path class="line" d="M126 91 L149 91" opacity=".5"/>
    </g>
  </svg>`;
}

/* ============ 屏幕内容（每个模块不同的动画） ============ */
function screenHTML(type) {
  switch (type) {
    case "chat": // 客户接待：对话流
      return `
        <div class="scr">
          <div class="bubble b1">您好，需求已收到 🎧</div>
          <div class="bubble b2 me">核对 3 月票据并出具报告</div>
          <div class="bubble b3">好的，已生成工单 ✅</div>
          <div class="typing-row"><i></i><i></i><i></i></div>
        </div>`;
    case "scan": // 票据处理：扫描识别
      return `
        <div class="scr scr--scan">
          <div class="doc">
            <div class="doc-head"></div>
            <div class="doc-line l1"></div>
            <div class="doc-line l2"></div>
            <div class="doc-line l3"></div>
            <div class="doc-line l4"></div>
            <div class="scan-bar"></div>
          </div>
          <div class="ocr-chip">OCR 识别中…</div>
        </div>`;
    case "compare": // 数据核对：账务比对
      return `
        <div class="scr scr--compare">
          <div class="cmp-row r1"><span>系统 ¥128,400</span><em>=</em><span>票据 ¥128,400</span><b class="check">✓</b></div>
          <div class="cmp-row r2"><span>系统 ¥86,200</span><em>=</em><span>票据 ¥86,200</span><b class="check">✓</b></div>
          <div class="cmp-row r3 diff-row"><span>系统 ¥52,900</span><em>≠</em><span>票据 ¥52,860</span><b class="check">✓</b></div>
        </div>`;
    case "shield": // 风险与交付：护盾 + 进度环
      return `
        <div class="scr scr--shield">
          <div class="ring-wrap">
            <svg viewBox="0 0 60 60">
              <circle class="ring-bg" cx="30" cy="30" r="25" fill="none" stroke-width="6"/>
              <circle class="ring-value" cx="30" cy="30" r="25" fill="none" stroke-width="6"/>
            </svg>
            <div class="ring-label">交付</div>
          </div>
          <div class="shield-icon">✓</div>
          <div class="scr-note">风险评估通过</div>
        </div>`;
    default:
      return "";
  }
}

/* ============ 工位 ============ */
function stationHTML(station, meta, accent) {
  return `
    <div class="station">
      <span class="station-tag">${station.name}</span>
      <span class="station-chip"><i></i><span class="sc-text">待处理</span></span>
      <div class="scene">
        <div class="monitor">
          <div class="screen">${screenHTML(meta.screen)}</div>
          <div class="stand"></div>
          <div class="stand-base"></div>
        </div>
        <div class="cat-wrap">${catSVG(accent)}</div>
      </div>
      <div class="keyboard"></div>
      <div class="desk-bar"></div>
      <span class="spark s1">✦</span><span class="spark s2">✦</span><span class="spark s3">✦</span>
    </div>`;
}

/* ============ 流向连接线 ============ */
function flowHTML() {
  return `
    <div class="flow" data-on="0">
      <div class="flow-line"></div>
      <div class="flow-dots"><i></i><i></i><i></i></div>
      <svg viewBox="0 0 24 24" class="ic flow-arrow"><path d="M9 6l6 6-6 6"/></svg>
    </div>`;
}

/* ============ 渲染整条流水线 ============ */
let stageEls = [];
let flowEls = [];

function renderPipeline(modules) {
  const pipeline = document.getElementById("pipeline");
  const html = modules.map((m, i) => {
    const meta = STAGE_META[m.id] || { screen: "chat" };
    return `
      ${i > 0 ? flowHTML() : ""}
      <section class="stage" data-accent="${m.accent}" data-state="idle">
        <div class="stage-head">
          <span class="stage-no">${i + 1}</span>
          <span class="stage-title">${m.name}</span>
          <span class="stage-chip">待处理</span>
        </div>
        <div class="task-chip"><span class="tc-dot"></span><span class="tc-text"></span></div>
        <div class="stations">
          ${m.stations.map((s) => stationHTML(s, meta, m.accent)).join("")}
        </div>
        <div class="stage-progress"><div class="sp-fill"></div></div>
      </section>`;
  }).join("");
  pipeline.innerHTML = html;
  stageEls = Array.from(pipeline.querySelectorAll(".stage"));
  flowEls = Array.from(pipeline.querySelectorAll(".flow"));
}

/* ============ 模块状态机 ============ */
function setStage(i, state, taskId) {
  const el = stageEls[i];
  if (!el) return;
  el.dataset.state = state;

  const chip = el.querySelector(".stage-chip");
  chip.textContent = state === "active" ? "处理中" : state === "done" ? "已完成" : "待处理";

  const scTexts = el.querySelectorAll(".sc-text");
  scTexts.forEach((t) => {
    t.textContent = state === "active" ? "工作中"
      : state === "done" ? "已完成" : "待处理";
  });

  if (taskId) {
    const tc = el.querySelector(".tc-text");
    if (tc) tc.textContent = `任务 ${taskId} · ${state === "done" ? "已办结" : "处理中"}`;
  }

  // 模块点亮时，通往下一模块的连接线开始流动
  if (i < flowEls.length) {
    flowEls[i].dataset.on = state === "idle" ? "0" : "1";
    flowEls[i].style.setProperty("--accent", `var(--${el.dataset.accent === "amber" ? "amber" : el.dataset.accent})`);
  }
}

function resetStages() {
  stageEls.forEach((_, i) => setStage(i, "idle"));
  flowEls.forEach((f) => (f.dataset.on = "0"));
}

/* ============ 消息流 / 统计 / 提示 ============ */
function log(text, color) {
  const box = document.getElementById("ticker-items");
  const item = document.createElement("span");
  item.className = "tk";
  item.innerHTML = `<i class="dot ${color || "blue"}"></i>${text} <em>刚刚</em>`;
  box.prepend(item);
  while (box.children.length > 6) box.removeChild(box.lastChild);
}

function bumpStats(delta) {
  const totalEl = document.getElementById("stat-total");
  const procEl = document.getElementById("stat-processing");
  const delivEl = document.getElementById("stat-delivered");
  totalEl.textContent = Number(totalEl.textContent) + (delta.total || 0);
  procEl.textContent = Math.max(0, Number(procEl.textContent) + (delta.processing || 0));
  delivEl.textContent = Number(delivEl.textContent) + (delta.delivered || 0);
}

function setHint(text) {
  document.getElementById("task-hint").textContent = text;
}

function toast(text) {
  const el = document.getElementById("toast");
  el.textContent = text;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 4500);
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

/* ============ 任务流转主流程 ============
 * 客户接待 → 票据处理 → 数据核对 → 风险与交付
 */
let running = false;

async function runTask(requirement) {
  if (running) return;
  running = true;

  const btn = document.getElementById("task-submit");
  btn.disabled = true;

  const task = await API.submitTask(requirement);
  const id = "#" + task.id;

  resetStages();
  bumpStats({ total: 1, processing: 1 });
  log(`任务 ${id}｜客户需求已接收：${requirement}`, "blue");

  for (let i = 0; i < stageEls.length; i++) {
    const key = Object.keys(STAGE_META)[i];
    const meta = STAGE_META[key];
    const name = stageEls[i].querySelector(".stage-title").textContent;

    setStage(i, "active", id);
    setHint(`任务 ${id} 正在「${name}」处理 · ${meta.working}…`);
    await wait(3400);

    setStage(i, "done", id);
    log(`任务 ${id}｜${meta.doneLog}`, meta.logColor);
    await wait(450);
  }

  bumpStats({ processing: -1, delivered: 1 });
  setHint("任务将依次流经：客户接待 → 票据处理 → 数据核对 → 风险与交付");
  toast(`任务 ${id} 已交付 ✅ ${requirement}`);

  btn.disabled = false;
  running = false;
}

/* ============ 启动 ============ */
async function init() {
  const [overview, messages, alerts, groups] = await Promise.all([
    API.getOverview(),
    API.getMessages(20),
    API.getAlerts(),
    API.getGroups(),
  ]);

  // 顶部统计
  document.getElementById("stat-total").textContent = overview.totalTasks;
  document.getElementById("stat-processing").textContent = overview.processing;
  document.getElementById("stat-delivered").textContent = overview.delivered;
  document.getElementById("stat-latency").textContent =
    overview.avgCycleMinutes == null ? "—" : overview.avgCycleMinutes + "min";

  // 消息条
  const msgBox = document.getElementById("ticker-items");
  messages.list.forEach((m) => {
    const mins = Math.floor((Date.now() - new Date(m.occurredAt).getTime()) / 60000);
    const label = mins < 60 ? `${mins}分钟前` : `${Math.floor(mins / 60)}小时前`;
    const item = document.createElement("span");
    item.className = "tk";
    item.innerHTML = `<i class="dot ${m.level}"></i>${m.text} <em>${label}</em>`;
    msgBox.prepend(item);
  });

  // 流水线
  renderPipeline(groups.list);

  // 下发任务
  const input = document.getElementById("task-input");
  document.getElementById("task-submit").addEventListener("click", () => {
    runTask(input.value.trim() || "未命名客户需求");
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") runTask(input.value.trim() || "未命名客户需求");
  });

  // 自动演示：页面打开后自动跑一遍完整流程，之后循环
  setTimeout(() => runTask(input.value.trim() || "未命名客户需求"), 1400);
  setInterval(() => {
    if (!running) runTask(input.value.trim() || "未命名客户需求");
  }, 26000);
}

/* ============ 实时时钟 ============ */
function tick() {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  document.getElementById("clock").textContent =
    `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
}

init();
tick();
setInterval(tick, 1000);
