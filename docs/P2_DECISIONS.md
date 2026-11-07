# LedgerCrew 第二阶段决策登记表

本表是第二阶段业务实现的唯一确认入口。`current_status` 只能为 `pending`、`proposed`、`confirmed`、`rejected`。**只有 confirmed 且写明决定与确认日期的条目可作为正式业务规则。** `proposed_options` 仅供讨论，不表示默认选择；`—` 表示尚未确认。技术安全边界与已存在的 MVP 行为仍按项目规范执行。更新状态时保留历史决定记录于 Git。

## DEC-001 Python 版本

| 字段 | 内容 |
| --- | --- |
| decision_id | DEC-001 |
| question | 第二阶段 `server/` 使用哪个 Python 版本？ |
| current_status | confirmed |
| proposed_options | Python 3.11；其他版本（已被用户排除） |
| decision_owner | 项目负责人（用户） |
| business_impact | 后端部署与协作环境统一。 |
| technical_impact | `requires-python >=3.11,<3.12`、Ruff py311、锁文件/CI/测试均以 3.11 验证；不兼容 Agent 隔离。 |
| confirmed_decision | 后端固定 Python 3.11，不因 Agent 依赖升级。 |
| confirmation_date | 2026-11-07 |

## DEC-002 首个地区

| 字段 | 内容 |
| --- | --- |
| decision_id | DEC-002 |
| question | 首个可支持地区及地区代码是什么？ |
| current_status | pending |
| proposed_options | 由业务负责人提出候选地区，AI 核查官方来源，三人确认；当前不预设。 |
| decision_owner | 业务负责人 + 前端 + 后端 + AI |
| business_impact | 决定适用政策与客户可见的服务边界。 |
| technical_impact | SupportedScope 地区配置、规则检索、材料清单与表单版本。 |
| confirmed_decision | — |
| confirmation_date | — |

## DEC-003 经营主体与纳税人身份

| 字段 | 内容 |
| --- | --- |
| decision_id | DEC-003 |
| question | 首个经营主体类型、纳税人身份及所需核验字段是什么？ |
| current_status | pending |
| proposed_options | 由真实客户场景与官方材料共同确定；主体类型与纳税人身份分开记录。 |
| decision_owner | 业务负责人 + AI；后端/前端会签 |
| business_impact | 决定支持范围和资料收集。 |
| technical_impact | TaxProfile 字段与校验、规则适用条件；不能把 OPC 当税务身份。 |
| confirmed_decision | — |
| confirmation_date | — |

## DEC-004 申报事项与所属期

| 字段 | 内容 |
| --- | --- |
| decision_id | DEC-004 |
| question | 首个成果属于税务申报、财务报表还是工商年报？所属期及更正/补报如何定义？ |
| current_status | pending |
| proposed_options | 分别核查官方事项和表单后选定一个首发事项；不预设周期。 |
| decision_owner | 业务负责人 + AI；后端/前端会签 |
| business_impact | 决定产品承诺、办理提醒和材料。 |
| technical_impact | FilingPeriod、FilingTask、表单模板、状态与版本。 |
| confirmed_decision | — |
| confirmation_date | — |

## DEC-005 平台与导出格式

| 字段 | 内容 |
| --- | --- |
| decision_id | DEC-005 |
| question | 首个平台、导出文件格式及版本、字段口径、外部编号是什么？ |
| current_status | pending |
| proposed_options | 以真实平台样例和导出说明比较候选；不预设平台。 |
| decision_owner | 业务负责人 + AI；后端/前端会签 |
| business_impact | 决定导入能力与核对结果可解释性。 |
| technical_impact | 解析适配器、列映射、重复检测、结算分配与 Mock 更新。 |
| confirmed_decision | — |
| confirmation_date | — |

## DEC-006 Studio 与税务主体关系

| 字段 | 内容 |
| --- | --- |
| decision_id | DEC-006 |
| question | 一个 Studio 可关联几个税务主体？主体归属和访问如何授权？ |
| current_status | pending |
| proposed_options | 单主体；多主体；按有效期关联。均未选定。 |
| decision_owner | 业务负责人 + 后端 + 前端 |
| business_impact | 决定客户资料与工作台结构。 |
| technical_impact | TaxProfile 关系、数据库约束、租户权限和 API 列表。不得先加单主体唯一约束。 |
| confirmed_decision | — |
| confirmation_date | — |

## DEC-007 历史税务身份

| 字段 | 内容 |
| --- | --- |
| decision_id | DEC-007 |
| question | 历史身份变更如何影响不同所属期、规则适用和已生成草稿？ |
| current_status | pending |
| proposed_options | 以生效区间、申报事项或人工核验决定；需官方依据，不预设优先级。 |
| decision_owner | 业务负责人 + AI + 后端 |
| business_impact | 避免错误适用规则。 |
| technical_impact | 档案版本、生效区间、计算快照与失效处理。 |
| confirmed_decision | — |
| confirmation_date | — |

## DEC-008 申报任务粒度与唯一性

| 字段 | 内容 |
| --- | --- |
| decision_id | DEC-008 |
| question | 同一主体、事项、所属期能否存在多个任务或更正/补报任务？ |
| current_status | pending |
| proposed_options | 一任务多版本；多任务并列；主任务加更正任务。均未选定。 |
| decision_owner | 业务负责人 + 后端 + 前端 |
| business_impact | 决定客户可见的任务和历史。 |
| technical_impact | FilingTask 业务唯一键、幂等范围、状态和数据迁移；确认前不得添加业务唯一约束。 |
| confirmed_decision | — |
| confirmation_date | — |

## DEC-009 资金来源与结算口径

| 字段 | 内容 |
| --- | --- |
| decision_id | DEC-009 |
| question | 银行/支付流水从 MVP 订单引用还是独立导入？跨期、内部转账、无外部 ID 重复项如何核对？ |
| current_status | pending |
| proposed_options | 复用有授权来源；独立导入；两者并存。具体核对阈值与人工责任待定。 |
| decision_owner | 业务负责人 + 后端 + AI |
| business_impact | 影响结算差额、账务分类和可追溯性。 |
| technical_impact | 证据关联、去重、SettlementBatch/Allocation 与权限。 |
| confirmed_decision | — |
| confirmation_date | — |

## DEC-010 分类确认与审批权限

| 字段 | 内容 |
| --- | --- |
| decision_id | DEC-010 |
| question | 客户与老板分别能确认哪些分类、规则、草稿及资料包动作？是否需要多人审批？ |
| current_status | pending |
| proposed_options | 客户确认后老板复核；老板单人确认；多人复核。均未选定。 |
| decision_owner | 业务负责人 + 前端 + 后端 + AI |
| business_impact | 决定人工责任与操作体验。 |
| technical_impact | 新接口授权策略、审计、状态转换；现有 MVP 权限不变。 |
| confirmed_decision | — |
| confirmation_date | — |

## DEC-011 政策来源、规则与表单

| 字段 | 内容 |
| --- | --- |
| decision_id | DEC-011 |
| question | 哪些官方来源可采信？谁确认规则冲突、税率/优惠、表单字段及版本？ |
| current_status | pending |
| proposed_options | 官方网页/快照或人工导入官方材料；具体来源和确认流程待核查。 |
| decision_owner | 业务负责人 + AI；后端/前端会签 |
| business_impact | 影响申报准确性与支持范围。 |
| technical_impact | PolicySource/Rule、FormTemplate 版本、计算参数和证据门禁；不得预置具体值。 |
| confirmed_decision | — |
| confirmation_date | — |

## DEC-012 资料包发布与历史访问

| 字段 | 内容 |
| --- | --- |
| decision_id | DEC-012 |
| question | 草稿预览、资料包发布/撤回、历史版本访问期限和下载权限如何规定？ |
| current_status | pending |
| proposed_options | 发布后可追溯；可撤回；按期限保留。具体行为待三人确认。 |
| decision_owner | 业务负责人 + 前端 + 后端 |
| business_impact | 决定客户交付承诺。 |
| technical_impact | Package 状态、权限、下载与审计；不复用 MVP 报告发布规则作默认。 |
| confirmed_decision | — |
| confirmation_date | — |

## DEC-013 生产认证与角色

| 字段 | 内容 |
| --- | --- |
| decision_id | DEC-013 |
| question | 生产身份服务、角色映射及租户授权何时确定？ |
| current_status | pending |
| proposed_options | 延续开发模拟头仅用于非生产；生产方案另行确定。 |
| decision_owner | 业务负责人 + 后端 + 前端 |
| business_impact | 决定真实客户是否可安全使用。 |
| technical_impact | 认证依赖、鉴权测试、生产环境开关；MVP 当前生产 503 门禁保留。 |
| confirmed_decision | — |
| confirmation_date | — |

## DEC-014 Agent 与后端运行边界

| 字段 | 内容 |
| --- | --- |
| decision_id | DEC-014 |
| question | 现有 Agent 依赖和工作流是否在 Python 3.11 `server/` 内运行，还是通过独立服务接入？ |
| current_status | pending |
| proposed_options | 若 3.11 实测兼容，可在进程内通过 Gateway；若不兼容，独立服务隔离。不得升级后端 Python。 |
| decision_owner | 后端 + AI |
| business_impact | 影响交付时间与运行稳定性。 |
| technical_impact | 包依赖、锁文件、部署和 AgentGateway 适配。2026-11-07 已在 Python 3.11.18 安装全部锁定依赖并通过现有 102 项测试；这只证明当前测试覆盖的兼容性，不决定未来进程边界。 |
| confirmed_decision | — |
| confirmation_date | — |
