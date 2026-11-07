import type { Metadata } from 'next';
import ReceptionClient from '../reception-client';
import '../customer.css';

export const metadata: Metadata = { title: '账清 · 咨询与材料提交' };
export default function UploadPage() { return <div className="customer-surface"><ReceptionClient/></div>; }
