'use client';

import { useEffect, useRef } from 'react';
import { panelRibbonOffset, panelRibbonWidth, panelSpark } from '@/lib/panel-flow';
import { streakStar, streakTrail } from '@/lib/streak-flow';

export type PanelEffect = 'ribbons' | 'streaks';

// Which treatment the slide-over panels use. Flip to compare: 'ribbons' is the
// flowing vertical light bands, 'streaks' is the parallax starfield with
// passing light trails. The console keeps its own node mesh either way.
export const PANEL_EFFECT: PanelEffect = 'ribbons';

const RIBBONS = 4;
const SPARKS = 30;
const STARS = 42;
const TRAILS = 7;

export function PanelBackdrop() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext('2d');
    if (!context) return;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    let width = 0, height = 0, frame = 0, seconds = 0, lastTime = 0, lastPaint = 0;
    let inView = true;
    let wash: CanvasGradient | null = null;

    function drawRibbons() {
      if (!context || !wash) return;
      // One soft light band per lane, closed from its own centreline so the band
      // keeps an even thickness as it snakes.
      const steps = 24;
      for (let r = 0; r < RIBBONS; r += 1) {
        const half = panelRibbonWidth(r, width) / 2;
        context.beginPath();
        for (let i = 0; i <= steps; i += 1) {
          const t = i / steps;
          const x = panelRibbonOffset(r, seconds, t, width) - half;
          if (i === 0) context.moveTo(x, t * height); else context.lineTo(x, t * height);
        }
        for (let i = steps; i >= 0; i -= 1) {
          const t = i / steps;
          context.lineTo(panelRibbonOffset(r, seconds, t, width) + half, t * height);
        }
        context.closePath();
        context.globalAlpha = 0.5 + (r % 2) * 0.18;
        context.fillStyle = wash;
        context.fill();
      }

      const count = width < 420 ? 18 : SPARKS;
      for (let index = 0; index < count; index += 1) {
        const spark = panelSpark(index, seconds, width, height);
        context.globalAlpha = Math.min(spark.opacity * 0.3, 0.18);
        context.fillStyle = '#7ad5ee';
        context.beginPath();
        context.arc(spark.x, spark.y, spark.radius * 3.6, 0, Math.PI * 2);
        context.fill();
        context.globalAlpha = Math.min(spark.opacity * 1.2, 0.85);
        context.fillStyle = '#2fb9d9';
        context.beginPath();
        context.arc(spark.x, spark.y, spark.radius, 0, Math.PI * 2);
        context.fill();
      }
    }

    function drawStreaks() {
      if (!context) return;
      // Far layer first so nearer stars and trails sit on top of it.
      const count = width < 420 ? 24 : STARS;
      for (let index = 0; index < count; index += 1) {
        const star = streakStar(index, seconds, width, height);
        const near = star.depth === 2 ? 1.25 : star.depth === 1 ? 1 : 0.85;
        context.globalAlpha = Math.min(star.opacity * 0.32 * near, 0.2);
        context.fillStyle = '#7ad5ee';
        context.beginPath();
        context.arc(star.x, star.y, star.radius * 3.4, 0, Math.PI * 2);
        context.fill();
        context.globalAlpha = Math.min(star.opacity * 1.15 * near, 0.85);
        context.fillStyle = '#2fb9d9';
        context.beginPath();
        context.arc(star.x, star.y, star.radius, 0, Math.PI * 2);
        context.fill();
      }

      // Each trail is a tapered stroke: transparent at the tail, bright at the
      // head, so it reads as light passing through rather than a drawn line.
      context.lineCap = 'round';
      context.lineWidth = 2.1;
      for (let index = 0; index < TRAILS; index += 1) {
        const trail = streakTrail(index, seconds, width, height);
        if (trail.alpha <= 0.01) continue;
        const tailX = trail.x - Math.cos(trail.angle) * trail.length;
        const tailY = trail.y - Math.sin(trail.angle) * trail.length;
        const fade = context.createLinearGradient(tailX, tailY, trail.x, trail.y);
        fade.addColorStop(0, 'rgba(122,213,238,0)');
        fade.addColorStop(1, 'rgba(168,241,255,0.9)');
        context.globalAlpha = trail.alpha * 0.85;
        context.strokeStyle = fade;
        context.beginPath();
        context.moveTo(tailX, tailY);
        context.lineTo(trail.x, trail.y);
        context.stroke();
        context.globalAlpha = trail.alpha;
        context.fillStyle = '#a8f1ff';
        context.beginPath();
        context.arc(trail.x, trail.y, 2, 0, Math.PI * 2);
        context.fill();
      }
    }

    function draw() {
      if (!context) return;
      context.clearRect(0, 0, width, height);
      if (PANEL_EFFECT === 'streaks') drawStreaks(); else drawRibbons();
      context.globalAlpha = 1;
    }

    function tick(timestamp: number) {
      if (lastTime) seconds += Math.min((timestamp - lastTime) / 1000, 0.08);
      lastTime = timestamp;
      if (timestamp - lastPaint >= 1000 / 30) { draw(); lastPaint = timestamp; }
      frame = requestAnimationFrame(tick);
    }
    function sync() {
      cancelAnimationFrame(frame);
      lastTime = 0;
      draw();
      if (!reduced.matches && inView && !document.hidden) frame = requestAnimationFrame(tick);
    }
    function measure() {
      if (!canvas || !context) return;
      const bounds = canvas.getBoundingClientRect();
      width = bounds.width; height = bounds.height;
      const ratio = Math.min(window.devicePixelRatio || 1, width < 420 ? 1.5 : 2);
      canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      wash = context.createLinearGradient(0, 0, 0, height);
      wash.addColorStop(0, 'rgba(122,213,238,0)');
      wash.addColorStop(0.34, 'rgba(122,213,238,0.17)');
      wash.addColorStop(0.68, 'rgba(168,241,255,0.14)');
      wash.addColorStop(1, 'rgba(168,241,255,0)');
      sync();
    }
    const resize = new ResizeObserver(measure);
    resize.observe(canvas);
    const intersection = new IntersectionObserver(entries => {
      inView = entries[0].isIntersecting; sync();
    });
    intersection.observe(canvas);
    reduced.addEventListener('change', sync);
    document.addEventListener('visibilitychange', sync);
    measure();
    return () => {
      cancelAnimationFrame(frame); resize.disconnect(); intersection.disconnect();
      reduced.removeEventListener('change', sync);
      document.removeEventListener('visibilitychange', sync);
    };
  }, []);

  return (
    <div className={`panel-backdrop panel-backdrop-${PANEL_EFFECT}`} aria-hidden="true">
      <canvas ref={canvasRef} className="panel-backdrop-canvas" />
    </div>
  );
}
