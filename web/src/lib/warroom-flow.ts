// Deterministic nodes for the owner console backdrop. They share a handful of
// slow lanes and drift left-to-right at their own rate, so the field reads as
// one calm current rather than independent random noise — the same idea as the
// landing particle flow, tuned for a dashboard that is mostly covered by cards.
export type WarroomNode = {
  x: number;
  y: number;
  radius: number;
  opacity: number;
  lane: number;
};

const LANE_COUNT = 6;

export function warroomNode(index: number, seconds: number, width: number, height: number): WarroomNode {
  const lane = index % LANE_COUNT;
  // Each node keeps its own period so the mesh never settles into a pattern.
  const progress = ((index * 0.61803398875 + seconds / (150 + (index % 4) * 35)) % 1 + 1) % 1;
  const drift = Math.sin(progress * Math.PI * 2 + lane * 0.7 + seconds / 30);
  return {
    x: progress * width,
    y: height * (0.08 + lane * 0.164 + drift * 0.035),
    radius: 1.1 + (index % 4) * 0.45,
    // Fade both ends so the wrap seam never pops.
    opacity: Math.min(progress * 7, (1 - progress) * 7, 1) * (0.3 + 0.12 * Math.sin(seconds / 9 + lane)),
    lane,
  };
}

/** Alpha for a link between two points, 0 once they are a full step apart. */
export function warroomLinkAlpha(ax: number, ay: number, bx: number, by: number, maxDistance: number) {
  const distance = Math.hypot(ax - bx, ay - by);
  return distance >= maxDistance ? 0 : 1 - distance / maxDistance;
}
