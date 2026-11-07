import type { Metadata } from 'next';
import OwnerConsole from '@/components/owner/owner-console';

export const metadata: Metadata = { title: '老板作战室' };
export default function Page() { return <OwnerConsole view="overview"/>; }
