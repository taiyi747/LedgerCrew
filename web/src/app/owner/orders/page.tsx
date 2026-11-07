import type { Metadata } from 'next';
import OwnerConsole from '@/components/owner/owner-console';

export const metadata: Metadata = { title: '订单与审批' };
export default function Page() { return <OwnerConsole view="orders"/>; }
