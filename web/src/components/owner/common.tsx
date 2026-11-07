import type { ReactNode } from 'react';
import { CheckCircledIcon, ExclamationTriangleIcon, InfoCircledIcon } from '@radix-ui/react-icons';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { stateLabels, type OwnerEvidenceLocation } from '@/lib/owner-api';
import { formatMoney } from '@/lib/ledger';
import { cn } from '@/lib/utils';

export function StatusBadge({ status }: { status: string }) {
  // Tones follow the brand swatch: soft sky for live work, the lemon band for
  // anything waiting on a person, restrained green/red for settled outcomes.
  const tone = ['failed','precheck_failed'].includes(status) ? 'border-[#f0c8c3] bg-[#fbe7e4] text-[#a63a32]' :
    ['running','processing','checking'].includes(status) ? 'border-[#9ddde8] bg-[#dff4fa] text-[#243e4c]' :
    ['paused','awaiting_owner_review','awaiting_customer','waiting_customer','waiting_owner','needs_info','ready_with_warnings','in_review'].includes(status) ? 'border-[#e6e3a6] bg-[#fffedb] text-[#5c5a26]' :
    ['delivered','succeeded','published','resolved'].includes(status) ? 'border-[#bfe3c9] bg-[#e9f7ed] text-[#285c3a]' : 'border-border bg-muted/60 text-muted-foreground';
  return <Badge variant="outline" className={cn('gap-1.5 rounded-md px-2 py-1 text-[11px] font-normal', tone)}><span className={cn('size-1.5 rounded-full bg-current', ['running','checking'].includes(status) && 'motion-safe:animate-pulse')}/>{stateLabels[status] || status}</Badge>;
}
export function EmptyState({ title, description, action, icon }: { title: string; description: string; action?: ReactNode; icon?: ReactNode }) {
  return <div className="flex min-h-52 flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border px-6 py-10 text-center"><span className="flex size-10 items-center justify-center rounded-xl bg-muted text-muted-foreground">{icon || <InfoCircledIcon className="size-5"/>}</span><div><h3 className="text-sm font-medium">{title}</h3><p className="mt-1.5 max-w-sm text-xs leading-6 text-muted-foreground">{description}</p></div>{action}</div>;
}
export function ErrorNotice({ message, retry }: { message: string; retry?: () => void }) {
  return <Alert variant="destructive" className="rounded-xl border-[#f0c8c3] bg-[#fbe7e4] text-[#a63a32]"><ExclamationTriangleIcon/><AlertTitle>操作未完成</AlertTitle><AlertDescription className="flex flex-wrap items-center gap-3">{message}{retry && <Button size="sm" variant="outline" onClick={retry}>重新加载</Button>}</AlertDescription></Alert>;
}
export function SuccessNotice({ children }: { children: ReactNode }) {
  return <Alert className="rounded-xl border-[#bfe3c9] bg-[#e9f7ed] text-[#285c3a]"><CheckCircledIcon/><AlertDescription>{children}</AlertDescription></Alert>;
}
export function PanelSkeleton() {
  return <div aria-label="正在加载" className="space-y-5"><Skeleton className="h-6 w-44"/><Skeleton className="h-4 w-72 max-w-full"/><div className="grid gap-3 sm:grid-cols-2"><Skeleton className="h-28"/><Skeleton className="h-28"/></div><Skeleton className="h-48 w-full"/></div>;
}
const evidenceFieldMeta: Record<string, { label: string; hint: string }> = {
  issue_date: { label: '开票日期', hint: '必填，需能解析成日期，并且落在订单账期内' },
  seller: { label: '销售方', hint: '必填，需能识别出交易对手，不能为空或纯空白' },
  buyer: { label: '购买方', hint: '必填，需能识别出交易对手，不能为空或纯空白' },
  total_amount_cents: { label: '价税合计', hint: '必填，正数，单位是分（1 元 = 100 分）' },
  extraction_status: { label: '票据识别状态', hint: '必须为 ready；needs_review 或 invalid 都要先人工确认' },
  invoice_number: { label: '发票号码', hint: '为空时改用源文件指纹判断是否重复' },
  amount_cents: { label: '不含税金额', hint: '不小于 0，单位是分' },
  tax_cents: { label: '税额', hint: '不小于 0，单位是分' },
  external_id: { label: '流水编号', hint: '银行流水自带的外部唯一编号' },
  transaction_date: { label: '交易日期', hint: '需落在订单账期内' },
  direction: { label: '收支方向', hint: 'IN 为收入，OUT 为支出' },
};
const evidenceKeyLabels: Record<string, string> = {
  missing_or_invalid_fields: '待确认字段', duplicate_of_invoice_id: '被重复的票据', duplicate_of_transaction_id: '被重复的流水',
  candidate_transaction_ids: '候选流水', competing_invoice_ids: '同时命中的票据', basis: '判重依据', reason: '判定原因',
  invoice_amount_cents: '票据金额', transaction_amount_cents: '流水金额', amount_cents: '金额',
  normalized_counterparty: '规范化交易对手', date_difference_days: '日期相差天数', invoice_date: '票据日期',
  transaction_date: '流水日期', input_revision: '输入版本', input_refs: '引用的输入', receipts: '工具回执', tool: '工具',
};
const evidenceValueLabels: Record<string, Record<string, string>> = {
  basis: { invoice_number: '发票号码相同', source_file_sha256: '源文件指纹相同', external_id: '流水编号相同', exact_fields: '日期、对手方、方向、金额、摘要全部相同' },
  reason: { invoice_outside_order_period: '票据日期不在订单账期内', studio_identity_ambiguous: '无法判断本工作室是买方还是卖方', multiple_amount_conflicts: '同期存在多笔金额不同的候选流水' },
  direction: { IN: '收入', OUT: '支出' },
  extraction_status: { ready: '已识别完成', needs_review: '需人工复核', invalid: '识别失败' },
};
const shortId = (text: string) => text.length > 12 ? `${text.slice(0, 8)}…` : text;
function EvidenceValue({ name, value }: { name: string; value: unknown }) {
  if (value === null || value === undefined || value === '') return <span className="text-muted-foreground">—</span>;
  if (typeof value === 'boolean') return <>{value ? '是' : '否'}</>;
  if (typeof value === 'number') return <span className="font-mono">{name.endsWith('_cents') ? formatMoney(value) : value}</span>;
  if (Array.isArray(value)) {
    if (!value.length) return <span className="text-muted-foreground">无</span>;
    if (value.some(item => typeof item === 'object' && item !== null)) return <ol className="space-y-1">{value.map((item, index) => <li key={index}><code className="block overflow-x-auto rounded bg-muted/60 px-2 py-1 font-mono text-[11px]">{JSON.stringify(item)}</code></li>)}</ol>;
    return <span className="flex flex-wrap gap-1">{value.map((item, index) => <Badge key={index} variant="outline" title={String(item)} className="rounded-md font-normal">{name.endsWith('_fields') ? `${evidenceFieldMeta[String(item)]?.label || item} ${item}` : shortId(String(item))}</Badge>)}</span>;
  }
  if (typeof value === 'object') return <code className="block overflow-x-auto rounded bg-muted/60 px-2 py-1 font-mono text-[11px]">{JSON.stringify(value)}</code>;
  const text = String(value);
  return <span className="font-mono break-all">{evidenceValueLabels[name]?.[text] || text}</span>;
}
export function EvidenceDetails({ value, title = '查看证据与来源', location }: { value: unknown; title?: string; location?: OwnerEvidenceLocation | null }) {
  const record = value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
  const missing = record && Array.isArray(record.missing_or_invalid_fields) ? record.missing_or_invalid_fields as string[] : [];
  const basis = record ? Object.entries(record).filter(([key]) => key !== 'missing_or_invalid_fields') : [];
  const scope = record?.missing_or_invalid_fields ? '票据记录（invoice_records）' : null;
  const hint = [location ? `${location.table_label} · ${location.row_number ? `第 ${location.row_number} ${location.row_unit || '行'}` : '未定位到具体行'}` : null, missing.length ? `${missing.length} 个字段待确认` : null].filter(Boolean).join(' · ');
  return <details className="rounded-lg border border-border bg-muted/30 text-xs">
    <summary className="flex cursor-pointer flex-wrap items-baseline gap-2 px-3 py-2.5 text-muted-foreground hover:text-foreground"><span>{title}</span>{hint && <span className="text-[11px] text-muted-foreground">{hint}</span>}</summary>
    <div className="space-y-4 border-t px-3 py-3">
      {location && <dl className="grid grid-cols-2 gap-x-4 gap-y-2 rounded-lg border bg-card px-3 py-2.5 text-[11px] sm:grid-cols-4">
        <div><dt className="text-muted-foreground">来源表</dt><dd className="mt-0.5">{location.table_label}<span className="ml-1 font-mono text-[10px] text-muted-foreground">{location.table}</span></dd></div>
        <div><dt className="text-muted-foreground">位置</dt><dd className="mt-0.5">{location.row_number ? `第 ${location.row_number} ${location.row_unit || '行'}` : '—'}</dd></div>
        <div><dt className="text-muted-foreground">记录</dt><dd className="mt-0.5 font-mono break-all">{location.record_label || location.record_id || '—'}</dd></div>
        <div><dt className="text-muted-foreground">{location.source_file ? '原始文件' : '发生日期'}</dt><dd className="mt-0.5 break-all">{location.source_file || location.occurred_on || '—'}</dd></div>
      </dl>}
      {record?.missing_or_invalid_fields !== undefined && <section>
        <p className="font-medium text-muted-foreground">待确认字段{scope ? ` · 来自${scope}` : ''}</p>
        <ul className="mt-2 space-y-2">{missing.map(name => <li key={name} className="rounded-md border bg-card px-3 py-2"><p className="text-xs font-medium">{evidenceFieldMeta[name]?.label || name}<span className="ml-1 font-mono text-[10px] text-muted-foreground">{name}</span></p>{evidenceFieldMeta[name]?.hint && <p className="mt-1 text-[11px] leading-5 text-muted-foreground">{evidenceFieldMeta[name].hint}</p>}</li>)}{!missing.length && <li className="text-muted-foreground">无</li>}</ul>
      </section>}
      {basis.length > 0 && <section>
        <p className="font-medium text-muted-foreground">判定依据</p>
        <dl className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">{basis.map(([key, item]) => <div key={key} className="rounded-md border bg-card px-3 py-2"><dt className="text-[11px] text-muted-foreground">{evidenceKeyLabels[key] || key}<span className="ml-1 font-mono text-[10px]">{key}</span></dt><dd className="mt-1"><EvidenceValue name={key} value={item}/></dd></div>)}</dl>
      </section>}
      {!record && Array.isArray(value) && <section>
        <p className="font-medium text-muted-foreground">引用清单（{value.length}）</p>
        <ul className="mt-2 space-y-1">{value.map((item, index) => <li key={index} className="font-mono break-all">{typeof item === 'string' ? item : JSON.stringify(item)}</li>)}{!value.length && <li className="text-muted-foreground">无</li>}</ul>
      </section>}
      <details className="text-[11px] text-muted-foreground"><summary className="cursor-pointer hover:text-foreground">查看原始数据</summary><pre className="mt-2 max-h-56 overflow-auto rounded-md bg-muted/50 p-2 leading-5 whitespace-pre-wrap break-all">{JSON.stringify(value, null, 2)}</pre></details>
    </div>
  </details>;
}
