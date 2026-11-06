/* ============ 仪表盘 · 渲染引擎 ============
 * 数据来自 js/api.js（window.API.getDashboard）：
 *   后端就绪 → 接口数据；后端未就绪 → 内置 Mock。
 * 契约见 api/接口文档.md
 */

const ACCENTS = {
  blue:  "#3b82f6",
  amber: "#f59e0b",
  teal:  "#14b8a6",
  green: "#22c55e",
  red:   "#ef4444",
  gray:  "#9ca3af",
};

/* ============ 小猫吉祥物（趋势图角落） ============ */
function mascotSVG() {
  return `
  <svg viewBox="0 0 120 100">
    <path d="M28 40 L22 8 L52 28 Z" fill="#F6B26B"/>
    <path d="M92 40 L98 8 L68 28 Z" fill="#F6B26B"/>
    <path d="M31 37 L27 16 L48 30 Z" fill="#f2a2a2"/>
    <path d="M89 37 L93 16 L72 30 Z" fill="#f2a2a2"/>
    <ellipse cx="60" cy="52" rx="38" ry="33" fill="#F6B26B"/>
    <ellipse cx="46" cy="50" rx="6" ry="7.5" fill="#2b2f36"/>
    <ellipse cx="74" cy="50" rx="6" ry="7.5" fill="#2b2f36"/>
    <circle cx="48.2" cy="47" r="2" fill="#fff"/>
    <circle cx="76.2" cy="47" r="2" fill="#fff"/>
    <ellipse cx="34" cy="62" rx="6.5" ry="4" fill="#f79e9e" opacity=".55"/>
    <ellipse cx="86" cy="62" rx="6.5" ry="4" fill="#f79e9e" opacity=".55"/>
    <ellipse cx="60" cy="64" rx="14" ry="9" fill="#FFE9CE"/>
    <path d="M60 59 l4 3 -4 3.5 -4 -3.5 z" fill="#e58a8a"/>
    <path d="M60 65.5 q-4 4 -7 1 M60 65.5 q4 4 7 1" stroke="rgba(23,24,28,.35)" stroke-width="2" fill="none" stroke-linecap="round"/>
  </svg>`;
}

/* ============ KPI 卡片 ============ */
function sparkSVG(values, color) {
  const w = 72, h = 30, max = Math.max(...values), min = Math.min(...values);
  const pts = values.map((v, i) => {
    const x = (i * w) / (values.length - 1);
    const y = h - 3 - ((v - min) / Math.max(max - min, 1)) * (h - 8);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return `
  <svg class="kpi-spark" viewBox="0 0 ${w} ${h}">
    <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`;
}

function renderKPIs(kpis) {
  document.getElementById("kpi-row").innerHTML = kpis.map((k) => `
    <div class="kpi-card" style="--accent:${ACCENTS[k.color] || ACCENTS.blue}">
      <div class="kpi-label"><span class="kpi-dot"></span>${k.label}</div>
      <div class="kpi-value">${k.value}<small>${k.unit || ""}</small></div>
      <div class="kpi-delta ${k.deltaType}">${k.delta} <span class="vs">${k.vs}</span></div>
      ${sparkSVG(k.spark, ACCENTS[k.color] || ACCENTS.blue)}
    </div>
  `).join("");
}

/* ============ 任务流转趋势（双折线 + 面积） ============ */
function renderTrend(trend) {
  const w = 640, h = 210, pad = 34;
  const all = [...trend.received, ...trend.delivered];
  const max = Math.max(...all) * 1.18;
  const x = (i) => pad + (i * (w - pad * 2)) / (trend.labels.length - 1);
  const y = (v) => h - pad - (v / max) * (h - pad * 2);

  const lineOf = (arr) => arr.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const areaOf = (arr) => `${lineOf(arr)} L${x(arr.length - 1).toFixed(1)},${h - pad} L${x(0).toFixed(1)},${h - pad} Z`;

  const grid = [0, 1, 2, 3].map((g) => {
    const gy = pad + ((h - pad * 2) * g) / 3;
    return `<line x1="${pad}" y1="${gy}" x2="${w - pad}" y2="${gy}" stroke="#eef0f3" stroke-width="1"/>`;
  }).join("");

  const labels = trend.labels.map((l, i) =>
    `<text x="${x(i)}" y="${h - 10}" font-size="10" fill="#8a8f98" text-anchor="middle">${l}</text>`
  ).join("");

  const dots = (arr, color) => arr.map((v, i) =>
    `<circle cx="${x(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="3.4" fill="#fff" stroke="${color}" stroke-width="2"/>`
  ).join("");

  document.getElementById("trend-chart").innerHTML = `
  <svg viewBox="0 0 ${w} ${h}">
    <defs>
      <linearGradient id="gBlue" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="${ACCENTS.blue}" stop-opacity=".26"/>
        <stop offset="1" stop-color="${ACCENTS.blue}" stop-opacity="0"/>
      </linearGradient>
      <linearGradient id="gGreen" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="${ACCENTS.green}" stop-opacity=".22"/>
        <stop offset="1" stop-color="${ACCENTS.green}" stop-opacity="0"/>
      </linearGradient>
    </defs>
    ${grid}
    <path d="${areaOf(trend.received)}" fill="url(#gBlue)"/>
    <path d="${areaOf(trend.delivered)}" fill="url(#gGreen)"/>
    <path d="${lineOf(trend.received)}" fill="none" stroke="${ACCENTS.blue}" stroke-width="2.4" stroke-linecap="round"/>
    <path d="${lineOf(trend.delivered)}" fill="none" stroke="${ACCENTS.green}" stroke-width="2.4" stroke-linecap="round"/>
    ${dots(trend.received, ACCENTS.blue)}
    ${dots(trend.delivered, ACCENTS.green)}
    ${labels}
  </svg>`;
}

/* ============ 任务状态分布（环形图） ============ */
function renderDonut(status) {
  const total = status.done + status.doing + status.todo + status.err || 1;
  const segs = [
    { v: status.done,  c: ACCENTS.green, name: "已交付" },
    { v: status.doing, c: ACCENTS.amber, name: "处理中" },
    { v: status.todo,  c: ACCENTS.gray,  name: "待处理" },
    { v: status.err,   c: ACCENTS.red,   name: "异常"   },
  ];

  const R = 54, C = 2 * Math.PI * R;
  let offset = 0;
  const circles = segs.map((s) => {
    const len = (s.v / total) * C;
    const el = `<circle cx="74" cy="74" r="${R}" fill="none"
      stroke="${s.c}" stroke-width="18"
      stroke-dasharray="${len.toFixed(2)} ${(C - len).toFixed(2)}"
      stroke-dashoffset="${(-offset).toFixed(2)}"/>`;
    offset += len;
    return el;
  }).join("");

  document.getElementById("donut-chart").innerHTML = `
  <svg viewBox="0 0 148 148" style="transform:rotate(-90deg)">
    <circle cx="74" cy="74" r="${R}" fill="none" stroke="#f0f1f3" stroke-width="18"/>
    ${circles}
  </svg>
  <div class="donut-center"><b>${total}</b><span>任务总数</span></div>`;

  document.getElementById("donut-legend").innerHTML = segs.map((s) => `
    <div class="dl-row">
      <i style="background:${s.c}"></i>
      <span>${s.name}</span>
      <b>${s.v} · ${Math.round((s.v / total) * 100)}%</b>
    </div>
  `).join("");
}

/* ============ 各模块处理量（柱状图） ============ */
function renderBars(modules) {
  const max = Math.max(...modules.map((m) => m.count));
  document.getElementById("bar-chart").innerHTML = `
  <div class="bars">
    ${modules.map((m, i) => `
      <div class="bar-col">
        <div class="bar-val">${m.count}</div>
        <div class="bar" style="--accent:${ACCENTS[m.accent]};--h:${Math.round((m.count / max) * 118)}px;animation-delay:${i * 0.12}s"></div>
        <div class="bar-name">${m.name}</div>
      </div>
    `).join("")}
  </div>`;
}

/* ============ 各模块平均处理时长（横条） ============ */
function renderHBars(modules) {
  const max = Math.max(...modules.map((m) => m.avgMinutes));
  document.getElementById("hbar-chart").innerHTML = `
  <div class="hbars">
    ${modules.map((m, i) => `
      <div class="hb-row" style="--accent:${ACCENTS[m.accent]}">
        <div class="hb-top"><span>${m.name}</span><b>${m.avgMinutes} 分钟</b></div>
        <div class="hb-track">
          <div class="hb-fill" style="--w:${Math.round((m.avgMinutes / max) * 100)}%;animation-delay:${i * 0.12}s"></div>
        </div>
      </div>
    `).join("")}
  </div>`;
}

/* ============ 核验结果 ============ */
function renderVerify(verify) {
  document.getElementById("verify-chart").innerHTML = `
  <div class="verify-list">
    <div class="vr-row vr-ok"><div class="vr-ic">✓</div><div>已核对 <small>票款一致</small></div><b>${verify.checked}</b></div>
    <div class="vr-row vr-warn"><div class="vr-ic">?</div><div>待说明 <small>需补凭证</small></div><b>${verify.pending}</b></div>
    <div class="vr-row vr-bad"><div class="vr-ic">!</div><div>异常 <small>待人工介入</small></div><b>${verify.failed}</b></div>
  </div>`;
}

/* ============ 最近任务表格 ============ */
const STATUS_TEXT = { done: "已交付", doing: "处理中", todo: "待处理", err: "异常" };

function renderTable(recent) {
  document.getElementById("task-tbody").innerHTML = recent.map((t) => `
    <tr>
      <td class="task-id">#${t.id}</td>
      <td class="task-req" title="${t.requirement}">${t.requirement}</td>
      <td>${t.module}</td>
      <td><span class="tst ${t.status}"><i></i>${STATUS_TEXT[t.status]}</span></td>
      <td>${t.duration}</td>
      <td class="task-time">${t.createdAt}</td>
    </tr>
  `).join("");
}

/* ============ 筛选切换 ============ */
function bindFilters() {
  const chips = Array.from(document.querySelectorAll(".chip"));
  chips.forEach((chip) => {
    chip.addEventListener("click", () => {
      chips.forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      loadDashboard(chip.dataset.range);
    });
  });
}

/* ============ 加载 ============ */
async function loadDashboard(range) {
  const dash = await API.getDashboard(range);
  renderKPIs(dash.kpis);
  renderTrend(dash.trend);
  renderDonut(dash.status);
  renderBars(dash.modules);
  renderHBars(dash.modules);
  renderVerify(dash.verify);
  renderTable(dash.recent);

  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  document.getElementById("dash-sync").textContent =
    `数据更新于 ${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

/* ============ 顶部统计 + 时钟 ============ */
async function loadOverview() {
  const ov = await API.getOverview();
  document.getElementById("stat-total").textContent = ov.totalTasks;
  document.getElementById("stat-processing").textContent = ov.processing;
  document.getElementById("stat-delivered").textContent = ov.delivered;
  document.getElementById("stat-latency").textContent =
    ov.avgCycleMinutes == null ? "—" : ov.avgCycleMinutes + "min";
}

function tick() {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  document.getElementById("clock").textContent =
    `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
}

/* ============ 启动 ============ */
document.getElementById("mascot").innerHTML = mascotSVG();
bindFilters();
loadOverview();
loadDashboard("7d");
tick();
setInterval(tick, 1000);
