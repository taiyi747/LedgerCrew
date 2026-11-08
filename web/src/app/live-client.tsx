'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowDownToLine, ArrowRight, ArrowUp, BookOpenCheck, Check, CheckCheck, ChevronRight, FileImage, FileSpreadsheet, FileText, FolderOpen, LoaderCircle, MessageSquare, Paperclip, Plus, ShieldCheck, TriangleAlert, X } from 'lucide-react';
import { api, ApiError, download, subscribe, issueLabels, statuses, type Batch, type Invoice, type Material, type Message, type Order, type Report, type Run, type Ticket, type Transaction, type Match } from '@/lib/api';
import { formatMoney, validateCsvContent } from '@/lib/ledger';
import { useAccount } from '@/components/account/account-context';
import './live.css';

function Mark() { return <span className="brand-mark"><BookOpenCheck size={23} strokeWidth={1.6}/></span>; }
const issueStates: Record<string,string> = { open:'待老板复核',waiting_customer:'等待你补充',waiting_owner:'补充待复核',resolved:'已处理',accepted_unresolved:'保留未核实事项' };
const financialLabels: Record<string,string> = {income_total_cents:'收入',expense_total_cents:'支出',net_cash_change_cents:'净资金变动'};
type View = { files: Material[]; messages: Message[]; batch: Batch|null; invoices: Invoice[]; transactions: Transaction[]; matches: Match[]; tickets: Ticket[]; reports: Report[]; run: Run|null };
const empty: View = { files:[],messages:[],batch:null,invoices:[],transactions:[],matches:[],tickets:[],reports:[],run:null };
async function optional<T>(path: string, fallback: T): Promise<T> { try { return await api<T>(path); } catch(e) { if(e instanceof ApiError && e.status===404) return fallback; throw e; } }

export default function LiveClient({initialOrderId,onNewConsultation,onBackToIntakes}:{initialOrderId?:string;onNewConsultation?:()=>void;onBackToIntakes?:()=>void}={}) {
  const account=useAccount();
  const [orders,setOrders]=useState<Order[]>([]), [order,setOrder]=useState<Order|null>(null), [orderId,setOrderId]=useState('');
  const [view,setView]=useState<View>(empty),[input,setInput]=useState(''),[pending,setPending]=useState<File[]>([]);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[connected,setConnected]=useState(false);
  const [creating,setCreating]=useState(false),[name,setName]=useState(''),[period,setPeriod]=useState('2026-10');
  const [ticket,setTicket]=useState<Ticket|null>(null),[explanation,setExplanation]=useState(''),[proof,setProof]=useState<File|null>(null),[asInvoice,setAsInvoice]=useState(true);
  const [report,setReport]=useState<Report|null>(null),[materialsOpen,setMaterialsOpen]=useState(false);
  const fileInput=useRef<HTMLInputElement>(null), bottom=useRef<HTMLDivElement>(null), debounce=useRef<ReturnType<typeof setTimeout>|null>(null);
  const lock=useRef(false), selected=useRef(''); selected.current=orderId;
  const refreshSerial=useRef(0);

  const refreshOrders=useCallback(async()=>{
    const all=await api<Order[]>('/orders');setOrders(all);return all;
  },[]);
  const refresh=useCallback(async()=>{
    if(!orderId)return;
    const request=++refreshSerial.current;
    const base=`/orders/${orderId}`;
    const [current,files,messages,run,invoices,transactions,batch,matches,tickets,reports]=await Promise.all([
      api<Order>(base),api<Material[]>(base+'/files'),api<Message[]>(base+'/messages'),api<Run|null>(base+'/runs/current'),
      api<Invoice[]>(base+'/invoices'),api<Transaction[]>(base+'/transactions'),optional<Batch|null>(base+'/reconciliation',null),
      optional<Match[]>(base+'/matches',[]),optional<Ticket[]>(base+'/exceptions',[]),api<Report[]>(base+'/reports'),
    ]);
    if(selected.current!==orderId||request!==refreshSerial.current)return;
    setOrder(current);setView({files,messages,run,invoices,transactions,batch:run?.batch_current?batch:null,matches:run?.batch_current?matches:[],tickets:run?.batch_current?tickets:[],reports});
  },[orderId]);

  useEffect(()=>{ void refreshOrders().then(all=>{
    const saved=initialOrderId||localStorage.getItem('ledgercrew.order-id');
    const current=all.find(o=>o.id===saved)||all[0];if(current){setOrderId(current.id);setOrder(current);}
  }).catch(e=>setError(e.message)); },[refreshOrders,initialOrderId]);
  useEffect(()=>{
    if(!orderId)return;
    localStorage.setItem('ledgercrew.order-id',orderId);setView(empty);setError('');
    void refresh().catch(e=>setError(e.message));
    const stop=subscribe(`/orders/${orderId}/events/stream`,()=>{
      if(debounce.current)clearTimeout(debounce.current);
      debounce.current=setTimeout(()=>void refresh().catch(e=>setError(e.message)),300);
    },setConnected);
    const poll=setInterval(()=>void refresh().catch(e=>setError(e.message)),5000);
    return()=>{refreshSerial.current++;stop();clearInterval(poll);if(debounce.current)clearTimeout(debounce.current);};
  },[orderId,refresh]);
  useEffect(()=>{bottom.current?.scrollIntoView({behavior:'smooth'});},[view.messages.length]);

  async function action(fn:()=>Promise<void>){if(lock.current)return;lock.current=true;setBusy(true);setError('');try{await fn();}catch(e){setError(e instanceof Error?e.message:'操作未完成，请重试');}finally{lock.current=false;setBusy(false);if(orderId)void refresh().catch(e=>setError(e.message));}}
  async function create(){await action(async()=>{
    const studio=await api<{id:string}>('/studios',{method:'POST',body:JSON.stringify({name:name.trim(),business_type:'small_studio'})});
    const [year,month]=period.split('-').map(Number),end=new Date(year,month,0).getDate();
    const created=await api<Order>('/orders',{method:'POST',body:JSON.stringify({studio_id:studio.id,period_start:`${period}-01`,period_end:`${period}-${end}`,service_scope:'monthly_records'})});
    setCreating(false);setOrder(created);setOrderId(created.id);setPending([]);setInput('');await refreshOrders();
  });}
  async function addFiles(list: FileList|null){if(!list)return;setError('');try{
    const files=Array.from(list),existing=view.files.filter(f=>f.is_active);
    const images=files.filter(f=>!f.name.toLowerCase().endsWith('.csv'));
    if(images.length+pending.filter(f=>!f.name.endsWith('.csv')).length+existing.filter(f=>f.file_category==='invoice_image').length>20)throw new Error('每单最多 20 张有效票据');
    if(files.filter(f=>f.name.toLowerCase().endsWith('.csv')).length+pending.filter(f=>f.name.toLowerCase().endsWith('.csv')).length+existing.filter(f=>f.file_category==='bank_statement_csv').length>1)throw new Error('每单固定一份 CSV；修正流水请新建订单');
    for(const file of files){const csv=file.name.toLowerCase().endsWith('.csv');if(!csv&&!/\.(jpe?g|png)$/i.test(file.name))throw new Error('仅支持 JPG、PNG 和 CSV');if(file.size>(csv?2:5)*1024*1024)throw new Error(`${file.name} 超过大小限制`);if(csv){const invalid=validateCsvContent(await file.text());if(invalid)throw new Error(invalid);}}
    setPending(prev=>[...prev,...files]);
  }catch(e){setError((e as Error).message);}finally{if(fileInput.current)fileInput.current.value='';}}
  async function revision(){return (await api<Order>(`/orders/${orderId}`)).input_revision;}
  // 补充材料后重新触发一次处理；由发送动作内部调用，不在界面暴露入口。
  async function process(){if(!orderId)return;const current=await api<Order>(`/orders/${orderId}`);await api(`/orders/${orderId}/runs`,{method:'POST',body:JSON.stringify({idempotency_key:crypto.randomUUID(),expected_revision:current.input_revision})});}
  async function send(){if(!orderId){setCreating(true);return;}await action(async()=>{
    const sentFiles:string[]=[];const hasFiles=pending.length>0;
    for(const file of [...pending]){const csv=file.name.toLowerCase().endsWith('.csv'),form=new FormData();form.append('file_category',csv?'bank_statement_csv':'invoice_image');form.append('files',file);form.append('expected_revision',String(await revision()));
      const uploaded=await api<{files:Material[]}>(`/orders/${orderId}/files`,{method:'POST',body:form});const saved=uploaded.files[0];setPending(prev=>prev.filter(f=>f!==file));sentFiles.push(saved.id);
      if(saved.validation_status!=='valid')throw new Error(`${file.name} 未通过后端格式检查`);
      if(csv){const imported=await api<{failed_rows:number;success_rows:number;errors:{row_number:number;reason:string}[]}>(`/orders/${orderId}/imports/csv`,{method:'POST',body:JSON.stringify({file_id:saved.id,expected_revision:await revision()})});if(imported.failed_rows)throw new Error(`流水有 ${imported.failed_rows} 行未通过：${imported.errors.map(e=>`第${e.row_number}行 ${e.reason}`).join('；')}。请修正后新建订单。`);}
    }
    await api(`/orders/${orderId}/messages`,{method:'POST',body:JSON.stringify({client_message_id:crypto.randomUUID(),content:input.trim()||'请处理本期材料。',intent:hasFiles?'materials':'question',file_ids:sentFiles})});setInput('');
    if(hasFiles)await process();
  });}
  async function supplement(){if(!ticket)return;await action(async()=>{
    const form=new FormData();if(explanation.trim())form.append('explanation',explanation.trim());
    if(proof&&asInvoice){const upload=new FormData();upload.append('file_category','invoice_image');upload.append('files',proof);upload.append('expected_revision',String(await revision()));const old=view.invoices.find(i=>i.id===ticket.invoice_id);if(ticket.exception_type==='INVOICE_FIELD_MISSING'&&old)upload.append('replaces_file_id',old.source_file_id);const result=await api<{files:Material[]}>(`/orders/${orderId}/files`,{method:'POST',body:upload});form.append('existing_file_id',result.files[0].id);}
    else if(proof)form.append('file',proof);
    form.append('expected_revision',String(await revision()));
    await api(`/exceptions/${ticket.id}/supplements`,{method:'POST',body:form});setTicket(null);setProof(null);setExplanation('');
  });}
  const processing=!!view.run&&['queued','running'].includes(view.run.status);
  const waitingChat=view.messages.some(m=>m.role==='user'&&m.workflow_run_id&&!view.messages.some(a=>a.role==='assistant'&&a.workflow_run_id===m.workflow_run_id));
  const invoices=new Map(view.invoices.map(i=>[i.id,i])),transactions=new Map(view.transactions.map(t=>[t.id,t]));
  const visibleFiles=view.files.filter(f=>f.is_active);
  function materials(){return <div className="material-content"><div className="section-title"><span>本单真实材料</span><span>{visibleFiles.length} 份</span></div><div className="file-list">{visibleFiles.map(file=><button className="file-row" key={file.id} onClick={()=>void action(()=>download(`/files/${file.id}/download`,file.original_filename))}><span className={`file-icon ${file.file_category==='bank_statement_csv'?'csv':''}`}>{file.file_category==='bank_statement_csv'?<FileSpreadsheet size={18}/>:<FileImage size={18}/>}</span><span className="file-info"><span>{file.original_filename}</span><small>{(file.file_size/1024).toFixed(1)} KB · {file.validation_status==='valid'?'已保存':'需要重新上传'}</small></span><Check size={13}/></button>)}{!visibleFiles.length&&<div className="empty-files"><FolderOpen size={28}/><p>还没有上传材料</p><span>选择票据和一份标准 CSV 流水</span></div>}</div><a className="add-material" href="/api/v1/templates/statement.csv"><ArrowDownToLine size={14}/>下载流水模板</a>{view.reports.map(item=><button className="report-file" key={item.id} onClick={()=>setReport(item)}><FileText size={22}/><span><strong>账目核对报告 v{item.version}</strong><small>已发布 · 可追溯原始材料</small></span><ChevronRight size={16}/></button>)}{!view.reports.length&&<p className="report-note">报告经老板审核发布后在此领取。</p>}</div>;}

  return <div className="app-shell">
    <aside className="sidebar"><a className="brand" href="/"><Mark/><span><strong>小账房</strong><small>LedgerCrew</small></span></a><button className="new-chat" onClick={()=>onNewConsultation?onNewConsultation():setCreating(true)}><Plus size={18}/>新建咨询</button><nav className="main-nav">{onBackToIntakes&&<button className="nav-item" onClick={onBackToIntakes}>接洽与材料预检</button>}<button className="nav-item active"><MessageSquare size={17}/>财务咨询</button><button className="nav-item" onClick={()=>setMaterialsOpen(true)}><FolderOpen size={17}/>材料与报告</button>{account?.role==='owner'&&<a className="nav-item" href="/owner/" target="_blank" rel="noreferrer"><BookOpenCheck size={17}/>老板控制台</a>}</nav><div className="history"><div className="history-label">真实订单</div>{orders.map(item=><button className={`history-item ${orderId===item.id?'selected':''}`} key={item.id} onClick={()=>{setOrderId(item.id);setOrder(item);}}><span><span className="history-title">{item.period_start.slice(0,7)} 账目核对</span><small>{statuses[item.status]||item.status}</small></span></button>)}</div><div className="sidebar-bottom"><div className="quiet-note"><p>每一笔，<br/>都有据可查。</p></div></div></aside>
    <main className="main-area"><header className="topbar"><div className="breadcrumb"><span>工作台</span><ChevronRight size={13}/><strong>财务咨询</strong></div><span className="preview-label"><span/>{connected?'实时连接':'等待连接'}</span></header><div className="workspace-body"><section className="chat-panel" aria-label="财务咨询聊天"><header className="conversation-header"><div><div className="title-line"><h1>{order?`${order.period_start.slice(0,7)} 账目核对`:'新的账目咨询'}</h1><span className="conversation-status"><span/>{view.run?statuses[view.run.status]||view.run.status:order?statuses[order.status]:'请先建档'}</span></div><p>{order?`${order.period_start} — ${order.period_end}`:'确认工作室和账期后上传本期材料'}</p></div><button className="text-button" onClick={()=>setMaterialsOpen(true)}><FolderOpen size={16}/>材料与报告</button></header>
    {error&&<div className="upload-error" role="alert"><TriangleAlert size={15}/><span>{error}</span><button onClick={()=>setError('')}>关闭</button></div>}
    {view.run?.status==='failed'&&<div className="upload-error"><TriangleAlert size={15}/><span>{view.run.error||'处理未完成'}</span><button onClick={()=>void action(async()=>{await api(`/runs/${view.run!.id}/retry`,{method:'POST'});})}>请总管重试</button></div>}
    <div className="chat-scroll"><div className="chat-content">{!order&&<div className="welcome"><Mark/><span className="welcome-overline">你的真实材料，交给小账房</span><h2>把每一笔账，理清楚。</h2><p>创建订单，提交票据与流水。<br/>总管会安排 AI 员工逐项处理，关键异常由老板复核。</p><div className="welcome-actions"><button onClick={()=>setCreating(true)}><Plus size={18}/><span><strong>建立本期订单</strong><small>确认工作室抬头与账期</small></span><ArrowRight size={16}/></button></div></div>}
      {order&&!view.messages.length&&<div className="welcome"><Mark/><h2>发来本期票据与流水。</h2><p>发送材料后，总管将实际安排票据识别、对账与交付任务。<br/>如果暂时只有票据，可以先上传，再补充流水。</p></div>}
      {view.messages.map(message=><article className={`message ${message.role==='user'?'user':'assistant'}`} key={message.id}>{message.role==='user'?<><div className="user-label">你</div><div className="user-bubble"><p>{message.content}</p>{!!message.file_ids.length&&<div className="message-files">{message.file_ids.map(id=><span key={id}><FileText size={14}/>{view.files.find(f=>f.id===id)?.original_filename||'已提交材料'}</span>)}</div>}</div></>:<><div className="assistant-label"><Mark/><strong>账清助理</strong>{message.status==='failed'&&<span>未完成</span>}</div><div className="assistant-body"><p className="assistant-text">{message.content}</p></div></>}</article>)}
      {(processing||waitingChat)&&<div className="busy-state" role="status"><LoaderCircle size={16} className="live-spin"/><span>{waitingChat?'提问已排队，正在等待答复…':'正在处理本单材料，请稍候…'}</span></div>}
      {view.batch&&view.reports.length>0&&<div className="result-card"><div className="result-heading"><div className="result-heading-top"><span><CheckCheck size={16}/>真实账目核对结果</span><span>{view.run?.wait_reason==='waiting_customer'?'等待补充':'以当前批次为准'}</span></div><h2>{view.batch.matched_count} 笔匹配，{view.batch.exception_count} 项待核实事项</h2><div className="result-stats"><div><span>收入</span><strong>{formatMoney(view.batch.income_total_cents)}</strong></div><div><span>支出</span><strong>{formatMoney(view.batch.expense_total_cents)}</strong></div><div><span>净资金变动</span><strong>{formatMoney(view.batch.net_cash_change_cents)}</strong></div></div></div><div className="table-scroll"><table><thead><tr><th>交易方／凭证</th><th className="number">票据金额</th><th className="number">流水／差额</th><th>核对状态</th><th>依据</th></tr></thead><tbody>{view.matches.map(match=>{const i=invoices.get(match.invoice_id),t=transactions.get(match.transaction_id);return <tr key={match.id}><td><strong>{t?.counterparty||i?.seller||'交易记录'}</strong><small>{i?.invoice_number}</small></td><td className="number">{i?.total_amount_cents==null?'待确认':formatMoney(i.total_amount_cents)}</td><td className="number">{t?formatMoney(t.amount_cents):'—'}</td><td><span className="row-status matched"><Check size={12}/>核对一致</span></td><td><button className="text-button" onClick={()=>{const f=view.files.find(f=>f.id===i?.source_file_id);if(f)void action(()=>download(`/files/${f.id}/download`,f.original_filename));}}>原票据</button></td></tr>;})}{view.tickets.map(item=>{const i=invoices.get(item.invoice_id||''),t=transactions.get(item.transaction_id||'');return <tr key={item.id}><td><strong>{t?.counterparty||i?.seller||issueLabels[item.exception_type]||'待核实'}</strong><small>{i?.invoice_number||item.exception_no}</small></td><td className="number">{i?.total_amount_cents==null?'—':formatMoney(i.total_amount_cents)}</td><td className="number">{item.difference_cents!=null?`差 ${formatMoney(item.difference_cents)}`:t?formatMoney(t.amount_cents):'—'}</td><td><span className="row-status difference">{issueLabels[item.exception_type]||'待核实'}</span><small>{issueStates[item.status]||item.status}</small></td><td><button className="text-button" disabled={['resolved','accepted_unresolved'].includes(item.status)} onClick={()=>{setTicket(item);setExplanation('');setProof(null);setAsInvoice(true);}}>补充说明</button></td></tr>;})}</tbody></table></div><div className="result-footer"><span><ShieldCheck size={14}/>金额与结论均来自后端批次</span><button onClick={()=>void action(()=>download(`/orders/${orderId}/exports/matches.csv`,'匹配明细.csv'))}>下载明细<ArrowDownToLine size={14}/></button></div></div>}
<div ref={bottom}/></div></div>
    <div className="composer-area"><form className="composer" onSubmit={e=>{e.preventDefault();void send();}} onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();void addFiles(e.dataTransfer.files);}}>{pending.length>0&&<div className="pending-files">{pending.map((f,index)=><span key={index}><FileText size={13}/>{f.name}<button type="button" aria-label={`移除${f.name}`} onClick={()=>setPending(prev=>prev.filter((_,i)=>i!==index))}><X size={12}/></button></span>)}</div>}<textarea value={input} onChange={e=>setInput(e.target.value)} aria-label="输入咨询内容" placeholder={order?'问问本单账目，或添加票据与流水…':'先建立本期订单，再提交材料…'} rows={2} maxLength={3000}/><div className="composer-tools"><div><button type="button" className="icon-btn" aria-label="上传票据和流水" onClick={()=>order?fileInput.current?.click():setCreating(true)} disabled={busy||processing}><Paperclip size={19}/></button><span>JPG / PNG / CSV</span></div><button type="submit" className="send-button" aria-label="发送消息" disabled={busy||(!input.trim()&&!pending.length)}><ArrowUp size={20}/></button></div></form><input ref={fileInput} className="sr-only" type="file" accept=".jpg,.jpeg,.png,.csv" multiple onChange={e=>void addFiles(e.target.files)}/><div className="composer-footnote"><span><ShieldCheck size={12}/>仅展示业务状态与可追溯结果</span><span>真实 MiMo · 本机联调</span></div></div></section><aside className="evidence-panel"><div className="aside-heading"><span>材料与报告</span><FolderOpen size={17}/></div>{materials()}<div className="aside-bottom"><BookOpenCheck size={28}/><p>有问题的账，<br/>一起核清楚。</p><span>净资金变动不等于利润或应税所得</span></div></aside></div></main>
    {creating&&<div className="live-modal-backdrop"><section className="modal live-dialog" role="dialog" aria-modal="true" aria-label="建立本期订单"><div className="modal-top"><strong>建立本期订单</strong><button className="icon-btn" onClick={()=>setCreating(false)}><X size={20}/></button></div><form className="workspace-form modal-body" onSubmit={e=>{e.preventDefault();void create();}}><label>工作室名称（与票据抬头一致）<input value={name} onChange={e=>setName(e.target.value)} placeholder="请输入工作室名称" required maxLength={100}/></label><label>账期<input type="month" value={period} onChange={e=>setPeriod(e.target.value)} required/></label><p>本机开发订单，不发生真实扣款。资料创建后按该工作室和账期处理。</p><button className="primary-button" disabled={busy||!name.trim()}>确认建档<ArrowRight size={16}/></button></form></section></div>}
    {ticket&&<div className="live-modal-backdrop"><section className="modal live-dialog" role="dialog" aria-modal="true" aria-label="补充说明"><div className="modal-top"><strong>{issueLabels[ticket.exception_type]||'补充说明'}</strong><button className="icon-btn" onClick={()=>setTicket(null)}><X size={20}/></button></div><div className="modal-body workspace-form"><p>{issueStates[ticket.status]}。补充内容需复核，不会自动改变原始金额。</p><label>说明<textarea value={explanation} onChange={e=>setExplanation(e.target.value)} maxLength={5000}/></label><label>可选凭证<input type="file" accept=".jpg,.jpeg,.png" onChange={e=>setProof(e.target.files?.[0]||null)}/></label>{proof&&<label className="live-checkbox"><input type="checkbox" checked={asInvoice} onChange={e=>setAsInvoice(e.target.checked)}/>这是补充发票；字段不清晰时替换原票据</label>}<button className="primary-button" disabled={busy||(!explanation.trim()&&!proof)} onClick={()=>void supplement()}>提交给总管复核</button></div></section></div>}
    {materialsOpen&&<div className="live-modal-backdrop"><section className="modal live-dialog" role="dialog" aria-modal="true" aria-label="材料与报告"><div className="modal-top"><strong>材料与报告</strong><button className="icon-btn" onClick={()=>setMaterialsOpen(false)}><X size={20}/></button></div>{materials()}</section></div>}
    {report&&<div className="live-modal-backdrop"><section className="modal report-modal live-dialog" role="dialog" aria-modal="true" aria-label="已发布报告"><div className="modal-top"><strong>已发布报告 v{report.version}</strong><button className="icon-btn" onClick={()=>setReport(null)}><X size={20}/></button></div><div className="modal-body print-report"><h2>账目核对报告</h2><p className="report-paragraph">{report.report_content}</p><div className="report-summary">{Object.entries(report.financial_summary).map(([key,value])=><div key={key}><span>{financialLabels[key]||key}</span><strong>{formatMoney(value)}</strong></div>)}</div><h3>未解决事项</h3><ul className="report-issues">{report.unresolved_items.map((note,index)=><li key={index}>{note}</li>)}</ul><div className="modal-actions"><button className="primary-button" onClick={()=>void action(()=>download(`/reports/${report.id}/download`,`账目报告-v${report.version}.html`))}>下载可打印报告</button><button className="secondary-button" onClick={()=>void action(()=>download(`/orders/${orderId}/exports/exceptions.csv`,'异常明细.csv'))}>下载异常 CSV</button></div></div></section></div>}
  </div>;
}
