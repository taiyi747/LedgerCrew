import type { Metadata } from 'next';
import LiveClient from '../live-client';
import { AccountGuard } from '@/components/account/account-guard';

export const metadata: Metadata = { title: '账清 · 资料提交与清账结果' };
export default function UploadPage() { return <AccountGuard><LiveClient/></AccountGuard>; }
