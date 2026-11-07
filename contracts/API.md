# LedgerCrew P2-0 后端接口契约（待三人确认）

状态：**设计稿，P2-0 尚未冻结**。`openapi.json` 合并了当前 FastAPI 的 29 条既有路径（28 条 `/api/v1` 路径和 `/health`）与标为 `x-ledgercrew-status: proposed` 的第二阶段路径；后者尚未挂载，也不能视为可调用接口。`schemas.py` 是独立的 Pydantic 2 线协议设计，不导入业务代码。本轮不创建表、不修改旧路由、不执行迁移。所有未获确认的范围、权限、任务粒度和交付行为均由 [决策登记表](../docs/P2_DECISIONS.md) 控制；旧草案中的业务默认值不得作为实现依据。Python 3.11 已由 DEC-001 确认。

## 1. MVP 盘点与扩展边界

| 方面 | 现状与依据 | 第二阶段接法 |
| --- | --- | --- |
| 数据库 | `Studio` 以 `owner_user_id` 归属客户；`Order` 为月度模拟订单；`UploadedFile` 必须有 `order_id`。`StatementImport`、`BankTransaction` 保存 CSV 文件、原行与标准化流水；`InvoiceRecord` 关联审核/提取任务；`ReconciliationBatch/Match` 与 `ExceptionTicket` 是订单内确定性对账；`ReportVersion/ReviewAction` 是订单报告版本与审批。`AgentRun/Task`、`WorkflowEvent`、`AuditLog` 保存运行、事件和审计。见 `server/app/models/`。 | 保留所有表和 API；新 `FilingTask` 只以可选 `source_order_id` 关联旧订单，不能继承旧订单状态。新 `FilingFile` 独立保存申报来源；引用旧文件时必须通过关联订单与工作室归属校验。 |
| API | 现有 `/api/v1` 有工作室、订单、文件、流水导入、对账、异常、报告审核/发布、CSV 导出、订单 SSE 共 28 条路径；`/health` 为第 29 条。精确现状由 `server/app/main.py` 导出的 OpenAPI 复制到本文件的 OpenAPI。 | 新路由仍用 `/api/v1`，资源名为 filing/tax/platform/policy。旧路径、请求与响应保持原样。 |
| 权限 | 开发/测试以 `X-User-Id` 模拟身份，`DEV_OWNER_USER_IDS` 是老板；客户仅访问自有 Studio，越权对象通常 404；老板可审**MVP 报告**；生产受保护 API 返回 503。见 `security.py`、`access.py`。 | 新增资源继承身份与租户隔离安全边界；客户/老板对分类、规则、草稿和资料包的具体权限待 DEC-010、DEC-012、DEC-013 确认。生产认证未就绪仍返回 503。 |
| Agent | `AgentGateway` 是后端可信服务协议；任务状态 `queued/running/paused/succeeded/failed`，订单内幂等；v1 输入输出严格校验，任务创建和调用无客户 HTTP 写入口。真实 MiMo 工作流与 Gateway 尚未联调。 | 第二阶段 AI 通过可信内部适配器提交候选；不得直接写表或调用老板审批。P2 新 Agent schema 用 `2.0`，不改变 MVP 的 `1.0`。 |
| 状态 | 旧订单有 `draft → awaiting_materials → ready_to_process → processing → ... → delivered/failed`；报告有 `draft/in_review/approved/published/superseded`；异常有独立处理状态。见 `order_state.py`、`delivery.py`。 | FilingTask、Draft、Package 各有独立状态和版本；旧订单状态机完全不参与 P2 迁移。 |
| 迁移 | Alembic 线性 `0001_initial` → `0008_invoice_provenance`；`env.py` 使用 SQLite batch migration、外键检查，应用启动不建表。 | BE2-01 从 `0008` 新增独立迁移；优先新表，旧表只在经过兼容评审后扩列。迁移不能猜测旧 Studio 归属。 |

MVP 的 `ReconciliationMatch` 只允许一个票据对应一条流水且差额为零；第二阶段的多对一/一对多平台结算由新 `SettlementAllocation` 表表达，不能修改旧匹配语义。MVP 报告只基于订单对账，不能被当作税务申报草稿。`OPC` 是产品定位，不是 `entity_type` 或 `taxpayer_identity` 的合法默认值。

## 2. 通用线协议

- **ID**：新增实体和引用统一规范小写 UUID 字符串（JSON Schema `format: uuid`）；沿用 MVP 已有 UUID 值，不改旧 API 对 ID 的解析方式。事件与审计仍可用整数自增 ID。
- **金额**：`*_cents` 是 JSON 整数，Python `StrictInt`，允许有符号差额；原始金额文本只留在原始行，转换失败要报行错误。币种不能从平台样例推断，实际支持币种待 DEC-005 确认；Mock 中的 `CNY` 仅供结构展示。
- **比率**：十进制非负字符串，如 `"0.125"`；后端用 `Decimal`，禁用二进制浮点和科学计数法。具体税率、阈值与舍入办法来自已批准的规则版本，契约不预置。
- **日期/时间**：`YYYY-MM-DD`；时间输出 `YYYY-MM-DDTHH:mm:ss[.ffffff]Z`。输入带偏移量的时间先转 UTC，拒绝无时区时间。时间字段和业务所属期分开。
- **枚举**：取值只由 `schemas.py`/OpenAPI 定义，未知状态不当作成功。`filing_kind`、`entity_type`、`taxpayer_identity`、`region_code`、`platform_code` 保留受支持范围配置值；在首个场景经三人确认前不伪造枚举成员。
- **证据**：`EvidenceRef={kind,id,locator?,content_hash?}`。`locator` 指页码/行号/字段，不是存储路径。服务端逐条验证存在、租户归属、版本与内容哈希；不向客户/AI 泄露 `storage_key`。不可把未验证的 URL 当作已确认政策证据。
- **版本**：`data_version` 是申报任务数据快照的正整数；档案或已确认分类变化才推进。`rule_version` 是政策规则独立不可变字符串版本；`form_version` 属官方表单模板。`draft_version`/`package_version` 各自在任务内递增。草稿、计算与资料包记录固定的所有输入版本及 SHA256。改变数据、规则或表单使下游旧结果 `stale`，旧审批不再可用于发布。
- **错误**：MVP 外形 `{"error":{"code":"...","message":"..."}}` 保持兼容；P2 可增加 `blockers` 数组。`401 unauthorized`、`403 forbidden`（已知全局动作）、`404 not_found`（跨租户对象隐藏）、`409 business_blocked|idempotency_conflict`、`412 version_conflict`、`422 validation_error`、`503 authentication_unavailable`。非法状态转换为 409；未知 ID 为 404；错误不返回敏感对象存在性。
- **分页**：列表默认 `limit=20`、最大 100，`cursor` 为不透明字符串；返回 `{items,next_cursor}`，空结果 `{items:[],next_cursor:null}`。过滤参数见下节。固定稳定排序（创建时间、ID），游标绑定过滤条件。
- **写入**：所有 P2 POST/PATCH 除纯查询 `/supported-scopes/check` 必须带 `Idempotency-Key`；相同键+相同规范化请求返回同一结果，相同键+不同请求为 409。需版本前置的写入还带 `If-Match`，其值是文档中的目标版本字符串；缺失为 428 `precondition_required`，过期为 412。OpenAPI 中分别显式声明。

## 3. 领域模型与迁移规格

以下为**候选** SQLAlchemy/SQLite 结构，`!` 必填，`?` 可空；公共 `id! UUID PK`、`created_at! UTC` 不逐行重复。尚未写入 Alembic。所有 FK 在 SQLite 开启 `PRAGMA foreign_keys=ON`；状态与正版本须有 `CHECK`；时间/归属复合关系在服务层复核。`JSON` 内不是权威金额来源。表中仅保留技术身份/版本唯一约束；依赖 DEC-005/006/008/009/010/012 的业务唯一性一律不预设。

| 模型/表 | 字段（PK 外）与关系 | 唯一约束、索引、状态/版本 |
| --- | --- | --- |
| `MerchantTaxProfile / merchant_tax_profiles` | `studio_id! → studios.id`，`registered_name!`，`region_code!`，`entity_type!`，`taxpayer_identity?`，`tax_identifier?`，`effective_from!`，`effective_to?`，`profile_version!`，`updated_at!` | `INDEX(studio_id,effective_from)`、`CHECK(profile_version>0)`；区间不得反转；身份缺失时允许保存，但任务/计算阻塞。`id` 稳定，PATCH 递增版本；另有 `merchant_tax_profile_revisions` 以 `UNIQUE(profile_id,version)` 存不可变历史。税号等敏感字段只在授权读中返回。 |
| `FilingPeriod / filing_periods` | `period_start!`，`period_end!`，`period_label!`；任务 `filing_period_id! → filing_periods.id` | `INDEX(period_start,period_end)`；无业务唯一约束（DEC-004/008 待定）；所属期与创建时间不同。 |
| `SupportedScope / supported_scopes` | `region_code!`，`entity_type!`，`taxpayer_identity?`，`filing_kind!`，`platform_code!`，`platform_format_version!`，`form_version?`，`status!`，`scope_version!`，`verified_at?`，`unsupported_reason?` | `INDEX(status,region_code,filing_kind)`；`draft/verified/active/retired` 为候选状态；范围组合唯一性与任务可创建条件待 DEC-002～005/008。 |
| `RequiredMaterial / required_materials` | `scope_id! → supported_scopes.id`，`material_code!`，`display_name!`，`required!`，`accepted_types! JSON`，`rule_version?` | `INDEX(scope_id,required)`；材料代码是否在范围内唯一待 DEC-004/011；不从 AI 自由文字直接变更。 |
| `FilingTask / filing_tasks` | `profile_id! → merchant_tax_profiles.id`，`scope_id! → supported_scopes.id`，`filing_period_id! → filing_periods.id`，`source_order_id? → orders.id`，`status!`，`data_version!`，`scope_version!`，`updated_at!` | `INDEX(profile_id,status)`、`INDEX(source_order_id)`；**不设业务唯一约束**，任务粒度与更正/补报待 DEC-004/008；`source_order_id` 若有必须同 Studio。 |
| `PlatformImport / platform_imports` | `filing_task_id! → filing_tasks.id`，`filing_file_id! → filing_files.id`，`platform_code!`，`format_version!`，`status!`，`column_map_json!`，`total_rows!`，`accepted_rows!`，`duplicate_rows!`，`rejected_rows!`，`data_version!` | `INDEX(filing_task_id,created_at)`；`pending/parsed/needs_mapping/failed` 为候选状态；同文件是否可重导及去重口径待 DEC-005/009。 |
| `SettlementBatch / settlement_batches` | `filing_task_id! → filing_tasks.id`，`platform_code!`，`external_batch_id!`，`settlement_date?`，`expected_cents?`，`received_cents?`，`difference_cents?`，`status!`，`data_version!` | `INDEX(filing_task_id,settlement_date)`；`unmatched/partial/matched/needs_review` 为候选状态；批次唯一性、重复检测及多对多分配口径待 DEC-005/009。 |
| `PlatformRecord / platform_records` | `filing_task_id! → filing_tasks.id`，`import_id! → platform_imports.id`，`row_number!`，`external_id?`，`record_kind!`，`occurred_on!`，`settlement_external_id?`，`amount_cents!`，`currency!`，`source_hash!`，`raw_row_json!`，`data_version!` | `UNIQUE(import_id,row_number)` 仅标识导入文件中的物理行；不设跨导入外部 ID 唯一约束。`INDEX(filing_task_id,occurred_on)`、`INDEX(import_id,settlement_external_id)`；去重口径待 DEC-005/009。原始行不可改，标准化修正生成新版本。 |
| `AccountingSuggestion / accounting_suggestions` | `filing_task_id!`、`platform_record_id!`、`source_task_id? → filing_agent_tasks.id`、`proposed_category!`，`proposed_account_code?`，`rationale!`，`confidence!`，`evidence! JSON`，`status!`，`suggestion_version!`，`data_version!` | `INDEX(filing_task_id,status)`；`proposed/accepted/rejected/superseded` 为候选状态；建议不自动成为申报依据，确认流程待 DEC-010。 |
| `AccountingEntry / accounting_entries` | `filing_task_id!`，`platform_record_id?`，`suggestion_id? → accounting_suggestions.id`，`category!`，`account_code?`，`amount_cents!`，`evidence! JSON`，`confirmed_by!`，`entry_version!`，`data_version!` | `INDEX(filing_task_id,category)`；不设按平台记录的业务唯一约束；多分录/修订口径待 DEC-009/010。旧记录只作历史，跨来源金额不能重复计入。 |
| `PolicySource / policy_sources` | `title!`，`issuing_authority!`，`official_url!`，`published_on?`，`effective_from?`，`effective_to?`，`region_code!`，`snapshot_file_id? → filing_files.id`，`fetched_at!`，`content_hash!`，`source_version!`，`status!` | `UNIQUE(official_url,content_hash)`；`INDEX(region_code,effective_from)`；`candidate/verified/unavailable/retired`；官方链接和快照是证据，抓取失败不推定规则仍有效。 |
| `PolicyRule / policy_rules` | `rule_key!`，`rule_version!`，`region_code!`，`entity_type!`，`taxpayer_identity?`，`filing_kind!`，`period_start!`，`period_end?`，`form_version?`，`parameters! JSON`，`explanation!`，`status!`，`approved_by?`，`approved_at?`；来源通过 `policy_rule_sources` 多对多 | `UNIQUE(rule_key,rule_version)`；`INDEX(region_code,filing_kind,period_start,status)`；`candidate/under_review/approved/rejected/retired`。批准版本不可改，冲突不得自动挑一条。 |
| `TaxCalculation / tax_calculations` | `filing_task_id!`，`status!`，`data_version!`，`rule_versions! JSON`，`form_version!`，`calculation_version!`，`input_hash!`，`input_snapshot! JSON`，`lines! JSON`，`blockers! JSON` | `UNIQUE(filing_task_id,calculation_version)` 为版本身份；`INDEX(filing_task_id,status)`；`blocked/completed/stale`。输入哈希可索引但不预设不可重复计算；仅确定性代码可产出金额，保存公式、参数、舍入和中间值。 |
| `TaxReturnDraft / tax_return_drafts` | `filing_task_id!`，`calculation_id! → tax_calculations.id`，`form_version!`，`draft_version!`，`data_version!`，`rule_versions! JSON`，`status!`，`fields! JSON`，`missing_material_codes! JSON`，`blockers! JSON`，`content_hash!`，`approved_by?`，`approved_at?` | `UNIQUE(filing_task_id,draft_version)`；`INDEX(filing_task_id,status)`；`blocked/draft/in_review/approved/stale`。`fields` 仅存已核实官方表单版本的字段键；缺失用 `null` 加 blocker，不默认零。 |
| `FilingPackage / filing_packages` | `filing_task_id!`，`draft_id! → tax_return_drafts.id`，`draft_version!`，`data_version!`，`rule_versions! JSON`，`form_version!`，`package_version!`，`status!`，`manifest! JSON`，`content_hash!`，`approved_by?`，`approved_at?`，`published_at?` | `UNIQUE(filing_task_id,package_version)`；`INDEX(filing_task_id,status)`；`prepared/approved/published/superseded`。发布绑定审核的精确哈希与版本，站内发布不代表税务机关受理。 |

辅助新表候选：`merchant_tax_profile_revisions`（档案历史快照）、`filing_files`（申报文件元数据与不可变存储键；`filing_task_id` FK、SHA256、校验状态、大小、MIME）、`settlement_allocations`（批次与平台记录的金额分配，分配唯一性待 DEC-009）、`settlement_receipts`（批次与已授权银行流水/新申报流水的关联和分配金额）、`policy_rule_sources`（规则与来源关联）、`form_templates`（官方表单版本、来源、审核状态和经核实的字段映射）、`filing_agent_runs`/`filing_agent_tasks`/`filing_events`（申报独立编排、检查点和事件，可复用 Gateway 协议而不要求旧 `agent_tasks.order_id`）、`filing_review_actions`（审核动作、操作者、版本、哈希、理由、UTC 时间）、`filing_idempotency_keys`（actor、scope、key、请求哈希、响应引用唯一）。这些表是实现上述 14 个模型关系的候选结构，不复用订单报告表；业务关联/唯一性须待对应决策 confirmed 后落地。

**原始/标准化边界**：原文件与平台原行、银行原行、政策快照不可覆盖；解析映射、平台记录、结算分配、分类分录、计算和草稿是派生层。派生数据每次写入带来源 ID、哈希、数据/规则版本。`PlatformRecord.amount_cents` 可为有符号值，但业务含义取决于 `record_kind` 与官方导出格式；不从净到账推营业收入。跨期与内部转账必须显式标记并留证据。原始 JSON 不作为前端和 AI 的默认读取面。

## 4. 状态与权限

FilingTask、Draft 和 Package 的枚举目前仅是前端/AI 协作的**候选状态词汇**，并非已确认状态机。任务初始状态、允许的转换、谁能确认/取消/发布、资料包撤回与历史访问全部待 DEC-004/008/010/012。已确认的技术边界是数据、规则或表单变化不能继续使用过期计算和审批；客户端不能任意写入状态。任何正式状态转换都须待业务确认后在服务层实现。

新增资源的细粒度角色与可见性统一记为 `D`（decision pending，DEC-010/012/013）；唯一已确认的底线是沿用 MVP 身份与 Studio 租户隔离，生产模拟身份仍不可用。不得把 MVP 报告审批权限直接套到 P2 分类、规则、草稿或资料包。

## 5. 新 HTTP API 逐项契约

表内路径省略共同 `/api/v1`。`P` 为路径参数（均 UUID）；列表参数统一 `limit,cursor`，可用下列过滤：档案 `studio_id`；任务 `profile_id,status`；导入/记录 `status,record_kind`；批次 `status`；建议 `status`；规则 `region_code,filing_kind,status`；计算/草稿/包 `status`。查询过滤值不合法为 422。`∅` 表示无 Body。响应 `List<T>` 即 `{items:T[],next_cursor:string|null}`。`E` 为通用 `401/403/404/409/412/422/503`；`409` 的具体业务码列在后方。所有路由均有 `E`，即使某种错误在正常路径下不常见。写入缺少前置头另外返回 `428 precondition_required`。`K` 表示必需 `Idempotency-Key`；`Vn` 表示 `If-Match` 目标版本；`—` 表示只读/纯查询无需幂等和条件版本。返回结构由 `schemas.py` 和 `openapi.json` 精确定义。

| Method / URL | 参数 / Body | 成功响应 | 权限 | 幂等 / 版本 | 409 业务阻塞码 |
| --- | --- | --- | --- | --- | --- |
| GET `/studios/{studio_id}/tax-profiles` | P、分页 / ∅ | 200 `List<MerchantTaxProfileRead>` | D | — | `profile_unavailable` |
| POST `/studios/{studio_id}/tax-profiles` | P / `MerchantTaxProfileCreate` | 201 `MerchantTaxProfileRead` | D | K；新 `profile_version=1` | `profile_review_required` |
| GET `/tax-profiles/{profile_id}` | P / ∅ | 200 `MerchantTaxProfileRead` | D | — | `profile_unavailable` |
| PATCH `/tax-profiles/{profile_id}` | P / `MerchantTaxProfileUpdate` | 200 `MerchantTaxProfileRead` | D | K、V=`profile_version` | `profile_review_required` |
| GET `/supported-scopes` | 分页、范围过滤 / ∅ | 200 `List<SupportedScopeRead>` | D | —；响应带 `scope_version` | `scope_unavailable` |
| POST `/supported-scopes/check` | ∅ / `ScopeCheckRequest` | 200 `ScopeCheckResponse`（不支持为 `supported=false`） | D | 纯查询；响应带版本 | `scope_ambiguous` |
| POST `/filing-tasks` | ∅ / `FilingTaskCreate` | 201 `FilingTaskRead` | D | K；新资源版本起点为 1 | `unsupported_scope`；重复任务规则待 DEC-008 |
| GET `/filing-tasks` | 分页、过滤 / ∅ | 200 `List<FilingTaskRead>` | D | —；响应带数据/范围版本 | `task_unavailable` |
| GET `/filing-tasks/{filing_task_id}` | P / ∅ | 200 `FilingTaskRead` | D | —；响应带版本 | `task_unavailable` |
| POST `/filing-tasks/{filing_task_id}/files` | P、multipart `file` | 201 `FilingFileRead` | D | K、V=`data_version`；跨请求去重待 DEC-009 | `invalid_file`,`material_blocked` |
| POST `/filing-tasks/{filing_task_id}/platform-imports` | P / `PlatformImportCreate` | 201 `PlatformImportRead` | D | K、V=`data_version`；重复导入待 DEC-005/009 | `format_unsupported`,`mapping_required` |
| GET `/filing-tasks/{filing_task_id}/platform-imports` | P、分页 / ∅ | 200 `List<PlatformImportRead>` | D | —；带 `data_version` | `import_unavailable` |
| GET `/platform-imports/{import_id}` | P / ∅ | 200 `PlatformImportRead` | D | —；带 `data_version` | `import_unavailable` |
| GET `/platform-imports/{import_id}/records` | P、分页、过滤 / ∅ | 200 `List<PlatformRecordRead>` | D | —；带 `data_version` | `import_not_parsed` |
| GET `/filing-tasks/{filing_task_id}/settlement-batches` | P、分页、过滤 / ∅ | 200 `List<SettlementBatchRead>` | D | —；带 `data_version` | `settlement_pending` |
| GET `/settlement-batches/{batch_id}` | P / ∅ | 200 `SettlementBatchRead` | D | —；带 `data_version` | `settlement_pending` |
| GET `/filing-tasks/{filing_task_id}/accounting-suggestions` | P、分页、过滤 / ∅ | 200 `List<AccountingSuggestionRead>` | D | —；带 `data_version` | `suggestion_pending` |
| POST `/accounting-suggestions/{suggestion_id}/decisions` | P / `AccountingDecision` | 200 `AccountingDecisionResult`（拒绝时 `entry=null`） | D | K、V=`data_version` | `suggestion_stale`,`evidence_missing` |
| GET `/filing-tasks/{filing_task_id}/accounting-entries` | P、分页 / ∅ | 200 `List<AccountingEntryRead>` | D | —；带 `data_version` | `entry_unavailable` |
| GET `/policy-sources` | 分页、过滤 / ∅ | 200 `List<PolicySourceRead>` | D | —；带 `source_version` | `source_unavailable` |
| GET `/policy-rules` | 分页、过滤 / ∅ | 200 `List<PolicyRuleRead>` | D | —；带 `rule_version` | `rule_conflict` |
| GET `/policy-rules/{rule_id}` | P / ∅ | 200 `PolicyRuleRead` | D | —；带 `rule_version` | `rule_unavailable` |
| POST `/policy-rules/{rule_id}/decisions` | P / `PolicyRuleDecision` | 200 `PolicyRuleRead` | D | K、V=`rule_version` | `rule_conflict`,`source_unverified` |
| POST `/filing-tasks/{filing_task_id}/tax-calculations` | P / `TaxCalculationRun` | 201 `TaxCalculationRead`，阻塞时 `status=blocked` 且金额缺失 | D | K、V=`data_version`；规则/表单版本锁定 | `rule_missing`,`input_incomplete` |
| GET `/filing-tasks/{filing_task_id}/tax-calculations` | P、分页 / ∅ | 200 `List<TaxCalculationRead>` | D | —；所有版本保留 | `calculation_unavailable` |
| GET `/tax-calculations/{calculation_id}` | P / ∅ | 200 `TaxCalculationRead` | D | —；结果不可变 | `calculation_unavailable` |
| POST `/filing-tasks/{filing_task_id}/tax-return-drafts` | P / `TaxReturnDraftCreate` | 201 `TaxReturnDraftRead` | D | K、V=`data_version`；固定计算/表单版本 | `calculation_blocked`,`form_unverified` |
| GET `/filing-tasks/{filing_task_id}/tax-return-drafts` | P、分页 / ∅ | 200 `List<TaxReturnDraftRead>` | D | —；所有版本保留 | `draft_unavailable` |
| GET `/tax-return-drafts/{draft_id}` | P / ∅ | 200 `TaxReturnDraftRead` | D | —；内容不可变 | `draft_unavailable` |
| POST `/tax-return-drafts/{draft_id}/reviews` | P / `DraftReviewRequest` | 200 `TaxReturnDraftRead` | D | K、V=`draft_version`+哈希+`data_version` | `draft_blocked`,`stale_draft` |
| POST `/filing-tasks/{filing_task_id}/filing-packages` | P / `FilingPackagePrepare` | 201 `FilingPackageRead` | D | K、V=`data_version`+`draft_version` | `draft_not_approved` |
| GET `/filing-tasks/{filing_task_id}/filing-packages` | P、分页 / ∅ | 200 `List<FilingPackageRead>` | D | —；版本访问待 DEC-012 | `package_unavailable` |
| GET `/filing-packages/{package_id}` | P / ∅ | 200 `FilingPackageRead` | D | —；版本访问待 DEC-012 | `package_unavailable` |
| POST `/filing-packages/{package_id}/actions` | P / `PackageAction` | 200 `FilingPackageRead` | D | K、V=`package_version`+哈希 | `package_stale`,`approval_missing` |
| GET `/filing-packages/{package_id}/download` | P / ∅ | 200 `application/zip` | D | —；下载条件待 DEC-012 | `package_not_published` |

`D`：新资源的角色、可见性与审批人待 DEC-010/012/013，表中方法/Body/响应仅为接口扩展点，不能在业务决策前启用。平台结算候选由后端确定性服务生成，不开放任意“创建批次”接口；来源和分类候选由可信 AI 内部适配器提交，不开放客户 HTTP 写入，见 §7。

分类决策统一返回 `AccountingDecisionResult`；拒绝时 `entry=null`，接受或纠正时返回确认分录。前端可始终读取 `suggestion.status` 与 `data_version`。

## 6. 前端 Mock 与显示规则

`examples/` 按主要资源给出 `success`、`empty`、`validation_error`、`forbidden`、`business_blocked` JSON，可直接作为前端静态 fixture；目录 README 列出调用与字段说明。数字是**界面测试假数据**，不是税率、政策或实际申报表字段。Mock 不证明后端路由已经实现。前端在金额上按整数分显示，不能把 `null` 显示为零。显示规则或表单版本时带证据、状态和生效期；`blocked/stale` 草稿不能出现“可提交税局”按钮。站内交付只叫“已交付资料包”。

## 7. AI 内部契约

AI 可读：经服务层授权且按申报任务限域的商户档案必要字段、支持范围及所需材料、已验证的文件内容/受限下载句柄、标准化平台记录、结算分配、已确认分录、已批准政策与官方来源、确定性计算结果、草稿字段证据和 blockers。税号、原始文件与原始行按任务最小必要原则提供；存储键、其他客户、未授权订单不可读。

AI 可提交：`AgentSuggestionEnvelope` 内的 `AccountingSuggestionSubmit`，先用 `AgentPolicySourceEnvelope` 提交 `PolicySourceSubmit`，取得后端生成的来源 ID，再用 `AgentPolicyRuleEnvelope` 提交引用这些来源的 `PolicyRuleSubmit`；还可提交有证据的解释、问题和风险候选。`schema_version="2.0"`、来源任务、当前 `data_version`、证据引用必填；服务层先用 Pydantic 校验，再验证证据归属、版本、幂等。分类候选、政策候选只能处于 `proposed/candidate`，不能自动成为已确认分录或已批准规则。

AI 可调用的可信后端服务（非公开写路由）：`get_filing_context`、`get_normalized_platform_records`、`get_settlement_reconciliation`、`list_approved_policy_rules`、`run_tax_calculation`、`validate_form_mapping`、`submit_accounting_suggestions`、`submit_policy_candidates`。确定性计算、适用性判断、数据版本推进和持久化由后端负责；AI 只接收结构化结果并解释。

AI 不可修改：MVP 订单/文件/流水/对账、P2 原始文件和原始行、已确认分录、已批准规则、计算金额、表单模板、草稿已批准版本、包的发布状态、客户归属、审计日志。不得调用老板审核/发布接口，不得直接写 SQLite，不得自行假设税率或表单字段。

人工确认门禁：身份与适用范围有歧义、分类确认/纠正、官方来源与可执行规则批准、政策冲突处理、表单版本/字段映射批准、草稿审核、资料包发布。缺证据、规则/材料/字段不全则阻塞，不能用 Agent 文字替代确认。现有 `AgentGateway` 的 `1.0` 契约不被 `2.0` 自动覆盖；适配方式由 AI/后端在 BE2 阶段确定。

## 8. 兼容性与验证门槛

| 检查 | 当前 P2-0 结果 / BE2 实施门槛 |
| --- | --- |
| MVP 订单 | 旧订单、报告、上传与状态模型保持原样；本轮只修改 Python 版本配置和一处 3.11 语法。需在 3.11 跑完整现有 `pytest`。 |
| 原 API | `openapi.json` 拷贝现有 29 条 MVP 路径，再追加 P2 路径；BE2 应对比旧路径的 method、schema、状态码与鉴权。 |
| 申报任务独立 | 新 task、文件、批次、草稿、包均独立；与旧订单仅可选 FK；不得共享 `order_state`。 |
| 权限 | 沿用 MVP 身份和 Studio 租户隔离；P2 新审批/发布角色待 DEC-010/012/013。需回归跨租户 404 与生产 503。 |
| 独立迁移 | 新表从 `0008` 增量迁移，不能更改旧表的语义；BE2 在旧库副本升级、`foreign_key_check` 和回退验证。 |
| 规则/表单版本 | 规则、scope、表单模板、计算、草稿、包分别锁版本；BE2 测规则变更和表单变更导致审批失效。 |

P2-0 契约文件可解析，11 组 Mock JSON 可读取，35 个提议操作的 Schema 引用完整，现有 29 条 OpenAPI 路径与当前应用输出一致。2026-11-07 使用 Python 3.11.18 和新 `uv.lock` 安装全部 47 个依赖包，`ruff check app/agents scripts tests/agents` 通过，现有后端测试 **102 passed**。先前在 3.12 环境的测试不能作为兼容性证明。第二阶段 API、迁移及业务流程仍未实现。

## 9. 三人待确认的业务问题

1. **首个范围**：地区代码、实际经营主体类型、纳税人身份、申报事项（税务申报/财务报表/工商年报三选一）、平台及导出格式/版本分别是什么？AI 需给官方来源、所需材料与不支持边界，前端确认展示文案。
2. **档案与身份**：一个 Studio 是否可有多税务主体、历史身份如何生效、税号是否必须收集、客户能否自行修改已用于申报的档案？
3. **任务粒度**：同主体/事项/所属期是否允许补报、更正申报或多次交付？当前不添加申报任务业务唯一约束（DEC-008）。
4. **平台口径**：首个平台导出字段、原始 ID、退款/费用/补贴符号、结算批次与银行到账关联依据是什么？无外部 ID 时重复判定需要人工阈值还是全部待核实？
5. **资金与证据**：申报任务的银行/支付流水从旧订单引用、单独导入，还是两者并存？跨期和内部转账的确认角色是谁？
6. **分类确认人**：确认/纠正分类由谁操作，是否需要复核？待 DEC-010，当前不预设角色。
7. **政策与表单**：哪些官方来源可作为依据、规则批准人是谁、冲突升级给谁、表单模板版本如何命名和留存？实际税率/字段待官方核查后另行配置。
8. **资料包交付**：客户是否能预览未发布草稿、资料包格式与清单、发布后是否允许撤回、历史发布版本的可见期限是什么？
9. **认证与审批**：生产身份服务、老板角色与多人审批规则何时确定？当前开发头不能用于真实申报资料。

Python 3.11 已由 DEC-001 确认；Agent 运行边界仍待 DEC-014 实测与确认。

三人按 `docs/P2_DECISIONS.md` 确认受影响条目后才能冻结对应业务契约；与未确认业务无关的 Python 3.11 和基础设施工作可继续。税率、政策参数和表单字段需以已审核的官方版本单独落地。
