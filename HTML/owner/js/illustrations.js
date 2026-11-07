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
  logomark: '<svg class="ic" viewBox="0 0 24 24" style="width:20px;height:20px"><rect x="1" y="1" width="18" height="18" rx="5"/><path d="M5.5 12.5v-5M10 12.5v-8M14.5 12.5v-3"/></svg>',
};

/* ---------- 工位插画共用渐变 defs ---------- */
const DEFS_SVG = `
<svg width="0" height="0" style="position:absolute" aria-hidden="true">
  <defs>
    <linearGradient id="d-screen" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#33333a"/><stop offset="1" stop-color="#1c1c21"/>
    </linearGradient>
    <linearGradient id="d-glass" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#ffffff" stop-opacity=".10"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="d-desk-top" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#fbfbfa"/><stop offset="1" stop-color="#edecea"/>
    </linearGradient>
    <linearGradient id="d-desk-edge" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#e4e3e0"/><stop offset="1" stop-color="#d2d1cd"/>
    </linearGradient>
    <linearGradient id="d-chair" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#f0efec"/><stop offset="1" stop-color="#dedcd8"/>
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
  const barW = [48, 61, 40];
  return `
  <svg class="desk-art" viewBox="0 0 176 126" aria-hidden="true">
    <!-- 玻璃屏 -->
    <rect x="42" y="2" width="92" height="44" rx="5" fill="url(#d-screen)"/>
    <rect x="47" y="6" width="82" height="36" rx="3" fill="#26262c"/>
    <path d="M47 6h34L55 42h-8z" fill="url(#d-glass)"/>
    ${busy ? `
    <!-- 工作流程：三条进度条依次填满，每满一条工件下移一站，以此类推 -->
    <rect x="65" y="10.5" width="${barW[0]}" height="3" rx="1.5" fill="#3f3f46"/>
    <rect class="bar-fill s1" x="65" y="10.5" width="${barW[0]}" height="3" rx="1.5" fill="${color}"/>
    <rect x="65" y="22.5" width="${barW[1]}" height="3" rx="1.5" fill="#3f3f46"/>
    <rect class="bar-fill s2" x="65" y="22.5" width="${barW[1]}" height="3" rx="1.5" fill="${color}"/>
    <rect x="65" y="34.5" width="${barW[2]}" height="3" rx="1.5" fill="#3f3f46"/>
    <rect class="bar-fill s3" x="65" y="34.5" width="${barW[2]}" height="3" rx="1.5" fill="${color}"/>
    <circle class="station s1" cx="55" cy="12" r="3.4" fill="#8b929b"/>
    <circle class="station s2" cx="55" cy="24" r="3.4" fill="#8b929b"/>
    <circle class="station s3" cx="55" cy="36" r="3.4" fill="#8b929b"/>
    <rect class="workpiece" x="50" y="7" width="10" height="10" rx="3" fill="${color}"/>
    ` : `
    <rect x="53" y="11" width="36" height="2.4" rx="1.2" fill="#3f3f46"/>
    <rect x="53" y="18" width="54" height="2.4" rx="1.2" fill="#3f3f46"/>
    <rect x="53" y="25" width="25" height="2.4" rx="1.2" fill="#3f3f46"/>
    <rect x="53" y="32" width="42" height="2.4" rx="1.2" fill="#3f3f46"/>
    `}
    <!-- 桌板：比原版略拉长（12 → 18px） -->
    <rect x="14" y="46" width="148" height="18" rx="2" fill="url(#d-desk-top)" stroke="#d8d7d3"/>
    <rect x="14" y="63" width="148" height="5" fill="url(#d-desk-edge)"/>
    <!-- 桌角状态灯 -->
    <circle cx="25" cy="54" r="3.6" fill="${color}"/>
    <path d="M22.6 52.4a3.6 3.6 0 0 1 2.2-1.7" stroke="#fff" stroke-opacity=".55" stroke-width="1.2" fill="none" stroke-linecap="round"/>
    <!-- 桌腿 -->
    <rect x="28" y="68" width="8" height="26" fill="#dedcd8"/>
    <rect x="140" y="68" width="8" height="26" fill="#dedcd8"/>
    <!-- 投影 -->
    <ellipse cx="88" cy="110" rx="62" ry="15" fill="url(#d-shadow)"/>
    <!-- 员工剪影：画在座椅**之前**，所以白色的椅背盖住黑身体，
         只露脖子以上的头 —— 看着就是靠在椅子上。
         「往前挪」= 朝桌面方向（图面上为向上）移，露出的头从 9px 增到 12px；
         耳朵收到 r8，头顶距屏幕仍有 1px，避免两块黑叠在一起。 -->
    <g fill="#2c2c30">
      <circle cx="74" cy="55" r="8"/>
      <circle cx="102" cy="55" r="8"/>
      <circle cx="88" cy="68" r="20"/>
      <path d="M62 95v-6a26 26 0 0 1 52 0v6z"/>
    </g>
    <path d="M76 61a14 14 0 0 1 22-4" stroke="#fff" stroke-opacity=".1" stroke-width="3" fill="none" stroke-linecap="round"/>

    <!-- 座椅（盖在员工身体之上） -->
    <rect x="52" y="60" width="72" height="38" rx="15" fill="url(#d-chair)"/>
    <rect x="34" y="76" width="20" height="32" rx="10" fill="url(#d-chair)"/>
    <rect x="122" y="76" width="20" height="32" rx="10" fill="url(#d-chair)"/>
  </svg>`;
}
