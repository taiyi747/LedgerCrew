import { BookOpenCheck, Check, FileImage, FileSpreadsheet, GitMerge, ScanLine, SearchCheck } from 'lucide-react';
import styles from './landing.module.css';
import { GlassCube } from './glass-cube';

/** Static scene: replace this component with an image, video or animation without changing the hero layout. */
export function HeroVisual() {
  return <div className={styles.visual} role="img" aria-label="静态协作示意：票据与银行流水经过整理、核对和复核，形成可追溯的清账报告。" data-visual-slot="hero">
    <div className={styles.visualGrid} aria-hidden="true"/>
    <div className={styles.sceneLabel} aria-hidden="true"><span/>LEDGERCREW / 财务协作示意</div>
    <div className={styles.sourceStack} aria-hidden="true"><div><FileImage size={22}/><span>本期票据<small>发票 · 报销凭证</small></span><Check size={14}/></div><div><FileSpreadsheet size={22}/><span>银行流水<small>收支记录 · CSV</small></span><Check size={14}/></div></div>
    <div className={styles.sceneConnector} aria-hidden="true"/>
    <div className={styles.agentRow} aria-hidden="true"><div><ScanLine size={20}/><span>整理</span></div><i/><div><GitMerge size={20}/><span>核对</span></div><i/><div><SearchCheck size={20}/><span>复核</span></div></div>
    <div className={styles.reportPaper} aria-hidden="true"><div className={styles.paperTop}><span><span className={styles.brandName}>小账房</span> / REPORT</span><BookOpenCheck size={21}/></div><h3>每一笔，都有依据。</h3><p>账目核对报告</p><div className={styles.paperRule}/><div className={styles.paperLine}><Check size={14}/><span>票据与流水对应</span><span>已核对</span></div><div className={styles.paperLine}><Check size={14}/><span>材料来源可追溯</span><span>已关联</span></div><div className={`${styles.paperLine} ${styles.paperReview}`}><span className={styles.reviewDot}/><span>差异单独列明</span><span>待核实</span></div><div className={styles.paperBottom}>从材料出发，以清晰交付。</div></div>
    <div className={styles.visualCaption} aria-hidden="true"><BookOpenCheck size={16}/><span>一份资料，一路有迹可循。</span><small>静态产品示意</small></div>
    <GlassCube/>
  </div>;
}
