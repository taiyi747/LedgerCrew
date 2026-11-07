'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ownerApi, ownerSubscribe, type OwnerDashboard } from '@/lib/owner-api';

export function useOwnerDashboard() {
  const [data, setData] = useState<OwnerDashboard | null>(null);
  const [selected, setSelected] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [connected, setConnected] = useState(false);
  const selectedRef = useRef(''), request = useRef(0);
  const refresh = useCallback(async (orderId = selectedRef.current, quiet = true) => {
    const current = ++request.current;
    if (!quiet) setLoading(true);
    try {
      let next = await ownerApi<OwnerDashboard>('/owner/dashboard' + (orderId ? '?order_id=' + encodeURIComponent(orderId) : ''));
      if (orderId && !next.orders.some(o => o.id === orderId)) next = await ownerApi<OwnerDashboard>('/owner/dashboard');
      if (current !== request.current) return;
      setData(next); setError('');
      const chosen = next.selected_order_id || '';
      setSelected(chosen); selectedRef.current = chosen;
      if (chosen) localStorage.setItem('ledgercrew.owner-order', chosen);
    } catch (e) {
      if (current === request.current) setError(e instanceof Error ? e.message : '工作台加载失败');
    } finally { if (current === request.current) setLoading(false); }
  }, []);
  useEffect(() => {
    selectedRef.current = new URLSearchParams(window.location.search).get('order') || localStorage.getItem('ledgercrew.owner-order') || '';
    void refresh(selectedRef.current, false);
    let timer: ReturnType<typeof setTimeout> | null = null;
    const stop = ownerSubscribe(() => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => void refresh(), 220);
    }, setConnected);
    const poll = setInterval(() => void refresh(), 10000);
    return () => { request.current++; stop(); clearInterval(poll); if (timer) clearTimeout(timer); };
  }, [refresh]);
  function choose(id: string) { selectedRef.current = id; setSelected(id); void refresh(id, false); }
  return { data, selected, choose, refresh, loading, error, connected };
}
