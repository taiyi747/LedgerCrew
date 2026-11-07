import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = {
  title: '账清社 LedgerCrew · 把每一笔账，理清楚',
  description: '面向小型工作室的票据整理与账目核对。用户端交互预览，使用明确标注的合成示例数据。'
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
