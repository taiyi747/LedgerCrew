'use client';

import {useCallback,useEffect,useRef,useState} from 'react';
import {ArrowUp,BookOpenCheck,FileText,LoaderCircle,Paperclip,Plus,ShieldCheck} from 'lucide-react';
import LiveClient from './live-client';
import { useAccount } from '@/components/account/account-context';
import {api,download,subscribe,type Order} from '@/lib/api';
import './live.css';
import './intake.css';

type Item={id:string;original_filename:string;category:string;mime_type:string;included:boolean;validation_status:string;archive_file_id:string|null;archive_entry_path:string|null;replaced_by_file_id:string|null;derived_from_file_id?:string|null;file_size:number};
type Issue={id:string;message:string;file_id:string|null};
type Result={blockers:Issue[];warnings:Issue[];sampled_file_ids:string[];skipped_file_ids?:string[];note:string;narrative:{summary:string;questions:string[]};csv_details:{file_id:string;rows:number;valid_rows:number;errors:{row_number:number;reason:string}[]}[]};
type Service={code:string;version:number;name:string;price_cents:number;currency:string;delivery_note:string;deliverables:string[]};
type Intake={id:string;status:string;revision:number;order_id:string|null;studio_id:string|null;studio_name:string|null;period_start:string|null;period_end:string|null;profile_confirmed:boolean;service:Service;files:Item[];precheck:{id:string;status:string;revision:number;requests_used:number;request_limit:number|null;result:Result|null;error:string|null;todos:MaterialTodo[]}|null;confirmation:{precheck_id:string;revision:number;service_version:number;price_cents:number;warnings:Issue[]}|null};
type Conversation={id:string;role:string;content:string;status:string;file_ids:string[];job_id:string|null};
type History={id:string;studio_name:string|null;status:string;order_id:string|null};
type Studio={id:string;name:string};
type MaterialTodo={id:string;file_id:string;kind:string;title:string;status:'pending'|'running'|'completed'|'blocked'|'skipped';detail:string};
type UploadAttempt={files:File[];status:'uploading'|'failed';error?:string};
const labels:Record<string,string>={collecting:'收集材料',checking:'材料预检中',needs_info:'需要补充资料',ready:'可以受理',ready_with_warnings:'有待确认项',precheck_failed:'预检未完成',ordered:'已创建订单'};
const categoryNames:Record<string,string>={invoice_image:'票据',supporting_material:'说明凭证',bank_statement_csv:'CSV 流水',archive:'原始 ZIP',unclassified:'待选择类别',source_document:'原始文档'};
const todoKinds:Record<string,string>={inspect_archive:'解压压缩包',read_document:'读取材料文件',normalize_statement:'整理流水',prepare_receipts:'整理票据',check_materials:'检查材料'};
const todoStatusNames:Record<string,string>={pending:'待处理',running:'处理中',completed:'已完成',blocked:'待确认',skipped:'已跳过'};
/** 同类待办合并成一行，避免 20 份票据刷出 20 条「读取某文件」。 */
function groupTodos(todos:MaterialTodo[]){const groups:{kind:string;items:MaterialTodo[]}[]=[];for(const task of todos){const last=groups[groups.length-1];if(last&&last.kind===task.kind)last.items.push(task);else groups.push({kind:task.kind,items:[task]});}return groups;}

export default function ReceptionClient(){
  const account=useAccount();
  const [intakes,setIntakes]=useState<History[]>([]),[orders,setOrders]=useState<Order[]>([]),[studios,setStudios]=useState<Studio[]>([]);
  const [id,setId]=useState(''),[orderId,setOrderId]=useState(''),[state,setState]=useState<Intake|null>(null),[messages,setMessages]=useState<Conversation[]>([]);
  const [text,setText]=useState(''),[upload,setUpload]=useState<UploadAttempt|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[connected,setConnected]=useState(false);
  const [name,setName]=useState(''),[period,setPeriod]=useState(''),[studioId,setStudioId]=useState(''),[acks,setAcks]=useState<string[]>([]);
  const lock=useRef(false),current=useRef(''),picker=useRef<HTMLInputElement>(null),replacement=useRef<HTMLInputElement>(null),replacing=useRef<Item|null>(null),key=useRef('');
  const materialCard=useRef<HTMLElement>(null),conversation=useRef<HTMLDivElement>(null),todoList=useRef<HTMLDivElement>(null);
  current.current=id;
  const history=useCallback(async()=>{
    const [a,b,c]=await Promise.all([api<History[]>('/intakes'),api<Order[]>('/orders'),api<Studio[]>('/studios')]);setIntakes(a);setOrders(b);setStudios(c);return {a,b};
  },[]);
  function showOrder(oid:string){localStorage.setItem('ledgercrew.active-view','order');localStorage.setItem('ledgercrew.order-id',oid);setOrderId(oid);}
  const refresh=useCallback(async()=>{
    if(!id)return;
    const [snapshot,chat]=await Promise.all([api<Intake>(`/intakes/${id}`),api<Conversation[]>(`/intakes/${id}/messages`)]);
    if(current.current!==id)return;
    setState(previous=>previous?.id===snapshot.id&&previous.revision>snapshot.revision?previous:snapshot);setMessages(chat);
    if(snapshot.order_id)showOrder(snapshot.order_id);
  },[id]);
  useEffect(()=>{void history().then(({a,b})=>{
    const saved=localStorage.getItem('ledgercrew.intake-id'),chosen=a.find(i=>i.id===saved);
    if(localStorage.getItem('ledgercrew.active-view')==='order'&&b.some(o=>o.id===localStorage.getItem('ledgercrew.order-id'))){setOrderId(localStorage.getItem('ledgercrew.order-id')!);return;}
    if(chosen){if(chosen.order_id)showOrder(chosen.order_id);else setId(chosen.id);}
    else if(a.find(i=>!i.order_id))setId(a.find(i=>!i.order_id)!.id);
    else if(b[0])showOrder(b[0].id);
  }).catch(e=>setError(e.message));},[history]);
  useEffect(()=>{
    if(!id||orderId)return;
    localStorage.setItem('ledgercrew.intake-id',id);localStorage.setItem('ledgercrew.active-view','intake');setState(null);setMessages([]);
    void refresh().catch(e=>setError(e.message));
    let timer:ReturnType<typeof setTimeout>|null=null;
    const stop=subscribe(`/intakes/${id}/events/stream`,()=>{if(timer)clearTimeout(timer);timer=setTimeout(()=>void refresh().catch(e=>setError(e.message)),200);},setConnected);
    return()=>{stop();if(timer)clearTimeout(timer);};
  },[id,orderId,refresh]);
  useEffect(()=>{setAcks([]);key.current=crypto.randomUUID();},[state?.revision,state?.precheck?.id]);
  useEffect(()=>{setName(state?.studio_name||'');setStudioId(state?.studio_id||'');setPeriod(state?.period_start?.slice(0,7)||'');},[state?.id,state?.studio_name,state?.period_start,state?.studio_id]);
  async function action(fn:()=>Promise<void>){if(lock.current)return;lock.current=true;setBusy(true);setError('');try{await fn();}catch(e){setError(e instanceof Error?e.message:'操作未完成');}finally{lock.current=false;setBusy(false);if(id&&!orderId)void refresh().catch(e=>setError(e.message));void history().catch(e=>setError(e.message));}}
  async function ensure(){if(id&&!orderId)return id;const created=await api<Intake>('/intakes',{method:'POST',body:'{}'});setOrderId('');setId(created.id);setState(created);return created.id;}
  async function newConsultation(){await action(async()=>{setId('');setState(null);setMessages([]);setUpload(null);setText('');const created=await api<Intake>('/intakes',{method:'POST',body:'{}'});setOrderId('');setId(created.id);setState(created);});}
  async function send(){if(!text.trim())return;await action(async()=>{
    const intakeId=await ensure();
    await api(`/intakes/${intakeId}/messages`,{method:'POST',body:JSON.stringify({client_message_id:crypto.randomUUID(),content:text.trim(),intent:'question'})});
    setText('');if(intakeId===id)await refresh();
  });}
  async function uploadMaterials(chosen:File[]){
    if(lock.current||checking||!chosen.length)return;
    await action(async()=>{
      setUpload({files:chosen,status:'uploading'});
      let saved:Intake;
      try{
        const intakeId=await ensure();
        const latest=await api<Intake>(`/intakes/${intakeId}`),form=new FormData();
        form.append('expected_revision',String(latest.revision));
        chosen.forEach(file=>form.append('files',file));
        saved=await api<Intake>(`/intakes/${intakeId}/files`,{method:'POST',body:form});
        setState(saved);setUpload(null);
      }catch(cause){
        const message=cause instanceof Error?cause.message:'上传未完成，请重试。';
        setUpload({files:chosen,status:'failed',error:message});
        throw cause;
      }
      // Upload is already acknowledged. A later Agent-start failure must not turn it into an upload failure.
      await api(`/intakes/${saved.id}/prechecks`,{method:'POST',body:JSON.stringify({expected_revision:saved.revision})});
      requestAnimationFrame(()=>materialCard.current?.scrollIntoView({behavior:'smooth',block:'center'}));
    });
  }
  async function beginConversation(){
    if(!state||upload||!state.files.length)return;
    await action(async()=>{
      await api(`/intakes/${id}/prechecks`,{method:'POST',body:JSON.stringify({expected_revision:state.revision})});
      await refresh();
    });
    conversation.current?.lastElementChild?.scrollIntoView({behavior:'smooth',block:'nearest'});
  }
  async function saveProfile(){if(!state)return;await action(async()=>{const [y,m]=period.split('-').map(Number),end=new Date(y,m,0).getDate();await api(`/intakes/${id}`,{method:'PATCH',body:JSON.stringify({expected_revision:state.revision,studio_id:studioId||null,studio_name:name.trim(),period_start:`${period}-01`,period_end:`${period}-${String(end).padStart(2,'0')}`,profile_confirmed:true})});});}
  async function changeFile(file:Item,change:object){if(!state)return;await action(async()=>{await api(`/intakes/${id}/files/${file.id}`,{method:'PATCH',body:JSON.stringify({expected_revision:state.revision,...change})});});}
  async function replaceFile(file:File){const old=replacing.current;if(!state||!old)return;await action(async()=>{
    const form=new FormData();form.append('expected_revision',String(state.revision));form.append('files',file);const uploaded=await api<Intake>(`/intakes/${id}/files`,{method:'POST',body:form});const fresh=uploaded.files.filter(f=>!state.files.some(old=>old.id===f.id)&&f.category!=='archive')[0];if(!fresh)throw new Error('替换文件上传失败');await api(`/intakes/${id}/files/${fresh.id}`,{method:'PATCH',body:JSON.stringify({expected_revision:uploaded.revision,replaces_file_id:old.id})});
  });}
  function add(files:FileList|null){if(!files)return;const chosen=Array.from(files);if(picker.current)picker.current.value='';void uploadMaterials(chosen);}
  const checking=!!state?.precheck&&['queued','running'].includes(state.precheck.status),result=state?.precheck?.result;
  const chatMessages=messages.filter(message=>!(message.role==='user'&&message.content==='已提交材料。'&&message.file_ids.length));
  function filePurpose(file:Item){
    if(state?.files.some(child=>child.derived_from_file_id===file.id))return '原始材料（已保留）';
    if(file.category==='bank_statement_csv')return file.derived_from_file_id?'整理后的流水':'原始流水';
    return categoryNames[file.category]||'原始材料';
  }
  function fileReadStatus(file:Item){
    if(file.validation_status!=='valid')return '需要核实';
    if(file.derived_from_file_id)return '已整理';
    const todo=state?.precheck?.todos.find(task=>task.file_id===file.id&&task.kind==='read_document');
    return todo?.status==='skipped'?'待下单后识别':todo?.status==='completed'?'已读取':todo?.status==='blocked'?'待确认读取方式':'已保存，待读取';
  }
  function materialSummary(){
    const files=state?.files.filter(file=>file.included&&file.category!=='archive')||[];
    const images=files.filter(file=>file.mime_type.startsWith('image/')).length;
    const statements=files.filter(file=>file.category==='bank_statement_csv').length;
    const other=files.length-images-statements;
    return [images?`${images} 张图片`:'',statements?`${statements} 份流水文件`:'',other?`${other} 份其他材料`:''].filter(Boolean).join('、');
  }
  function confirmationWarning(issue:Issue){
    return issue.id.startsWith('duplicate_file')?'发现内容相同的文件，正式处理时会单独标记重复项。请确认按当前提交材料继续。':issue.message;
  }
  const lastMessage=messages.at(-1);
  useEffect(()=>{
    if(checking){todoList.current?.scrollIntoView({behavior:'smooth',block:'nearest'});}
    else if(lastMessage?.role==='assistant'&&lastMessage.job_id&&lastMessage.job_id===state?.precheck?.id){
      conversation.current?.lastElementChild?.scrollIntoView({behavior:'smooth',block:'nearest'});
    }
  },[checking,lastMessage?.id,lastMessage?.job_id,lastMessage?.role,state?.precheck?.id]);
  if(orderId)return <LiveClient initialOrderId={orderId} onNewConsultation={()=>void newConsultation()} onBackToIntakes={()=>{setUpload(null);setOrderId('');setState(null);setMessages([]);localStorage.setItem('ledgercrew.active-view','intake');setId(intakes.find(i=>!i.order_id)?.id||'');}}/>;
  return <div className="app-shell"><aside className="sidebar"><a className="brand" href="/"><span className="brand-mark"><BookOpenCheck size={23}/></span><span><strong>小账房</strong><small>LedgerCrew</small></span></a><button className="new-chat" onClick={()=>void newConsultation()} disabled={busy}><Plus size={18}/>新建咨询</button><nav className="main-nav"><span className="nav-item active">接洽与材料预检</span>{account?.role==='owner'&&<a className="nav-item" href="/owner/" target="_blank" rel="noreferrer">老板控制台</a>}</nav><div className="history"><div className="history-label">接洽会话</div>{intakes.filter(i=>!i.order_id).map(i=><button className={`history-item ${id===i.id?'selected':''}`} key={i.id} disabled={busy} onClick={()=>{setId(i.id);setUpload(null);setError('');}}><span>{i.studio_name||'新的材料咨询'}<small>{labels[i.status]||i.status}</small></span></button>)}<div className="history-label">服务订单</div>{orders.map(o=><button className="history-item" key={o.id} disabled={busy} onClick={()=>showOrder(o.id)}><span>{o.period_start.slice(0,7)} 账目核对<small>{o.order_no.slice(0,15)}</small></span></button>)}</div><div className="sidebar-bottom"><p className="report-note">确认前不会创建订单</p></div></aside>
    <main className="main-area"><header className="topbar"><div className="breadcrumb"><span>客户服务</span><strong>材料接洽</strong></div><span className="preview-label"><span/>{connected?'实时连接':'等待连接'}</span></header><div className="workspace-body"><section className="chat-panel" aria-label="材料接洽聊天"><header className="conversation-header"><div><h1>{state?.studio_name||'先聊需求，再确认服务'}</h1><p>{state?labels[state.status]:'提交材料，了解服务并确认。'}</p></div><span className="conversation-status">{state?'尚未创建订单':'新的咨询'}</span></header>
    {error&&<div className="upload-error" role="alert"><span>{error}</span><button onClick={()=>setError('')}>关闭</button></div>}
    <div className="chat-scroll"><div className="chat-content">{!id&&<div className="welcome"><span className="brand-mark"><BookOpenCheck size={25}/></span><span className="welcome-overline">一家由你确认开工的 AI 财务服务公司</span><h2>先把材料交给我们。</h2><p>聊天、票据、CSV 或 ZIP 都可以先发来。<br/>客服先检查材料，确认服务后，总管再安排正式处理。</p><button className="primary-button" onClick={()=>void newConsultation()}>开始咨询</button></div>}
    <div ref={conversation} className="intake-conversation" role="region" aria-label="客服对话">{chatMessages.map(m=><article className={`message ${m.role==='user'?'user':'assistant'}`} key={m.id}>{m.role==='user'?<div className="user-label">你</div>:<div className="assistant-label"><span className="brand-mark small"><BookOpenCheck size={18}/></span><strong>材料接收客服</strong></div>}<div className={m.role==='user'?'user-bubble':'assistant-body'}><p className="assistant-text">{m.content}</p>{!!m.file_ids.length&&<div className="message-files">{m.file_ids.map(fid=><span key={fid}><FileText size={14}/>{state?.files.find(f=>f.id===fid)?.original_filename||'已提交材料'}</span>)}</div>}{m.status==='queued'&&<small>等待实际客服答复…</small>}</div></article>)}
    {checking&&<div className="busy-state" role="status"><LoaderCircle className="live-spin" size={16}/><span>客服正在查看已上传材料，完成后会在这里继续对话。</span></div>}
    </div>
    {id&&state&&<>
      <section className="intake-card" aria-label="工作室与账期资料"><div className="intake-card-heading"><strong>本次服务资料</strong><span>{state.profile_confirmed?'已确认':'待确认'}</span></div><div className="intake-profile">{studios.length>0&&<label>已有工作室<select value={studioId} disabled={checking||busy} onChange={e=>{setStudioId(e.target.value);const selected=studios.find(s=>s.id===e.target.value);if(selected)setName(selected.name);}}><option value="">新建工作室</option>{studios.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>}<label>工作室名称<input aria-label="工作室名称" value={name} disabled={checking||busy} onChange={e=>{setName(e.target.value);setStudioId('');}} maxLength={200} placeholder="与票据抬头一致"/></label><label>账期<input aria-label="账期" type="month" value={period} disabled={checking||busy} onChange={e=>setPeriod(e.target.value)}/></label><button className="secondary-button" disabled={checking||busy||!name.trim()||!period} onClick={()=>void saveProfile()}>确认服务资料</button></div></section>
      <section ref={materialCard} className="intake-card" aria-label="材料清单" aria-busy={upload?.status==='uploading'}><div className="intake-card-heading"><strong>已收到的材料 · {state.files.length} 份文件</strong><button className="text-button" disabled={checking||busy} onClick={()=>picker.current?.click()}>添加材料</button></div><p className="report-note intake-upload-hint">上传原始材料后，Agent 会列出待办，查看目录、读取文件并整理需要确认的问题。</p>
      {state.precheck&&(()=>{const todos=state.precheck!.todos,done=todos.filter(t=>t.status==='completed'||t.status==='skipped').length,pct=todos.length?Math.round(done/todos.length*100):0;return <div ref={todoList} className="intake-todos" role="region" aria-label="Agent 待办"><div className="intake-todos-heading"><strong>材料 Agent</strong><span>{done} / {todos.length}</span></div><div className="intake-todo-progress" aria-hidden="true"><i style={{width:`${pct}%`}}/></div>{!todos.length&&<p className="report-note">{checking?'正在查看材料目录并制定待办…':'本次尚未产生执行待办。'}</p>}<ol>{groupTodos(todos).map(group=>{const groupDone=group.items.filter(t=>t.status==='completed'||t.status==='skipped').length,skipped=group.items.filter(t=>t.status==='skipped').length,active=group.items.find(t=>t.status!=='completed'&&t.status!=='skipped'),status=active?active.status:skipped===group.items.length?'skipped':'completed';return <li className={`intake-todo intake-todo-${status}`} key={group.items[0].id}><span className="intake-todo-status">{todoStatusNames[status]}</span><div><strong>{todoKinds[group.kind]||'待办'}{group.items.length>1?` · ${groupDone}/${group.items.length}`:''}</strong>{active?<p>{active.title}</p>:<p>{skipped?`已跳过 ${skipped} 项图片预读，下单后再识别`:'已全部完成'}</p>}</div></li>;})}</ol></div>;})()}
      {upload&&<div className={`intake-upload-state ${upload.status==='failed'?'intake-upload-failed':''}`} role={upload.status==='failed'?'alert':'status'}>
        {upload.files.map((file,index)=><div className="intake-upload-item" key={index}><FileText size={16}/><span>{file.name}<small>{(file.size/1024).toFixed(1)} KB · {upload.status==='uploading'?'正在上传':'上传未完成'}</small></span></div>)}
        {upload.status==='uploading'?<p><LoaderCircle className="live-spin" size={15}/>正在将材料保存到工作区，请稍候…</p>:<><p>{upload.error}</p><div className="intake-upload-actions"><button className="secondary-button" disabled={busy} onClick={()=>void uploadMaterials(upload.files)}>重试上传</button><button className="text-button" disabled={busy} onClick={()=>{setUpload(null);setError('');}}>移除未上传文件</button></div></>}
      </div>}
      {!state.files.length&&!upload&&<p className="report-note">还没有收到文件。可以提交压缩包、PDF、Excel、图片或其他原始材料，由 Agent 确认读取方式。</p>}{state.files.map(file=><div className={`intake-file ${!file.included?'intake-file-excluded':''}`} key={file.id}><div><button className="text-button intake-file-name" onClick={()=>void action(()=>download(`/intakes/${id}/files/${file.id}/download`,file.original_filename))}><FileText size={16}/>{file.original_filename}</button><small>{file.derived_from_file_id?'由 '+(state.files.find(f=>f.id===file.derived_from_file_id)?.original_filename||'原始材料')+' 整理':file.archive_entry_path||filePurpose(file)} · {(file.file_size/1024).toFixed(1)} KB · {fileReadStatus(file)}{file.replaced_by_file_id?' · 已被替换':''}</small></div>{file.category!=='archive'&&<div className="intake-file-controls">{file.mime_type.startsWith('image/')?<select aria-label={`${file.original_filename}类别`} value={file.category} disabled={checking||busy} onChange={e=>void changeFile(file,{category:e.target.value})}><option value="invoice_image">票据</option><option value="supporting_material">说明凭证</option><option value="unclassified">待选择类别</option></select>:<span>{filePurpose(file)}</span>}<label><input type="checkbox" checked={file.included} disabled={checking||busy||!!file.replaced_by_file_id} onChange={e=>void changeFile(file,{included:e.target.checked})}/>纳入</label><button className="text-button" disabled={checking||busy||!!file.replaced_by_file_id} onClick={()=>{replacing.current=file;replacement.current?.click();}}>替换</button></div>}</div>)}<div className="intake-card-actions"><span className="report-note">按原样提交，Agent 负责整理。</span><button className="primary-button" disabled={busy||checking||!!upload||!state.files.length} onClick={()=>void beginConversation()}>{checking?<><LoaderCircle className="live-spin" size={16}/>Agent 正在读取材料…</>:result||state.precheck?.status==='failed'?'重新整理材料':'开始对话'}</button></div></section>
      {state.precheck?.status==='failed'&&<div className="upload-error" role="alert">{state.precheck.error} · 请求 {state.precheck.requests_used} 次</div>}
      {result&&<section className="intake-card" aria-label="材料预检结果"><div className="intake-card-heading"><strong>{result.blockers.length?'待补材料':result.warnings.length?'材料检查摘要 · 有待确认项':'材料检查摘要 · 可以受理'}</strong><span>{result.skipped_file_ids?.length?'图片留待下单后识别':`已读 ${result.sampled_file_ids.length} 张图片`}</span></div><p className="report-note">客服的检查结论和补充问题已显示在对话中，你可以直接在下方回复。</p>{result.blockers.map(b=><div className="intake-blocker" key={b.id}>{b.message} {state.files.find(f=>f.id===b.file_id)?.original_filename}</div>)}{result.csv_details.map(c=><div key={c.file_id} className="report-note">流水 {c.valid_rows}/{c.rows} 行有效{c.errors.map(e=><p key={e.row_number}>第 {e.row_number} 行：{e.reason}</p>)}</div>)}<p className="report-note">{result.note}</p></section>}
      {state.confirmation&&<section className="intake-card intake-offer" aria-label="服务确认卡"><div className="intake-card-heading"><strong>确认本次处理</strong></div><h2>{state.service.name}</h2><p>{state.studio_name} · {state.period_start} — {state.period_end}</p><p className="intake-material-summary">本次处理材料：{materialSummary()}</p><p className="intake-scope-label">接下来我们会：</p><ul><li>识别、整理票据中的账目信息</li><li>核对收付款流水，列出差额和待核实事项</li><li>生成核对报告与明细，审核后交付</li></ul>{state.confirmation.warnings.map(w=><label className="intake-ack" key={w.id}><input type="checkbox" checked={acks.includes(w.id)} onChange={e=>setAcks(a=>e.target.checked?[...a,w.id]:a.filter(x=>x!==w.id))}/><span>{confirmationWarning(w)}</span></label>)}<p className="report-note">确认后开始正式识别与核对。处理过程中需要补充的说明或凭证，会单独列出。</p><button className="primary-button" disabled={busy||checking||state.confirmation.warnings.some(w=>!acks.includes(w.id))} onClick={()=>void action(async()=>{const c=state.confirmation!;const created=await api<{order_id:string}>(`/intakes/${id}/confirm`,{method:'POST',body:JSON.stringify({expected_revision:state.revision,precheck_id:c.precheck_id,service_version:c.service_version,idempotency_key:key.current,acknowledged_warning_ids:acks})});await history();showOrder(created.order_id);})}>确认并开始处理</button></section>}
    </>}<div className="intake-bottom-space"/></div></div>
    <div className="composer-area"><form className="composer" onSubmit={e=>{e.preventDefault();void send();}} onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();if(!checking&&!busy)add(e.dataTransfer.files);}}><textarea aria-label="输入咨询内容" value={text} onChange={e=>setText(e.target.value)} rows={2} maxLength={3000} placeholder="告诉 Agent 本次需求，或补充它需要确认的信息…"/><div className="composer-tools"><div><button className="icon-btn" type="button" aria-label="上传接洽材料" disabled={busy||checking} onClick={()=>picker.current?.click()}><Paperclip size={18}/></button><span>原始文件 · 自动上传</span></div><button className="send-button" type="submit" aria-label="发送接洽消息" disabled={busy||checking||!text.trim()}><ArrowUp size={20}/></button></div></form><div className="composer-footnote"><span><ShieldCheck size={12}/>预检后由你确认下单</span><span>真实客服 Agent</span></div></div></section></div></main>
    <input ref={picker} className="sr-only" type="file" multiple onChange={e=>add(e.target.files)}/><input ref={replacement} className="sr-only" type="file" accept=".jpg,.jpeg,.png,.csv" onChange={e=>{const f=e.target.files?.[0];if(f)void replaceFile(f);e.target.value='';}}/>
  </div>;
}
