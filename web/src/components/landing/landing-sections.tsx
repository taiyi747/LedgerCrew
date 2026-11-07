import { ArrowRight, Files, FileSearch, ScanLine } from 'lucide-react';
import styles from './landing.module.css';

const capabilities = [
  { icon: ScanLine, title: '智能票据整理', text: '将发票、订单、报销凭证归到一处，让杂乱资料有序可查。', label: '资料有来源' },
  { icon: Files, title: '财务流水核对', text: '辅助比对银行流水与业务单据，梳理每笔收支的对应关系。', label: '收支有对应' },
  { icon: FileSearch, title: '异常识别与报告', text: '标记金额差异、重复与缺票，形成清晰的核对结果和待核实清单。', label: '差异有说明' },
];
export function ServiceCapabilities() {
  return <section id="capabilities" className={styles.section} aria-labelledby="capabilities-title">
    <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>服务能力 / CAPABILITIES</p><h2 id="capabilities-title">从一堆资料，<br/>到一本明白账。</h2></div><p>让整理、核对与复核衔接起来。<br/>每一个结论，都能回到对应的材料。</p></div>
    <div className={styles.capabilityGrid}>{capabilities.map(({ icon: Icon, title, text, label }, index) => <article className={styles.capabilityCard} key={title} data-motion-slot="capability"><div className={styles.capabilityTop}><span className={styles.capabilityIcon}><Icon size={25}/></span><span>0{index+1}</span></div><h3>{title}</h3><p>{text}</p><div className={styles.capabilityFoot}>{label}<ArrowRight size={16}/></div></article>)}</div>
    <p className={styles.scopeNote}>票据整理、流水核对与报告交付相互衔接，需要核实的事项会单独保留。</p>
  </section>;
}
export function Workflow() {
  const steps = [
    { title:'提交资料', text:'准备同一账期的发票、账单与银行流水，在用户端添加支持格式的文件。' },
    { title:'AI 团队处理', text:'由 AI 分工识别、整理与辅助核对，待核实事项留待复核。' },
    { title:'查看清账结果', text:'查看清晰的核对报告、异常清单与对应依据，继续补充所需材料。' },
  ];
  return <section id="workflow" className={`${styles.section} ${styles.workflow}`} aria-labelledby="workflow-title"><div className={styles.sectionHeading}><div><p className={styles.eyebrow}>工作流程 / HOW IT WORKS</p><h2 id="workflow-title">三步，把账理清楚。</h2></div><p>你提交材料，我们呈现清晰的结果。<br/>需要核实的地方，始终明确保留。</p></div><ol className={styles.steps} data-motion-slot="workflow">{steps.map((step,index)=><li key={step.title}><span className={styles.stepNumber}>0{index+1}</span><h3>{step.title}</h3><p>{step.text}</p></li>)}</ol></section>;
}
