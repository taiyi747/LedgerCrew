import type { Metadata } from 'next';
import OwnerConsole from '@/components/owner/owner-console';

export const metadata: Metadata = { title: '经营仪表盘' };
export default function Page() { return <OwnerConsole view="dashboard"/>; }
