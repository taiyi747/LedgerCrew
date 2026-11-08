'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ArrowDownToLine, ArrowRight, ArrowUp, BookOpenCheck, Check, ChevronDown, ChevronRight, CircleHelp, FileCheck2, FileImage, FileSpreadsheet, FileText, FolderOpen, Menu, MessageSquare, Paperclip, Plus, Printer, RotateCcw, ShieldCheck, Square, TriangleAlert, X } from 'lucide-react';
import { LedgerCharts } from '@/components/ledger-charts';
import type { TransactionStatus } from '@/lib/chart-data';
import { useLedgerMotion } from '@/hooks/use-ledger-motion';
import { DEMO_FILES, DEMO_ROWS, validateCsvContent, exportCsv, formatMoney, getSummary, validateFiles, type LedgerRow } from '@/lib/ledger';

type Message = { id: number; role: 'user' | 'assistant'; text: string; result?: boolean; files?: string[] };
type Modal = 'report' | 'evidence' | 'materials' | 'workspace' | 'help' | null;
const initialMessages: Message[] = [
  { id: 1, role: 'user', text: '帮我核对一下 10 月的账，看看有没有对不上的地方。', files: ['10 月票据 · 6 张', '10 月银行流水.csv'] },
  { id: 2, role: 'assistant', text: '4 笔付款与票据一致。有 1 笔金额不一致，另外需要核实 1 张重复票据和 1 笔缺票付款。', result: true },
];
const statusText = { matched: '核对一致', difference: '金额不一致', duplicate: '重复票据', missing: '缺少凭证' };
const summary = getSummary(DEMO_ROWS);
const differenceRow = DEMO_ROWS.find(row => row.status === 'difference')!;

function Mark({ small = false }: { small?: boolean }) {
  return <span className={`brand-mark ${small ? 'small' : ''}`}><BookOpenCheck size={small ? 18 : 24} strokeWidth={1.6} /></span>;
}
function downloadCsv() {
  const blob = new Blob([exportCsv(DEMO_ROWS)], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = '小账房-2026年10月核对明细-示例.csv'; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function Money({ value }: { value: number | null }) { return <span className="money">{value === null ? '—' : formatMoney(value)}</span>; }

export default function Page() {
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const rootRef = useRef<HTMLDivElement>(null);
  const [replay, setReplay] = useState(0);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [input, setInput] = useState('');
  const [filter, setFilter] = useState<'all' | 'issues' | TransactionStatus>('all');
  const [modal, setModal] = useState<Modal>(null);
  const [selectedRow, setSelectedRow] = useState<LedgerRow>(DEMO_ROWS.find(r => r.status === 'difference')!);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [addedFiles, setAddedFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [fileBusy, setFileBusy] = useState(false);
  const [error, setError] = useState('');
  const [sidebar, setSidebar] = useState(false);
  const [showDemo, setShowDemo] = useState(true);
  const [workspace, setWorkspace] = useState('青屿设计工作室');
  const [period, setPeriod] = useState('2026-10');
  const [draftName, setDraftName] = useState(workspace);
  const [draftPeriod, setDraftPeriod] = useState(period);
  const bottomRef = useRef<HTMLDivElement>(null);
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const messageId = useRef(10);
  const sessionVersion = useRef(0);

  useEffect(() => { if (messages.length > 2 || busy) bottomRef.current?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'end' }); }, [messages, busy]);
  useEffect(() => { if (modal) dialogRef.current?.showModal(); else dialogRef.current?.close(); }, [modal]);
  useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current); }, []);
  useEffect(() => { const id = requestAnimationFrame(() => { const firstAnswer = scrollRef.current?.querySelector<HTMLElement>(window.innerHeight < 850 ? '.chart-grid' : '.message.assistant'); if (firstAnswer && scrollRef.current) scrollRef.current.scrollTo({ top: scrollRef.current.scrollTop + firstAnswer.getBoundingClientRect().top - scrollRef.current.getBoundingClientRect().top - 16, behavior: 'instant' }); }); return () => cancelAnimationFrame(id); }, []);

  useLedgerMotion({ root: rootRef, showDemo, replay, filter, detailsOpen, modal, messageCount: messages.length, busy });

  function replayMotion() {
    const answer = scrollRef.current?.querySelector<HTMLElement>(".chart-grid");
    if (answer && scrollRef.current) scrollRef.current.scrollTo({ top: scrollRef.current.scrollTop + answer.getBoundingClientRect().top - scrollRef.current.getBoundingClientRect().top - 16, behavior: 'instant' });
    setReplay(value => value + 1);
  }

  function newChat() {
    sessionVersion.current += 1; setFileBusy(false); setDetailsOpen(false);
    if (timerRef.current) clearTimeout(timerRef.current);
    setBusy(false); setMessages([]); setShowDemo(false); setInput(''); setPendingFiles([]); setAddedFiles([]); setError(''); setSidebar(false); inputRef.current?.focus();
  }
  function openDemo() {
    sessionVersion.current += 1; setFileBusy(false); setDetailsOpen(false);
    if (timerRef.current) clearTimeout(timerRef.current);
    setBusy(false); setMessages(initialMessages); setShowDemo(true); setFilter('all'); setPendingFiles([]); setAddedFiles([]); setError(''); setSidebar(false);
    requestAnimationFrame(() => scrollRef.current?.scrollTo({ top: 0 }));
  }
  function selectChartStatus(status: TransactionStatus) {
    setFilter(status); setDetailsOpen(true);
    requestAnimationFrame(() => detailsRef.current?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'nearest' }));
  }
  function openEvidence(row: LedgerRow) { setSelectedRow(row); setModal('evidence'); }
  function answer(text: string, hasFiles: boolean) {
    if (hasFiles) return '已添加你选择的材料。这个预览不会读取票据内容或生成真实核对结论。你可以点击「查看示例」体验完整的核对结果；正式处理需要连接小账房服务。';
    if (/我补充说明|补充说明[:：]|原因是|是因为/.test(text)) return '补充说明已记录在本次演示会话中。差额仍待核实；正式服务会在复核凭证后更新报告。';
    if (/270|差额|金额|2850|2,850|运费/.test(text)) return '示例中的这笔付款，票据金额为 ¥2,580.00，银行流水为 ¥2,850.00，相差 ¥270.00。请补充对应的付款说明或其他凭证。即使说明是运费，也需要凭证和人工核实后才能确认；目前保留「金额不一致」。';
    if (/重复/.test(text)) return '示例中有 1 张重复票据，与已匹配票据对应同一笔交易。它已单独标记，未重复计入有效票据总额。你可以在核对结果中点开「重复票据」查看来源。';
    if (/缺|凭证/.test(text)) return '示例有 1 笔 ¥560.00 的付款缺少对应票据。缺少凭证并不等于账目错误，请补充这笔交易的 JPG / PNG 票据或用途说明；补充后仍需核实。';
    if (/材料|上传|格式|怎么/.test(text)) return '准备同一账期的票据照片和银行流水即可。支持最多 20 张 JPG / PNG 图片，单张不超过 5 MB，以及 1 份不超过 200 行的 CSV 流水。点击输入框左下角的回形针添加材料。';

    return showDemo ? '这份示例共核对 6 条流水：4 笔核对一致，1 笔金额不一致，1 笔缺少凭证；另发现 1 张重复票据。你可以继续问我 ¥270.00 的差额，或点开结果查看凭证依据。' : '我可以帮你整理票据、核对流水，并把金额差异和缺少的凭证列清楚。你可以先添加本期材料，也可以点击「查看示例」了解最后会收到什么。本预览中的咨询回复为预设示例。';
  }
  function send(text = input) {
    if (busy || fileBusy || (!text.trim() && !pendingFiles.length)) return;
    const files = [...pendingFiles];
    const clean = text.trim() || '请帮我核对这些材料。';
    setMessages(prev => [...prev, { id: ++messageId.current, role: 'user', text: clean, files: files.map(f => f.name) }]);
    setAddedFiles(prev => [...prev, ...files]); setPendingFiles([]); setInput(''); setError(''); setBusy(true);
    timerRef.current = setTimeout(() => {
      setMessages(prev => [...prev, { id: ++messageId.current, role: 'assistant', text: answer(clean, files.length > 0) }]);
      setBusy(false); timerRef.current = null;
    }, 1000);
  }
  function stop() {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null; setBusy(false);
    setMessages(prev => [...prev, { id: ++messageId.current, role: 'assistant', text: '本次答复已停止，你可以修改问题后重新发送。' }]);
  }
  async function addFiles(list: FileList | File[] | null) {
    if (!list || busy || fileBusy) return;
    const files = Array.from(list); if (!files.length) return;
    const version = sessionVersion.current;
    const validation = validateFiles(files, [...addedFiles, ...pendingFiles]);
    if (validation) { setError(validation); return; }
    setFileBusy(true); setError('');
    try {
      for (const file of files) {
        if (/\.csv$/i.test(file.name)) { const content = await file.text(); if (version !== sessionVersion.current) return; const csvError = validateCsvContent(content); if (csvError) { setError(csvError); return; } }
      }
      if (version === sessionVersion.current) setPendingFiles(prev => [...prev, ...files]);
    } catch { if (version === sessionVersion.current) setError('文件无法读取，请重新选择'); }
    finally { if (version === sessionVersion.current) { setFileBusy(false); if (fileRef.current) fileRef.current.value = ''; } }
  }
  const visibleRows = [...DEMO_ROWS].sort((a, b) => Number(a.status === 'matched') - Number(b.status === 'matched')).filter(row => filter === 'all' || (filter === 'issues' ? row.status !== 'matched' : row.status === filter));
  const periodLabel = `${Number(period.split('-')[1])} 月`;

  function materials() {
    return <div className="material-content">
      <div className="section-title"><span>本次材料</span><span className="count">{(showDemo ? DEMO_FILES.length : 0) + addedFiles.length} 份</span></div>

      <div className="file-list">
        {showDemo && DEMO_FILES.map(file => <button className="file-row" key={file.id} onClick={() => { if (file.kind === 'csv') { setModal('report'); return; } const row = DEMO_ROWS.find(r => r.evidence.some(e => e === file.name)); if (row) openEvidence(row); }}>
          <span className={`file-icon ${file.kind === 'csv' ? 'csv' : ''}`}>{file.kind === 'csv' ? <FileSpreadsheet size={18} /> : <FileImage size={18} />}</span>
          <span className="file-info"><span>{file.name}</span><small>{file.sizeLabel}</small></span><Check size={13} className="file-check" />
        </button>)}
        {addedFiles.map((file, i) => <div className="file-row" key={i}><span className="file-icon"><FileText size={18} /></span><span className="file-info"><span>{file.name}</span><small>仅本地添加 · 尚未处理</small></span></div>)}
        {!showDemo && !addedFiles.length && <div className="empty-files"><FolderOpen size={28} /><p>还没有添加材料</p><span>从聊天框上传票据和流水</span></div>}
      </div>
      <button className="add-material" onClick={() => { setModal(null); fileRef.current?.click(); }} disabled={busy || fileBusy}><Plus size={15} />补充材料</button>
      {showDemo && <div className="aside-report"><div className="section-title"><span>交付报告</span><span className="report-version">v1.0 · 已发布</span></div><button className="report-file" onClick={() => setModal('report')}><span className="report-icon"><FileCheck2 size={22} strokeWidth={1.5}/></span><span><strong>10 月账目核对报告</strong><small>含异常说明与核对明细</small></span><ChevronRight size={16}/></button></div>}
    </div>;
  }

  function table(rows: LedgerRow[], full = false) {
    return <div className={`table-scroll ${full ? 'full' : ''}`}><table><thead><tr><th>交易 / 对方</th><th className="number">票据金额</th><th className="number">流水金额</th><th>核对结果</th><th className="row-action"><span className="sr-only">查看依据</span></th></tr></thead><tbody>{rows.map(row => <tr key={row.id} onClick={() => openEvidence(row)} tabIndex={0} onKeyDown={e => { if (e.key === 'Enter') openEvidence(row); }} aria-label={`${row.counterparty}，${statusText[row.status]}，查看依据`}><td><strong>{row.counterparty}</strong><small>{row.date.slice(5).replace('-', '.')} <span>· {row.id}</span></small></td><td className="number"><Money value={row.invoiceCents}/></td><td className="number"><Money value={row.transactionCents}/></td><td><span className={`row-status ${row.status}`}>{row.status === 'matched' ? <Check size={12}/> : <span className="status-dot"/>}{statusText[row.status]}</span></td><td className="row-action"><ChevronRight size={13}/></td></tr>)}</tbody></table></div>;
  }

  return <div className="app-shell" ref={rootRef} data-motion-engine="gsap">
    {sidebar && <button className="sidebar-scrim" aria-label="关闭导航" onClick={() => setSidebar(false)}/>}
    <aside className={`sidebar ${sidebar ? 'is-open' : ''}`}>
      <a className="brand" href="/" aria-label="小账房首页"><Mark/><span><strong>小账房</strong><small>LedgerCrew</small></span></a>
      <button className="new-chat" onClick={newChat}><Plus size={18}/><span>新建咨询</span><kbd>＋</kbd></button>
      <nav className="main-nav" aria-label="主导航"><button className="nav-item active" onClick={() => { setSidebar(false); inputRef.current?.focus(); }}><MessageSquare size={17}/>财务咨询<span className="nav-dot"/></button><button className="nav-item" onClick={() => {setModal('materials'); setSidebar(false);}}><FolderOpen size={17}/>材料与报告<ChevronRight size={14}/></button></nav>
      <div className="history"><div className="history-label"><span>最近咨询</span><MessageSquare size={13}/></div><button className={`history-item ${showDemo ? 'selected' : ''}`} onClick={openDemo}><span><span className="history-title">10 月账目核对</span><small>6 条流水 · 3 项待核实</small></span><span className="history-dot"/></button>{!showDemo && <button className="history-item selected" onClick={() => setSidebar(false)}><span><span className="history-title">{periodLabel}新咨询</span><small>等待添加材料</small></span></button>}</div>
      <div className="sidebar-bottom"><button className="help-link" onClick={() => setModal('help')}><CircleHelp size={16}/>服务说明<ArrowRight size={14}/></button><button className="workspace" onClick={() => {setDraftName(workspace);setDraftPeriod(period);setModal('workspace');}}><span className="workspace-avatar">{workspace.slice(0,1)}</span><span><strong>{workspace}</strong><small>个人工作空间</small></span><ChevronDown size={14}/></button></div>
    </aside>

    <main className="main-area">
      <header className="topbar"><div className="breadcrumb"><button className="icon-btn mobile-menu" aria-label="打开导航" onClick={() => setSidebar(true)}><Menu size={20}/></button><span>工作台</span><ChevronRight size={13}/><strong>财务咨询</strong></div><div className="topbar-right"><span className="preview-label"><span/>示例账目</span><button className="icon-btn" aria-label="服务说明" onClick={() => setModal('help')}><CircleHelp size={18}/></button><span className="top-avatar">{workspace.slice(0,1)}</span></div></header>
      <div className="workspace-body">
        <section className="chat-panel" aria-label="财务咨询聊天">
          <header className="conversation-header"><div><div className="title-line"><h1>{showDemo ? '10 月账目核对' : `${periodLabel}新咨询`}</h1><span className={`conversation-status ${showDemo ? '' : 'neutral'}`}><span/>{showDemo ? '已核对 · 3 项待核实' : '等待材料'}</span></div><p>{showDemo ? '2026.10.01 — 2026.10.31' : `${period.replace('-', ' 年 ')} 月`}<span className="meta-divider">/</span>{workspace}</p></div><div className="conversation-controls">{showDemo && <button className="replay-motion" onClick={replayMotion} title="重播柱状图与环形图的展开效果"><RotateCcw size={14}/><span>重播图表</span></button>}<button className="text-button material-toggle" aria-label="查看材料与报告" onClick={() => setModal('materials')}><FolderOpen size={16}/><span>材料与报告</span></button></div></header>
          <div className="preview-notice"><ShieldCheck size={14}/><span>演示模式 · 材料与核对结果均为示例</span><button onClick={() => setModal('help')}>了解详情<ArrowRight size={12}/></button></div>
          <div className="chat-scroll" ref={scrollRef}>
            <div className="chat-content">
              {messages.length === 0 && <div className="welcome"><h2>这次要核对哪个账期？</h2><p>添加同一账期的票据和银行流水，再告诉我需要核对的内容。</p><div className="welcome-actions"><button onClick={() => fileRef.current?.click()}><Paperclip size={18}/><span><strong>上传本期材料</strong><small>JPG、PNG 票据与 CSV 流水</small></span><ArrowRight size={16}/></button><button onClick={openDemo}><FileCheck2 size={18}/><span><strong>先看一份核对示例</strong><small>看看一笔 ¥270.00 的差额</small></span><ArrowRight size={16}/></button></div></div>}
              {messages.length > 0 && <div className="date-separator"><span/>{showDemo ? '10 月核对示例' : '本次咨询'}<span/></div>}
              {messages.map(message => <article className={`message ${message.role}`} key={message.id}>
                {message.role === 'user' ? <><div className="user-label">你</div><div className="user-bubble"><p>{message.text}</p>{message.files && <div className="message-files">{message.files.map((file, index) => <span key={index}><FileText size={14}/>{file}</span>)}</div>}</div></> : <><div className="assistant-label"><Mark small/><strong>账清助理</strong><span>{message.result ? '10 月核对' : '演示答复'}</span></div><div className="assistant-body"><p className="assistant-text">{message.text}</p>{message.result && <>
                  <LedgerCharts rows={DEMO_ROWS} selectedStatus={filter} onOpenEvidence={openEvidence} onSelectStatus={selectChartStatus}/>
                  <section className="result-card discrepancy" aria-label="方圆印务金额差异">
                    <div className="result-heading">
                      <div className="case-caption"><span>方圆印务</span><span>10 月 23 日 · LC-005</span></div>
                      <h2>付款与票据金额不一致</h2>
                      <dl className="case-amounts">
                        <div><dt>票据金额</dt><dd><Money value={differenceRow.invoiceCents}/></dd></div>
                        <div><dt>银行付款</dt><dd><Money value={differenceRow.transactionCents}/></dd></div>
                        <div className="case-difference"><dt>相差</dt><dd>{formatMoney(summary.differenceCents)}</dd></div>
                      </dl>
                    </div>
                    <div className="case-action">
                      <p>请补充这笔付款的说明或对应凭证，核实差额原因。</p>
                      <div><button className="primary-button" onClick={() => { setInput('关于方圆印务这笔 ¥270.00 的差额，我补充说明：'); inputRef.current?.focus(); }}>说明这笔差额<ArrowRight size={15}/></button><button className="evidence-link" onClick={() => openEvidence(DEMO_ROWS.find(r => r.status === 'difference')!)}>查看票据与流水依据</button></div>
                    </div>
                  </section>
                  <div className="other-findings" aria-label="另外两项待核实事项">
                    <div className="finding"><div><span className="finding-type">重复票据</span><strong>和光空间</strong><p>同一张票据出现了两次，未重复计入。</p></div><button onClick={() => openEvidence(DEMO_ROWS.find(r => r.status === 'duplicate')!)}>查看<ChevronRight size={14}/></button></div>
                    <div className="finding"><div><span className="finding-type">缺少凭证</span><strong>拾光办公 · ¥560.00</strong><p>已付款，尚未找到对应票据，需补充凭证。</p></div><button onClick={() => openEvidence(DEMO_ROWS.find(r => r.status === 'missing')!)}>查看<ChevronRight size={14}/></button></div>
                  </div>
                  <details className="ledger-details" ref={detailsRef} open={detailsOpen} onToggle={e => setDetailsOpen(e.currentTarget.open)}>
                    <summary><ChevronRight size={15}/><span>查看全部核对明细</span><small>4 笔一致 · 3 项待核实</small></summary>
                    <div className="result-detail">{(filter === 'difference' || filter === 'missing') && <div className="specific-filter"><span>当前筛选：{statusText[filter]}</span><button onClick={() => setFilter('all')}>显示全部</button></div>}<div className="result-toolbar"><div className="result-tabs" aria-label="筛选核对明细">{([{key:'all',name:'全部',count:7},{key:'issues',name:'待核实',count:3},{key:'matched',name:'核对一致',count:4}] as const).map(tab => <button key={tab.key} aria-pressed={filter === tab.key} className={filter === tab.key ? 'active' : ''} onClick={() => setFilter(tab.key)}>{tab.name}<span>{tab.count}</span></button>)}</div></div>{table(visibleRows)}<div className="detail-download"><button onClick={downloadCsv}><ArrowDownToLine size={15}/>下载 CSV 明细</button></div></div>
                  </details>
                  <div className="report-entry"><span>已发布报告保留以上待核实事项</span><button onClick={() => setModal('report')}>查看完整报告<ArrowRight size={15}/></button></div>
                </>}</div></>}
              </article>)}
              {busy && <div className="busy-state" role="status"><Mark small/><span>正在整理答复…</span><button onClick={stop}>停止</button></div>}
              <div ref={bottomRef}/>
            </div>
          </div>
          <div className="composer-area"><div className="suggestions">{showDemo ? <><button onClick={() => send('这笔 ¥270.00 的差额是什么？')} disabled={busy}>这笔差额是什么？<ArrowUp size={12}/></button><button onClick={() => send('缺少的凭证要怎么补？')} disabled={busy}>如何补充凭证？<ArrowUp size={12}/></button></> : <button onClick={openDemo}>查看示例<ArrowRight size={12}/></button>}</div><form className="composer" onSubmit={e => {e.preventDefault();send();}} onDragOver={e => e.preventDefault()} onDrop={e => {e.preventDefault();void addFiles(e.dataTransfer.files);}}>
            {pendingFiles.length > 0 && <div className="pending-files">{pendingFiles.map((file,i) => <span key={i}><FileText size={13}/><span>{file.name}</span><button type="button" aria-label={`移除${file.name}`} onClick={() => setPendingFiles(prev => prev.filter((_,index) => i !== index))}><X size={12}/></button></span>)}</div>}
            <textarea ref={inputRef} value={input} onChange={e => setInput(e.target.value)} aria-label="输入咨询内容" placeholder="输入问题或补充说明…" rows={2} maxLength={3000} onKeyDown={e => {if(e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing){e.preventDefault();send();}}}/><div className="composer-tools"><div><button type="button" className="icon-btn attach-btn" aria-label="上传票据和流水" onClick={() => fileRef.current?.click()} disabled={busy || fileBusy}><Paperclip size={19}/></button><span>{fileBusy ? '正在检查文件…' : 'JPG / PNG / CSV'}</span></div><div><span className="enter-hint">Enter 发送</span>{busy ? <button type="button" className="send-button" aria-label="停止答复" onClick={stop}><Square size={15} fill="currentColor"/></button> : <button type="submit" className="send-button" aria-label="发送消息" disabled={fileBusy || (!input.trim() && !pendingFiles.length)}><ArrowUp size={20}/></button>}</div></div></form><input className="sr-only" ref={fileRef} type="file" accept=".jpg,.jpeg,.png,.csv" multiple onChange={e => void addFiles(e.target.files)}/>{error && <div className="upload-error" role="alert"><TriangleAlert size={14}/>{error}<button onClick={() => {setError('');if(fileRef.current)fileRef.current.value='';}}>知道了</button></div>}<div className="composer-footnote"><span>支持 JPG、PNG 票据和 CSV 流水</span></div></div>
        </section>
        <aside className="evidence-panel" aria-label="材料与报告"><div className="aside-heading"><span>材料与报告</span><FolderOpen size={17}/></div>{materials()}</aside>
      </div>
    </main>

    <dialog ref={dialogRef} onCancel={() => setModal(null)} onClick={e => {if(e.target === e.currentTarget) setModal(null);}} className={`modal ${modal === 'report' ? 'report-modal' : ''}`} aria-labelledby="modal-title">
      <div className="modal-top"><span><Mark small/><strong id="modal-title">{modal === 'report' ? '10 月账目核对报告' : modal === 'evidence' ? '核对依据' : modal === 'materials' ? '材料与报告' : modal === 'workspace' ? '本次咨询信息' : '关于小账房'}</strong></span><button className="icon-btn" aria-label="关闭弹窗" onClick={() => setModal(null)}><X size={20}/></button></div>
      <div className="modal-body">
        {modal === 'report' && <div className="print-report"><div className="report-cover"><span className="report-kicker">LedgerCrew · 小账房</span><h2>10 月账目核对报告</h2><p>{workspace} · 2026.10.01 — 2026.10.31</p><span className="demo-stamp">合成示例 · 已发布 v1.0</span></div><div className="report-summary"><div><span>有效票据金额</span><strong>{formatMoney(summary.invoiceTotalCents)}</strong></div><div><span>银行流水金额</span><strong>{formatMoney(summary.transactionTotalCents)}</strong></div><div><span>单笔金额差额</span><strong>{formatMoney(summary.differenceCents)}</strong></div></div><h3>核对结论</h3><p className="report-paragraph">4 笔交易符合示例匹配条件；1 笔票据与流水相差 ¥270.00；1 张票据为重复件，未重复计入；1 笔 ¥560.00 的付款缺少票据。票据与流水总额相差 ¥830.00，由 ¥270.00 的单笔差额和 ¥560.00 的缺票付款组成。</p>{table(DEMO_ROWS,true)}<h3>未解决事项</h3><ul className="report-issues"><li>金额差异：补充 ¥270.00 差额的付款说明及对应凭证</li><li>重复票据：保留重复件标记，核实后归档</li><li>缺少凭证：补充 ¥560.00 付款的票据或用途说明</li></ul><p className="report-disclaimer">本报告仅用于展示用户端交付体验。示例结果不构成对实际账目的核验、审计或税务意见。</p><div className="modal-actions"><button className="secondary-button" onClick={() => window.print()}><Printer size={16}/>打印报告</button><button className="primary-button" onClick={downloadCsv}><ArrowDownToLine size={16}/>下载 CSV 明细</button></div></div>}
        {modal === 'evidence' && <div className="evidence-detail"><span className={`row-status ${selectedRow.status}`}><span className="status-dot"/>{statusText[selectedRow.status]}</span><h2>{selectedRow.counterparty}</h2><p>{selectedRow.date} · {selectedRow.id} · 合成示例</p><div className="evidence-amounts"><div><span>票据金额</span><strong><Money value={selectedRow.invoiceCents}/></strong></div><ArrowRight size={18}/><div><span>流水金额</span><strong><Money value={selectedRow.transactionCents}/></strong></div></div><h3>核对说明</h3><p className="report-paragraph">{selectedRow.status === 'matched' ? '示例中交易方、收支方向和金额一致，日期相差不超过 3 天，且对应关系唯一。' : selectedRow.status === 'difference' ? '票据金额 ¥2,580.00，银行付款 ¥2,850.00，金额相差 ¥270.00。需补充对应凭证或付款说明，目前无法判定差额原因。' : selectedRow.status === 'duplicate' ? '本票据与另一张票据对应同一笔交易，已单独标记，不重复计入有效票据金额。' : '存在 ¥560.00 的银行付款，但未找到对应票据。当前仅标记为缺少凭证，不能据此认定交易错误。'}</p><h3>材料来源</h3><ul className="evidence-sources">{selectedRow.evidence.map((source,i) => <li key={i}><FileText size={16}/><span>{source}</span></li>)}</ul><div className="modal-actions"><button className="primary-button" onClick={() => {setModal(null);setInput(`关于${selectedRow.counterparty}这笔交易，我补充说明：`);inputRef.current?.focus();}}>补充这笔交易的说明<ArrowRight size={16}/></button></div></div>}
        {modal === 'materials' && materials()}
        {modal === 'workspace' && <form className="workspace-form" onSubmit={(e:FormEvent) => {e.preventDefault();setWorkspace(draftName.trim());setPeriod(draftPeriod);setModal(null);}}><label>工作室名称<input value={draftName} maxLength={24} required onChange={e => setDraftName(e.target.value)} /></label><label>账期<input type="month" value={draftPeriod} min="2020-01" max="2099-12" required onChange={e => setDraftPeriod(e.target.value)}/></label><p>修改信息会用于新咨询；示例报告仍使用 2026 年 10 月的账期。</p><button className="primary-button" disabled={!draftName.trim() || !draftPeriod}>保存信息<Check size={16}/></button></form>}
        {modal === 'help' && <div className="help-content"><h2>小账房服务说明</h2><p>小账房为小型工作室提供票据整理、基础对账、异常说明和报告交付服务。</p><h3>第一阶段服务范围</h3><ul><li>最多 20 张 JPG / PNG 票据，单张不超过 5 MB</li><li>1 份 CSV 银行流水，不超过 200 条记录</li><li>人民币账目核对、异常清单、CSV 明细与可打印报告</li></ul><h3>这个预览可以体验什么</h3><p>查看合成示例，体验聊天、材料选择、结果筛选、证据查看、补充说明和报告下载。选择的文件仅保留在当前页面内存中，不上传；刷新即清除。聊天使用预设演示答复，不会分析真实文件。</p><h3>结论怎么展示</h3><p>只展示业务进度、核对结论和材料依据；缺少凭证或尚未核实的说明不会直接判定为错误。真实服务中的报告须审核发布后才向客户开放。</p><a href="https://github.com/taiyi747/LedgerCrew/blob/main/docs/PLAN.md" target="_blank" rel="noreferrer" className="source-link">查看项目第一阶段说明<ArrowRight size={14}/></a><h3>预览交互</h3><p>页面使用 GSAP 提供消息、筛选和弹窗的交互反馈；金额始终直接显示最终数值。</p>{showDemo && <button className="secondary-button" onClick={() => {setModal(null);replayMotion();}}><RotateCcw size={14}/>重播结果呈现</button>}<p className="attribution">界面工艺参考 <a href="https://github.com/heydamir/unslop" target="_blank" rel="noreferrer">unslop</a> · Damir Sokolovsky · CC BY 4.0</p></div>}
      </div>
    </dialog>
  </div>;
}
