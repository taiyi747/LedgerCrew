# BE2-10-11 申报表字段与表间关系测试

执行日期：2026-11-07。状态：**partially_completed（synthetic 测试模板上的通用字段映射与校验机制测试完成；申报草稿字段、表间关系与官方表单验收 BLOCKED）**。本报告不代表任何真实申报表、官方字段或申报草稿已通过验收。

## 结论与范围

仓库当前没有 TaxReturnDraft、TaxCalculation、AccountingEntry、FormTemplate 的运行时模型、Alembic migration、Service 或 API。可测的只有三类通用机制：

1. [policy_template_preview.py](../server/app/services/policy_template_preview.py) 的非持久化候选模板预检（字段定义、来源钉定、内容哈希、版本身份）；
2. [contracts/schemas.py](../contracts/schemas.py) 的 P2 候选线协议（`TaxReturnDraftCreate/Read`、`TaxFieldValue`、`TaxCalculationRead`、`CalculationLine`、`EvidenceRef`、`DraftReviewRequest` 等，**设计产物、未挂载路由**）的严格解析与版本钉定字段；
3. MVP [report_service.py](../server/app/services/report_service.py) 的证据引用校验与版本审批失效机制（`ReportVersion` 是 **MVP 报告，不是申报草稿**，只验证现有边界）。

本轮全部表单 fixture 均为 **SYNTHETIC_TEST_\* 测试模板**（`SYNTHETIC_TEST_TEMPLATE` / `synthetic-v1` / `synthetic-v2`，字段键 `SYNTHETIC_TEST_FIELD_*`），不含任何真实申报字段、税率或政策内容。新增 [test_be2_10_11_form_validation.py](../server/tests/test_be2_10_11_form_validation.py) 共 **27 个用例**（25 个纯函数机制用例 + 2 个 MVP 证据引用数据库用例）；命名 `test_gap_*` 的用例把**当前缺失的拦截**固化为已知缺口，通过不代表需求满足，BE2-07/08 落地时必须改为断言拒绝。本轮未修改业务代码、数据库结构、`server/uv.lock` 或决策状态。

## 现有实现检查

| 检查项 | 现状 | 本轮可测机制 |
| --- | --- | --- |
| TaxReturnDraft | 仅候选契约 `TaxReturnDraftCreate/Read`（含 `fields`、`missing_material_codes`、`blockers`、`content_hash`）与候选 OpenAPI；无模型/迁移/路由 | 契约解析、必填钉定、状态枚举 |
| 表单模板模型 | `FormTemplateCandidate`（纯函数预检，不写库、不批准）；无持久化模板 | 字段定义（`value_type`/`required`）、版本身份 `(template_id, template_version)`、来源哈希 |
| 表单字段映射 | `TemplateField` 仅 `value_type`+`required`；`validate_form_mapping`（API.md 承诺的可信服务）**未实现** | 字段键与类型的结构校验 |
| 表单校验 Service | **无**；`validation_rules` 仅 `list[dict[str, str]]` 形状，无执行器、无表间关系求值 | 仅形状校验（见 gap 用例） |
| TaxCalculation | 仅契约 `TaxCalculationRun/Read`、`CalculationLine`（`amount_cents` 可空+`blockers`，不默认零）；无确定性计算（BE2-06 未实现） | 金额/比率格式、阻塞态表达 |
| AccountingEntry | 仅契约 `AccountingEntryRead`；无模型（同 BE2-10-08 结论） | 金额格式；防重复汇总无机制 |
| Evidence Reference | 契约 `EvidenceRef`（`kind`/`id`/`locator`/`content_hash`）；运行时校验仅 MVP `_validate_evidence_references`（引用须属于本订单） | 引用形状 + MVP 运行时边界（2 个 DB 用例） |
| 草稿版本管理 | 契约层 `draft_version`/`data_version`/`content_hash` + `DraftReviewRequest`（`expected_draft_version`/`expected_content_hash`/`expected_data_version`）；运行时仅 MVP `ReportVersion`（版本唯一、`superseded`、审批绑定内容哈希、输入变化即失效） | 契约钉定 + MVP 失效机制（既有测试覆盖） |

## 决策门禁

`DEC-002`～`DEC-004`（首发范围/主体/申报事项/所属期）、`DEC-009`、`DEC-010`、`DEC-011`（官方来源、表单字段与版本确认）、`DEC-012` 均为 `pending`（见 [P2_DECISIONS.md](P2_DECISIONS.md)）。因此不能确认任何官方申报表字段；`contracts/` 的候选 Schema/Mock 不能当作已审核数据。

## 三、字段测试（12 项）

| # | 场景 | 实测结果 / 当前边界（测试模板 fixture） | 用例 | v0.2 验收 |
| --- | --- | --- | --- | --- |
| 1 | 必填字段完整 | 模板保留每字段 `required` 标记；含全部 4 个字段的完整草稿通过契约解析 | `test_s1_required_and_optional_fields_parse_completely` | 机制级通过；运行时完整性核验 **BLOCKED** |
| 2 | 必填字段缺失 | **缺口**：草稿缺必填字段仍可解析，无任何交叉校验（特性测试锁定现状） | `test_gap_s2_missing_required_field_is_not_rejected` | **BLOCKED**，BE2-07 需服务端校验 |
| 3 | 可选字段缺失 | 可选字段可缺省或取 `null`，解析通过 | `test_s3_optional_field_may_be_absent_or_null` | 机制级通过 |
| 4 | 字段类型错误 | 非法 `value_type`、`TaxFieldValue.value` 传整数、额外未知键均被拒绝（strict 解析） | `test_s4_field_type_errors_are_rejected` | 机制级通过（契约层） |
| 5 | 日期格式错误 | 模板 `effective_from` 非法格式、区间倒置、`FilingPeriodCreate` 区间倒置均被拒绝；**缺口**：字段值内日期（如 `2026-13-01`）不校验，`value` 是无类型字符串 | `test_s5_date_format_errors_are_rejected`、`test_gap_s5_date_format_of_field_values_is_not_checked` | 部分（模板级通过；字段值级 **BLOCKED**） |
| 6 | 金额格式错误 | `Money=StrictInt` 拒绝字符串 `"123.45"` 与小数 `12.34`；`Rate` 拒绝 `1.2.3`、接受 `0.05` | `test_s6_amount_format_errors_are_rejected` | 机制级通过 |
| 7 | 非法字段值 | 候选入口不能自报 `review_status="approved"`；`DraftStatus`/`EvidenceKind`/计算状态非法枚举均被拒绝 | `test_s7_illegal_field_values_are_rejected` | 机制级通过 |
| 8 | 字段来源不存在 | 模板来源不存在返回 `source_not_found`；来源哈希不符 `source_version_conflict`；内容哈希被改 `content_hash_mismatch` | `test_s8_field_source_must_exist_and_match_pinned_hash` | 机制级通过（调用方索引；官方来源审核 **BLOCKED**） |
| 9 | 证据引用失效 | `EvidenceRef` 强制 `kind` 枚举、UUID、64 位十六进制哈希；运行时失效校验仅 MVP：引用不属本订单或输出引用不在任务输入内均拒 `invalid_report_evidence`（2 个 DB 用例） | `test_s9_evidence_reference_shape_is_enforced`、`test_mvp_report_rejects_unknown_evidence_reference`、`test_mvp_report_rejects_output_reference_missing_from_task_input` | 部分（MVP 边界已验证；申报草稿字段级证据运行时校验 **BLOCKED**） |
| 10 | 计算结果缺失 | `TaxReturnDraftCreate` 强制 `calculation_id`；`blocked` 计算可带 `blockers` 且金额行缺失不自动补零 | `test_s10_draft_requires_pinned_calculation_result` | 机制级通过；计算与草稿的运行时联动 **BLOCKED** |
| 11 | 字段与所属期不一致 | 仅区间自身合法可校验；**缺口**：模板生效窗口与申报所属期无交叉校验，`TaxReturnDraftRead` 连所属期字段都没有 | `test_s11_period_range_is_validated`、`test_gap_s11_template_window_is_not_cross_checked_with_filing_period` | **BLOCKED**（待 DEC-004） |
| 12 | 草稿与模板版本不一致 | 草稿创建必须钉定 `form_version`；**缺口**：草稿 `form_version` 与其计算的 `form_version` 不一致不会被拒（特性测试锁定现状） | `test_s12_draft_creation_pins_form_version`、`test_gap_s12_draft_form_version_is_not_cross_checked_with_calculation` | 部分（钉定字段存在；一致性校验 **BLOCKED**） |

## 四、表间关系测试

| 关系 | 实测结果 / 当前边界 | 用例 | v0.2 验收 |
| --- | --- | --- | --- |
| 明细金额与汇总金额一致 | 无计算/汇总运行时可比对（BE2-06 未实现） | — | **BLOCKED** |
| 申报字段与计算结果一致 | `TaxFieldValue.calculation_line_key` 可链接计算行且可断言；**缺口**：字段值与所链计算行金额不一致不被拒 | `test_r2_field_values_link_to_calculation_lines`、`test_gap_r2_field_value_is_not_compared_with_calculation_line` | 部分（链路字段存在；一致性 **BLOCKED**） |
| 申报字段与证据引用一致 | 字段携带 `EvidenceRef`；MVP 运行时校验证据必须属于本订单（见字段 9） | `test_r3_field_values_carry_evidence_references` + 2 个 DB 用例 | 部分；申报草稿运行时 **BLOCKED** |
| 相关字段满足模板定义的校验关系 | **缺口**：`validation_rules` 仅 `dict[str, str]` 形状，无求值器，规则内容不被执行 | `test_gap_r4_validation_rules_are_untyped_and_not_evaluated` | **BLOCKED** |
| 不同表单之间的数据引用正确 | 无多表单/跨表单引用模型 | — | **BLOCKED** |
| 同一数据不会被重复汇总 | `AccountingEntryRead` 无去重键；`API.md` 明示不设按平台记录的业务唯一约束（DEC-009/010 pending） | — | **BLOCKED** |
| 缺失材料能够阻塞完整交付 | 契约可表达 `status=blocked`+`missing_material_codes`+`blockers`；**缺口**：契约不禁止 `status=approved` 与缺失材料共存（特性测试锁定现状） | `test_r7_blocking_state_can_be_expressed`、`test_gap_r7_draft_can_be_marked_approved_with_missing_materials` | **BLOCKED**（见下节关键约束） |

## 五、版本测试

| # | 场景 | 实测结果 / 当前边界 | 用例 | v0.2 验收 |
| --- | --- | --- | --- | --- |
| 1 | 模板 V1 生成对应草稿 | V1 模板预检返回 `new`（身份 `(SYNTHETIC_TEST_TEMPLATE, synthetic-v1)`）；草稿创建契约钉定 `form_version`。草稿生成服务不存在 | `test_v1_template_preview_and_pinned_draft_creation` | **BLOCKED**（生成链路未实现） |
| 2 | V2 不误用 V1 字段映射 | 预检按 `(template_id, template_version)` 分离身份：V2 返回独立 `new`、V1 内容不被覆盖；V1 同版本改内容返回 `version_conflict` 不静默覆盖；映射键变化随版本隔离 | `test_v2_new_template_version_keeps_v1_mapping_separate` | 机制级通过；运行时映射解析 **BLOCKED** |
| 3 | 历史草稿追溯原模板版本 | 草稿读模型保留 `form_version`/`draft_version`/`rule_versions`/`content_hash`/`calculation_id`；不可变与历史保留目前只是契约与 [API 契约](../contracts/API.md)承诺。MVP 侧历史保留（`superseded` 不删除）由既有 `test_stage6` 覆盖 | `test_v3_draft_retains_template_and_version_trace_fields` | 部分（追溯字段存在；运行时 **BLOCKED**） |
| 4 | 输入更新后旧草稿审批失效 | 契约强制审核请求携带 `expected_draft_version`+`expected_content_hash`+`expected_data_version`，拒绝必须带理由；MVP 失效机制已验证（`stale_report`、`report_content_changed`、`approval_missing`，既有 `test_stage6`、`tests/agents/test_workflow.py`）。申报草稿的失效识别运行时 **BLOCKED** | `test_v4_review_request_pins_versions_and_hash` | 部分 |
| 5 | 草稿字段追溯来源记录 | 字段链路 `TaxFieldValue → calculation_line_key → CalculationLine(formula/evidence) → EvidenceRef` 在契约层完整可断言；MVP 证据引用可回溯到本订单记录。申报字段到输入记录的运行时追溯 **BLOCKED** | `test_r2`/`test_r3` + 2 个 DB 用例 | 部分 |

## 证据追溯小结

- **已验证**：`EvidenceRef` 形状强制（枚举/UUID/哈希）；模板来源钉定（来源 ID→哈希不符即拒）；MVP 运行时证据引用必须属于本订单记录、Agent 输出引用必须⊆任务输入（`invalid_report_evidence`，422）；草稿契约每字段可携带证据与计算行键。
- **缺口**：申报草稿的字段级证据引用没有运行时存在性/一致性解析；`TaxFieldValue.evidence` 允许空数组；来源记录（输入快照）与字段的关联待 BE2-06/07 实现。

## 关键约束核查：关键字段或材料缺失不得标记完整可交付

- **当前没有代码路径能产出“完整可交付”的申报草稿**（草稿运行时不存在），因此今天不会发生错误的完整交付。
- **但门禁缺失属实**：候选契约允许 `status="approved"` 与非空 `missing_material_codes`/`blockers` 共存（`test_gap_r7_draft_can_be_marked_approved_with_missing_materials` 锁定该现状），必填字段缺失也不被拒（gap S2）。BE2-07/08 必须实现服务端完整性门禁：关键字段或材料缺失时草稿只能处于 `blocked`，不得进入 approve/打包/交付；届时上述 gap 用例必须翻转为断言拒绝。
- MVP 侧对应防线已存在且经既有测试验证：未解决异常必须披露（`unresolved_exception_undisclosed`）、输入变化使旧审批失效（`stale_report`）、审批绑定内容哈希（`approval_missing`）。该防线属于 MVP 报告，不能直接当作申报草稿门禁。

## 执行记录

- 环境：Python **3.11.18**（`server/.venv/py311-env/Scripts/python.exe`），项目锁定依赖不变；每个数据库用例独立临时 SQLite 库，未连接开发或客户数据库。
- `python -B -m ruff check tests/test_be2_10_11_form_validation.py` → **All checks passed**。
- `python -B -m pytest -q tests/test_be2_10_11_form_validation.py` → **27 passed**（5.22 秒）。
- `python -B -m pytest -q` 全量回归 → **205 passed，4 failed**（73.46 秒）。4 个失败全部位于并发加入的 `tests/test_be2_10_12_workflow_recovery.py`（BE2-10-12 范围的进行中测试模块，非本任务产物；本任务只新增测试文件，未改任何业务代码，失败断言均在该模块自身场景逻辑内，与本任务用例无共享状态）。除该模块外全部通过；待其稳定后需重跑全量确认。
- 环境备注：受限文件沙箱下 pytest 以 `mode=0o700` 创建的测试临时目录在本机会立即变为不可读（连创建进程与 `icacls` 都被拒），导致 `tmp_path` 类用例无法运行；Windows 权限诊断脚本检查 `.pytest_tmp` 及全部上级后判定 `NOT_THIS_CLASS`、未修改任何权限（报告：`acl-recovery-be21011/acl-report-ec2baa03692047de9eb35899ba6c14a6.jsonl`）。最终测试命令经用户授权以不受限方式运行完成，测试逻辑与 fixture 未做任何迁就。

## 未确认问题与后续门禁

1. `DEC-011`：官方来源采信、表单字段与版本的确认人和流程——确认前不得把任何 synthetic 字段升格为申报字段，也不得宣称真实申报表通过验收。
2. `DEC-002`～`DEC-004`：首发地区、主体/纳税人身份、申报事项与所属期定义（字段 11 的期间一致性依赖此项）。
3. `DEC-009`/`DEC-010`：资金来源、重复汇总口径与分类审批权限（表间关系第 6 项依赖此项）。
4. `DEC-012`：资料包发布/撤回与历史访问（完整交付门禁的出口侧）。
5. BE2-06/07/08 实现后：在**已确认官方表单**上重跑本报告全部 12+7+5 场景；所有 `test_gap_*` 用例翻转为断言拒绝；补字段↔计算↔证据的运行时一致性、跨表单引用、去重汇总与审批失效测试。官方模板未确认前只允许 synthetic fixture 与通用机制测试。
