'use client';

import {useCallback,useEffect,useRef,useState} from 'react';
import {ArrowUp,BookOpenCheck,FileText,FolderOpen,LoaderCircle,Paperclip,Plus,ShieldCheck} from 'lucide-react';
import LiveClient from './live-client';
import {api,download,subscribe,type Order} from '@/lib/api';
import {formatMoney} from '@/lib/ledger';
import './live.css';
import './intake.css';

type Item={id:string;original_filename:string;category:string;mime_type:string;included:boolean;validation_status:string;archive_file_id:string|null;archive_entry_path:string|null;replaced_by_file_id:string|null;file_size:number};
type Issue={id:string;message:string;file_id:string|null};
type Result={blockers:Issue[];warnings:Issue[];sampled_file_ids:string[];note:string;narrative:{summary:string;questions:string[]};csv_details:{file_id:string;rows:number;valid_rows:number;errors:{row_number:number;reason:string}[]}[]};
type Service={code:string;version:number;name:string;price_cents:number;currency:string;delivery_note:string;deliverables:string[]};
type Intake={id:string;status:string;revision:number;order_id:string|null;studio_id:string|null;studio_name:string|null;period_start:string|null;period_end:string|null;profile_confirmed:boolean;service:Service;files:Item[];precheck:{id:string;status:string;revision:number;requests_used:number;request_limit:number|null;result:Result|null;error:string|null}|null;confirmation:{precheck_id:string;revision:number;service_version:number;price_cents:number;warnings:Issue[]}|null};
type Conversation={id:string;role:string;content:string;status:string;file_ids:string[];job_id:string|null};
type History={id:string;studio_name:string|null;status:string;order_id:string|null};
type Studio={id:string;name:string};
type UploadAttempt={files:File[];status:'uploading'|'failed';error?:string};
const labels:Record<string,string>={collecting:'收集材料',checking:'材料预检中',needs_info:'需要补充资料',ready:'可以受理',ready_with_warnings:'有待确认项',precheck_failed:'预检未完成',ordered:'已创建订单'};
const categoryNames:Record<string,string>={invoice_image:'票据',supporting_material:'说明凭证',bank_statement_csv:'CSV 流水',archive:'原始 ZIP',unclassified:'待选择类别'};

export default function ReceptionClient(){
  const [intakes,setIntakes]=useState<History[]>([]),[orders,setOrders]=useState<Order[]>([]),[studios,setStudios]=useState<Studio[]>([]);
  const [catalog,setCatalog]=useState<Service|null>(null);
  const [id,setId]=useState(''),[orderId,setOrderId]=useState(''),[state,setState]=useState<Intake|null>(null),[messages,setMessages]=useState<Conversation[]>([]);
  const [text,setText]=useState(''),[upload,setUpload]=useState<UploadAttempt|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[connected,setConnected]=useState(false);
  const [name,setName]=useState(''),[period,setPeriod]=useState(''),[studioId,setStudioId]=useState(''),[acks,setAcks]=useState<string[]>([]);
  const lock=useRef(false),current=useRef(''),picker=useRef<HTMLInputElement>(null),replacement=useRef<HTMLInputElement>(null),replacing=useRef<Item|null>(null),key=useRef('');
  const materialCard=useRef<HTMLElement>(null),conversation=useRef<HTMLDivElement>(null);
  current.current=id;
  const history=useCallback(async()=>{
    const [a,b,c,d]=await Promise.all([api<History[]>('/intakes'),api<Order[]>('/orders'),api<Studio[]>('/studios'),api<Service[]>('/services')]);setIntakes(a);setOrders(b);setStudios(c);setCatalog(d[0]||null);return {a,b};
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
      try{
        const intakeId=await ensure();
        const latest=await api<Intake>(`/intakes/${intakeId}`),form=new FormData();
        form.append('expected_revision',String(latest.revision));
        chosen.forEach(file=>form.append('files',file));
        const saved=await api<Intake>(`/intakes/${intakeId}/files`,{method:'POST',body:form});
        setState(saved);setUpload(null);
        requestAnimationFrame(()=>materialCard.current?.scrollIntoView({behavior:'smooth',block:'center'}));
      }catch(cause){
        const message=cause instanceof Error?cause.message:'上传未完成，请重试。';
        setUpload({files:chosen,status:'failed',error:message});
        throw cause;
      }
    });
  }
  async function beginConversation(){
    if(!state||upload||!state.files.some(file=>file.included&&file.category!=='archive'))return;
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
  function add(files:FileList|null){if(!files)return;const chosen=Array.from(files);if(picker.current)picker.current.value='';if(chosen.some(f=>!(/\.(png|jpe?g|csv|zip)$/i.test(f.name)))){setError('请提交 JPG、PNG、CSV 或 ZIP。');return;}void uploadMaterials(chosen);}
  const checking=!!state?.precheck&&['queued','running'].includes(state.precheck.status),result=state?.precheck?.result;
  const includedCount=state?.files.filter(file=>file.included&&file.category!=='archive').length||0;
  const chatMessages=messages.filter(message=>!(message.role==='user'&&message.content==='已提交材料。'&&message.file_ids.length));
  const lastMessage=messages.at(-1);
  useEffect(()=>{
    if(checking||(lastMessage?.role==='assistant'&&lastMessage.job_id&&lastMessage.job_id===state?.precheck?.id)){
      conversation.current?.lastElementChild?.scrollIntoView({behavior:'smooth',block:'nearest'});
    }
  },[checking,lastMessage?.id,lastMessage?.job_id,lastMessage?.role,state?.precheck?.id]);
  if(orderId)return <LiveClient initialOrderId={orderId} onNewConsultation={()=>void newConsultation()} onBackToIntakes={()=>{setUpload(null);setOrderId('');setState(null);setMessages([]);localStorage.setItem('ledgercrew.active-view','intake');setId(intakes.find(i=>!i.order_id)?.id||'');}}/>;
  return <div className="app-shell"><aside className="sidebar"><a className="brand" href="/"><span className="brand-mark"><BookOpenCheck size={23}/></span><span><strong>账清社.</strong><small>LedgerCrew</small></span></a><button className="new-chat" onClick={()=>void newConsultation()} disabled={busy}><Plus size={18}/>新建咨询</button><nav className="main-nav"><span className="nav-item active">接洽与材料预检</span><a className="nav-item" href="/owner/" target="_blank" rel="noreferrer">老板控制台</a></nav><div className="history"><div className="history-label">接洽会话</div>{intakes.filter(i=>!i.order_id).map(i=><button className={`history-item ${id===i.id?'selected':''}`} key={i.id} disabled={busy} onClick={()=>{setId(i.id);setUpload(null);setError('');}}><span>{i.studio_name||'新的材料咨询'}<small>{labels[i.status]||i.status}</small></span></button>)}<div className="history-label">服务订单</div>{orders.map(o=><button className="history-item" key={o.id} disabled={busy} onClick={()=>showOrder(o.id)}><span>{o.period_start.slice(0,7)} 账目核对<small>{o.order_no.slice(0,15)}</small></span></button>)}</div><div className="sidebar-bottom"><p className="report-note">本机受控演示 · 模拟交易<br/>确认前不会创建订单</p></div></aside>
    <main className="main-area"><header className="topbar"><div className="breadcrumb"><span>客户服务</span><strong>材料接洽</strong></div><span className="preview-label"><span/>{connected?'实时连接':'等待连接'}</span></header><div className="workspace-body"><section className="chat-panel" aria-label="材料接洽聊天"><header className="conversation-header"><div><h1>{state?.studio_name||'先聊需求，再确认服务'}</h1><p>{state?labels[state.status]:'提交材料，了解服务，确认后再交给总管处理。'}</p></div><span className="conversation-status">{state?'尚未创建订单':'新的咨询'}</span></header>
    {error&&<div className="upload-error" role="alert"><span>{error}</span><button onClick={()=>setError('')}>关闭</button></div>}
    <div className="chat-scroll"><div className="chat-content">{!id&&<div className="welcome"><span className="brand-mark"><BookOpenCheck size={25}/></span><span className="welcome-overline">一家由你确认开工的 AI 财务服务公司</span><h2>先把材料交给我们。</h2><p>聊天、票据、CSV 或 ZIP 都可以先发来。<br/>客服先检查材料，确认服务后，总管再安排正式处理。</p><button className="primary-button" onClick={()=>void newConsultation()}>开始咨询</button></div>}
    <div ref={conversation} className="intake-conversation" role="region" aria-label="客服对话">{chatMessages.map(m=><article className={`message ${m.role==='user'?'user':'assistant'}`} key={m.id}>{m.role==='user'?<div className="user-label">你</div>:<div className="assistant-label"><span className="brand-mark small"><BookOpenCheck size={18}/></span><strong>材料接收客服</strong></div>}<div className={m.role==='user'?'user-bubble':'assistant-body'}><p className="assistant-text">{m.content}</p>{!!m.file_ids.length&&<div className="message-files">{m.file_ids.map(fid=><span key={fid}><FileText size={14}/>{state?.files.find(f=>f.id===fid)?.original_filename||'已提交材料'}</span>)}</div>}{m.status==='queued'&&<small>等待实际客服答复…</small>}</div></article>)}
    {checking&&<div className="busy-state" role="status"><LoaderCircle className="live-spin" size={16}/><span>客服正在查看已上传材料，完成后会在这里继续对话。</span></div>}
    </div>
    {id&&state&&<>
      <section className="intake-card" aria-label="工作室与账期资料"><div className="intake-card-heading"><strong>本次服务资料</strong><span>{state.profile_confirmed?'已确认':'待确认'}</span></div><div className="intake-profile">{studios.length>0&&<label>已有工作室<select value={studioId} disabled={checking||busy} onChange={e=>{setStudioId(e.target.value);const selected=studios.find(s=>s.id===e.target.value);if(selected)setName(selected.name);}}><option value="">新建工作室</option>{studios.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>}<label>工作室名称<input aria-label="工作室名称" value={name} disabled={checking||busy} onChange={e=>{setName(e.target.value);setStudioId('');}} maxLength={200} placeholder="与票据抬头一致"/></label><label>账期<input aria-label="账期" type="month" value={period} disabled={checking||busy} onChange={e=>setPeriod(e.target.value)}/></label><button className="secondary-button" disabled={checking||busy||!name.trim()||!period} onClick={()=>void saveProfile()}>确认服务资料</button></div></section>
      <section ref={materialCard} className="intake-card" aria-label="材料清单" aria-busy={upload?.status==='uploading'}><div className="intake-card-heading"><strong>已收到的材料 · {includedCount} 份已上传</strong><button className="text-button" disabled={checking||busy} onClick={()=>picker.current?.click()}>添加材料</button></div><p className="report-note intake-upload-hint">选择文件后立即上传到这里，ZIP 会自动展开为票据和流水，无需点击聊天发送。</p>
      {upload&&<div className={`intake-upload-state ${upload.status==='failed'?'intake-upload-failed':''}`} role={upload.status==='failed'?'alert':'status'}>
        {upload.files.map((file,index)=><div className="intake-upload-item" key={index}><FileText size={16}/><span>{file.name}<small>{(file.size/1024).toFixed(1)} KB · {upload.status==='uploading'?'正在上传':'上传未完成'}</small></span></div>)}
        {upload.status==='uploading'?<p><LoaderCircle className="live-spin" size={15}/>正在上传并展开材料，请稍候…</p>:<><p>{upload.error}</p><div className="intake-upload-actions"><button className="secondary-button" disabled={busy} onClick={()=>void uploadMaterials(upload.files)}>重试上传</button><button className="text-button" disabled={busy} onClick={()=>{setUpload(null);setError('');}}>移除未上传文件</button></div></>}
      </div>}
      {!state.files.length&&!upload&&<p className="report-note">还没有收到文件。可直接添加 JPG / PNG / CSV / ZIP，暂不支持 PDF 识别。</p>}{state.files.map(file=><div className={`intake-file ${!file.included?'intake-file-excluded':''}`} key={file.id}><div><button className="text-button intake-file-name" onClick={()=>void action(()=>download(`/intakes/${id}/files/${file.id}/download`,file.original_filename))}><FileText size={16}/>{file.original_filename}</button><small>{file.archive_entry_path||categoryNames[file.category]} · {(file.file_size/1024).toFixed(1)} KB · {file.validation_status==='valid'?'格式可读取':'不支持或无法读取'}{file.replaced_by_file_id?' · 已被替换':''}</small></div>{file.category!=='archive'&&<div className="intake-file-controls">{file.mime_type.startsWith('image/')?<select aria-label={`${file.original_filename}类别`} value={file.category} disabled={checking||busy} onChange={e=>void changeFile(file,{category:e.target.value})}><option value="invoice_image">票据</option><option value="supporting_material">说明凭证</option><option value="unclassified">待选择类别</option></select>:<span>{categoryNames[file.category]}</span>}<label><input type="checkbox" checked={file.included} disabled={checking||busy||!!file.replaced_by_file_id} onChange={e=>void changeFile(file,{included:e.target.checked})}/>纳入</label><button className="text-button" disabled={checking||busy||!!file.replaced_by_file_id} onClick={()=>{replacing.current=file;replacement.current?.click();}}>替换</button></div>}</div>)}<div className="intake-card-actions"><a className="text-button" href="/api/v1/templates/statement.csv">下载 CSV 模板</a><button className="primary-button" disabled={busy||checking||!!upload||!includedCount} onClick={()=>void beginConversation()}>{checking?<><LoaderCircle className="live-spin" size={16}/>客服正在查看材料…</>:result||state.precheck?.status==='failed'?'重新开始对话':'开始对话'}</button></div></section>
      {state.precheck?.status==='failed'&&<div className="upload-error" role="alert">{state.precheck.error} · 请求 {state.precheck.requests_used} 次</div>}
      {result&&<section className="intake-card" aria-label="材料预检结果"><div className="intake-card-heading"><strong>{result.blockers.length?'待补材料':result.warnings.length?'材料检查摘要 · 有待确认项':'材料检查摘要 · 可以受理'}</strong><span>抽查 {result.sampled_file_ids.length} 张图片</span></div><p className="report-note">客服的检查结论和补充问题已显示在对话中，你可以直接在下方回复。</p>{result.blockers.map(b=><div className="intake-blocker" key={b.id}>{b.message} {state.files.find(f=>f.id===b.file_id)?.original_filename}</div>)}{result.csv_details.map(c=><div key={c.file_id} className="report-note">流水 {c.valid_rows}/{c.rows} 行有效{c.errors.map(e=><p key={e.row_number}>第 {e.row_number} 行：{e.reason}</p>)}</div>)}<p className="report-note">{result.note}</p></section>}
      {state.confirmation&&<section className="intake-card intake-offer" aria-label="服务确认卡"><div className="intake-card-heading"><strong>请确认本次服务</strong><span>模拟交易</span></div><h2>{state.service.name}</h2><div className="intake-price">{formatMoney(state.service.price_cents)}<small> / 单</small></div><p>{state.studio_name} · {state.period_start} — {state.period_end}</p><p>有效材料：{state.files.filter(f=>f.included&&f.category!=='archive').map(f=>f.original_filename).join('、')}</p><ul>{state.service.deliverables.map(d=><li key={d}>{d}</li>)}</ul><p>{state.service.delivery_note}</p>{state.confirmation.warnings.map(w=><label className="intake-ack" key={w.id}><input type="checkbox" checked={acks.includes(w.id)} onChange={e=>setAcks(a=>e.target.checked?[...a,w.id]:a.filter(x=>x!==w.id))}/><span>{w.message}</span></label>)}<p className="report-note">确认仅表示材料达到启动条件；正式识别和核对仍可能发现未知字段、缺票或差额。</p><button className="primary-button" disabled={busy||checking||state.confirmation.warnings.some(w=>!acks.includes(w.id))} onClick={()=>void action(async()=>{const c=state.confirmation!;const created=await api<{order_id:string}>(`/intakes/${id}/confirm`,{method:'POST',body:JSON.stringify({expected_revision:state.revision,precheck_id:c.precheck_id,service_version:c.service_version,idempotency_key:key.current,acknowledged_warning_ids:acks})});await history();showOrder(created.order_id);})}>确认创建订单</button></section>}
    </>}<div className="intake-bottom-space"/></div></div>
    <div className="composer-area"><form className="composer" onSubmit={e=>{e.preventDefault();void send();}} onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();if(!checking&&!busy)add(e.dataTransfer.files);}}><textarea aria-label="输入咨询内容" value={text} onChange={e=>setText(e.target.value)} rows={2} maxLength={3000} placeholder="先说说需求，或发来本期材料…"/><div className="composer-tools"><div><button className="icon-btn" type="button" aria-label="上传接洽材料" disabled={busy||checking} onClick={()=>picker.current?.click()}><Paperclip size={18}/></button><span>JPG / PNG / CSV / ZIP</span></div><button className="send-button" type="submit" aria-label="发送接洽消息" disabled={busy||checking||!text.trim()}><ArrowUp size={20}/></button></div></form><div className="composer-footnote"><span><ShieldCheck size={12}/>预检后由你确认下单</span><span>真实客服 Agent</span></div></div></section><aside className="evidence-panel"><div className="aside-heading">服务说明<FolderOpen size={17}/></div><div className="material-content intake-service"><h2>先了解，再开工。</h2><p>票据整理＋流水核对＋异常报告</p><strong className="intake-price">{catalog?formatMoney(catalog.price_cents):'—'} <small>/ 单 · 模拟交易</small></strong><p>客服预检 → 你确认订单 → 总管派工 → 老板审核 → 报告交付</p><p className="report-note">最多 20 张票据、一份标准 CSV。ZIP 可混合提交材料，原包与来源保留。</p><p className="report-note">预检不代表完整识别或财务结论。</p></div></aside></div></main>
    <input ref={picker} className="sr-only" type="file" multiple accept=".jpg,.jpeg,.png,.csv,.zip" onChange={e=>add(e.target.files)}/><input ref={replacement} className="sr-only" type="file" accept=".jpg,.jpeg,.png,.csv" onChange={e=>{const f=e.target.files?.[0];if(f)void replaceFile(f);e.target.value='';}}/>
  </div>;
}
