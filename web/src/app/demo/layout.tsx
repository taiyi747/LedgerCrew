import './demo.css';

export default function DemoLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <div className="demo-surface">{children}</div>;
}
