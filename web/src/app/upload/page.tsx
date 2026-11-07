import type { Metadata } from 'next';
import LiveClient from '../live-client';

export const metadata: Metadata = { title: '账清 · 资料提交与清账结果' };
export default function UploadPage() { return <LiveClient/>; }
