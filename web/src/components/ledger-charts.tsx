'use client';

import { useState } from 'react';
import { formatMoney, getSummary, type LedgerRow } from '@/lib/ledger';
import { getChartData, type TransactionStatus } from '@/lib/chart-data';

type Props = {
  rows: LedgerRow[];
  selectedStatus: string;
  onOpenEvidence: (row: LedgerRow) => void;
  onSelectStatus: (status: TransactionStatus) => void;
};
const categoryColors: Record<TransactionStatus, string> = {
  matched: 'var(--accent)', difference: 'var(--review)', missing: 'var(--ink)',
};
const shortNames: Record<string, string> = {
  'LC-001': '和光', 'LC-002': '设备', 'LC-003': '素材',
  'LC-004': '制作', 'LC-005': '印务', 'LC-007': '办公',
};

function arcPath(start: number, length: number) {
  const gap = Math.min(.4, length / 4);
  const angle = (percent: number) => (percent * 3.6 - 90) * Math.PI / 180;
  const a = angle(start + gap), b = angle(start + length - gap);
  return `M ${110 + 76 * Math.cos(a)} ${110 + 76 * Math.sin(a)} A 76 76 0 ${length - gap * 2 > 50 ? 1 : 0} 1 ${110 + 76 * Math.cos(b)} ${110 + 76 * Math.sin(b)}`;
}
export function LedgerCharts({ rows, selectedStatus, onOpenEvidence, onSelectStatus }: Props) {
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [focusId, setFocusId] = useState<string | null>(null);
  const activeId = hoverId ?? focusId;
  const summary = getSummary(rows);
  const { transactions, slices, duplicateCount } = getChartData(rows);
  const maxCents = Math.max(100000, Math.ceil(Math.max(0, ...transactions.flatMap(row => [row.invoiceCents ?? 0, row.transactionCents ?? 0])) / 100000) * 100000);
  const baseline = 190;
  const chartHeight = 160;
  const plotLeft = 42;
  const groupWidth = 310 / Math.max(transactions.length, 1);
  const activeRow = transactions.find(row => row.id === activeId) || transactions.find(row => row.status === 'difference') || transactions[0];
  let offset = 0;

  return <section className="ledger-visuals" aria-label="本期账目图表摘要">
    <div className="metric-grid">
      <div className="metric-card"><span>有效票据合计</span><strong>{formatMoney(summary.invoiceTotalCents)}</strong><small>已排除重复票据</small></div>
      <div className="metric-card"><span>银行流水合计</span><strong>{formatMoney(summary.transactionTotalCents)}</strong><small>{transactions.length} 笔付款</small></div>
      <div className="metric-card"><span>核对一致</span><strong>{summary.matched}<em> 笔</em></strong><small>票据与流水对应</small></div>
      <div className="metric-card"><span>需要核实</span><strong>{summary.difference + summary.duplicate + summary.missing}<em> 项</em></strong><small>差额、重复与缺票</small></div>
    </div>
    <div className="chart-grid">
      <section className="chart-card bar-card" aria-labelledby="bar-chart-title">
        <div className="chart-heading"><h3 id="bar-chart-title">票据与付款金额</h3><span>人民币 / 元</span></div>
        <div className="chart-legend"><span><i className="invoice-swatch"/>票据金额</span><span><i className="payment-swatch"/>银行付款</span></div>
        <svg className="comparison-chart" viewBox="0 0 360 230" role="group" aria-label={`${transactions.length}笔交易的票据和付款金额对比，点击交易查看依据`}>
          {[0, .5, 1].map(fraction => {
            const y = baseline - fraction * chartHeight;
            return <g key={fraction} aria-hidden="true"><line x1={plotLeft} x2="352" y1={y} y2={y} className="chart-grid-line"/><text x="34" y={y + 4} textAnchor="end" className="axis-label">{(maxCents * fraction / 100).toLocaleString('zh-CN')}</text></g>;
          })}
          {transactions.map((row, index) => {
            const x = plotLeft + groupWidth * index + groupWidth / 2;
            const invoiceHeight = (row.invoiceCents ?? 0) / maxCents * chartHeight;
            const transactionHeight = (row.transactionCents ?? 0) / maxCents * chartHeight;
            const label = `${row.counterparty}，票据${row.invoiceCents === null ? '未提供' : formatMoney(row.invoiceCents)}，付款${formatMoney(row.transactionCents!)}，点击查看依据`;
            return <g className="chart-bar-group" key={row.id} role="button" tabIndex={0} aria-label={label}
              onClick={() => onOpenEvidence(row)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpenEvidence(row); } }}
              onPointerEnter={() => setHoverId(row.id)} onPointerLeave={() => setHoverId(null)} onFocus={() => setFocusId(row.id)} onBlur={() => setFocusId(null)}>
              <title>{label}</title>
              <rect className="chart-hit-area" x={x - groupWidth / 2 + 2} y="18" width={groupWidth - 4} height="194" rx="4"/>
              {row.invoiceCents === null ? <text x={x - 9} y={baseline - 5} textAnchor="middle" className="missing-bar-label">缺</text> : <rect x={x - 17} y={baseline - invoiceHeight} width="14" height={invoiceHeight} rx="3" className="invoice-bar"/>}
              <rect className="payment-bar" x={x + 3} y={baseline - transactionHeight} width="14" height={transactionHeight} rx="3" fill="var(--ink)"/>
              <text x={x} y="218" textAnchor="middle" className="bar-caption">{shortNames[row.id] || row.counterparty.slice(0, 2)}</text>
            </g>;
          })}
        </svg>
        <div className="bar-readout" aria-live="polite" aria-atomic="true">{activeRow && <><strong>{activeRow.counterparty}</strong><span>票据 {activeRow.invoiceCents === null ? '未提供' : formatMoney(activeRow.invoiceCents)}<b> / </b>付款 {formatMoney(activeRow.transactionCents!)}</span></>}</div>
        <p className="chart-footnote">点击柱形查看依据 · 缺票不按 0 元计算</p>
      </section>
      <section className="chart-card donut-card" aria-labelledby="donut-chart-title">
        <div className="chart-heading"><h3 id="donut-chart-title">流水核对情况</h3><span>按笔数</span></div>
        <div className="donut-plot"><svg viewBox="0 0 220 220" role="group" aria-label={`流水核对情况：${slices.map(slice => `${slice.label}${slice.count}笔`).join('，')}`}>
          <circle cx="110" cy="110" r="76" fill="none" stroke="var(--raised)" strokeWidth="26"/>
          {slices.map(slice => {
            const fraction = transactions.length ? slice.count / transactions.length : 0;
            const start = offset; offset += fraction * 100;
            if (!slice.count) return null;
            return <path key={slice.status} className="donut-segment" d={arcPath(start, fraction * 100)} fill="none" stroke={categoryColors[slice.status]} strokeWidth={selectedStatus === slice.status ? 31 : 26}

              role="button" tabIndex={0} aria-label={`${slice.label}，${slice.count} 笔，点击筛选明细`} aria-pressed={selectedStatus === slice.status}
              onClick={() => onSelectStatus(slice.status)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelectStatus(slice.status); } }}><title>{`${slice.label} ${slice.count} 笔`}</title></path>;
          })}
          <text x="110" y="109" textAnchor="middle" className="donut-total" aria-hidden="true">{transactions.length}<tspan className="donut-unit"> 笔</tspan></text>
          <text x="110" y="134" textAnchor="middle" className="donut-caption" aria-hidden="true">本期银行流水</text>
        </svg></div>
        <div className="donut-legend" aria-label="按核对状态筛选明细">{slices.map(slice => <button key={slice.status} aria-pressed={selectedStatus === slice.status} disabled={!slice.count} onClick={() => onSelectStatus(slice.status)}><span className="legend-dot" style={{backgroundColor:categoryColors[slice.status]}}/><span>{slice.label}</span><strong>{slice.count}<small> 笔</small></strong></button>)}</div>
        <p className="chart-footnote">另有 {duplicateCount} 张重复票据，未计入本图</p>
      </section>
    </div>
    <p className="totals-explanation">总额相差 <strong>{formatMoney(summary.transactionTotalCents - summary.invoiceTotalCents)}</strong>，包含单笔差额 {formatMoney(summary.differenceCents)} 与缺票付款 {formatMoney(transactions.filter(row => row.status === 'missing').reduce((sum, row) => sum + (row.transactionCents ?? 0), 0))}。</p>
  </section>;
}
