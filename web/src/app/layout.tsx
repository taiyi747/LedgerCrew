import type { Metadata } from 'next';
import { GeistSans } from 'geist/font/sans';
import './globals.css';

export const metadata: Metadata = {
  title: { default: '小账房 LedgerCrew', template: '%s · 小账房' },
  description: '由一位经营者统筹多 Agent 团队，完成材料接洽、票据核对与报告交付。',
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // 浏览器扩展（如沉浸式翻译）会在 hydration 前给 <html> 注入属性，忽略该元素自身的属性比对。
  return <html lang="zh-CN" className={GeistSans.variable} suppressHydrationWarning><body className="font-sans antialiased" suppressHydrationWarning>{children}</body></html>;
}
