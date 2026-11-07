// Parallax starfield with passing light streaks for the owner slide-over panels.
// Third treatment alongside the console's node mesh and the panel's light
// ribbons: here the depth comes from layers crossing at different rates, and
// the drama comes from an occasional streak with a tapering tail rather than a
// constant field of connected parts.
export type StreakStar = {
  x: number;
  y: number;
  radius: number;
  opacity: number;
  depth: number;
};

export type StreakTrail = {
  x: number;
  y: number;
  angle: number;
  length: number;
  alpha: number;
};

// 0 is the far layer (small, slow, faint) and 2 the near layer.
const LAYERS = 3;

export function streakStar(index: number, seconds: number, width: number, height: number): StreakStar {
  const depth = index % LAYERS;
  const period = 26 - depth * 7;
  const progress = ((index * 0.61803398875 + seconds / period) % 1 + 1) % 1;
  const lane = (index * 0.3819660113) % 1;
  return {
    x: progress * width,
    y: height * (0.05 + lane * 0.9),
    radius: 0.9 + depth * 0.85,
    depth,
    // Fade both ends so the wrap seam never pops.
    opacity: Math.min(progress * 8, (1 - progress) * 8, 1) * (0.2 + depth * 0.15),
  };
}

/**
 * One light streak crossing the drawer. `alpha` is 0 while the streak is idle,
 * so callers can draw every index without branching on a null.
 */
export function streakTrail(index: number, seconds: number, width: number, height: number): StreakTrail {
  const period = 8.5 + (index % 4) * 3.2;
  const visible = 0.2;
  const phase = (((seconds / period) + index * 0.41) % 1 + 1) % 1;
  const startX = width * (-0.05 + (index % 3) * 0.32);
  const startY = height * (0.04 + (index % 2) * 0.22);
  const runX = width * 0.95;
  const runY = height * 0.62;
  const angle = Math.atan2(runY, runX);
  const p = Math.min(phase / visible, 1);
  // Only the tail-end of the pass is drawn; the rest of the period is idle.
  const alpha = phase > visible ? 0 : Math.sin(Math.PI * p);
  return {
    x: startX + runX * p,
    y: startY + runY * p,
    angle,
    length: width * (0.16 + (index % 2) * 0.09) * (0.45 + p * 0.55),
    alpha,
  };
}
