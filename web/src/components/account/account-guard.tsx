'use client';
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import { accountApi, type Account } from '@/lib/account';
import { ApiError } from '@/lib/api';
import styles from './account.module.css';
export function AccountGuard({children}: {children: ReactNode}) {
  const router=useRouter();
  const [user,setUser]=useState<Account|null>(null),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
  const check=useCallback(async()=>{
    setError('');
    try{setUser(await accountApi.me());}
    catch(e){if(e instanceof ApiError && e.status===401)router.replace('/start/?next='+encodeURIComponent(window.location.pathname+window.location.search+window.location.hash));else setError('暂时无法连接账号服务。请稍后重试。');}
  },[router]);
  useEffect(()=>{void check();const onFocus=()=>void check();window.addEventListener('focus',onFocus);return()=>window.removeEventListener('focus',onFocus);},[check]);
  useEffect(()=>{if(!user)return;const message=sessionStorage.getItem('ledgercrew.trial-notice');if(!message)return;setNotice(message);sessionStorage.removeItem('ledgercrew.trial-notice');sessionStorage.removeItem(`ledgercrew.trial-request.${user.id}`);const timer=setTimeout(()=>setNotice(''),6000);return()=>clearTimeout(timer);},[user]);
  async function logout(){if(busy)return;setBusy(true);try{await accountApi.logout();setUser(null);localStorage.removeItem('ledgercrew.order-id');router.replace('/start/');}catch(e){setError((e as Error).message);setBusy(false);}}
  if(!user)return <div className={styles.loading} role="status">{error||'正在确认登录状态…'}{error&&<button onClick={check}>重试</button>}</div>;
  return <div className={styles.workspace}><div className={styles.accountBar}><span>免费体验 · {user.username}</span>{error&&<span role="alert">{error}</span>}<button onClick={logout} disabled={busy}>{busy?'正在退出…':'退出登录'}</button></div>{children}{notice&&<div role="status" className={styles.notice}>{notice}</div>}</div>;
}
