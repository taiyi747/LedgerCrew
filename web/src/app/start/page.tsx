import type { Metadata } from 'next';
import { AccountEntry } from '@/components/account/account-entry';
export const metadata: Metadata = { title: '小账房 · 开启你的智能清账之旅' };
export default function StartPage() { return <AccountEntry/>; }
