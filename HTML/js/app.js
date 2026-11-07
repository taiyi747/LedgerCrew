/* ============================================================
   渲染引擎：顶栏 / 消息条 / 作战室 / 工位卡 / 抽屉 / 仪表盘 / 设置
   视图由 body[data-page] = warroom | dashboard | settings 决定
   ============================================================ */

/* ---------- 图标（16×16 · stroke 1.5 · lucide 风格） ---------- */
const ICONS = {
  clock: '<svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
  wifi: '<svg class="ic" viewBox="0 0 24 24"><path d="M2 8.5a15 15 0 0 1 20 0"/><path d="M5 12a11 11 0 0 1 14 0"/><path d="M8.5 15.5a6 6 0 0 1 7 0"/><circle cx="12" cy="19" r="1.2"/></svg>',
  lock: '<svg class="ic" viewBox="0 0 24 24"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>',
  gear: '<svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1"/></svg>',
  grid: '<svg class="ic" viewBox="0 0 24 24"><rect x="4" y="4" width="6" height="6" rx="1"/><rect x="14" y="4" width="6" height="6" rx="1"/><rect x="4" y="14" width="6" height="6" rx="1"/><rect x="14" y="14" width="6" height="6" rx="1"/></svg>',
  chart: '<svg class="ic" viewBox="0 0 24 24"><path d="M4 20V10M10 20V4M16 20v-8M22 20H2"/></svg>',
  refresh: '<svg class="ic" viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 4v5h-5"/></svg>',
  heat: '<svg class="ic" viewBox="0 0 24 24"><path d="M12 22c3.9 0 6-2.5 6-6 0-4-6-10-6-10S6 12 6 16c0 3.5 2.1 6 6 6z"/><circle cx="12" cy="16" r="2.4"/></svg>',
  anchor: '<svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="5" r="2.5"/><path d="M12 7.5V22M5 13H2a10 10 0 0 0 20 0h-3"/></svg>',
  spark: '<svg class="ic" viewBox="0 0 24 24"><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 16l.9 2.6L22.5 19.5l-2.6.9L19 23l-.9-2.6-2.6-.9 2.6-.9z"/></svg>',
  close: '<svg class="ic" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  sun: '<svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1"/></svg>',
  moon: '<svg class="ic" viewBox="0 0 24 24"><path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/></svg>',
  lockOn: '<svg class="ic" viewBox="0 0 24 24"><rect x="5" y="11" width="14" height="9" rx="2" fill="currentColor" stroke="none"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>',
  logomark: '<svg class="ic" viewBox="0 0 24 24" style="width:20px;height:20px"><rect x="1" y="1" width="18" height="18" rx="5"/><path d="M5.5 12.5v-5M10 12.5v-8M14.5 12.5v-3"/></svg>',
};

/* ---------- 工位插画共用渐变 defs（色值走 --art-* 变量，跟随昼夜切换） ---------- */
const DEFS_SVG = `
<svg width="0" height="0" style="position:absolute" aria-hidden="true">
  <defs>
    <linearGradient id="d-screen" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="var(--art-screen-a)"/><stop offset="1" stop-color="var(--art-screen-b)"/>
    </linearGradient>
    <linearGradient id="d-glass" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="var(--art-glass)" stop-opacity=".10"/><stop offset="1" stop-color="var(--art-glass)" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="d-desk-top" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="var(--art-desk-a)"/><stop offset="1" stop-color="var(--art-desk-b)"/>
    </linearGradient>
    <linearGradient id="d-desk-edge" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="var(--art-desk-edge-a)"/><stop offset="1" stop-color="var(--art-desk-edge-b)"/>
    </linearGradient>
    <linearGradient id="d-chair" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="var(--art-chair-a)"/><stop offset="1" stop-color="var(--art-chair-b)"/>
    </linearGradient>
    <radialGradient id="d-shadow" cx=".5" cy=".5" r=".5">
      <stop offset="0" stop-color="#000" stop-opacity=".14"/><stop offset="1" stop-color="#000" stop-opacity="0"/>
    </radialGradient>
  </defs>
</svg>`;

/* ---------- 工位 SVG（viewBox 176×126，坐标照规格书） ----------
   working / urgent 时屏幕跑「工作流程」动画（工件过站），
   空闲 / 休眠时是静止的四条内容线。 */
function deskSVG(status) {
  const color = STATUS_META[status].color;
  const busy = status === "working" || status === "urgent";
  // 三条进度条长度随机（屏宽 82 单位，取 30~66 —— 都在 1/3 以上）
  const barW = [0, 0, 0].map(() => 30 + Math.round(Math.random() * 36));
  return `
  <svg class="desk-art" viewBox="0 0 176 126" aria-hidden="true">
    <!-- 玻璃屏 -->
    <rect x="42" y="2" width="92" height="44" rx="5" fill="url(#d-screen)"/>
    <rect x="47" y="6" width="82" height="36" rx="3" fill="var(--art-screen)"/>
    <path d="M47 6h34L55 42h-8z" fill="url(#d-glass)"/>
    ${busy ? `
    <!-- 工作流程：三条进度条依次填满，每满一条工件下移一站，以此类推 -->
    <rect x="65" y="10.5" width="${barW[0]}" height="3" rx="1.5" fill="var(--art-line)"/>
    <rect class="bar-fill s1" x="65" y="10.5" width="${barW[0]}" height="3" rx="1.5" fill="${color}"/>
    <rect x="65" y="22.5" width="${barW[1]}" height="3" rx="1.5" fill="var(--art-line)"/>
    <rect class="bar-fill s2" x="65" y="22.5" width="${barW[1]}" height="3" rx="1.5" fill="${color}"/>
    <rect x="65" y="34.5" width="${barW[2]}" height="3" rx="1.5" fill="var(--art-line)"/>
    <rect class="bar-fill s3" x="65" y="34.5" width="${barW[2]}" height="3" rx="1.5" fill="${color}"/>
    <circle class="station s1" cx="55" cy="12" r="3.4" fill="var(--art-station)"/>
    <circle class="station s2" cx="55" cy="24" r="3.4" fill="var(--art-station)"/>
    <circle class="station s3" cx="55" cy="36" r="3.4" fill="var(--art-station)"/>
    <rect class="workpiece" x="50" y="7" width="10" height="10" rx="3" fill="${color}"/>
    ` : `
    <rect x="53" y="11" width="36" height="2.4" rx="1.2" fill="var(--art-line)"/>
    <rect x="53" y="18" width="54" height="2.4" rx="1.2" fill="var(--art-line)"/>
    <rect x="53" y="25" width="25" height="2.4" rx="1.2" fill="var(--art-line)"/>
    <rect x="53" y="32" width="42" height="2.4" rx="1.2" fill="var(--art-line)"/>
    `}
    <!-- 桌板：比原版略拉长（12 → 18px） -->
    <rect x="14" y="46" width="148" height="18" rx="2" fill="url(#d-desk-top)" stroke="var(--art-stroke)"/>
    <rect x="14" y="63" width="148" height="5" fill="url(#d-desk-edge)"/>
    <!-- 桌角状态灯 -->
    <circle cx="25" cy="54" r="3.6" fill="${color}"/>
    <path d="M22.6 52.4a3.6 3.6 0 0 1 2.2-1.7" stroke="var(--art-hi)" stroke-opacity=".55" stroke-width="1.2" fill="none" stroke-linecap="round"/>
    <!-- 桌腿 -->
    <rect x="28" y="68" width="8" height="26" fill="var(--art-desk-edge-a)"/>
    <rect x="140" y="68" width="8" height="26" fill="var(--art-desk-edge-a)"/>
    <!-- 投影 -->
    <ellipse cx="88" cy="110" rx="62" ry="15" fill="url(#d-shadow)"/>
    <!-- 员工剪影：画在座椅**之前**，所以浅色椅背盖住深色身体，
         只露脖子以上的头 —— 看着就是靠在椅子上。
         「往前挪」= 朝桌面方向（图面上为向上）移，露出的头从 9px 增到 12px；
         耳朵收到 r8，头顶距屏幕仍有 1px，避免两块深色叠在一起。 -->
    <g fill="var(--art-figure)">
      <circle cx="74" cy="55" r="8"/>
      <circle cx="102" cy="55" r="8"/>
      <circle cx="88" cy="68" r="20"/>
      <path d="M62 95v-6a26 26 0 0 1 52 0v6z"/>
    </g>
    <path d="M76 61a14 14 0 0 1 22-4" stroke="var(--art-hi)" stroke-opacity=".1" stroke-width="3" fill="none" stroke-linecap="round"/>

    <!-- 座椅（盖在员工身体之上） -->
    <rect x="52" y="60" width="72" height="38" rx="15" fill="url(#d-chair)"/>
    <rect x="34" y="76" width="20" height="32" rx="10" fill="url(#d-chair)"/>
    <rect x="122" y="76" width="20" height="32" rx="10" fill="url(#d-chair)"/>
  </svg>`;
}

/* ---------- 连接状态浮层（顶栏 WiFi 按钮） ---------- */
function netPopover() {
  const ov = overview();
  return `
  <div class="net-pop" id="net-pop" hidden>
    <div class="net-row"><span class="k">${t("连接")}</span><span class="v"><i class="lamp ${state.apiReady ? "lamp-working" : "lamp-idle"}"></i>${state.apiReady ? t("已连上后端") : t("内置演示数据")}</span></div>
    <div class="net-row"><span class="k">API Base</span><span class="v mono">${API_BASE}</span></div>
    <div class="net-row"><span class="k">${t("延迟")}</span><span class="v mono">${state.latencyMs}ms</span></div>
    <div class="net-row"><span class="k">${t("在线工位")}</span><span class="v mono">${ov.online}/${ov.agents}</span></div>
    <div class="net-row"><span class="k">${t("紧急")}</span><span class="v mono">${ov.urgent}</span></div>
    <div class="net-row"><span class="k">${t("消息")}</span><span class="v mono">${ov.totalMessages}</span></div>
  </div>`;
}

/* ---------- 顶栏 ---------- */
function renderTopbar() {
  const ov = overview();
  document.getElementById("topbar").innerHTML = `
    <div class="topbar-left">
      <span class="lang-switch" role="group" aria-label="${t("语言")}">
        <button class="lang-opt${state.lang === "zh" ? " on" : ""}" onclick="setLang('zh')" lang="zh-CN">中文</button>
        <button class="lang-opt${state.lang === "en" ? " on" : ""}" onclick="setLang('en')" lang="en">英文</button>
      </span>
      <span class="clock">${ICONS.clock}<span id="clock">${clockTime(new Date())}</span></span>
      <span class="demo-chip"><i class="lamp lamp-working"></i>${t("演示模式")}</span>
    </div>
    <div class="topbar-center">
      ${ICONS.logomark}
      <span class="t-title">${t("AIWHO WEBHOOK 中台")}</span>
    </div>
    <div class="topbar-right">
      <div class="stat-inline"><span class="v">${ov.totalMessages}</span><span class="l">${t("消息")}</span></div>
      <div class="v-sep"></div>
      <div class="stat-inline"><span class="v ${ov.urgent > 0 ? "neg" : ""}">${ov.urgent}</span><span class="l">${t("紧急")}</span></div>
      <div class="v-sep"></div>
      <div class="stat-inline"><span class="v">${ov.online}/${ov.agents}</span><span class="l">${t("在线工位")}</span></div>
      <div class="v-sep"></div>
      <div class="stat-inline"><span class="v">${ov.latencyMs}ms</span><span class="l">${t("响应")}</span></div>
      <button class="icon-btn" id="t-net" title="${t("连接状态")}" aria-label="${t("连接状态")}" aria-expanded="false">${ICONS.wifi}</button>
      <button class="icon-btn" id="t-lock" title="${state.uiLocked ? t("解除锁定") : t("锁定界面")}" aria-label="${state.uiLocked ? t("解除锁定") : t("锁定界面")}" aria-pressed="${state.uiLocked}">${state.uiLocked ? ICONS.lockOn : ICONS.lock}</button>
      <button class="icon-btn" id="t-theme" title="${state.theme === "dark" ? t("切换到浅色") : t("切换到深色")}" aria-label="${state.theme === "dark" ? t("切换到浅色") : t("切换到深色")}">${state.theme === "dark" ? ICONS.moon : ICONS.sun}</button>
    </div>
    ${netPopover()}`;
}

/* ---------- 消息条 ---------- */
function renderTicker() {
  const items = state.events.slice(0, 6);
  const critical = state.events.filter((e) => e.level === "critical").length;
  const body = items.length
    ? items.map((e) => `
      <span class="ticker-item" title="${esc(t(e.detail))}">
        <i class="lamp ${LEVEL_META[e.level].lamp}"></i>
        <span class="title">${esc(t(e.title))}</span>
        <span class="t-meta">${relativeTime(e.ts)}</span>
      </span>`).join("")
    : `<span class="ticker-empty">${t("暂无消息")}</span>`;

  document.getElementById("ticker").innerHTML = `
    <div class="ticker-items">${body}</div>
    <div class="ticker-right">
      ${critical > 0
        ? `<i class="lamp lamp-urgent"></i><span class="neg">${t("{n} 条待处理", { n: critical })}</span>`
        : `<i class="lamp lamp-dormant"></i><span class="t-meta">${t("无")}</span>`}
    </div>`;
}

/* ---------- 作战室 ---------- */
function renderWarroom() {
  const html = state.workspaces.map((w, i) => {
    const agents = state.agents.filter((a) => a.workspace === w.key);
    const online = agents.filter((a) => a.status !== "dormant").length;
    const urgent = agents.filter((a) => a.status === "urgent").length;
    // 模块灯：只在「需要看」时亮（有紧急工位），否则留一颗安静的钢灰点
    const mod = urgent > 0 ? "urgent" : "dormant";
    return `
    <section class="panel enter" style="animation-delay:${Math.min(i, 5) * 50}ms">
      <div class="panel-head">
        <i class="lamp ${STATUS_META[mod].lamp}"></i>
        <span class="t-title">${esc(t(w.name))}</span>
        <span class="grow"></span>
        <span class="t-meta">${online}/${agents.length} ${t("在线")}</span>
        ${urgent > 0 ? `<span class="t-meta" style="color:var(--negative)">${t("{n} 项待处理", { n: urgent })}</span>` : ""}
      </div>
      <div class="deck deck-floor">
        ${agents.map(deskCard).join("")}
      </div>
    </section>`;
  }).join("");
  document.getElementById("view").innerHTML =
    `<div class="grid3 ${state.workspaces.length <= 4 ? "grid2" : ""}">${html}</div>`;
}

function deskCard(a) {
  const meta = STATUS_META[a.status];
  return `
  <div class="desk ${state.showLoad ? "show-load" : ""}" role="button" tabindex="0"
       data-agent="${a.id}" aria-label="${esc(t(a.name))} · ${statusLabel(a.status)}">
    <div class="desk-top">
      ${a.queue > 0 ? `<span class="queue-badge">${a.queue}</span>` : ""}
      <span class="nameplate"><span class="name" title="${esc(t(a.name))}">${esc(t(a.name))}</span></span>
    </div>
    <div class="desk-art-wrap">
      ${deskSVG(a.status)}
      <span class="desk-pill" style="background:${meta.pill}">${statusLabel(a.status)}</span>
    </div>
    <div class="loadbar"><i style="width:${Math.max(a.load, 3)}%"></i></div>
  </div>`;
}

/* ---------- 抽屉 ---------- */
let drawerAgentId = null;

function renderDrawer() {
  const scrim = document.getElementById("scrim");
  const drawer = document.getElementById("drawer");
  const a = state.agents.find((x) => x.id === drawerAgentId);
  if (!a) {
    scrim.classList.remove("open");
    drawer.classList.remove("open");
    return;
  }
  const meta = STATUS_META[a.status];
  const ws = state.workspaces.find((w) => w.key === a.workspace);
  const calls = state.calls[a.id] || [];

  drawer.innerHTML = `
    <div class="drawer-head">
      <i class="lamp lamp-lg ${meta.lamp}"></i>
      <div>
        <div class="t-title">${esc(t(a.name))}</div>
        <div class="t-meta">${statusLabel(a.status)}</div>
        <div class="t-meta">${esc(t(ws.name))} · ${esc(a.id)}</div>
      </div>
      <button class="icon-btn close" aria-label="${t("关闭")}" title="${t("关闭")}" onclick="closeDrawer()">${ICONS.close}</button>
    </div>
    <div class="drawer-body">
      <div class="drawer-section">
        <div class="fig-row">
          <div class="fig-item"><span class="t-figure">${a.load}%</span><span class="t-meta">${t("负载")}</span></div>
          <div class="fig-item"><span class="t-figure">${a.queue}</span><span class="t-meta">${t("待处理")}</span></div>
        </div>
      </div>
      <div class="drawer-section">
        <div class="section-title">${t("当前任务")}</div>
        <div class="t-body">${a.currentTask ? esc(t(a.currentTask)) : t("暂无任务")}</div>
      </div>
      <div class="drawer-section">
        <div class="section-title">${t("工作轨迹")}</div>
        <div class="trace">
          ${(() => {
            const steps = (state.traces[a.id] || []).slice(-8);
            return steps.length ? steps.map((s, i) => `
          <div class="trace-step">
            <div class="trace-meta">${t("第 {n} 轮", { n: i + 1 })} · ${relativeTime(s.ts)}</div>
            <div class="trace-say">${esc(t(s.say, s.sayVars))}</div>
            <div class="trace-tool st-${esc(s.status || "ok")}">
              <div class="tool-row">
                <span class="tool-name">${esc(s.tool)}</span>
                ${s.input ? `<span class="tool-args">${esc(s.input)}</span>` : ""}
              </div>
              <div class="tool-out">${esc(t(s.output, s.outputVars))}</div>
            </div>
          </div>`).join("") : `<div class="t-meta">${t("暂无轨迹")}</div>`;
          })()}
        </div>
      </div>
      <div class="drawer-section">
        <div class="section-title">${t("遥测")}</div>
        ${(() => {
          const entries = Object.entries(a.metrics || {});
          return entries.length ? entries.map(([k, v]) => {
            const m = metricMeta(k);
            return `
          <div class="kv-row"><span class="t-caption">${esc(m.label)}</span><span class="t-num">${esc(v)}${m.unit ? ` <span class="t-meta">${esc(m.unit)}</span>` : ""}</span></div>`;
          }).join("") : `<div class="t-meta">${t("暂无遥测")}</div>`;
        })()}
      </div>
      <div class="drawer-section">
        <div class="section-title">${t("下发指令")}</div>
        <div class="t-meta">POST ${API_BASE}/workspaces/${a.workspace}/agents/${a.id}/command</div>
        <input class="input" id="cmd-task" placeholder="${t("任务描述，可选")}">
        <div class="btn-grid">
          <button class="btn btn-primary" data-cmd="assign">${cmdLabel("assign")}</button>
          <button class="btn" data-cmd="escalate">${cmdLabel("escalate")}</button>
          <button class="btn" data-cmd="on">${cmdLabel("on")}</button>
          <button class="btn" data-cmd="off">${cmdLabel("off")}</button>
          <button class="btn btn-quiet" data-cmd="reset">${cmdLabel("reset")}</button>
        </div>
      </div>
      <div class="drawer-section">
        <div class="section-title">${t("调用记录")}</div>
        ${calls.length
          ? calls.map((c) => `<div class="t-meta" style="color:${c.ok ? "var(--text-secondary)" : "var(--negative)"}">${esc(callLogText(c))}</div>`).join("")
          : `<div class="t-meta">${t("暂无调用")}</div>`}
      </div>
    </div>`;
  scrim.classList.add("open");
  drawer.classList.add("open");
}

function openDrawer(id) { drawerAgentId = id; renderDrawer(); }
function closeDrawer() { drawerAgentId = null; renderDrawer(); }

/* 调用记录存结构化字段，渲染时才走 t() —— 切语言后历史记录跟着换 */
function callLogText(c) {
  const head = clockTime(new Date(c.ts));
  return c.ok
    ? `${head}  ${t("已下发 {cmd} 至 {name}", { cmd: cmdLabel(c.cmd), name: t(c.name) })}`
    : `${head}  ${c.message}`;
}

async function execCommand(cmd, btn) {
  const a = state.agents.find((x) => x.id === drawerAgentId);
  if (!a) return;
  const input = document.getElementById("cmd-task");
  const task = input ? input.value.trim() : "";
  btn.disabled = true;
  const old = btn.textContent;
  btn.textContent = "…";
  const res = await runCommand(a.id, cmd, task);
  state.calls[a.id] = state.calls[a.id] || [];
  state.calls[a.id].unshift({ ok: res.ok, ts: Date.now(), cmd, name: a.name, message: res.message });
  state.calls[a.id] = state.calls[a.id].slice(0, 5);
  btn.disabled = false;
  btn.textContent = old;
  renderDrawer();
  renderView();
  renderTicker();
  renderTopbar();
}

/* ---------- 仪表盘 ---------- */
function renderDashboard() {
  const ov = overview();
  const critical = ov.urgent;
  const dormant = state.agents.filter((a) => a.status === "dormant").length;

  /* ① 统计卡 */
  const stats = `
  <div class="row4">
    <div class="stat-card">
      <span class="t-meta">${t("消息")}</span>
      <span class="t-figure-lg">${ov.totalMessages}</span>
      <span class="t-meta">${t("+4.2% vs 上一小时")}</span>
    </div>
    <div class="stat-card">
      <span class="t-meta">${t("紧急")}</span>
      <span class="t-figure-lg ${critical > 0 ? "neg" : ""}">${critical}</span>
      <span class="t-meta">${critical > 0 ? t("未处理") : t("无")}</span>
    </div>
    <div class="stat-card">
      <span class="t-meta">${t("在线工位")}</span>
      <span class="t-figure-lg">${ov.online}/${ov.agents}</span>
      <span class="t-meta">${t("{n} 个休眠", { n: dormant })}</span>
    </div>
    <div class="stat-card">
      <span class="t-meta">${t("响应")}</span>
      <span class="t-figure-lg">${ov.latencyMs}ms</span>
      <span class="t-meta">${t("连接正常")}</span>
    </div>
  </div>`;

  /* ② 折线 + 负载排行 */
  const topLoad = [...state.agents].sort((x, y) => y.load - x.load).slice(0, 6);
  const maxLoad = Math.max(...topLoad.map((a) => a.load), 1);
  const row3 = `
  <div class="row3">
    <div class="card">
      <div class="card-title">
        <span class="t-title">${t("消息吞吐")}</span>
        <span class="t-meta card-sub">${t("全部工作区合计 · 最近 2 小时 · 每 5 分钟")}</span>
      </div>
      ${lineChartSVG()}
    </div>
    <div class="card">
      <div class="card-title">
        <span class="t-title">${t("工位负载")}</span>
        <span class="t-meta card-sub">${t("取最高的 6 个工位")}</span>
      </div>
      <div class="barlist">
        ${topLoad.map((a) => `
          <div class="bar-row">
            <span class="label">${esc(t(a.name))}</span>
            <span class="track"><i style="width:${(a.load / maxLoad) * 100}%"></i></span>
            <span class="val">${a.load}%</span>
            <span class="st">${statusLabel(a.status)}</span>
          </div>`).join("")}
      </div>
    </div>
  </div>`;

  /* ③ 状态分布 / 各工作区 / 近期异常 */
  const counts = {};
  STATUS_ORDER.forEach((s) => (counts[s] = state.agents.filter((a) => a.status === s).length));
  const total = state.agents.length;

  const row3b = `
  <div class="row3b">
    <div class="card">
      <div class="card-title"><span class="t-title">${t("状态分布")}</span></div>
      <div class="stack" role="img" aria-label="${t("工位状态分布")}">
        ${STATUS_ORDER.filter((s) => counts[s] > 0)
          .map((s) => `<i style="flex-grow:${counts[s]};background:${STATUS_META[s].color}"></i>`).join("")}
      </div>
      <div class="stack-legend">
        ${STATUS_ORDER.map((s) => `
          <div class="legend-row">
            <i class="lamp ${STATUS_META[s].lamp}"></i>
            <span class="name">${statusLabel(s)}</span>
            <span class="num">${counts[s]}</span>
            <span class="pct">${Math.round((counts[s] / total) * 100)}%</span>
          </div>`).join("")}
      </div>
    </div>
    <div class="card">
      <div class="card-title"><span class="t-title">${t("各工作区")}</span></div>
      <table class="table">
        <thead><tr><th>${t("工作区")}</th><th>${t("吞吐")}</th><th>${t("延迟")}</th></tr></thead>
        <tbody>
          ${state.workspaces.map((w) => `
            <tr>
              <td>${esc(t(w.name))}</td>
              <td>${40 + Math.round(Math.random() * 70)}/min</td>
              <td>${120 + Math.round(Math.random() * 180)}ms</td>
            </tr>`).join("")}
        </tbody>
      </table>
    </div>
    <div class="card">
      <div class="card-title"><span class="t-title">${t("近期异常")}</span></div>
      ${(() => {
        const alerts = state.events.filter((e) => e.level !== "info").slice(0, 8);
        return alerts.length
          ? alerts.map((e) => `
            <div class="alert-row">
              <div class="r1">
                <i class="lamp ${LEVEL_META[e.level].lamp}"></i>
                <span class="title">${esc(t(e.title))}</span>
                <span class="t-meta">${shortTime(e.ts)}</span>
              </div>
              <div class="detail">${esc(t(e.detail))}</div>
            </div>`).join("")
          : `<div class="t-meta">${t("暂无异常")}</div>`;
      })()}
    </div>
  </div>`;

  document.getElementById("view").innerHTML = `<div class="main-inner">${stats}${row3}${row3b}</div>`;
}

function lineChartSVG() {
  const vals = throughputSeries();
  const W = 900, H = 320, PAD = { t: 16, r: 20, b: 26, l: 20 };
  const min = Math.min(...vals), max = Math.max(...vals);
  const y0 = min * 0.82, y1 = max * 1.08;
  const x = (i) => PAD.l + (i * (W - PAD.l - PAD.r)) / (vals.length - 1);
  const y = (v) => PAD.t + (1 - (v - y0) / (y1 - y0)) * (H - PAD.t - PAD.b);
  const line = vals.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");

  const grid = [0, 1, 2, 3, 4].map((g) => {
    const gy = PAD.t + ((H - PAD.t - PAD.b) * g) / 4;
    return `<line x1="${PAD.l}" y1="${gy}" x2="${W - PAD.r}" y2="${gy}" stroke="var(--grid-line)" stroke-opacity=".05"/>`;
  }).join("");

  const endT = Date.now();
  const startT = endT - (vals.length - 1) * 5 * 60000;

  return `
  <svg class="chart-svg" viewBox="0 0 ${W} ${H}">
    ${grid}
    <line x1="${PAD.l}" y1="${H - PAD.b}" x2="${W - PAD.r}" y2="${H - PAD.b}" stroke="var(--grid-line)" stroke-opacity=".12"/>
    <path d="${line}" fill="none" stroke="var(--accent)" stroke-width="2"/>
    <circle cx="${x(vals.length - 1).toFixed(1)}" cy="${y(vals[vals.length - 1]).toFixed(1)}" r="3.5" fill="var(--accent)"/>
    <text x="${PAD.l}" y="${H - 8}" font-size="11" fill="var(--text-muted)">${shortTime(new Date(startT).toISOString())}</text>
    <text x="${W - PAD.r}" y="${H - 8}" font-size="11" fill="var(--text-muted)" text-anchor="end">${shortTime(new Date(endT).toISOString())}</text>
  </svg>`;
}

/* ---------- 设置页 ---------- */
function renderSettings() {
  const srcChip = state.apiReady
    ? '<span class="chip"><i class="lamp lamp-working"></i>/api/v1</span>'
    : `<span class="chip"><i class="lamp lamp-idle"></i>${t("内置数据")}</span>`;
  const srcText = state.apiReady ? t("已连上后端，状态会写进中台") : t("内置演示数据，双击也能跑");
  const demoTitle = t("票面异常 · 金额不符 2 笔");
  const demoDetail = t("INV-233 与流水差 ¥40，INV-241 缺凭证");

  const webhookForm = `
  <div class="card" id="webhook">
    <div class="card-title"><span class="t-title">${t("回调调试")}</span></div>
    <div class="t-caption">${t("向消息流写入一条回调，会立刻出现在顶栏和作战室")}</div>
    <div class="form-grid">
      <label class="form-label"><span>${t("目标工作区")}</span>
        <select class="input" id="w-workspace">
          ${state.workspaces.map((w) => `<option value="${w.key}" ${w.key === "ticketing" ? "selected" : ""}>${esc(t(w.name))} · ${w.key}</option>`).join("")}
        </select>
      </label>
      <label class="form-label"><span>${t("等级")}</span>
        <select class="input" id="w-level">
          <option value="info">info</option>
          <option value="warn" selected>warn</option>
          <option value="critical">critical</option>
        </select>
      </label>
      <label class="form-label"><span>${t("工位 role")}</span>
        <input class="input" id="w-role" value="review" placeholder="review">
      </label>
      <label class="form-label"><span>${t("标题")}</span>
        <input class="input" id="w-title" value="${esc(demoTitle)}">
      </label>
      <label class="form-label full"><span>${t("详情")}</span>
        <input class="input" id="w-detail" value="${esc(demoDetail)}">
      </label>
    </div>
    <div class="flex">
      <button class="btn btn-primary" id="w-send">${t("发送回调")}</button>
      <span class="t-meta" id="w-result">${esc(state.webhookResult)}</span>
    </div>
    <pre class="code">POST ${API_BASE}/workspaces/{key}/webhook
{
  "type": "demo.callback",
  "title": "${demoTitle}",
  "detail": "${demoDetail}",
  "level": "warn",
  "agentRole": "review",
  "source": "demo.webhook",
  "idempotencyKey": "dbg-1730000000000"
}</pre>
  </div>`;

  const commonTable = `
  <div class="card">
    <div class="card-title"><span class="t-title">${t("通用接口")}</span><span class="t-meta card-sub">base ${API_BASE}</span></div>
    <table class="table">
      <thead><tr><th>${t("方法")}</th><th>${t("路径")}</th><th>${t("说明")}</th></tr></thead>
      <tbody>
        ${COMMON_ENDPOINTS.map((e) => `<tr><td>${e.method}</td><td>${esc(e.path)}</td><td>${esc(t(e.summary))}</td></tr>`).join("")}
      </tbody>
    </table>
  </div>`;

  const wsTables = state.workspaces.map((w) => `
    <div class="card">
      <div class="card-title"><span class="t-title">${t("{name} 业务接口", { name: t(w.name) })}</span><span class="t-meta card-sub">${w.key}</span></div>
      <table class="table">
        <thead><tr><th>${t("方法")}</th><th>${t("路径")}</th><th>${t("说明")}</th></tr></thead>
        <tbody>
          ${w.endpoints.map((e) => `<tr><td>${e.method}</td><td>${esc(e.path)}</td><td>${esc(t(e.summary))}</td></tr>`).join("")}
        </tbody>
      </table>
    </div>`).join("");

  document.getElementById("view").innerHTML = `
  <div class="settings-stack">
    <div class="card">
      <div class="card-title"><span class="t-title">${t("后端接入")}</span></div>
      <div class="info-row"><span class="t-body grow">${t("数据来源")}</span><span class="t-meta">${srcText}</span>${srcChip}</div>
      <div class="info-row"><span class="t-body grow">API Base</span><span class="t-meta">${t("替换 apiJSON() 即可整套切换")}</span><span class="chip">${API_BASE}</span></div>
      <div class="info-row"><span class="t-body grow">${t("消息流")}</span><span class="chip">text/event-stream</span></div>
      <div class="info-row"><span class="t-body grow">${t("完整契约")}</span><span class="chip">API.md</span></div>
    </div>
    ${webhookForm}
    ${commonTable}
    ${wsTables}
  </div>`;

  document.getElementById("w-send").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = "…";
    const res = await sendWebhook({
      workspace: document.getElementById("w-workspace").value,
      level: document.getElementById("w-level").value,
      role: document.getElementById("w-role").value.trim(),
      title: document.getElementById("w-title").value.trim() || "demo.callback",
      detail: document.getElementById("w-detail").value.trim(),
    });
    state.webhookResult = res.message;
    btn.disabled = false;
    btn.textContent = t("发送回调");
    document.getElementById("w-result").textContent = state.webhookResult;
    renderTopbar();
    renderTicker();
  });
}

/* ---------- AI 助手（Marvis 式） ----------
   机器人消息只存「问题」，渲染时调 answer() 现算 —— 切语言自动换文案，
   依据块的数字也跟着实时数据走。用户消息存原文（是他说的话，不翻译）。 */
function renderAssistant() {
  if (!state.chat.seeded) {
    state.chat.seeded = true;
    state.chat.messages.push({ role: "bot", q: "你能帮我做什么？" });
    state.chat.suggestions = CHAT_SUGGESTIONS.slice(0, 6);
  }

  const msgs = state.chat.messages.map((m) => {
    if (m.role === "me") {
      return `<div class="msg me"><div class="msg-body"><div class="msg-bubble">${esc(m.text)}</div></div></div>`;
    }
    const a = answer(m.q);
    return `
    <div class="msg bot">
      <span class="msg-avatar">${ICONS.logomark}</span>
      <div class="msg-body">
        <div class="msg-bubble">${esc(a.text)}</div>
        ${a.evidence && a.evidence.length ? `<div class="msg-evidence">${a.evidence.map((e) => `
          <div class="ev-row">
            <span class="ev-label">${esc(e.label)}</span>
            ${e.bar !== undefined ? `<span class="ev-track"><i style="width:${e.bar}%"></i></span>` : ""}
            <span class="ev-value">${esc(e.value)}</span>
            ${e.sub ? `<span class="ev-sub">${esc(e.sub)}</span>` : ""}
          </div>`).join("")}</div>` : ""}
        ${a.actions && a.actions.length ? `<div class="msg-actions">${a.actions.map((x) => `
          <a class="btn" href="${x.href}">${esc(x.label)}</a>`).join("")}</div>` : ""}
      </div>
    </div>`;
  }).join("");

  const typing = state.chat.typing
    ? `<div class="msg bot"><span class="msg-avatar">${ICONS.logomark}</span>
       <div class="msg-body"><div class="msg-bubble typing"><i></i><i></i><i></i></div></div></div>`
    : "";

  const chips = state.chat.suggestions.map((s) =>
    `<button class="chip chat-chip" data-ask="${esc(t(s))}">${esc(t(s))}</button>`).join("");

  const insights = buildInsights();

  document.getElementById("view").innerHTML = `
  <div class="assistant">
    <section class="card chat">
      <div class="chat-head">
        <span class="msg-avatar">${ICONS.logomark}</span>
        <div>
          <div class="t-title">${t("AI 助手")}</div>
          <div class="t-meta">${t("基于 {n} 个工位的实时数据", { n: state.agents.length })}</div>
        </div>
      </div>
      <div class="chat-thread" id="chat-thread">${msgs}${typing}</div>
      <div class="chat-suggest">
        <span class="t-meta">${t("你可以接着问…")}</span>
        ${chips}
      </div>
      <div class="chat-input">
        <input class="input" id="chat-text" autocomplete="off"
               placeholder="${t("问点什么，比如「哪个工位现在最忙」")}">
        <button class="btn btn-primary" id="chat-send">${t("发送")}</button>
      </div>
    </section>

    <aside class="insights">
      <div class="section-title">${t("主动发现")}</div>
      ${insights.length ? insights.map((x) => `
        <div class="insight-card">
          <div class="r1"><i class="lamp ${LEVEL_META[x.level].lamp}"></i><span class="t-body grow">${esc(x.title)}</span></div>
          <div class="detail">${esc(x.detail)}</div>
          <div class="foot">
            <span class="t-meta">${t("置信度")} ${esc(x.confidence)}</span>
            <a class="btn btn-quiet" href="${x.action.href}">${esc(x.action.label)}</a>
          </div>
        </div>`).join("")
      : `<div class="t-meta">${t("暂时没有发现，一切正常")}</div>`}
    </aside>
  </div>`;

  const th = document.getElementById("chat-thread");
  if (th) th.scrollTop = th.scrollHeight;
  const input = document.getElementById("chat-text");
  if (input && state.chat.focus) { input.focus(); state.chat.focus = false; }
}

function askAssistant(text) {
  const q = String(text || "").trim();
  if (!q || state.chat.typing) return;
  state.chat.messages.push({ role: "me", text: q });
  state.chat.messages.push({ role: "bot", q });
  state.chat.typing = true;
  state.chat.suggestions = [];
  state.chat.focus = true;
  renderAssistant();
  setTimeout(() => {
    state.chat.typing = false;
    const a = answer(q);
    state.chat.suggestions = (a.followups && a.followups.length ? a.followups : CHAT_SUGGESTIONS.slice(0, 4));
    renderAssistant();
  }, 600);
}

/* ---------- 底部导航 / 工具条 ---------- */
function renderDock() {
  const page = document.body.dataset.page;
  const items = [
    { key: "warroom", label: t("作战室"), icon: ICONS.grid, href: "index.html" },
    { key: "dashboard", label: t("仪表盘"), icon: ICONS.chart, href: "dashboard.html" },
    { key: "assistant", label: t("AI 助手"), icon: ICONS.spark, href: "assistant.html" },
    { key: "settings", label: t("设置"), icon: ICONS.gear, href: "settings.html" },
  ];
  document.getElementById("dock").innerHTML = items.map((it) => `
    <button class="dock-item" ${it.key === page ? 'aria-current="page"' : ""} onclick="location.href='${it.href}';window.scrollTo(0,0)">
      ${it.icon}${it.label}
    </button>`).join("");

  document.getElementById("tools").innerHTML = `
    <button class="icon-btn" id="t-heat" aria-pressed="${state.showLoad}" title="${t("负载热力")}" aria-label="${t("负载热力")}">${ICONS.heat}</button>
    <button class="icon-btn" id="t-refresh" title="${t("刷新")}" aria-label="${t("刷新")}">${ICONS.refresh}</button>
    <button class="icon-btn" id="t-webhook" title="${t("回调调试")}" aria-label="${t("回调调试")}">${ICONS.anchor}</button>`;

  document.getElementById("t-heat").addEventListener("click", () => {
    state.showLoad = !state.showLoad;
    renderDock();
    if (document.body.dataset.page === "warroom") renderWarroom();
  });
  document.getElementById("t-refresh").addEventListener("click", () => {
    jitterLoads();
    renderView();
  });
  document.getElementById("t-webhook").addEventListener("click", () => {
    location.href = "settings.html#webhook";
  });
}

/* ---------- 视图调度 ---------- */
function renderView() {
  const page = document.body.dataset.page;
  if (page === "dashboard") renderDashboard();
  else if (page === "settings") renderSettings();
  else if (page === "assistant") renderAssistant();
  else renderWarroom();
}

/* 文档级文案：<html lang> / <title> / 抽屉 aria-label，都跟语言走 */
function applyLang() {
  document.documentElement.lang = state.lang === "en" ? "en" : "zh-CN";
  const page = document.body.dataset.page;
  const title = page === "dashboard" ? "AIWHO WEBHOOK 中台 · 仪表盘"
    : page === "settings" ? "AIWHO WEBHOOK 中台 · 设置"
    : page === "assistant" ? "AIWHO WEBHOOK 中台 · AI 助手"
    : "AIWHO WEBHOOK 中台 · 作战室";
  document.title = t(title);
  const drawer = document.getElementById("drawer");
  if (drawer) drawer.setAttribute("aria-label", t("工位详情"));
}

/* 昼夜：给 <html> 挂 data-theme，CSS 变量整套切换（含工位插画） */
function applyTheme() {
  document.documentElement.dataset.theme = state.theme;
  document.body.classList.toggle("ui-locked", state.uiLocked);
}

function renderAll() {
  renderTopbar();
  renderTicker();
  renderView();
  renderDock();
  renderDrawer();
  applyLang();
  applyTheme();
}

/* ---------- 事件绑定 ---------- */
function bindGlobal() {
  // 工位卡：点击 / Enter 开抽屉
  // 顶栏：连接状态浮层 / 界面锁定 / 昼夜切换
  document.addEventListener("click", (e) => {
    const net = e.target.closest("#t-net");
    if (net) {
      const pop = document.getElementById("net-pop");
      const open = pop.hasAttribute("hidden");
      pop.toggleAttribute("hidden", !open);
      net.setAttribute("aria-expanded", String(open));
      return;
    }
    if (e.target.closest("#t-lock")) { toggleLock(); return; }
    if (e.target.closest("#t-theme")) {
      setTheme(state.theme === "dark" ? "light" : "dark");
      return;
    }
    // 点别处收起连接浮层
    const pop = document.getElementById("net-pop");
    if (pop && !pop.hasAttribute("hidden") && !e.target.closest(".net-pop")) {
      pop.setAttribute("hidden", "");
      const btn = document.getElementById("t-net");
      if (btn) btn.setAttribute("aria-expanded", "false");
    }
    const chip = e.target.closest(".chat-chip");
    if (chip) { askAssistant(chip.dataset.ask); return; }
    if (e.target.closest("#chat-send")) {
      const input = document.getElementById("chat-text");
      if (input) askAssistant(input.value);
      return;
    }
    const desk = e.target.closest(".desk");
    if (desk && !state.uiLocked) openDrawer(desk.dataset.agent);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target.id === "chat-text") {
      e.preventDefault();
      askAssistant(e.target.value);
      return;
    }
    if (e.key === "Enter" && document.activeElement.classList.contains("desk") && !state.uiLocked) {
      openDrawer(document.activeElement.dataset.agent);
    }
    if (e.key === "Escape") closeDrawer();
  });

  // 遮罩点击关闭
  document.getElementById("scrim").addEventListener("click", closeDrawer);

  // 抽屉指令按钮（界面锁定时不响应，防误触）
  document.getElementById("drawer").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-cmd]");
    if (btn && !state.uiLocked) execCommand(btn.dataset.cmd, btn);
  });

  // 时钟 1s / 相对时间 30s 重算
  setInterval(() => {
    const el = document.getElementById("clock");
    if (el) el.textContent = clockTime(new Date());
  }, 1000);
  setInterval(renderTicker, 30000);

  // 设置页锚点
  if (location.hash === "#webhook") {
    setTimeout(() => document.getElementById("webhook")?.scrollIntoView({ behavior: "smooth" }), 60);
  }
}

/* ---------- 启动 ---------- */
document.body.insertAdjacentHTML("afterbegin", DEFS_SVG);
bindGlobal();
renderAll();
hydrate().then(() => renderAll()); // 后端就绪则整屏换真实数据
