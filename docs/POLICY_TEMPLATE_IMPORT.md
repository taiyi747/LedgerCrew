# 政策规则与申报模板导入契约状态

状态：**通用候选 JSON 校验与 dry_run 预检已实现；正式导入仍阻塞。** `server/app/` 中没有 PolicySource、PolicyRule、FormTemplate 模型、迁移、审核服务或导入 API；DEC-002～004、011 均为 pending。[预检模块](../server/app/services/policy_template_preview.py)只验证结构、来源/内容哈希和给定索引中的重复/版本冲突，不写库、不批准、不用于计算。不能编造真实政策、税率、舍入规则或申报字段，也不能把 `contracts/` 的候选 Schema/Mock 当成已审核数据。

## 未来结构化输入的最低要求

正式 JSON 契约需在业务决策 confirmed 后与 `contracts/API.md`、Pydantic 2 Schema、OpenAPI 同步冻结。至少区分三类记录：

| 记录 | 所需元数据 | 来源与版本边界 |
| --- | --- | --- |
| 原始政策来源 | 官方 URL/发布机关、抓取或人工上传时间、生效与失效日期、地区、内容哈希、受控快照引用、审核状态 | 原始快照不可覆盖；URL 字符串不能替代官方性审核。 |
| 结构化规则 | `rule_code`、`rule_version`、来源 ID+来源版本/哈希、地区、主体类型、纳税人身份条件、事项、所属期、生效/失效日期、参数、审核状态、内容哈希 | `candidate/under_review/approved/retired` 等状态和转换尚为候选；只有审核且适用性明确的规则可供正式计算。 |
| 申报模板 | `template_id`、`template_version`、事项、地区、适用主体/纳税人身份、生效/失效日期、字段定义、字段关系校验、官方来源引用、内容哈希、审核状态 | 字段、类型和关系必须来自确认的官方模板；历史版本不可静默覆盖。 |

这些字段名是**讨论中的导入结构**，不是已挂载 API 或正式税务语义。DEC-011 需确认来源采信、审批人与冲突升级；DEC-002～004 需确认首发适用范围和事项。无确认时，正式计算与交付必须阻塞。

## 预期事务与幂等语义

当前 `preview_policy_rule` 与 `preview_form_template` 已提供无写入的结构校验、哈希校验和 `new/duplicate/version_conflict` 预检；来源及已有版本索引由调用方传入，不能充当可信数据库查询。正式实施仍须提供 `import`（原子写入）、历史读取和冲突列表的明确接口或 CLI，并核验官方来源及证据。事务内同时写入来源引用、规则/模板版本、导入批次与审计记录；失败时整体回滚。相同标识与内容哈希重复执行只返回既有实体或新增批次历史，不复制规则；相同版本对应不同内容时产生显式冲突，禁止覆盖。预检比较键不是数据库业务唯一约束，最终版本身份与语义冲突粒度需要经业务确认后确定。

## 计划测试及当前结果

通用预检已有 **9 项 synthetic pytest 通过**，覆盖结构、重复/版本身份冲突、来源缺失、字段类型/版本/日期/哈希错误及候选入口不能自报批准；示例见 [规则 JSON](../contracts/examples/synthetic_policy_rule_import.json)和 [模板 JSON](../contracts/examples/synthetic_form_template_import.json)。正式导入、事务失败回滚、历史查询、语义冲突、未审核计算门禁及真实表间关系仍为 **BLOCKED**，详见 [BE2-10-05 报告](BE2_10_05_IMPORT_TEST.md)。Synthetic fixture 不能证明官方税表适用。
