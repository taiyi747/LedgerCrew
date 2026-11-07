import type { ReactNode } from 'react';
import { CheckCircledIcon, ExclamationTriangleIcon, InfoCircledIcon } from '@radix-ui/react-icons';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { stateLabels } from '@/lib/owner-api';
import { cn } from '@/lib/utils';

export function StatusBadge({ status }: { status: string }) {
  // Tones follow the brand swatch: soft sky for live work, the lemon band for
  // anything waiting on a person, restrained green/red for settled outcomes.
  const tone = ['failed','precheck_failed'].includes(status) ? 'border-[#f0c8c3] bg-[#fbe7e4] text-[#a63a32]' :
    ['running','processing','checking'].includes(status) ? 'border-[#9ddde8] bg-[#dff4fa] text-[#243e4c]' :
    ['paused','awaiting_owner_review','awaiting_customer','waiting_customer','waiting_owner','needs_info','ready_with_warnings','in_review'].includes(status) ? 'border-[#e6e3a6] bg-[#fffedb] text-[#5c5a26]' :
    ['delivered','succeeded','published','resolved'].includes(status) ? 'border-[#bfe3c9] bg-[#e9f7ed] text-[#285c3a]' : 'border-border bg-muted/60 text-muted-foreground';
  return <Badge variant="outline" className={cn('gap-1.5 rounded-md px-2 py-1 text-[11px] font-normal', tone)}><span className={cn('size-1.5 rounded-full bg-current', ['running','checking'].includes(status) && 'motion-safe:animate-pulse')}/>{stateLabels[status] || status}</Badge>;
}
export function EmptyState({ title, description, action, icon }: { title: string; description: string; action?: ReactNode; icon?: ReactNode }) {
  return <div className="flex min-h-52 flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border px-6 py-10 text-center"><span className="flex size-10 items-center justify-center rounded-xl bg-muted text-muted-foreground">{icon || <InfoCircledIcon className="size-5"/>}</span><div><h3 className="text-sm font-medium">{title}</h3><p className="mt-1.5 max-w-sm text-xs leading-6 text-muted-foreground">{description}</p></div>{action}</div>;
}
export function ErrorNotice({ message, retry }: { message: string; retry?: () => void }) {
  return <Alert variant="destructive" className="rounded-xl border-[#f0c8c3] bg-[#fbe7e4] text-[#a63a32]"><ExclamationTriangleIcon/><AlertTitle>操作未完成</AlertTitle><AlertDescription className="flex flex-wrap items-center gap-3">{message}{retry && <Button size="sm" variant="outline" onClick={retry}>重新加载</Button>}</AlertDescription></Alert>;
}
export function SuccessNotice({ children }: { children: ReactNode }) {
  return <Alert className="rounded-xl border-[#bfe3c9] bg-[#e9f7ed] text-[#285c3a]"><CheckCircledIcon/><AlertDescription>{children}</AlertDescription></Alert>;
}
export function PanelSkeleton() {
  return <div aria-label="正在加载" className="space-y-5"><Skeleton className="h-6 w-44"/><Skeleton className="h-4 w-72 max-w-full"/><div className="grid gap-3 sm:grid-cols-2"><Skeleton className="h-28"/><Skeleton className="h-28"/></div><Skeleton className="h-48 w-full"/></div>;
}
export function EvidenceDetails({ value, title = '查看证据与来源' }: { value: unknown; title?: string }) {
  return <details className="rounded-lg border border-border bg-muted/30 text-xs"><summary className="cursor-pointer px-3 py-2.5 text-muted-foreground hover:text-foreground">{title}</summary><pre className="max-h-64 overflow-auto border-t px-3 py-3 text-[11px] leading-5 whitespace-pre-wrap break-all">{JSON.stringify(value, null, 2)}</pre></details>;
}
