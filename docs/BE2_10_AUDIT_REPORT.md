# BE2-10 实现审查与验收差距

审查日期：2026-11-07。结论：**v0.2 不能验收或上线**。本报告依据实际 `server/app/`、`server/alembic/versions/`、`server/tests/`、当前路由和 [决策登记表](P2_DECISIONS.md)，没有把计划、候选 OpenAPI 或 Mock 当作实现。`docs/P2_READINESS_REPORT.md` 与 `docs/P2_TASK_DEPENDENCIES.md` 当前不存在。

状态口径：`completed`＝实现、测试和必要文档均具备；`partially_completed`＝有可验证的一部分；`blocked`＝工作已展开但关键决策使其无法继续；`not_implemented`＝该 BE2 业务模块尚无运行代码。业务阻塞原因另列，不把缺失代码称作已完成。

## 第一阶段：BE2-01～09 实际代码核对

`server/app/models/__init__.py` 只注册 MVP 的 Studio、Order、文件、流水、票据、对账、Agent、事件、异常和报告模型。`server/app/api/v1/router.py` 只挂载 MVP 资源及正在开发/测试环境启用的认证路由；未挂载任何 filing、tax、policy、platform 或 scope 路由。`server/alembic/versions/` 只有从 `0001_initial` 到 `0008_invoice_provenance` 的八个 MVP revision。`server/tests/` 中没有 v0.2 业务测试。`contracts/schemas.py`、`contracts/openapi.json` 和 `contracts/examples/` 是独立候选契约，不在运行应用中注册。

| 任务 | 状态 | 模型 / migration / Service / API / Schema | 权限 / 幂等 / 审计 / pytest / 文档 | 最终验收影响 |
| --- | --- | --- | --- | --- |
| BE2-01 商户与申报领域 | `not_implemented` | 五个目标模型及迁移、服务、运行 Schema、路由均无。 | 无相应权限、幂等、审计和测试；仅有候选契约。 | 无档案、范围、所属期和申报任务，后续链路无主实体。 |
| BE2-02 平台数据与来源 | `not_implemented` | 无 FilingFile/PlatformImport/PlatformRecord、解析服务或 API。MVP CSV 导入是订单流水，不能充当平台导入。 | 无 P2 隔离、去重、来源追溯测试。 | 平台原始数据无法导入或追溯。 |
| BE2-03 结算与到账 | `not_implemented` | 无 SettlementBatch/Allocation/Receipt、确定性结算服务或 API。MVP ReconciliationBatch 语义不同。 | 无 P2 结算权限、幂等、审计和跨期测试。 | 855 元示例及部分/跨期到账无法验收。 |
| BE2-04 账务分类与修订 | `not_implemented` | 无 AccountingSuggestion/Entry、分类确认服务或 API。 | 无 P2 人工确认、修订版本、权限和测试。 | 分类不能作为正式计算输入。 |
| BE2-05 政策与规则版本 | `partially_completed` | 有不写库的候选 JSON 预检；无 PolicySource/Rule、官方来源快照、正式导入或 API。 | 仅有 synthetic 结构/身份冲突测试；无批准、持久化幂等、审计或适用测试。 | 不存在可审核、可适用的正式规则。 |
| BE2-06 确定性税务计算 | `not_implemented` | 无 TaxCalculation 模型、迁移、Service、运行 API 或 Schema。MVP 确定性对账不是税务计算。 | 无规则版本锁定、重算和舍入测试。 | 税额不可根据来源复算，不能声称申报能力。 |
| BE2-07 字段与草稿 | `partially_completed` | 有不写库的 synthetic 模板 JSON 预检；无表单模板持久化、字段映射、TaxReturnDraft 或路由。 | 无官方表间关系、模板适用或草稿测试。 | 无官方表单字段或可审草稿。 |
| BE2-08 工作流与版本审批 | `not_implemented` | 无 FilingTask 运行/事件/检查点及草稿审批。MVP AgentTask/Run、WorkflowEvent、ReportReviewAction 均以 Order/Report 为中心。 | 无 P2 权限、审批失效、恢复或审计测试。当前认证开发路由不等于 P2 审批。 | 不能验证 V1/V2 审批隔离和恢复。 |
| BE2-09 资料包与交付 | `not_implemented` | 无 FilingPackage、生成/发布/下载服务或路由。MVP 报告不能替代资料包。 | 无 P2 发布权限、幂等、审计、历史访问测试。 | 无可交付资料包。 |

上述九项业务实现分别受 DEC-002～014 中相关 pending 决策约束，见 [P2-0.5 审查](phase-2/P2-0.5-REVIEW.md)。特别是地区/身份/事项、Studio 多主体、历史身份、任务唯一性、平台及结算口径、审批权、政策/表单、资料包交付、生产认证和 Agent 运行边界，均不能凭候选 Mock 定案。`DEC-001` Python 3.11 是唯一 confirmed 项。

## 第二阶段：现有 Alembic 与 MVP 基线

- 八个 revision 构成单 head 线性链，当前 head 为 `0008_invoice_provenance`；没有 v0.2 revision，因此不存在可供验证的 v0.2 升级、回退、重复建表或新增 FK。
- **工作区现有 `server/ledgercrew.db` 只读检查为 `0004_statement_imports`**，其 11 张业务/版本表与该 revision 预期表集合相符，`integrity_check` 和 `foreign_key_check` 均通过。该库低于代码 head，不能直接作为当前应用完整功能验收库；本轮没有对它升级、降级或写入。实际业务行内容未读取。
- 新增的隔离测试 `server/tests/test_migration_safety.py` 从空库升级，逐表比对 SQLAlchemy metadata 的表、列、可空性、FK、显式索引和唯一约束，并运行 SQLite `foreign_key_check` 与 `integrity_check`。
- 同一测试从 `0007_delivery` 写入覆盖 Studio、Order、UploadedFile、StatementImport、BankTransaction、AgentRun/Task、WorkflowEvent、InvoiceRecord、ReconciliationBatch/Match、ExceptionTicket、ReportVersion、AuditLog 的合成关联数据，再升级到 `0008`、降回 `0007`、重新升级；检查旧行、主键关联、revision 与 FK。使用 SQLite backup API 在 WAL 模式备份和恢复独立测试库。
- `0008` downgrade 会删除 `invoice_records.source_task_id` 与 `material_review_task_id`。**若这些列已有数据，回退会丢失来源关系，不能称为无损回滚。** `0007` 及更早 revision 的 downgrade 还会删除该阶段新增的整张业务表。生产回退应使用经校验的升级前备份，见 [数据库迁移手册](DATABASE_MIGRATION.md)。
- 模型应用连接在 `server/app/db/session.py` 启用 `PRAGMA foreign_keys=ON`。Alembic 的 SQLite batch 迁移连接临时设为 OFF 并在完成后执行 `foreign_key_check`；迁移后普通应用连接仍启用约束。没有执行或改动任何真实数据库。

## 第三至六阶段：不可验收项

| 验收组 | 当前结论 | 原因 |
| --- | --- | --- |
| 政策/模板导入与重复执行 | `partially_completed` | synthetic 候选 JSON 的结构、哈希和 dry_run 身份冲突预检通过；BE2-05/07 持久化模型、正式导入/审核和真实来源仍不存在，DEC-011 未确认。 |
| 平台去重、结算、跨期、内部转账 | `blocked` | BE2-02/03 未实现，DEC-005/009 未确认。MVP CSV/对账测试不能外推成 P2 口径。 |
| 税务适用、阈值、舍入、表间关系 | `blocked` | BE2-06/07 未实现；没有经确认的政策、舍入和官方表单。 |
| P2 审批失效与工作流恢复 | `blocked` | BE2-08/09 未实现，DEC-010/012/014 未确认；MVP 报告审批和 Agent 检查点不能证明 P2 行为。 |
| MVP 回归 | 见 [测试报告](BE2_10_TEST_REPORT.md) | 以本轮实际 Python 3.11 测试、OpenAPI 路径对比及迁移基线结果为准。 |

## 安全与上线差距

MVP 的 Studio/Order 归属检查、跨租户隐藏、上传 ZIP 限制、原始数据持久化、Fake Agent 生产禁用和生产模拟身份 503 门禁均有现有代码及测试；这些证明范围限于 MVP。P2 档案、导入、计算、草稿、资料包的授权及数据隔离无运行接口，无法做安全验收。当前认证路由在开发/测试环境启用，生产身份提供者仍为 503 占位，DEC-013 pending。不能以此宣称具备真实客户生产认证。

## 本次安全修复与未解决问题

本次没有修改既有业务、迁移或 `uv.lock`。新增迁移/备份回归测试和验收、操作文档，仅验证当前 MVP 基线。未解决的阻塞项是 BE2-01～09 未实施、13 项业务决策 pending、v0.2 迁移/规则/模板不存在、生产认证未确定。**BE2-10 最终状态：`partially_completed`；v0.2 验收不通过。**
