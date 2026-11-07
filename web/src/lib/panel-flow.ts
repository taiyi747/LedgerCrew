// Flowing vertical ribbons and rising sparks for the owner slide-over panels.
// Deliberately unlike the console backdrop: those panels are tall and narrow,
// so the current runs up the drawer instead of across the room, and the shape
// is soft light bands rather than a linked node mesh.
export type PanelSpark = { x: number; y: number; radius: number; opacity: number };

const RIBBONS = 4;

/** Centreline x of one ribbon at height fraction t (0 = top), drifting over time. */
export function panelRibbonOffset(index: number, seconds: number, t: number, width: number) {
  const base = ((index + 0.5) / RIBBONS) * width;
  const amplitude = width * (0.1 + (index % 3) * 0.035);
  const cycles = 1.3 + (index % 4) * 0.45;
  const speed = 0.035 + (index % 3) * 0.012;
  return base + Math.sin((t * cycles + seconds * speed) * Math.PI * 2) * amplitude;
}

export function panelRibbonWidth(index: number, width: number) {
  return width * (0.07 + (index % 3) * 0.022);
}

/** One rising spark. Fades at both ends so the wrap seam never pops. */
export function panelSpark(index: number, seconds: number, width: number, height: number): PanelSpark {
  const period = 9 + (index % 5) * 2.2;
  const progress = ((index * 0.61803398875 + seconds / period) % 1 + 1) % 1;
  const sway = Math.sin(progress * Math.PI * 2 + index) * width * 0.06;
  return {
    x: ((index * 0.37) % 1) * width * 0.86 + width * 0.07 + sway,
    y: height * (0.96 - progress * 0.92),
    radius: 1.2 + (index % 3) * 0.55,
    opacity: Math.min(progress * 6, (1 - progress) * 6, 1) * (0.32 + 0.12 * Math.sin(seconds / 7 + index)),
  };
}
