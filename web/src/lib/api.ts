export function customerId() {
  return typeof window === 'undefined' ? 'local-customer' : localStorage.getItem('ledgercrew.customer-id') || 'local-customer';
}

export async function api<T>(path: string, options: RequestInit = {}, user = customerId()): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set('X-User-Id', user);
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const response = await fetch('/api/v1' + path, { ...options, headers, cache: 'no-store' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const message = error.error?.message || (typeof error.detail === 'string' ? error.detail : '请求未完成，请检查输入或稍后重试');
    throw new ApiError(`${message}（${response.status}）`, response.status);
  }
  return response.json();
}

export async function download(path: string, name: string, user = customerId()) {
  const response = await fetch('/api/v1' + path, { headers: { 'X-User-Id': user } });
  if (!response.ok) throw new Error(`下载失败（${response.status}）`);
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = name; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function subscribe(path: string, onEvent: () => void, onState: (connected: boolean) => void, user = customerId()) {
  const controller = new AbortController();
  let cursor = 0;
  void (async () => {
    while (!controller.signal.aborted) {
      try {
        const response = await fetch('/api/v1' + path + (path.includes('?') ? '&' : '?') + `after_id=${cursor}`, {
          headers: { 'X-User-Id': user, ...(cursor ? { 'Last-Event-ID': String(cursor) } : {}) },
          signal: controller.signal,
        });
        if (!response.ok || !response.body) throw new Error('订阅未连接');
        onState(true);
        const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = '';
        while (true) {
          const { done, value } = await reader.read(); if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let split;
          while ((split = buffer.indexOf('\n\n')) !== -1) {
            const event = buffer.slice(0, split); buffer = buffer.slice(split + 2);
            if (event.startsWith(':')) continue;
            const id = /^id: (\d+)$/m.exec(event); if (id) cursor = Number(id[1]);
            if (/^data:/m.test(event)) onEvent();
          }
        }
      } catch { if (controller.signal.aborted) break; }
      onState(false);
      await new Promise(resolve => setTimeout(resolve, 1500));
    }
  })();
  return () => controller.abort();
}

export type Order = { id: string; order_no: string; period_start: string; period_end: string; studio_id: string; status: string; input_revision: number };
export type Material = { id: string; original_filename: string; file_category: string; file_size: number; validation_status: string; is_active: boolean };
export type Message = { id: string; role: string; content: string; status: string; workflow_run_id?: string; file_ids: string[]; created_at: string };
export type Run = { id: string; status: string; stage: string; wait_reason?: string; requests_used: number; request_limit: number; batch_current: boolean; error?: string };
export type Batch = { id: string; matched_count: number; unmatched_count: number; exception_count: number; income_total_cents: number; expense_total_cents: number; net_cash_change_cents: number };
export type Invoice = { id: string; source_file_id: string; seller: string | null; buyer: string | null; total_amount_cents: number | null; issue_date: string | null; invoice_number: string | null; extraction_status: string };
export type Transaction = { id: string; transaction_date: string; counterparty: string; amount_cents: number; source_file_id?: string };
export type Match = { id: string; invoice_id: string; transaction_id: string; evidence_json: Record<string, unknown> };
export type Ticket = { id: string; exception_no: string; exception_type: string; status: string; invoice_id: string | null; transaction_id: string | null; related_amount_cents: number | null; difference_cents: number | null; evidence_json: Record<string, unknown> };
export type Report = { id: string; version: number; status: string; report_content: string; financial_summary: Record<string, number>; unresolved_items: string[]; source_revision: number | null; created_at: string };
export const issueLabels: Record<string, string> = { AMOUNT_MISMATCH: '金额差异', MISSING_INVOICE: '缺少票据', MISSING_TRANSACTION: '缺少流水', DUPLICATE_INVOICE: '重复票据', DUPLICATE_TRANSACTION: '重复流水', MULTIPLE_CANDIDATES: '多个候选', INVOICE_FIELD_MISSING: '票据字段待确认', COUNTERPARTY_OR_DATE_CONFLICT: '交易方或日期待核实' };
export const statuses: Record<string, string> = { draft: '等待材料', awaiting_materials: '等待材料', ready_to_process: '材料已就绪', processing: '处理中', awaiting_customer: '等待补充', awaiting_owner_review: '等待老板复核', approved: '已批准待交付', delivered: '已交付', failed: '处理未完成', queued: '排队中', running: '执行中', paused: '等待人工', succeeded: '本轮完成' };
export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}
