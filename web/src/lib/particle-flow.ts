// All particles share one left-to-right current. Three broad arcs supply depth,
// not independent random velocities. Coordinates use CSS pixels.
export function particleFlowPoint(index: number, seconds: number, width: number, height: number) {
  const lane = index % 3;
  const progress = ((index * .61803398875 + seconds / 110) % 1 + 1) % 1;
  const bend = Math.sin(Math.PI * progress) ** 2;
  const ripple = Math.sin(progress * Math.PI * 2 + seconds / 9 - lane * .45);
  return {
    x: progress * width,
    y: height * (.20 + lane * .105 + bend * .38 + ripple * .016),
    radius: .75 + (index % 5) * .18,
    opacity: Math.min(progress * 8, (1 - progress) * 8, 1) * (.34 + .06 * Math.sin(seconds / 8 + lane)),
  };
}
