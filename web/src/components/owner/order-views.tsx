'use client';
import {useState} from 'react';
import {ArrowRightIcon,MagnifyingGlassIcon} from '@radix-ui/react-icons';
import {Button} from '@/components/ui/button';
import {Card,CardHeader,CardContent,CardTitle,CardDescription} from '@/components/ui/card';
import {Input} from '@/components/ui/input';
import {Table,TableHeader,TableHead,TableBody,TableRow,TableCell} from '@/components/ui/table';
import {EmptyState,StatusBadge} from './common';
import {cn} from '@/lib/utils';
import {roleLabels,type OwnerDashboard} from '@/lib/owner-api';
export function Stats({data}:{data:OwnerDashboard}){
  return <div className="grid grid-cols-2 overflow-hidden rounded-xl border bg-card md:grid-cols-4">{[
    {label:'服务订单',value:data.summary.orders,detail:'当前可见订单'},
    {label:'正在处理',value:data.summary.processing,detail:'AI 团队执行中'},
    {label:'等待处理',value:data.summary.waiting,detail:'人工审核或客户补充'},
    {label:'已完成交付',value:data.summary.delivered,detail:'客户可领取报告'},
  ].map((item,i)=><div className={cn('px-5 py-5 sm:px-6',i!==3&&'md:border-r',i<2&&'border-b md:border-b-0',i%2===0&&'border-r')} key={item.label}><p className="text-xs text-muted-foreground">{item.label}</p><p className="mt-2.5 font-mono text-3xl font-medium tracking-tight">{item.value}</p><p className="mt-1.5 text-[11px] text-muted-foreground">{item.detail}</p></div>)}</div>;
}

export function OrderList({data,select}:{data:OwnerDashboard;select:(id:string)=>void}){
  const [query,setQuery]=useState('');
  const rows=data.orders.filter(o=>!query||(o.studio_name||'').includes(query)||o.order_no.includes(query)||o.period_start.includes(query));
  return <section className="space-y-4"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center"><div><h2 className="text-sm font-medium">服务订单</h2><p className="mt-1 text-xs text-muted-foreground">选择订单查看本次处理的异常与报告。</p></div><div className="relative"><MagnifyingGlassIcon className="absolute top-2.5 left-3 size-4 text-muted-foreground"/><Input className="h-9 w-full pl-9 sm:w-64" value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜索商户、订单或账期" aria-label="搜索服务订单"/></div></div>{rows.length?<div className="overflow-hidden rounded-xl border bg-card"><Table><TableHeader><TableRow><TableHead className="pl-5">商户与订单</TableHead><TableHead>账期</TableHead><TableHead>业务状态</TableHead><TableHead className="text-right">材料版本</TableHead><TableHead className="pr-5 text-right">操作</TableHead></TableRow></TableHeader><TableBody>{rows.map(o=><TableRow key={o.id} className={o.id===data.selected_order_id?'bg-accent/50':''}><TableCell className="py-4 pl-5"><p className="font-medium">{o.studio_name||'工作室订单'}</p><p className="mt-1 font-mono text-[11px] text-muted-foreground">{o.order_no.slice(0,19)}</p></TableCell><TableCell>{o.period_start.slice(0,7)}</TableCell><TableCell><StatusBadge status={o.status}/></TableCell><TableCell className="text-right font-mono">v{o.input_revision}</TableCell><TableCell className="pr-5 text-right"><Button variant="ghost" size="sm" onClick={()=>select(o.id)}>{o.id===data.selected_order_id?'当前订单':'查看订单'}<ArrowRightIcon/></Button></TableCell></TableRow>)}</TableBody></Table></div>:<EmptyState title="暂无符合条件的订单" description="客户完成材料预检并确认服务后，会在这里生成订单。"/>}</section>;
}

export function Dashboard({data}:{data:OwnerDashboard}){
  const statusCounts=data.orders.reduce<Record<string,number>>((all,o)=>{all[o.status]=(all[o.status]||0)+1;return all;},{});
  return <div className="grid gap-6 xl:grid-cols-2"><Card className="shadow-none ring-border"><CardHeader><CardTitle>订单状态分布</CardTitle><CardDescription>按当前可见订单汇总。</CardDescription></CardHeader><CardContent>{Object.entries(statusCounts).length?<Table><TableHeader><TableRow><TableHead>业务状态</TableHead><TableHead className="text-right">订单数</TableHead></TableRow></TableHeader><TableBody>{Object.entries(statusCounts).map(([status,count])=><TableRow key={status}><TableCell><StatusBadge status={status}/></TableCell><TableCell className="text-right font-mono">{count}</TableCell></TableRow>)}</TableBody></Table>:<EmptyState title="还没有经营数据" description="第一笔服务订单创建后开始统计。"/>}</CardContent></Card><Card className="shadow-none ring-border"><CardHeader><CardTitle>当前订单 · Agent 产出</CardTitle><CardDescription>实际任务或派单的完成、排队与失败记录。</CardDescription></CardHeader><CardContent><Table><TableHeader><TableRow><TableHead>员工</TableHead><TableHead className="text-right">完成</TableHead><TableHead className="text-right">排队</TableHead><TableHead className="text-right">失败</TableHead></TableRow></TableHeader><TableBody>{data.agents.map(a=><TableRow key={a.id}><TableCell className="text-xs">{roleLabels[a.id]||a.name}</TableCell><TableCell className="text-right font-mono">{a.completed}</TableCell><TableCell className="text-right font-mono">{a.queued}</TableCell><TableCell className="text-right font-mono">{a.failed}</TableCell></TableRow>)}</TableBody></Table></CardContent></Card></div>;
}
