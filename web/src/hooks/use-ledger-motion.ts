'use client';

import { useEffect, type RefObject } from 'react';
import gsap from 'gsap';

type Options = {
  root: RefObject<HTMLDivElement | null>;
  showDemo: boolean;
  replay: number;
  filter: string;
  detailsOpen: boolean;
  modal: string | null;
  messageCount: number;
  busy: boolean;
};

// Scope feedback to this page and revert it on update, unmount or a change
// to reduced motion. Financial figures are never animated or interpolated.
function animate(scope: HTMLElement | null, build: (scope: HTMLElement) => void) {
  if (!scope) return;
  const media = gsap.matchMedia();
  media.add('(prefers-reduced-motion: no-preference)', () => {
    const context = gsap.context(() => build(scope), scope);
    return () => context.revert();
  });
  return () => media.revert();
}

export function useLedgerMotion({ root, showDemo, replay, filter, detailsOpen, modal, messageCount, busy }: Options) {
  useEffect(() => {
    const scope = root.current;
    if (!showDemo || !scope) return;
    const media = gsap.matchMedia();
    media.add('(prefers-reduced-motion: no-preference)', () => {
      const context = gsap.context(() => {}, scope);
      const played = new WeakSet<Element>();
      const observer = new IntersectionObserver(entries => {
        entries.forEach(entry => {
          if (!entry.isIntersecting || played.has(entry.target)) return;
          played.add(entry.target);
          observer.unobserve(entry.target);
          context.add(() => {
            const card = entry.target;
            const timeline = gsap.timeline({ defaults: { ease: 'power2.out' } });
            timeline.fromTo(card, { opacity: .35, y: 12 }, { opacity: 1, y: 0, duration: .45, clearProps: 'opacity,transform' }, 0);
            const bars = card.querySelectorAll('.invoice-bar, .payment-bar');
            if (bars.length) timeline.fromTo(bars, { scaleY: 0, transformOrigin: '50% 100%' }, {
              scaleY: 1, duration: .85, stagger: .055, clearProps: 'transform,transformOrigin',
            }, .15);
            card.querySelectorAll<SVGPathElement>('.donut-segment').forEach((segment, index) => {
              const length = segment.getTotalLength();
              timeline.fromTo(segment, { strokeDasharray: `${length} ${length}`, strokeDashoffset: length }, {
                strokeDashoffset: 0, duration: .9, ease: 'power2.inOut', clearProps: 'strokeDasharray,strokeDashoffset',
              }, .15 + index * .28);
            });
          });
        });
      }, { root: scope.querySelector('.chat-scroll'), threshold: .3 });
      scope.querySelectorAll('.chart-card').forEach(card => observer.observe(card));
      return () => { observer.disconnect(); context.revert(); };
    });
    return () => media.revert();
  }, [root, showDemo, replay]);
  useEffect(() => animate(root.current, () => {
    if (showDemo && detailsOpen) gsap.fromTo('.result-detail tbody tr', { opacity: .4, y: 6 }, {
      opacity: 1, y: 0, duration: .2, stagger: .025, ease: 'power2.out', clearProps: 'opacity,transform',
    });
  }), [root, filter, showDemo, detailsOpen]);

  useEffect(() => animate(root.current, scope => {
    const dialog = modal && scope.querySelector('dialog[open]');
    if (dialog) gsap.fromTo(dialog, { opacity: 0, y: 8 }, {
      opacity: 1, y: 0, duration: .2, ease: 'power2.out', clearProps: 'opacity,transform',
    });
  }), [root, modal]);

  useEffect(() => animate(root.current, scope => {
    if (messageCount <= 2 && !busy) return;
    const messages = scope.querySelectorAll('.message');
    const target = busy ? scope.querySelector('.busy-state') : messages[messages.length - 1];
    if (target) gsap.fromTo(target, { opacity: 0, y: 6 }, {
      opacity: 1, y: 0, duration: .24, ease: 'power2.out', clearProps: 'opacity,transform',
    });
  }), [root, messageCount, busy]);
}
