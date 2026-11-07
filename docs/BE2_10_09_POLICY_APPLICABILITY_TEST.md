# BE2-10-09 政策规则适用性测试

执行日期：2026-11-07。环境：Windows、Python **3.11**。主执行环境为独立解释器 3.11.9（`<工作区>/.tools/py311`，满足 DEC-001 `>=3.11,<3.12`）；`server/.venv/py311-env`（3.11.18）复跑本模块 15 项亦全部通过，但该解释器执行 pytest 时对 `--basetemp` 目录间歇性触发工作区既知的 Windows 文件权限删除拒绝（`.pytest_tmp` 等遗留目录同类现象），需每次换用全新 `--basetemp` 名称，属环境干扰而非代码失败。全部 fixture 为 **synthetic 占位值**；未连接真实数据库，无新增表与 Alembic 迁移，未修改锁文件、既有测试与既有 MVP 逻辑。

## 代码与决策检查

| 检查项 | 现状（2026-11-07 核对） |
| --- | --- |
| PolicySource | 无正式模型；仅 [policy_template_preview.py](../server/app/services/policy_template_preview.py) 的导入预检候选结构与 [contracts/schemas.py](../contracts/schemas.py) 线协议设计 |
| PolicyRule | 同上；候选 `PolicyRuleCandidate` 的 `review_status` 只能为 `candidate`，预检明确“不能使候选可用于计算” |
| MerchantTaxProfile / FilingPeriod / FilingTask | 无正式模型；仅 `contracts/schemas.py` 候选 Schema |
| SupportedScope | 无正式模型；仅候选 Schema（含 `status`、`form_version`、`platform_code`） |
| PolicyRule Service（审核/持久化） | **不存在**（BE2-05/06 未实现，见 [BE2-10 审计](BE2_10_AUDIT_REPORT.md)） |
| 规则适用性判断 Service | 本轮之前不存在；本轮新增通用框架 [policy_applicability.py](../server/app/services/policy_applicability.py)（纯函数、不建表、不挂载 API、无 AI 依赖） |
| 业务决策 | DEC-002～005、DEC-006～014 均为 `pending`（仅 DEC-001 confirmed）；真实地区、主体、纳税人身份、申报事项、政策与规则批准流程均未确认 |

## 已实现的通用适用性框架

`evaluate_rule_applicability(context, rules, sources) -> ApplicabilityResult`：对传入的规则结构做确定性适用性判定。**机制，不是政策**——模块不含任何真实地区、主体、身份、税率或表单值。

判定门按固定顺序执行，逐条给出阻塞原因：

| 顺序 | 门 | 阻塞码 | 核心要求对应 |
| --- | --- | --- | --- |
| 0 | 档案纳税人身份缺失 | `taxpayer_identity_missing` | 不猜测身份（整体阻塞，不做任何比对） |
| 1 | 来源明确（引用已知且 `verified` 的来源） | `source_missing` / `source_not_verified` | 来源明确 |
| 2 | 规则已审核（仅 `approved`） | `rule_not_approved` | 规则已审核 |
| 3 | 必要适用条件完整（region/entity/filing_kind/effective_from） | `missing_required_condition`（带 `condition`） | 不猜、不补默认 |
| 4 | 地区/主体/身份/申报事项比对 | `region_mismatch` / `entity_type_mismatch` / `taxpayer_identity_mismatch` / `filing_kind_mismatch` | 地区、主体、身份适用 |
| 5 | 所属期完全落入生效区间 | `period_before_effective` / `period_after_effective` / `period_crosses_effective_boundary` | 所属期适用 |
| 6 | 支持范围覆盖任务且规则落在范围内 | `scope_not_supported` / `scope_mismatch` | 支持范围匹配 |
| 7 | 无未解决冲突（显式冲突、同键多版本、多条适用） | `rule_conflict` / `rule_version_conflict` | 不存在未解决冲突 |
| 汇总 | 唯一适用规则 | `no_applicable_rule` | 不零税率、不默认最新 |

输出语义：`outcome=applicable` 时返回唯一 `rule_key@rule_version` 且 `parameters` **逐字回显**规则声明值；`outcome=blocked` 时 `parameters` 恒为空、`rule_key` 为空，`blockers` 给出每条规则的具体原因与汇总阻塞，`evaluated_rules` 给出逐条判定。`decision_hash` 为规范化 JSON 的 SHA256，用于确定性验证。

框架层约定（结构约定，**不是业务规则**，待 DEC-011 确认后可调整）：规则 `taxpayer_identity=None` 表示“不限身份”；多条规则同时适用视为未解决冲突一律阻塞（组合/优先级规则未确认）；所属期跨界生效边界即阻塞，不按比例拆分。

## synthetic fixture

`SYNTHETIC_REGION_A/B`、`SYNTHETIC_ENTITY_X/Y`、`SYNTHETIC_IDENTITY_P/Q`、`SYNTHETIC_FILING`、参数 `synthetic_rate=example_only` 均为结构验证占位，**没有税率或政策内容**，与 [synthetic_policy_rule_import.json](../contracts/examples/synthetic_policy_rule_import.json) 同一约定，不得升格为真实政策。

## 15 个测试维度结果

测试文件：[test_policy_applicability.py](../server/tests/test_policy_applicability.py)（15 项）。

| # | 维度 | 测试 | 结果 | 判定 / 阻塞码 |
| --- | --- | --- | --- | --- |
| 1 | 地区一致 | `test_region_consistency_and_mismatch` | PASS | `applicable` |
| 2 | 地区不一致 | 同上 | PASS | `region_mismatch` |
| 3 | 经营主体一致 | `test_entity_type_consistency_and_mismatch` | PASS | `applicable` |
| 4 | 经营主体不一致 | 同上 | PASS | `entity_type_mismatch` |
| 5 | 纳税人身份一致 | `test_taxpayer_identity_consistency_and_mismatch` | PASS | `applicable`（规则不限身份时亦适用） |
| 6 | 纳税人身份不一致 | 同上 | PASS | `taxpayer_identity_mismatch` |
| 7 | 规则生效日期之前 | `test_period_before_inside_and_after_effective_window` | PASS | `period_before_effective` |
| 8 | 规则生效日期之内 | 同上 | PASS | `applicable` |
| 9 | 规则失效日期之后 | 同上 | PASS | `period_after_effective` |
| 10 | 所属期跨越生效边界 | `test_period_crossing_effective_boundary_is_blocked` | PASS | `period_crosses_effective_boundary`（起止两侧均覆盖） |
| 11 | 规则尚未审核 | `test_unapproved_rules_never_enter_calculation` | PASS | `rule_not_approved`（candidate/under_review/rejected/retired 四态） |
| 12 | 存在冲突规则 | `test_conflicting_rules_block_without_auto_selection` | PASS | `rule_conflict` / `rule_version_conflict`，且不选任何一条 |
| 13 | 缺少纳税人身份 | `test_missing_taxpayer_identity_blocks_without_guessing` | PASS | `taxpayer_identity_missing`，不做任何比对 |
| 14 | 缺少必要适用条件 | `test_missing_required_condition_blocks` | PASS | `missing_required_condition` + 具体 `condition` |
| 15 | 支持范围不匹配 | `test_supported_scope_mismatch_blocks` | PASS | `scope_not_supported`（范围不覆盖/不可用）/ `scope_mismatch`（规则超出范围） |

附加维度：来源明确（`test_source_provenance_is_required`：`source_missing`、`source_not_verified`）。

## 版本验证

| 验证 | 测试 | 结果 |
| --- | --- | --- |
| 历史所属期选择当时生效的规则版本 | `test_historical_period_selects_historically_effective_version` | PASS：同 `rule_key` 的 v1（2025 生效）/v2（2026 生效），2025-06 所属期判定选中 **v1**、2026-06 选中 **v2**，不按“最新”选择 |
| 同一输入、同一规则版本判定一致 | `test_decision_is_deterministic` | PASS：两次判定 `model_dump` 与 `decision_hash` 完全一致；不同所属期产生不同 hash |

## 核心禁止项验证

| 禁止项 | 验证方式与结果 |
| --- | --- |
| 默认选择最新规则 | 多版本/多规则并存时 `outcome=blocked`、`rule_version=None`、`parameters={}`（PASS） |
| 未审核规则用于正式计算 | 四种非 `approved` 状态均 `rule_not_approved`，参数不外泄（PASS） |
| 缺失身份时猜测身份 | `taxpayer_identity_missing`，`evaluated_rules=[]`（PASS） |
| 缺失规则时使用零税率 | 空规则集与全不适用均 `no_applicable_rule`，`parameters={}`（PASS） |
| AI 临时生成税率补足 | 框架无任何 LLM/网络依赖；参数仅逐字回显规则声明值，无合成（PASS，`test_parameters_only_echo_declared_rule_values`） |

## 测试报告

| 检查 | 结果 |
| --- | --- |
| 本模块 `tests/test_policy_applicability.py` | **15 passed**（3.11.9 与 3.11.18 均通过；3.11.18 复跑 0.37 秒） |
| 全量 `python -B -m pytest -q`（3.11.9 快照） | **202 passed，2 failed**。失败 2 项属并行开发中的 `tests/test_be2_10_12_workflow_recovery.py`（该文件单独运行同样失败 4 项），与本模块无关；本任务开始时基线为 143 passed |
| Ruff（本任务新增两文件） | **通过**：`ruff check app/services/policy_applicability.py tests/test_policy_applicability.py` |
| Python 导入检查 | 通过（`app.services.policy_applicability` 在 3.11 可导入；无新增第三方依赖） |
| 数据库 / 迁移 | 无新增表、无迁移、未触碰业务数据（纯内存判定） |

## 阻塞原因与边界（BLOCKED）

| 事项 | 阻塞原因 |
| --- | --- |
| 真实规则的适用测试（真实地区/主体/身份/税率） | DEC-002～005、DEC-011 pending；没有已审核的真实规则与官方来源 |
| 正式 PolicySource/PolicyRule 模型、Alembic migration、审核 Service、导入 API | BE2-05/06 未实现；本框架不持久化、不替代它们 |
| 适用性判断接入确定性计算（TaxCalculation）与“进入正式计算”运行时门禁 | BE2-06 计算服务不存在；当前只能在框架层验证门禁语义 |
| 多规则组合适用、优先级与冲突裁决 | 当前安全默认“多条适用即阻塞”；组合/优先级/裁决人待 DEC-011 确认 |
| 规则 `taxpayer_identity=None` 的业务语义（不限身份 vs 必填） | 结构约定，待 DEC-003/011 确认 |

## 完成正式适用判断前置条件

1. DEC-011 确认官方来源采信、规则审核人/动作、冲突裁决与规则组合/优先级规则；DEC-002～004 确认首发地区、主体/身份、申报事项。
2. BE2-05/06 落地 PolicySource/PolicyRule 模型、Alembic migration、审核 Service 与版本 Repository；将本框架挂接到受权服务层，使其输出进入确定性计算的运行时门禁。
3. 用已审核的真实规则替换 synthetic fixture 重跑本矩阵；对规则版本变更、历史所属期回溯和冲突升级补集成测试。**不得将本报告的 synthetic 值或框架层结构约定升格为业务规则。**
