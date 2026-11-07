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
- 后端：Python 3.14、FastAPI、Pydantic 2、SQLite、SQLAlchemy 2、Alembic。
- AI：MiMo API、Microsoft Agent Framework Python SDK、WorkflowBuilder、FileCheckpointStorage。
- 部署：本地服务，通过公网隧道暴露 Next.js；Next.js 代理后端 API。

核心流程：**聊天上传 → 材料预检 → 客户确认服务 → 总管派工 → 正式核对 → 人工审核 → 报告交付。**

## 当前状态

新增下单前接洽、混合 ZIP、客服轻量预检与服务确认卡，详见 **[接单迭代说明](docs/INTAKE_RECEPTION.md)**。客户点击确认前不生成订单；确认后自动接入现有总管与交付流程。

已接通真实客户页、老板作战室、FastAPI、独立 Worker 与 MiMo 总管委派工作流。客户上传真实材料后，总管实际派单，专业 Agent 调用受控工具执行，异常与报告交给老板审批；客户只可领取已发布结果。

**[本机完整启动与联调说明](docs/LIVE_INTEGRATION.md)** · [真实 MiMo 联调记录](docs/verification/live-integration.json)

客户入口为 `http://127.0.0.1:3210/`，老板入口为 `/owner/`，后端为 `127.0.0.1:8000`。运行说明分别见 [web/README.md](web/README.md) 与 [server/README.md](server/README.md)。老板控制台是 Next.js 原生页面，保留原作战室布局、网格工位和插画；交互组件使用 shadcn/ui。客户页、老板作战室及其组件和工位资源统一在 `web/` 中维护。

AI 独立 CLI 与样例继续保留，见 [AI 模块接入说明](docs/AI_INTEGRATION.md)。本轮不扩展第二阶段税务申报。

两个阶段的任务计划继续作为协作依据。请先完成并验收第一阶段 MVP，再领取第二阶段任务；第二阶段按里程碑推进，不计入原 MVP 的 40 小时承诺。请从各自的功能分支提交 PR。

首版交付账目核对报告和异常清单；体验交易明确标注为模拟交易。
