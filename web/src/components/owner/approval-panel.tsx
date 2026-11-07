'use client';

import { useEffect, useRef, useState } from 'react';
import { ArrowDownIcon, CheckCircledIcon, FileTextIcon, LockClosedIcon } from '@radix-ui/react-icons';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { EmptyState, ErrorNotice, EvidenceDetails, PanelSkeleton, StatusBadge, SuccessNotice } from './common';
import { PanelBackdrop } from './panel-backdrop';
import { issueLabels } from '@/lib/api';
import { formatMoney } from '@/lib/ledger';
import { ownerApi, ownerDownload, type OwnerDashboard, type OwnerException, type OwnerReport } from '@/lib/owner-api';

const decisions = [ ['accept_unresolved','保留未解决事项并继续'], ['request_supplement','请客户补充材料'], ['resolve','确认已处理'], ['reanalyze','交给总管重新分析'], ['correct_classification','纠正业务分类'] ];
const batchDecisions = decisions.filter(([value]) => value !== 'correct_classification');
const settled = (status: string) => ['resolved','accepted_unresolved'].includes(status);

function ExceptionRow({ ticket, disabled, selected, onToggle, onSave }: { ticket: OwnerException; disabled: boolean; selected: boolean; onToggle: () => void; onSave: (ticket: OwnerException, action: string, reason: string, classification: string) => Promise<void> }) {
  const [action,setAction] = useState('accept_unresolved'), [reason,setReason] = useState(''), [classification,setClassification] = useState(''), [open,setOpen] = useState(false);
  return <><TableRow data-testid="owner-exception" className="cursor-pointer hover:bg-muted/40" onClick={()=>setOpen(o=>!o)}><TableCell className="pl-4" onClick={e=>e.stopPropagation()}>{!settled(ticket.status) && <input type="checkbox" className="size-4 accent-[#243e4c]" aria-label={`选择 ${ticket.exception_no}`} checked={selected} onChange={onToggle} disabled={disabled}/>}</TableCell><TableCell><p className="text-sm font-medium">{issueLabels[ticket.type] || ticket.type}</p><p className="mt-1 text-[11px] text-muted-foreground">{ticket.exception_no}</p></TableCell><TableCell className="font-mono text-sm">{ticket.related_amount_cents == null ? '—' : formatMoney(ticket.related_amount_cents)}</TableCell><TableCell className="font-mono text-sm">{ticket.difference_cents == null ? '—' : <span className="text-[#8a7420]">{formatMoney(ticket.difference_cents)}</span>}</TableCell><TableCell><StatusBadge status={ticket.status}/></TableCell><TableCell className="text-right" onClick={e=>e.stopPropagation()}>{settled(ticket.status) ? <span className="text-xs text-muted-foreground">已处理</span> : <Select value={action} onValueChange={v=>{setAction(v);setOpen(true);}} disabled={disabled}><SelectTrigger className="ml-auto h-8 w-44"><SelectValue/></SelectTrigger><SelectContent>{decisions.map(([value,label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent></Select>}</TableCell><TableCell className="pr-4 text-right" onClick={e=>e.stopPropagation()}>{settled(ticket.status) ? <CheckCircledIcon className="inline-block text-muted-foreground"/> : <Button type="button" size="sm" variant="outline" title={reason.trim() ? '保存这个决定' : '点开行详情填写处理理由后可保存'} disabled={disabled || !reason.trim() || (action === 'correct_classification' && !classification.trim())} onClick={()=>void onSave(ticket,action,reason,classification)}>保存</Button>}</TableCell></TableRow>{open&&<TableRow><TableCell colSpan={7} className="bg-muted/30 px-6 py-5 align-top"><article className="rounded-xl border border-border bg-card p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-sm font-medium">{issueLabels[ticket.type] || ticket.type}</p><p className="mt-1 text-[11px] text-muted-foreground">{ticket.exception_no}</p></div><StatusBadge status={ticket.status}/></div><div className="my-4 flex flex-wrap gap-6 text-xs"><div><span className="text-muted-foreground">关联金额</span><p className="mt-1 font-mono text-base">{ticket.related_amount_cents == null ? '—' : formatMoney(ticket.related_amount_cents)}</p></div>{ticket.difference_cents != null && <div><span className="text-muted-foreground">待核实差额</span><p className="mt-1 font-mono text-base text-[#8a7420]">{formatMoney(ticket.difference_cents)}</p></div>}</div><EvidenceDetails value={ticket.evidence} location={ticket.location}/>{settled(ticket.status) ? <p className="mt-4 flex items-center gap-2 text-xs text-muted-foreground"><CheckCircledIcon/>{ticket.status === 'accepted_unresolved' ? '该事项继续在报告中披露。' : '该事项已记录处理决定。'}</p> : <form className="mt-5 space-y-4" onSubmit={e => {e.preventDefault();void onSave(ticket,action,reason,classification);}}><div className="space-y-2"><Label htmlFor={'decision-'+ticket.id}>处理方式</Label><Select value={action} onValueChange={setAction} disabled={disabled}><SelectTrigger id={'decision-'+ticket.id} className="w-full"><SelectValue/></SelectTrigger><SelectContent>{decisions.map(([value,label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent></Select></div>{action === 'correct_classification' && <div className="space-y-2"><Label htmlFor={'classification-'+ticket.id}>更正后的业务分类</Label><Input id={'classification-'+ticket.id} value={classification} onChange={e=>setClassification(e.target.value)} maxLength={100} required/></div>}<div className="space-y-2"><Label htmlFor={'reason-'+ticket.id}>处理理由</Label><Textarea id={'reason-'+ticket.id} value={reason} onChange={e=>setReason(e.target.value)} placeholder="说明你依据什么作出这个决定" maxLength={5000} rows={3} required disabled={disabled}/></div><Button type="submit" disabled={disabled || !reason.trim() || (action === 'correct_classification' && !classification.trim())}>保存这个决定</Button></form>}</article></TableCell></TableRow>}</>;
}

export function ApprovalPanel({ data, refresh, onReport }: { data: OwnerDashboard; refresh: () => Promise<void>; onReport: (id: string) => void }) {
  const [busy,setBusy] = useState(false), [error,setError] = useState('');
  const [selected,setSelected] = useState<Set<string>>(new Set()), [batchAction,setBatchAction] = useState('accept_unresolved'), [batchReason,setBatchReason] = useState('');
  const lock=useRef(false);
  const order=data.orders.find(o=>o.id===data.selected_order_id);
  const running=!!data.run && ['queued','running'].includes(data.run.status);
  const visibleExceptions=data.exceptions.slice(0,2);
  const remainingCount=Math.max(0,data.exceptions.length-visibleExceptions.length);
  async function preserveOtherExceptions(reason:string){
    if(!order)return;
    const fresh=await ownerApi<OwnerDashboard>(`/owner/dashboard?order_id=${encodeURIComponent(order.id)}`);
    if(fresh.exceptions.slice(0,2).some(ticket=>!settled(ticket.status)))return;
    const remaining=fresh.exceptions.slice(2).filter(ticket=>!settled(ticket.status));
    if(!remaining.length)return;
    const current=fresh.orders.find(item=>item.id===order.id)!;
    await ownerApi(`/orders/${order.id}/exceptions/decisions`,{method:'POST',body:JSON.stringify({expected_revision:current.input_revision,target_version:fresh.next_report_version,decisions:remaining.map(ticket=>({exception_id:ticket.id,decision:'accept_unresolved',reason:`管理员完成前两项审核，其余事项保留未解决并写入报告。审核说明：${reason.trim()}`}))})});
  }
  async function save(ticket: OwnerException, action: string, reason: string, classification: string) {
    if(lock.current || !order)return;lock.current=true;setBusy(true);setError('');
    try {
      await ownerApi(`/exceptions/${ticket.id}/decisions`,{method:'POST',body:JSON.stringify({decision:action,reason:reason.trim(),expected_revision:order.input_revision,target_version:data.next_report_version,...(action==='correct_classification'?{classification_after:classification.trim()}: {})})});
      await preserveOtherExceptions(reason);
      await refresh();
    } catch(e) {setError(e instanceof Error?e.message:'决定保存失败');}
    finally {lock.current=false;setBusy(false);}
  }
  async function saveBatch() {
    if(lock.current || !order)return;
    const chosen=visibleExceptions.filter(t=>selected.has(t.id)&&!settled(t.status));
    if(!chosen.length)return;
    lock.current=true;setBusy(true);setError('');
    try {
      // 一批决定原子提交：绑定同一材料/报告版本，后端只推进一次输入版本并唤醒一次总管。
      await ownerApi(`/orders/${order.id}/exceptions/decisions`,{method:'POST',body:JSON.stringify({expected_revision:order.input_revision,target_version:data.next_report_version,decisions:chosen.map(t=>({exception_id:t.id,decision:batchAction,reason:batchReason.trim()}))})});
      await preserveOtherExceptions(batchReason);
      setSelected(new Set());
      setBatchReason('');
      await refresh();
    } catch(e) {setError(e instanceof Error?e.message:'批量决定保存失败');}
    finally {lock.current=false;setBusy(false);}
  }
  if(!order)return <EmptyState title="先选择一个服务订单" description="客户确认服务并下单后，异常与报告会出现在这里。" icon={<FileTextIcon className="size-5"/>}/>;
  return <div className="space-y-5">{error && <ErrorNotice message={error} retry={()=>void refresh()}/>}<div className="rounded-xl border border-border bg-muted/40 p-4 text-xs leading-6 text-muted-foreground"><p className="flex items-center gap-2 font-medium text-foreground"><LockClosedIcon/>输入版本 {order.input_revision} · 目标报告 v{data.next_report_version}</p><p className="mt-1">决定会与当前材料和报告版本绑定。保留未解决事项会继续写入交付报告。</p>{running && <p className="mt-2 text-[#8a7420]">总管正在处理本轮任务，完成后可以提交决定。</p>}</div>{data.risk && <Card className="shadow-none ring-border"><CardHeader><CardTitle className="text-sm">风险与交付 Agent 的说明</CardTitle></CardHeader><CardContent><p className="text-sm leading-7 whitespace-pre-wrap">{data.risk.summary}</p></CardContent></Card>}{data.questions && <details className="rounded-xl border p-4 text-xs"><summary className="cursor-pointer font-medium">客服补充询问草稿</summary><p className="mt-3 leading-7 whitespace-pre-wrap text-muted-foreground">{data.questions.text}</p></details>}<div className="flex items-center justify-between"><h3 className="text-sm font-medium">重点异常 · 前两项</h3><Badge variant="secondary">{visibleExceptions.filter(t=>!settled(t.status)).length} 项待决定</Badge></div>{visibleExceptions.some(t=>!settled(t.status))&&<div className="rounded-xl border border-border bg-card p-4"><div className="flex flex-wrap items-center gap-3 text-sm"><span className="font-medium">批量处理</span><Button type="button" variant="ghost" size="sm" onClick={()=>setSelected(new Set(visibleExceptions.filter(t=>!settled(t.status)).map(t=>t.id)))}>全选待决 {visibleExceptions.filter(t=>!settled(t.status)).length} 项</Button><Button type="button" variant="ghost" size="sm" disabled={!selected.size} onClick={()=>setSelected(new Set())}>清空</Button><span className="text-xs text-muted-foreground">已选 {selected.size} 项</span></div>{!!selected.size&&<form className="mt-3 flex flex-wrap items-end gap-3" onSubmit={e=>{e.preventDefault();void saveBatch();}}><div className="space-y-2"><Label htmlFor="batch-decision">统一处理方式</Label><Select value={batchAction} onValueChange={setBatchAction} disabled={busy||running}><SelectTrigger id="batch-decision" className="w-56"><SelectValue/></SelectTrigger><SelectContent>{batchDecisions.map(([value,label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent></Select></div><div className="min-w-64 flex-1 space-y-2"><Label htmlFor="batch-reason">统一处理理由</Label><Input id="batch-reason" value={batchReason} onChange={e=>setBatchReason(e.target.value)} placeholder="将应用到所有选中事项" disabled={busy||running}/></div><Button type="submit" disabled={busy||running||!batchReason.trim()}>批量保存 {selected.size} 项</Button><p className="w-full text-[11px] text-muted-foreground">「纠正业务分类」需逐项填写新分类，请在单张卡片里处理。</p></form>}</div>}{remainingCount>0&&<p className="rounded-lg bg-muted/50 p-3 text-xs leading-6 text-muted-foreground">后台只展示前两项供管理员处理。其余 {remainingCount} 项会保留为未解决事项，并写入报告；处理完以上两项后进入报告生成。</p>}<div className="overflow-hidden rounded-xl border border-border bg-card">{!data.exceptions.length ? <EmptyState title="当前没有异常待办" description={data.run?'正式核对完成后，异常和依据会显示在这里。':'将材料交给总管后开始正式处理。'}/> : <Table><TableHeader><TableRow><TableHead className="w-10 pl-4"></TableHead><TableHead>异常类型与编号</TableHead><TableHead>关联金额</TableHead><TableHead>待核实差额</TableHead><TableHead>状态</TableHead><TableHead className="text-right">处理方式</TableHead><TableHead className="pr-4 text-right">操作</TableHead></TableRow></TableHeader><TableBody>{visibleExceptions.map(t=><ExceptionRow key={t.id} ticket={t} disabled={busy||running} selected={selected.has(t.id)} onToggle={()=>setSelected(prev=>{const next=new Set(prev);if(next.has(t.id))next.delete(t.id);else next.add(t.id);return next;})} onSave={save}/>)}</TableBody></Table>}</div><Card className="shadow-none ring-border"><CardHeader><CardTitle className="text-sm">生成报告与交付</CardTitle><CardDescription>只有你批准并发布的版本，客户才能领取。</CardDescription></CardHeader><CardContent>{data.report ? <div className="space-y-4"><div className="flex flex-wrap items-center gap-2"><Badge variant="outline">v{data.report.version}</Badge><StatusBadge status={data.report.status}/>{!data.report.fresh && <span className="text-xs text-[#8a7420]">材料或决定已变化，等待新版本</span>}</div><Button variant="outline" onClick={()=>onReport(data.report!.id)}>查看报告并发布给客户</Button></div> : <p className="text-sm leading-6 text-muted-foreground">处理完前两项异常后，总管将生成报告；其余未解决事项会保留披露。</p>}</CardContent></Card></div>;
}

export function ReportSheet({ id, meta, inputRevision, onClose, refresh }: { id: string|null; meta: OwnerDashboard['report']; inputRevision?: number; onClose: ()=>void; refresh:()=>Promise<void> }) {
  const [report,setReport]=useState<OwnerReport|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[reason,setReason]=useState(''),[notice,setNotice]=useState('');
  const lock=useRef(false);
  useEffect(()=>{if(!id)return;let active=true;setReport(null);setError('');setReason('');setNotice('');void ownerApi<OwnerReport>('/reports/'+id).then(r=>{if(active)setReport(r);}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[id]);
  const fresh=!!report&&meta?.id===report.id&&meta.fresh&&report.source_revision===inputRevision;
  async function review(publish: boolean) {
    if(!id||lock.current)return;
    if(!reason.trim()){setError('请填写本次审核或退回的理由。');return;}
    lock.current=true;setBusy(true);setError('');
    try {
      let current=await ownerApi<OwnerReport>('/reports/'+id);
      const body=JSON.stringify({reason:reason.trim()});
      if(publish){
        if(current.status==='draft')current=await ownerApi<OwnerReport>('/reports/'+id+'/submit-review',{method:'POST'});
        if(current.status==='in_review')current=await ownerApi<OwnerReport>('/reports/'+id+'/approve',{method:'POST',body});
        if(current.status==='approved')current=await ownerApi<OwnerReport>('/reports/'+id+'/publish',{method:'POST'});
        setNotice('这个版本已发布，客户可以领取报告。');
      } else {
        if(current.status==='draft')current=await ownerApi<OwnerReport>('/reports/'+id+'/submit-review',{method:'POST'});
        current=await ownerApi<OwnerReport>('/reports/'+id+'/reject',{method:'POST',body});
        setNotice('报告已退回，总管将安排生成新版本。');
      }
      setReport(current);await refresh();
    } catch(e) {setError(e instanceof Error?e.message:'报告审核未完成');const latest=await ownerApi<OwnerReport>('/reports/'+id).catch(()=>null);if(latest)setReport(latest);}
    finally {lock.current=false;setBusy(false);}
  }
  return <Sheet open={!!id} onOpenChange={open=>{if(!open)onClose();}}><SheetContent className="owner-sheet-wide gap-0 p-0"><PanelBackdrop/><SheetHeader className="border-b px-6 py-5"><SheetTitle>报告 {report?'v'+report.version:''} · 审核与交付</SheetTitle><SheetDescription>核对金额、未解决事项和证据，确认后发布给客户。</SheetDescription></SheetHeader><div className="flex-1 space-y-6 overflow-y-auto px-6 py-6">{error&&<ErrorNotice message={error}/>} {notice&&<SuccessNotice>{notice}</SuccessNotice>}{!report ? <PanelSkeleton/> : <><div className="flex flex-wrap items-center justify-between gap-3"><StatusBadge status={report.status}/><Button size="sm" variant="outline" onClick={()=>void ownerDownload(`/reports/${report.id}/download`,`账目核对报告-v${report.version}.html`).catch(e=>setError(e.message))}><ArrowDownIcon/>下载报告</Button></div><div className="grid grid-cols-1 gap-3 border-y py-5 sm:grid-cols-3">{Object.entries(report.financial_summary).map(([key,value])=><div key={key}><p className="text-xs text-muted-foreground">{{income_total_cents:'收入',expense_total_cents:'支出',net_cash_change_cents:'净资金变动'}[key]||key}</p><p className="mt-2 font-mono text-xl tracking-tight">{formatMoney(value)}</p></div>)}</div><section><h3 className="mb-3 text-sm font-medium">核对报告</h3><p className="text-sm leading-8 whitespace-pre-wrap">{report.report_content}</p></section><section><h3 className="mb-3 text-sm font-medium">未解决事项</h3>{report.unresolved_items.length?<ul className="space-y-2 text-sm leading-7 text-muted-foreground">{report.unresolved_items.map((note,i)=><li className="rounded-lg bg-muted/60 px-4 py-3" key={i}>{note}</li>)}</ul>:<p className="text-sm text-muted-foreground">本版本没有未解决事项。</p>}</section>{!!report.exception_snapshot?.length&&<section><h3 className="mb-3 text-sm font-medium">异常快照</h3><Table><TableHeader><TableRow><TableHead>事项</TableHead><TableHead>状态</TableHead><TableHead className="text-right">差额</TableHead></TableRow></TableHeader><TableBody>{report.exception_snapshot.map(t=><TableRow key={t.exception_no}><TableCell>{issueLabels[t.exception_type]||t.exception_type}</TableCell><TableCell><StatusBadge status={t.status}/></TableCell><TableCell className="text-right font-mono">{t.difference_cents==null?'—':formatMoney(t.difference_cents)}</TableCell></TableRow>)}</TableBody></Table></section>}<EvidenceDetails title="查看本版本的证据引用" value={report.evidence_references}/>{report.status!=='published'&&<section className="space-y-4 rounded-xl border p-5"><div className="space-y-2"><Label htmlFor="report-review-reason">审核／退回理由</Label><Textarea id="report-review-reason" value={reason} onChange={e=>setReason(e.target.value)} maxLength={5000} placeholder="填写你核验的依据或需要修改的内容" rows={3}/></div>{!fresh&&<p className="text-xs leading-6 text-[#8a7420]">该版本已退回或输入发生变化，需总管生成新版本后审核。</p>}<div className="flex flex-wrap gap-3"><Button disabled={busy||!fresh||!reason.trim()} onClick={()=>void review(true)}>审核、批准并发布</Button><Button variant="outline" disabled={busy||!fresh||!reason.trim()||report.status==='approved'} onClick={()=>void review(false)}>退回并请总管修订</Button></div></section>}</>}</div></SheetContent></Sheet>;
}
