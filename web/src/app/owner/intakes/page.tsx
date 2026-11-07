import type { Metadata } from 'next';
import OwnerConsole from '@/components/owner/owner-console';

export const metadata: Metadata = { title: '接洽预检' };
export default function Page() { return <OwnerConsole view="intakes"/>; }
