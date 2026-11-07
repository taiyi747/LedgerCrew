import type { Metadata } from 'next';
import { GeistSans } from 'geist/font/sans';
import './globals.css';

export const metadata: Metadata = {
  title: { default: '账清社 LedgerCrew', template: '%s · 账清社' },
  description: '由一位经营者统筹多 Agent 团队，完成材料接洽、票据核对与报告交付。',
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN" className={GeistSans.variable}><body className="font-sans antialiased">{children}</body></html>;
}
