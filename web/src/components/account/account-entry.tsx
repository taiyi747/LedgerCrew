'use client';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowRight, BookOpenCheck, Check, CheckCircle2, LoaderCircle, LockKeyhole, ArrowLeft } from 'lucide-react';
import { accountApi, uploadDestination, type Account } from '@/lib/account';
import { ApiError } from '@/lib/api';
import styles from './account.module.css';

export function AccountEntry() {
  const router = useRouter();
  const [tab,setTab] = useState<'register'|'login'>('register');
  const [user,setUser] = useState<Account|null>(null), [checking,setChecking] = useState(true);
  const [username,setUsername] = useState(''), [password,setPassword] = useState(''), [confirm,setConfirm] = useState('');
  const [busy,setBusy] = useState(false), [error,setError] = useState(''), [success,setSuccess] = useState('');
  const lock = useRef(false), requestId = useRef('');
  useEffect(()=>{ let active=true; accountApi.me().then(value=>{if(active)setUser(value);}).catch(e=>{if(active && (!(e instanceof ApiError) || e.status!==401))setError('暂时无法连接账号服务，请稍后重试。');}).finally(()=>{if(active)setChecking(false);});return()=>{active=false;}; },[]);
  async function submit(event: FormEvent) {
    event.preventDefault(); if(lock.current || checking) return;
    setError('');setSuccess('');
    if(!user && !username.trim()){setError('请输入用户名');return;}
    if(!user && !password){setError('请输入密码');return;}
    if(!user && tab==='register' && password!==confirm){setError('两次输入的密码不一致');return;}
    lock.current=true;setBusy(true);
    try {
      const current = user || await (tab==='register' ? accountApi.register(username.trim(),password,confirm) : accountApi.login(username.trim(),password));
      setUser(current);setPassword('');setConfirm('');
      // Retain the same key across a lost response or a reload; clear only once navigation succeeds.
      if(!requestId.current) requestId.current=sessionStorage.getItem(`ledgercrew.trial-request.${current.id}`)||crypto.randomUUID();
      sessionStorage.setItem(`ledgercrew.trial-request.${current.id}`,requestId.current);
      await accountApi.trial(requestId.current);
      setSuccess('正在进入资料提交页…');
      router.replace(uploadDestination(new URLSearchParams(window.location.search).get('next')));
    } catch(e) { setError(e instanceof Error ? e.message : '操作未完成，请重试');lock.current=false;setBusy(false); }
  }
  async function logout() {
    if(lock.current)return;lock.current=true;setBusy(true);setError('');
    try{await accountApi.logout();setUser(null);setPassword('');setConfirm('');requestId.current='';localStorage.removeItem('ledgercrew.order-id');}
    catch(e){setError((e as Error).message);}finally{lock.current=false;setBusy(false);}
  }
  function switchTab(value: 'register'|'login'){setTab(value);setError('');setPassword('');setConfirm('');}
  return <div className={styles.page}>
    <header className={styles.header}><Link href="/" className={styles.brand}><span className="brand-mark"><BookOpenCheck size={24}/></span><span><span className={styles.brandName}>小账房</span><small>LedgerCrew</small></span></Link><Link href="/" className={styles.back}><ArrowLeft size={15}/>返回首页</Link></header>
    <main className={styles.main}>
      <div className={styles.intro}><p className={styles.eyebrow}>从这一笔，开始理清</p><h1>开启你的智能清账之旅<span>。</span></h1><p>选择免费体验，把繁杂的票据，交给有条理的 AI 财务团队。</p></div>
      <div className={styles.columns}>
        <section className={styles.plans} aria-labelledby="plans-title"><h2 id="plans-title" className={styles.sectionTitle}>服务方案<span>01 / 选择方案</span></h2>
          <article className={styles.free} aria-label="免费体验，已选中"><div className={styles.cardTop}><span className={styles.planCode}>FREE</span><span className={styles.selected}><CheckCircle2 size={15}/>已选中 · 当前开放</span></div><div className={styles.priceLine}><h3>免费体验</h3><p>¥<strong>0</strong><span>无需支付</span></p></div><ul><li><Check size={16}/>体验现有账单上传功能</li><li><Check size={16}/>体验现有 AI 清账功能</li><li><Check size={16}/>查看系统支持的处理结果</li></ul><p className={styles.supported}>当前支持 JPG / PNG 票据与 CSV 流水</p></article>
          <div className={styles.futureGrid}>{[{code:'PRO',name:'专业版',audience:'面向个人及高频使用者',detail:'规划更高使用额度、更丰富的账单处理能力和历史记录管理。'},{code:'ENTERPRISE',name:'企业版',audience:'面向企业和团队',detail:'规划批量账单处理、多成员协作和企业账目管理。'}].map(plan=><article key={plan.code} className={styles.future}><div className={styles.cardTop}><span className={styles.planCode}>{plan.code}</span><span className={styles.coming}>即将开放</span></div><h3>{plan.name}</h3><p className={styles.unpriced}>价格待公布</p><p>{plan.audience}</p><p className={styles.planDetail}>{plan.detail}</p></article>)}</div>
          <p className={styles.planning}>专业版与企业版为产品规划，暂不支持购买或开通。</p>
        </section>
        <section className={styles.account} aria-labelledby="account-title"><div className={styles.accountHeading}><span className={styles.step}>02 / 账号确认</span><LockKeyhole size={19}/></div><h2 id="account-title">{user?'准备好，理清第一笔账。':'为你的账目，留一个位置。'}</h2><p className={styles.accountLead}>{user?`当前账号：${user.username}`:'保存你的资料与清账进度，下次回来继续。'}</p>
          {!user && <div className={styles.tabs} role="tablist" aria-label="账号操作"><button id="register-tab" type="button" role="tab" aria-selected={tab==='register'} aria-controls="account-form" disabled={busy||checking} onClick={()=>switchTab('register')}>注册账号</button><button id="login-tab" type="button" role="tab" aria-selected={tab==='login'} aria-controls="account-form" disabled={busy||checking} onClick={()=>switchTab('login')}>登录账号</button></div>}
          <form id="account-form" onSubmit={submit} className={styles.form} aria-labelledby={user?'account-title':`${tab}-tab`}>
            {!user && <><label htmlFor="account-username">用户名<input id="account-username" name="username" autoComplete="username" value={username} maxLength={64} onChange={e=>setUsername(e.target.value)} disabled={busy||checking} placeholder="给你的账号起个名字" required/></label><label htmlFor="account-password">{tab==='register'?'设置密码':'密码'}<input id="account-password" name="password" type="password" autoComplete={tab==='register'?'new-password':'current-password'} value={password} maxLength={256} onChange={e=>setPassword(e.target.value)} disabled={busy||checking} required/></label>{tab==='register'&&<label htmlFor="account-confirm">确认密码<input id="account-confirm" name="confirm-password" type="password" autoComplete="new-password" value={confirm} maxLength={256} onChange={e=>setConfirm(e.target.value)} disabled={busy||checking} required/></label>}</>}
            {error&&<p role="alert" className={styles.error}>{error}</p>}{success&&<p role="status" className={styles.success}>{success}</p>}
            <button className={styles.submit} type="submit" disabled={busy||checking}>{busy||checking?<LoaderCircle size={18} className={styles.spin}/>:null}{checking?'正在确认登录状态…':busy?'正在开启免费体验…':user?'开始免费体验':tab==='register'?'注册并开始免费体验':'登录并继续体验'}{!busy&&!checking&&<ArrowRight size={18}/>}</button>
            {user&&<button type="button" className={styles.switchAccount} disabled={busy} onClick={logout}>退出登录 / 更换账号</button>}
          </form>
        </section>
      </div>
    </main><footer className={styles.footer}><span><span className={styles.brandName}>小账房</span> LedgerCrew</span><span>让每一笔账，都有迹可循。</span></footer>
  </div>;
}
