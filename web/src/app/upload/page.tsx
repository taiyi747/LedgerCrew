import type { Metadata } from 'next';
import { AccountGuard } from '@/components/account/account-guard';
import ReceptionClient from '../reception-client';
import '../customer.css';

export const metadata: Metadata = { title: '小账房 · 咨询与材料提交' };
export default function UploadPage() { return <AccountGuard><div className="customer-surface"><ReceptionClient/></div></AccountGuard>; }
