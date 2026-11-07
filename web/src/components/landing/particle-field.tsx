'use client';

import { useEffect, useRef } from 'react';
import { particleFlowPoint } from '@/lib/particle-flow';
import styles from './landing.module.css';

export function ParticleField() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    const hero = canvas?.parentElement;
    const copy = hero?.querySelector<HTMLElement>('[data-particle-clear]');
    if (!canvas || !hero || !copy) return;
    const context = canvas.getContext('2d');
    if (!context) return;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    let width = 0, height = 0, frame = 0, seconds = 0, lastTime = 0, lastPaint = 0;
    let inView = true;
    let quiet = { left: 0, right: 0, top: 0, bottom: 0 };

    function draw() {
      if (!context) return;
      context.clearRect(0, 0, width, height);
      const count = width < 640 ? 36 : 84;
      for (let index = 0; index < count; index++) {
        const point = particleFlowPoint(index, seconds, width, height);
        const dx = Math.max(quiet.left - point.x, 0, point.x - quiet.right);
        const dy = Math.max(quiet.top - point.y, 0, point.y - quiet.bottom);
        const clearance = Math.min(1, Math.hypot(dx, dy) / 65);
        if (!clearance) continue;
        // A quiet halo plus a small blue core; no per-frame blur or shadows.
        context.globalAlpha = point.opacity * clearance * .18;
        context.fillStyle = '#7ad5ee';
        context.beginPath();
        context.arc(point.x, point.y, point.radius * 3, 0, Math.PI * 2);
        context.fill();
        context.globalAlpha = point.opacity * clearance;
        context.fillStyle = '#5ebbd2';
        context.beginPath();
        context.arc(point.x, point.y, point.radius, 0, Math.PI * 2);
        context.fill();
      }
      context.globalAlpha = 1;
    }
    function tick(timestamp: number) {
      if (lastTime) seconds += Math.min((timestamp - lastTime) / 1000, .08);
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
      if (!canvas || !copy || !context) return;
      const bounds = canvas.getBoundingClientRect();
      const text = copy.getBoundingClientRect();
      width = bounds.width; height = bounds.height;
      const ratio = Math.min(window.devicePixelRatio || 1, width < 640 ? 1.5 : 2);
      canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      quiet = { left: text.left - bounds.left - 12, right: text.right - bounds.left + 12,
        top: text.top - bounds.top - 12, bottom: text.bottom - bounds.top + 12 };
      sync();
    }
    const resize = new ResizeObserver(measure);
    resize.observe(canvas); resize.observe(copy);
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
  return <canvas ref={canvasRef} className={styles.particleField} aria-hidden="true"/>;
}
