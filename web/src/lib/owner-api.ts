import { api, download, subscribe, type Report } from '@/lib/api';

export type OwnerView = 'overview' | 'orders' | 'intakes' | 'dashboard';
export type OwnerOrder = { id: string; order_no: string; status: string; input_revision: number; period_start: string; period_end: string; studio_id: string; studio_name?: string };
export type OwnerAgent = { id: string; name: string; workspace: string; model: string; status: string; current_task: string | null; queued: number; completed: number; failed: number; todos: { done: number; total: number }; waiting_on: string[] };
export type OwnerException = { id: string; exception_no: string; type: string; status: string; difference_cents: number | null; related_amount_cents: number | null; evidence: Record<string, unknown> };
export type OwnerDashboard = {
  orders: OwnerOrder[]; selected_order_id: string | null;
  run: { id: string; status: string; stage: string; input_revision: number; requests_used: number; request_limit: number; wait_reason: string | null } | null;
  agents: OwnerAgent[]; exceptions: OwnerException[];
  report: { id: string; version: number; status: string; fresh: boolean } | null;
  next_report_version: number; questions: { text: string } | null; risk: { summary: string } | null;
  worker: { at: string; pid: number } | null;
  summary: { orders: number; processing: number; delivered: number; waiting: number };
};
export type DelegationTodo = { id: string; title: string; status: 'pending' | 'running' | 'completed' | 'blocked'; detail: string };
export type OwnerTrace = {
  decisions: { decision_id: string; action: string; summary: string; delegation_ids?: string[] }[];
  tasks: { id: string; order_id: string; task_type: string; status: string; started_at: string | null; ended_at: string | null; delegation_id: string | null; error_message: string | null }[];
  delegations: { id: string; decision_id: string; task_type: string; goal: string; input_revision: number; input_refs: string[]; status: string; result: { summary?: string } | null; receipts: { tool: string; [key: string]: unknown }[]; todos: DelegationTodo[]; error: string | null }[];
};
export type IntakeTodo = { id: string; file_id: string; kind: string; title: string; status: 'pending' | 'running' | 'completed' | 'blocked'; detail: string };
export type OwnerIntake = {
  id: string; studio_name: string | null; period_start: string | null; period_end: string | null; status: string; revision: number; order_id: string | null;
  service: { name: string; price_cents: number; is_simulated: boolean };
  files: { id: string; original_filename: string; category: string; included: boolean; validation_status: string; archive_entry_path: string | null; derived_from_file_id: string | null }[];
  precheck: { status: string; requests_used: number; request_limit: number | null; error: string | null; todos: IntakeTodo[]; result: {
    narrative: { summary: string; questions: string[] }; blockers: { id: string; message: string }[]; warnings: { id: string; message: string }[];
    sampled_file_ids: string[]; note: string;
  } | null } | null;
};
export type OwnerReport = Report & { evidence_references: string[]; reconciliation_summary: { matched_count: number; unmatched_count: number; exception_count: number }; exception_snapshot: { exception_no: string; exception_type: string; status: string; difference_cents: number | null }[] };

export function ownerIdentity() { return typeof window === 'undefined' ? 'owner' : localStorage.getItem('ledgercrew.owner-id') || 'owner'; }
export function ownerApi<T>(path: string, init: RequestInit = {}) { return api<T>(path, init, ownerIdentity()); }
export function ownerDownload(path: string, name: string) { return download(path, name, ownerIdentity()); }
export function ownerSubscribe(onEvent: () => void, onState: (value: boolean) => void) { return subscribe('/owner/events/stream', onEvent, onState, ownerIdentity()); }
export const stateLabels: Record<string, string> = {
  idle: '空闲', queued: '排队中', running: '执行中', waiting_children: '等待子任务', paused: '等待人工', succeeded: '已完成', failed: '执行失败',
  draft: '待材料', processing: '处理中', awaiting_customer: '待客户补充', awaiting_owner_review: '待老板审核', approved: '已批准', delivered: '已交付',
  open: '待处理', waiting_customer: '待客户补充', waiting_owner: '待老板决定', resolved: '已处理', accepted_unresolved: '保留未解决',
  collecting: '收集材料', checking: '预检中', needs_info: '需要补充', ready: '可以受理', ready_with_warnings: '有待确认项', precheck_failed: '预检失败', ordered: '已下单',
  in_review: '待审核', published: '已发布', superseded: '历史版本',
};
export const roleLabels: Record<string, string> = { supervisor: '财税运营总管', invoice_processing: '票据处理', data_reconciliation: '数据核对', customer_reception: '客户服务', risk_delivery: '风险与交付' };
export const intakeTodoLabels: Record<string, string> = { pending: '待处理', running: '读取中', completed: '已完成', blocked: '待确认' };
export const todoStatusLabels: Record<string, string> = { pending: '待办', running: '进行中', completed: '已完成', blocked: '受阻' };
export const taskLabels: Record<string, string> = { workflow_dispatch: '决策与派工', invoice_batch: '批量票据处理', invoice_extraction: '票据识别', reconcile_order: '流水核对', intake: '材料接待', questions: '补充问题草稿', risk_summary: '风险说明', report_draft: '报告草稿', answer_question: '订单问答' };
export const toolLabels: Record<string, string> = { process_invoice_batch: '读取、识别与保存票据', reconcile_transactions: '确定性对账', save_customer_message: '保存受理说明', save_customer_questions: '保存询问草稿', save_risk_summary: '保存风险说明', create_report_draft: '创建报告草稿', save_answer: '保存答复', read_customer_context: '读取订单上下文', plan_todos: '规划待办清单', todo_status: '更新待办进度' };
export function timeLabel(value: string | null | undefined) { return value ? new Intl.DateTimeFormat('zh-CN', { month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'Asia/Shanghai' }).format(new Date(value)) : '—'; }
