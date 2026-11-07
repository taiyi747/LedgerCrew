import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowDown, ArrowUpRight, BookOpenCheck, ArrowRight } from 'lucide-react';
import { HeroVisual } from '@/components/landing/hero-visual';
import { ParticleField } from '@/components/landing/particle-field';
import { ServiceCapabilities, Workflow } from '@/components/landing/landing-sections';
import styles from '@/components/landing/landing.module.css';

export const metadata: Metadata = {
  title: '小账房 · 让每一笔账，都有迹可循。',
  description: '面向工作室、个体商户与小微企业的 AI 财务团队。了解票据整理、流水核对与异常报告，进入用户端体验。',
};

export default function LandingPage() {
  return <div className={styles.landing}>
    <a className={styles.skipLink} href="#main-content">跳到主要内容</a>
    <header className={styles.header}>
      <div className={styles.navInner}>
        <Link href="/" className={styles.brand} aria-label="小账房首页"><span className="brand-mark"><BookOpenCheck size={25}/></span><span><span className={styles.brandName}>小账房</span><small>LedgerCrew</small></span></Link>
        <nav className={styles.navigation} aria-label="首页导航"><a href="#product">产品介绍</a><a href="#capabilities">服务能力</a><a href="#workflow">工作流程</a></nav>
        <Link className={`primary-button ${styles.navCta}`} href="/start/">开始清账<ArrowUpRight size={16}/></Link>
      </div>
    </header>
    <main id="main-content">
      <section id="product" className={styles.hero} aria-labelledby="hero-title">
        <ParticleField/>
        <div className={styles.heroCopy} data-particle-clear>
          <p className={styles.eyebrow}><span/>你的 AI 财务团队</p>
          <h1 id="hero-title" className={styles.wordmark}>小账房</h1>
          <p className={styles.brandEnglish}>LedgerCrew</p>
          <h2 className={styles.tagline}>让每一笔账，都有迹可循。</h2>
          <p className={styles.subtitle}>从杂乱票据到清晰报告，<br className={styles.desktopBreak}/>让 AI 财务团队帮你理清每一笔账。</p>
          <p className={styles.description}>面向工作室、个体商户和小微企业，<br/>整理票据、核对流水，让需要关注的差异清楚呈现。</p>
          <div className={styles.heroActions}><Link href="/start/" className={`primary-button ${styles.mainCta}`}>开始清账<ArrowRight size={19}/></Link><a href="#workflow" className={styles.quietLink}>了解工作流程<ArrowDown size={15}/></a></div>
          <p className={styles.heroCaption}>从繁杂财务资料到清晰账目报告</p>
        </div>
        <HeroVisual/>
      </section>
      <div className={styles.audience}><span>为认真经营的你而做</span><p>小型工作室<i/>个体商户<i/>小微企业</p><span>把时间，留给经营本身。</span></div>
      <ServiceCapabilities/>
      <Workflow/>
      <section className={styles.finalCta} aria-labelledby="start-title"><div><p className={styles.eyebrow}>从这一笔，开始理清</p><h2 id="start-title">让每一笔账，<br/>都有迹可循。</h2></div><div className={styles.finalAction}><Link href="/start/" className={`primary-button ${styles.mainCta}`}>立即开始清账<ArrowRight size={19}/></Link><p>进入用户端，添加本期材料</p></div></section>
      <aside className={styles.previewNote} aria-label="当前版本说明"><strong>资料提交与演示体验</strong><p>开始清账将进入资料提交页；你也可以先查看演示体验。当前支持 JPG / PNG 票据与 CSV 流水，需要核实的事项会单独保留，报告经审核后交付。</p></aside>
    </main>
    <footer className={styles.footer}><span className={styles.footerBrand}><BookOpenCheck size={18}/><span className={styles.brandName}>小账房</span><small>LedgerCrew</small></span><p>让账目清楚，让经营从容。</p><nav className={styles.entryLinks} aria-label="其他项目入口"><Link href="/demo/">演示体验</Link></nav><a href="#product">返回顶部 ↑</a></footer>
  </div>;
}
