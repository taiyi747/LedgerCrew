'use client';

import { memo, useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Separator } from '@/components/ui/separator';
import { EmptyState, ErrorNotice, EvidenceDetails, PanelSkeleton, StatusBadge } from './common';
import { DESK_DEFS, deskSVG, type DeskVisual } from './desk-art';
import { PanelBackdrop } from './panel-backdrop';
import { ownerApi, roleLabels, stateLabels, taskLabels, todoStatusLabels, toolLabels, timeLabel, type OwnerAgent, type OwnerTrace } from '@/lib/owner-api';

export function DeskDefinitions() {
  return <div aria-hidden="true" dangerouslySetInnerHTML={{__html:DESK_DEFS}}/>;
}

const DeskArtwork = memo(function DeskArtwork({visual, seed}:{visual:DeskVisual; seed:string}) {
  // Only repository-owned static SVG and constant colors enter this markup; the
  // bar widths and step timings are derived from the desk's own id.
  return <span className="warroom-desk-svg" aria-hidden="true" dangerouslySetInnerHTML={{__html:deskSVG(visual, seed)}}/>;
});

const deskStatusLabel = (agent: OwnerAgent) =>
  agent.status === 'waiting_children' && agent.waiting_on?.length
    ? `等待${agent.waiting_on.map(r => roleLabels[r] || r).join('、')}`
    : stateLabels[agent.status] || agent.status;

export function AgentDesk({agent,onOpen,disabled=false}:{agent:OwnerAgent;onOpen:()=>void;disabled?:boolean}) {
  const visual:DeskVisual=agent.status==='running'?'working':agent.status==='failed'?'urgent':['paused','waiting_children','queued'].includes(agent.status)?'dormant':'idle';
  return <button type="button" className="warroom-desk" disabled={disabled} onClick={onOpen} aria-label={`${agent.name} · ${deskStatusLabel(agent)}`}>
    <span className="warroom-nameplate">{agent.name}</span>
    <span className="warroom-art-wrap"><DeskArtwork visual={visual} seed={agent.id}/><Badge variant="secondary" className={`warroom-desk-pill warroom-desk-pill-${visual}`}>{deskStatusLabel(agent)}</Badge></span>
    <small>{agent.model} · 完成 {agent.completed} · 失败 {agent.failed} · 排队 {agent.queued}{agent.todos?.total ? ` · 待办 ${agent.todos.done}/${agent.todos.total}` : ''}</small>
  </button>;
}

export function AgentTraceSheet({ role, orderId, onClose }: { role: string | null; orderId: string; onClose: () => void }) {
  const [trace, setTrace] = useState<OwnerTrace | null>(null), [error, setError] = useState('');
  useEffect(() => { if (!role || !orderId) return; let active = true; setTrace(null); setError('');
    const load = () => { void ownerApi<OwnerTrace>(`/owner/agents/${role}/trace?order_id=${encodeURIComponent(orderId)}`).then(t => { if (active) setTrace(t); }).catch(e => { if (active) setError(e.message); }); };
    load();
    const timer = setInterval(load, 4000);
    return () => { active = false; clearInterval(timer); };
  }, [role, orderId]);
  return <Sheet open={!!role} onOpenChange={open => { if (!open) onClose(); }}><SheetContent className="owner-sheet gap-0 p-0"><PanelBackdrop/><SheetHeader className="border-b px-6 py-5"><SheetTitle>{roleLabels[role || ''] || 'Agent'} · 执行轨迹</SheetTitle><SheetDescription>查看总管派单、工具回执和业务成果。</SheetDescription></SheetHeader><div className="flex-1 overflow-y-auto px-6 py-6">{error ? <ErrorNotice message={error}/> : !trace ? <PanelSkeleton/> : <Tabs defaultValue={role === 'supervisor' ? 'decisions' : 'delegations'}><TabsList className="mb-5"><TabsTrigger value="delegations">派单与回执 <span className="ml-1 text-xs opacity-60">{trace.delegations.length}</span></TabsTrigger>{role === 'supervisor' && <TabsTrigger value="decisions">总管决策</TabsTrigger>}<TabsTrigger value="tasks">执行记录</TabsTrigger></TabsList><TabsContent value="delegations" className="space-y-4">{trace.delegations.map(d => <section key={d.id} className="rounded-xl border bg-card p-5"><div className="mb-3 flex items-center justify-between gap-3"><Badge variant="secondary">{taskLabels[d.task_type] || d.task_type}</Badge><StatusBadge status={d.status}/></div><p className="text-sm leading-7">{d.goal}</p>{!!d.todos?.length&&<ol className="my-3 space-y-1.5 rounded-lg border p-3">{d.todos.map(t=><li key={t.id} className="flex items-start gap-2.5 text-xs leading-5"><Badge variant="outline" className="mt-0.5 shrink-0 font-normal">{todoStatusLabels[t.status]||t.status}</Badge><span className="min-w-0"><span className="text-sm leading-6">{t.title}</span>{t.detail&&<span className="ml-2 text-muted-foreground">{t.detail}</span>}</span></li>)}</ol>}{d.result?.summary && <p className="mt-3 text-xs leading-6 text-muted-foreground">{d.result.summary}</p>}<div className="my-4 flex flex-wrap gap-2">{d.receipts.map((r,i) => <Badge variant="outline" key={i} className="max-w-full break-all whitespace-normal font-normal">{toolLabels[r.tool] || r.tool}</Badge>)}</div>{d.error && <ErrorNotice message={d.error}/>}<EvidenceDetails title="工具回执与输入来源" value={{input_revision:d.input_revision,input_refs:d.input_refs,receipts:d.receipts}}/></section>)}{!trace.delegations.length && <EmptyState title="暂无专业派单" description="总管创建派单后，实际目标、工具和成果会显示在这里。"/>}</TabsContent><TabsContent value="decisions" className="space-y-5">{trace.decisions.map(d => <section className="border-l-2 border-primary/25 pl-5" key={d.decision_id}><p className="mb-2 text-xs font-medium text-primary">{{delegated:'委派专业任务',waiting_owner:'请求老板决定',waiting_customer:'等待客户补充',completed:'确认流程完成'}[d.action] || d.action}</p><p className="text-sm leading-7">{d.summary}</p><p className="mt-3 text-[11px] text-muted-foreground">{d.delegation_ids?.length ? `关联 ${d.delegation_ids.length} 项专业任务` : '业务状态已记录'}</p></section>)}{!trace.decisions.length && <EmptyState title="暂无决策记录" description="总管开始处理订单后显示实际决策。"/>}</TabsContent><TabsContent value="tasks" className="space-y-1">{trace.tasks.map(t => <div key={t.id} className="py-4"><div className="flex items-center justify-between gap-3"><p className="text-sm font-medium">{taskLabels[t.task_type] || t.task_type}</p><StatusBadge status={t.status}/></div><p className="mt-2 text-xs text-muted-foreground">{timeLabel(t.started_at)} → {timeLabel(t.ended_at)}</p>{t.error_message && <p className="mt-2 text-xs leading-6 text-destructive">{t.error_message}</p>}<Separator className="mt-4"/></div>)}{!trace.tasks.length && <EmptyState title="暂无执行记录" description="实际模型任务开始后显示状态与时间。"/>}</TabsContent></Tabs>}</div></SheetContent></Sheet>;
}
