// Workstation artwork retained from repository commit 451c88a; maintained in this module.
export type DeskVisual = 'working' | 'idle' | 'urgent' | 'dormant';

// Screen bars and the desk lamp share one colour per status, and one pace: a busy
// station ticks through its steps faster than an idle one. Colours are picked to
// read on the dark monitor glass as well as on the light desk top.
const STATUS_META: Record<DeskVisual, { color: string; pace: number }> = {
  working: { color: '#4ed7f1', pace: 1 },
  urgent: { color: '#f0736a', pace: 0.72 },
  idle: { color: '#7f949c', pace: 1.55 },
  dormant: { color: '#e3d76a', pace: 1.8 },
};

export const DESK_DEFS = `
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

/** Deterministic PRNG so a station keeps the same bars across re-renders and SSR. */
function hashSeed(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const pct = (seconds: number, cycle: number) => Math.round((seconds / cycle) * 10000) / 100;

export function deskSVG(status: DeskVisual, seed = 'desk') {
  const { color, pace } = STATUS_META[status];
  const rnd = mulberry32(hashSeed(`${seed}|${status}`));
  const between = (min: number, max: number) => min + rnd() * (max - min);

  // 显示区 x=47..129（宽 82）。进度条从 x=65 起画，宽度取 34..58，
  // 全部大于屏幕宽度的 1/3（82/3 ≈ 27.3，玻璃屏 92/3 ≈ 30.7）。
  const barW = [between(34, 58), between(34, 58), between(34, 58)];
  // 三条依次推进：第 n 条填满后才轮到第 n+1 条，节奏带随机，看着像真在跑活。
  const fillSeconds = [between(1, 1.9) * pace, between(1, 1.9) * pace, between(1, 1.9) * pace];
  const hold = between(0.35, 0.8) * pace;

  const starts: number[] = [];
  let cursor = 0;
  for (const seconds of fillSeconds) {
    starts.push(cursor);
    cursor += seconds;
  }
  const cycle = cursor + hold;
  const startPct = starts.map((s) => pct(s, cycle));
  const endPct = fillSeconds.map((d, i) => pct(starts[i] + d, cycle));
  const snapPct = pct(cursor + hold * 0.6, cycle);
  const uid = hashSeed(`${seed}|${status}`).toString(36);

  const barTrack = (i: number) => {
    const rules = [
      `${endPct[i]}%{transform:scaleX(1)}`,
      `${snapPct}%{transform:scaleX(1)}`,
      `100%{transform:scaleX(0)}`,
    ];
    rules.unshift(startPct[i] < 0.01 ? `0%{transform:scaleX(0)}` : `0%,${startPct[i]}%{transform:scaleX(0)}`);
    return `@keyframes lcBar${uid}-${i}{${rules.join('')}}`;
  };

  // 工件随每条进度条填满而下移一站，最后在收尾处淡出。
  const flowRules = [
    `0%{transform:translateY(0) scale(1);opacity:0}`,
    `2%{transform:translateY(0) scale(1.18);opacity:1}`,
    `5%{transform:translateY(0) scale(1);opacity:1}`,
    `${Math.max(6, endPct[0] - 1)}%{transform:translateY(0) scale(1);opacity:1}`,
    `${endPct[0]}%{transform:translateY(12px) scale(1.18);opacity:1}`,
    `${endPct[0] + 2}%{transform:translateY(12px) scale(1);opacity:1}`,
    `${Math.max(endPct[0] + 3, endPct[1] - 1)}%{transform:translateY(12px) scale(1);opacity:1}`,
    `${endPct[1]}%{transform:translateY(24px) scale(1.18);opacity:1}`,
    `${endPct[1] + 2}%{transform:translateY(24px) scale(1);opacity:1}`,
    `${snapPct}%{transform:translateY(24px) scale(1);opacity:1}`,
    `100%{transform:translateY(24px) scale(.9);opacity:0}`,
  ];

  // 站点圆点在自己那条进度条推进时点亮。
  const stationTrack = (i: number) => {
    const rules = [
      `${Math.min(98, startPct[i] + 2)}%{opacity:1;transform:scale(1.35)}`,
      `${endPct[i]}%{opacity:1;transform:scale(1.12)}`,
      `${Math.min(99, endPct[i] + 3)}%{opacity:.5;transform:scale(1)}`,
      `100%{opacity:.5;transform:scale(1)}`,
    ];
    rules.unshift(startPct[i] < 0.01 ? `0%{opacity:1;transform:scale(1.35)}` : `0%,${startPct[i]}%{opacity:.5;transform:scale(1)}`);
    return `@keyframes lcSt${uid}-${i}{${rules.join('')}}`;
  };

  return `
  <svg class="desk-art lc-${uid}" viewBox="0 0 176 126" aria-hidden="true">
    <style>
      ${[0, 1, 2].map(barTrack).join('\n      ')}
      ${[0, 1, 2].map(stationTrack).join('\n      ')}
      @keyframes lcFlow${uid}{${flowRules.join('')}}
      .lc-${uid} .bar-fill{transform-box:fill-box;transform-origin:left center;transform:scaleX(1)}
      .lc-${uid} .workpiece{transform-box:fill-box;transform-origin:center}
      .lc-${uid} .station{transform-box:fill-box;transform-origin:center;opacity:.5}
      .lc-${uid} .bar-fill.s1{animation:lcBar${uid}-0 ${cycle}s linear infinite}
      .lc-${uid} .bar-fill.s2{animation:lcBar${uid}-1 ${cycle}s linear infinite}
      .lc-${uid} .bar-fill.s3{animation:lcBar${uid}-2 ${cycle}s linear infinite}
      .lc-${uid} .station.s1{animation:lcSt${uid}-0 ${cycle}s ease-out infinite}
      .lc-${uid} .station.s2{animation:lcSt${uid}-1 ${cycle}s ease-out infinite}
      .lc-${uid} .station.s3{animation:lcSt${uid}-2 ${cycle}s ease-out infinite}
      .lc-${uid} .workpiece{animation:lcFlow${uid} ${cycle}s cubic-bezier(.4,0,.2,1) infinite}
    </style>
    <!-- 玻璃屏 -->
    <rect x="42" y="2" width="92" height="44" rx="5" fill="url(#d-screen)"/>
    <rect x="47" y="6" width="82" height="36" rx="3" fill="#26262c"/>
    <path d="M47 6h34L55 42h-8z" fill="url(#d-glass)"/>
    <!-- 工作流程：三条进度条从上到下依次填满，每满一条工件下移一站 -->
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
