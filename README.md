# LedgerCrew · 账清社

**一个人经营，一支 MiMo AI 财务团队交付。**

Junction China 2026 人工智能赛道参赛项目：为小型工作室提供票据整理、流水核对和异常说明服务，由一位老板统筹多个 AI Agent 完成接单、处理、审批和报告交付。

## 团队从这里开始

按两个阶段推进：先完成 MVP 并验收，再开发第二阶段。两个阶段各有前端、后端、AI 三份独立任务文档。

### 第一阶段：MVP（当前优先）

目标为票据整理、基础对账、异常处理和报告交付。接口约定与 40 小时排期见 **[MVP 公共协作约定](docs/PLAN.md)**。

| 角色 | 职责 | 独立任务文档 |
| --- | --- | --- |
| 前端开发 | 页面、交互、用户体验、前端部署与演示 | [FRONTEND.md · FE-01～FE-06](docs/FRONTEND.md) |
| 后端开发 | API、数据库、对账规则、Worker、审批与恢复 | [BACKEND.md · BE-01～BE-07](docs/BACKEND.md) |
| AI 开发 | MiMo 接入、Microsoft Agent Framework、Agent 与工作流 | [AI.md · AI-01～AI-07](docs/AI.md) |

### 第二阶段：MVP 验收后开发

目标为完整的 **OPC 财税服务运营平台**，服务 OPC、小型工作室和平台小微商户，扩展平台结算核对、账务分类、官方政策检索、确定性税务计算及申报材料生成。由一位经营者管理 Agent 团队，并审核关键异常和交付。

| 角色 | 第二阶段职责 | 独立任务文档 |
| --- | --- | --- |
| 前端开发 | 商户资料、结算核对、账务分类、政策依据、申报草稿与资料包 | [第二阶段前端计划](docs/phase-2/FRONTEND.md) |
| 后端开发 | 平台数据、结算规则、规则版本、税务计算、申报字段与版本化交付 | [第二阶段后端计划](docs/phase-2/BACKEND.md) |
| AI 开发 | 八个专业 Agent 与总管、官方政策研究、账务建议和申报协作 | [第二阶段 AI 计划](docs/phase-2/AI.md) |

第二阶段先验证 **一个地区、一类经营主体、一种申报事项、一个平台的数据格式**，再扩展覆盖。申报成果为带依据、可复核的草稿和材料清单，经人工审核后交付；自动提交至税务系统另行规划。

## 技术方案

- 前端：Next.js App Router、TypeScript、Tailwind CSS。
- 后端：Python 3.11、FastAPI、Pydantic 2、SQLite、SQLAlchemy 2、Alembic。第二阶段决策以 [P2_DECISIONS.md](docs/P2_DECISIONS.md) 为准。
- AI：MiMo API、Microsoft Agent Framework Python SDK、WorkflowBuilder、FileCheckpointStorage。
- 部署：本地服务，通过公网隧道暴露 Next.js；Next.js 代理后端 API。

仓库开发规范见 [AGENTS.md](AGENTS.md)；未确认的第二阶段业务规则不得进入正式实现。

核心流程：**模拟下单 → 上传材料 → 识别票据 → 核对流水 → 人工处理异常 → 审核报告 → 客户领取。**

## 当前状态

前端已新增 Next.js 客户端聊天界面和对账预览，运行说明见 [web/README.md](web/README.md)。

前端已提供 HTML/CSS/JavaScript 原型，包含任务流转大屏、接口文档和 Mock 后端，见 [HTML 前端](HTML/index.html) 与 [前端接口文档](HTML/api/接口文档.md)。

后端 v0.1 的第六个开发阶段已提供工作室、模拟订单、文件上传、ZIP 安全解压、资金流水 CSV 导入、确定性票据对账、Agent 集成契约、异常处理和版本化报告交付，安装、启动和测试说明见 [server/README.md](server/README.md)。

第一阶段 AI 模块已实现五个 Agent、真实 MiMo 调用、人工待办、报告草稿和检查点恢复。后端按依赖协议接入正式对账、数据库和 Worker，前端通过后端接口展示结果。

**[AI 模块安装、演示与后端接入](docs/AI_INTEGRATION.md)** · [真实调用验证记录](docs/verification/ai-live.json)

两个阶段的任务计划继续作为协作依据。请先完成并验收第一阶段 MVP，再领取第二阶段任务；第二阶段按里程碑推进，不计入原 MVP 的 40 小时承诺。请从各自的功能分支提交 PR。

首版交付账目核对报告和异常清单；体验交易明确标注为模拟交易。
