'use client';

import { useEffect, useRef } from 'react';
import { warroomLinkAlpha, warroomNode } from '@/lib/warroom-flow';

const NODES = 62;
const LINK_DISTANCE = 158;

export function WarroomBackdrop() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext('2d');
    if (!context) return;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    let width = 0, height = 0, frame = 0, seconds = 0, lastTime = 0, lastPaint = 0;
    let inView = true;

    function draw() {
      if (!context) return;
      context.clearRect(0, 0, width, height);
      const count = width < 640 ? 26 : NODES;
      const nodes = [];
      for (let index = 0; index < count; index += 1) nodes.push(warroomNode(index, seconds, width, height));

      // Links first so the nodes sit on top of their own mesh.
      context.lineWidth = 1;
      for (let i = 0; i < nodes.length; i += 1) {
        for (let j = i + 1; j < nodes.length; j += 1) {
          const a = nodes[i], b = nodes[j];
          const alpha = warroomLinkAlpha(a.x, a.y, b.x, b.y, LINK_DISTANCE) * Math.min(a.opacity, b.opacity) * 1.25;
          if (alpha < 0.012) continue;
          context.globalAlpha = Math.min(alpha, 0.42);
          context.strokeStyle = '#4ed7f1';
          context.beginPath();
          context.moveTo(a.x, a.y);
          context.lineTo(b.x, b.y);
          context.stroke();
        }
      }

      for (const node of nodes) {
        // A quiet halo plus a small core; no per-frame blur or shadows.
        context.globalAlpha = Math.min(node.opacity * 0.26, 0.16);
        context.fillStyle = '#7ad5ee';
        context.beginPath();
        context.arc(node.x, node.y, node.radius * 4, 0, Math.PI * 2);
        context.fill();
        context.globalAlpha = Math.min(node.opacity * 1.25, 0.8);
        context.fillStyle = '#2fb9d9';
        context.beginPath();
        context.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
        context.fill();
      }
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
      const ratio = Math.min(window.devicePixelRatio || 1, width < 640 ? 1.5 : 2);
      canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
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
    <div className="warroom-backdrop" aria-hidden="true">
      <span className="warroom-glow warroom-glow-a" />
      <span className="warroom-glow warroom-glow-b" />
      <canvas ref={canvasRef} className="warroom-backdrop-canvas" />
    </div>
  );
}
