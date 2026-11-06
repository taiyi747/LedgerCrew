# LedgerCrew · 账清社

**一个人经营，一支 MiMo AI 财务团队交付。**

Junction China 2026 人工智能赛道参赛项目：为小型工作室提供票据整理、流水核对和异常说明服务，由一位老板统筹多个 AI Agent 完成接单、处理、审批和报告交付。

## 团队从这里开始

三位成员分别阅读自己的任务文档，接口约定与 40 小时排期见 **[公共协作约定](docs/PLAN.md)**。

| 角色 | 职责 | 独立任务文档 |
| --- | --- | --- |
| 前端开发 | 页面、交互、用户体验、前端部署与演示 | [FRONTEND.md · FE-01～FE-06](docs/FRONTEND.md) |
| 后端开发 | API、数据库、对账规则、Worker、审批与恢复 | [BACKEND.md · BE-01～BE-07](docs/BACKEND.md) |
| AI 开发 | MiMo 接入、Microsoft Agent Framework、Agent 与工作流 | [AI.md · AI-01～AI-07](docs/AI.md) |

## 技术方案

- 前端：Next.js App Router、TypeScript、Tailwind CSS。
- 后端：Python 3.11、FastAPI、Pydantic 2、SQLite、SQLAlchemy 2、Alembic。
- AI：MiMo API、Microsoft Agent Framework Python SDK、WorkflowBuilder、FileCheckpointStorage。
- 部署：本地服务，通过公网隧道暴露 Next.js；Next.js 代理后端 API。

核心流程：**模拟下单 → 上传材料 → 识别票据 → 核对流水 → 人工处理异常 → 审核报告 → 客户领取。**

## 当前状态

后端第一阶段已提供 FastAPI、数据库模型和 Alembic 初始迁移，安装、启动和测试说明见 [server/README.md](server/README.md)。前端及 Agent 应用代码尚未实现；后续按阶段验收联调。

首版交付账目核对报告和异常清单；体验交易明确标注为模拟交易。
