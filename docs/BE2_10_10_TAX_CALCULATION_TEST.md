# BE2-10-10 税务计算阈值与舍入测试

执行日期：2026-11-07。

## 结论

**v0.2 确定性税务计算引擎（BE2-06）的正式阈值与舍入测试：BLOCKED。** 当前后端没有 `TaxCalculation` 模型、Alembic migration、税务计算 Service、运行 API 或输入/结果快照持久化；`TaxCalculation` 仅存在于 `contracts/` 契约草案。真实税率、优惠阈值与舍入政策均未确认（`docs/P2_DECISIONS.md` 中 `DEC-002`～`004`、`DEC-010`～`013` 全部 `pending`），不得自行设定。因此无法执行真实税务金额的阈值判定与舍入验收，**不能声称任何申报或税额计算能力**。

按任务要求，本次用**明确标注的 synthetic fixture**（占位比率、占位阈值、显式占位舍入方式）测试了计算引擎的**通用精度能力**，15 个场景在 Python 3.11 下全部通过：

- 金额以整数分进出、比率走 `Decimal`、float 与元字符串输入被拒绝；
- 中间值保留全精度，只在最终步做一次显式舍入；
- 阈值用整数分精确比较（正好等于、±1 个最小货币单位边界）；
- 缺失输入/缺失规则阻塞并记录原因，不置零；
- 同快照 + 同规则版本 + 同引擎版本 → 结果逐字节一致；规则/引擎版本变化 → 结果可区分。

本次**未新增或改写**任何业务规则、税率、阈值、舍入政策、模型、API、迁移和决策状态；未触及客户数据库或数据。测试文件 [test_tax_calc_precision_synthetic.py](../server/tests/test_tax_calc_precision_synthetic.py) 是 synthetic-only 测试夹具，不是业务引擎实现，其参数不得升格为业务规则。

## 现有实现与决策门禁

| 检查对象 | 实际情况 | 影响 |
| --- | --- | --- |
| TaxCalculation | 仅契约：`contracts/schemas.py` 的 `TaxCalculationRun`（`expected_data_version`/`rule_versions`/`form_version`）、`TaxCalculationRead`（`data_version`/`rule_versions`/`form_version`/`calculation_version`/`input_hash`/`lines`/`blockers`）、`CalculationLine`（`key`/`amount_cents`/`ratio`/`formula`/`evidence`）；`Money=StrictInt`、`Rate` 为 Decimal 字符串正则；`CalculationStatus=blocked/completed/stale`。`server/app/` 无任何对应模型或迁移 | 无可运行的计算对象，真实阈值/舍入测试无从执行 |
| 税务计算 Service | 不存在（BE2-10 审计已记录 BE2-06 `not_implemented`） | 无输入解析、规则装配、计算、重算或版本锁定流程可测 |
| 规则参数模型 | 仅契约/候选：`PolicyRuleSubmit.parameters: dict[str, str]`、候选预检 `PolicyRuleCandidate.parameters: dict[str, str]`、`TemplateField.value_type: integer_cents/decimal_string/date/text`；无批准规则持久化、无参数类型/单位约束 | 参数值语义（税率、阈值、舍入）未定义；不得由测试或代码自行填充 |
| 计算输入快照 | 契约有 `input_hash`（64 位 hex 模式），无快照结构、无规范化规则、无实现 | 同输入复算缺少可验证的基准 |
| 计算结果快照 | `CalculationLine` 只有 `key/amount_cents/ratio/formula/evidence`；**没有参数、舍入口径、中间值字段**（P2-0.5-REVIEW P1 已记录同一问题） | 结果不可完整审计复算；舍入依据不可追溯 |
| Decimal 使用情况 | 金额路径全部 `Decimal`：[money.py](../server/app/utils/money.py)、[csv_service.py](../server/app/services/csv_service.py)、[workflow.py](../server/app/agents/workflow.py) `amount_to_minor`、[fixtures.py](../server/app/agents/fixtures.py)；金额路径无 `float()`；`config.py` 的 `float()` 仅用于超时秒数 | 无 Decimal/float 混算；但都属 MVP 解析，不是税务计算 |
| 金额转换逻辑 | `parse_cents`：正则限定非负、≤2 位小数 → `int(Decimal(value)*100)`；CSV 同样拒绝负数与 >2 位小数，上限 `92233720368547758.07` 元；`amount_to_minor` 显式拒绝负数；DB `tax_cents >= 0` 约束；前端 `ledger.ts` 的 `/100` 仅用于展示与 CSV 导出 | 转换本身精确无截断；但负数（退款）在入口即被拒绝，退款场景进不了现有解析链 |
| 计算版本管理 | 契约有 `data_version`/`rule_versions`/`form_version`/`calculation_version`/`rule_version`/`content_hash` 字段族；无实现；P2-0.5-REVIEW 指出响应不暴露规则键-版本配对 | 版本区分设计方向正确，落地与可读性不足 |

`docs/P2_DECISIONS.md` 中 `DEC-002`～`004`（首发范围、主体/身份、所属期）与 `DEC-010`～`013`（分类审批、政策来源与规则、资料包、生产认证）均为 `pending`。真实税率、优惠阈值、舍入方式（含负数方向与中间步口径）必须由决策确认后写入规则参数；本文件所有数值均为占位 fixture。

## 金额精度验证

| 检查项 | 结果 |
| --- | --- |
| float 精度误差 | 业务金额路径未使用 float。对照演示（仅观察）：float `12345*0.07 = 864.1500000000001`（Decimal 精确为 `864.15`）；float `0.1+0.2 = 0.30000000000000004`；大额 `1234567890123456789×0.001` 用 float 得 `1234567890123456.8`，取整为 `1234567890123456`，与精确值 `1234567890123457` **差 1 分**。禁止 float 计税有实证依据 |
| Decimal 与 float 混算 | `Decimal("0.1") + 0.2` 直接 `TypeError`，混算自然失败；合约与解析层均为严格类型（`StrictInt`/Decimal 字符串） |
| 中间步骤提前舍入 | 场景 9：两步各 `0.50` 分，逐项舍入会得 2 分；引擎保留中间值、仅最终舍入得 **1 分**。中间值以全精度字符串（如 `"617.25"`、`"0.50"`）入快照 |
| 多次舍入导致误差 | 同上：单次最终舍入口径使 `Σ round(xᵢ) ≠ round(Σ xᵢ)` 的误差不进入结果；真实口径待确认后写入规则 |
| 金额单位混淆 | 计算入口只收整数分 `int`；float、元字符串均 `TypeError`（场景 12）。金额字段（`amount_cents`/`money=StrictInt`）与比率（Decimal 字符串）在契约层分型 |
| 负数金额处理 | 现有 MVP 解析（`parse_cents`/CSV/`amount_to_minor`）与 DB 约束拒绝负数 → **退款金额进不了现有链路**，这是已知缺口。synthetic 场景 10 验证引擎对负数的通用行为：`-864.15→-864`、精确半值 `-0.5→-1`（占位 ROUND_HALF_UP 远离零），正负配对归零、符号对称。真实负数舍入方向必须显式确认 |
| 边界上限 | `MAX_CENTS=2^63-1`、CSV 上限 `92233720368547758.07` 元；合约 `StrictInt` 无 SQLite 整数上界约束（P2-0.5 P2 已记录）。前端 `/100` 展示用 JS Number，超约 9×10¹⁵ 分（≈90 万亿元）时展示精度会丢，仅影响显示/导出，不影响计算 |

## synthetic fixture 与舍入口径（占位，非政策）

测试夹具位于 [test_tax_calc_precision_synthetic.py](../server/tests/test_tax_calc_precision_synthetic.py) 的 `run_calculation`，**全部参数是合成占位值**：

| 项目 | 合成 fixture 值 | 说明 |
| --- | --- | --- |
| 引擎版本 | `synthetic-engine-1` | 占位；真实引擎版本待 BE2-06 定义 |
| 规则版本 | `SYNTH-RULE-v1`（比率 `0.07`）、`SYNTH-RULE-v2`（比率 `0.09`）、`SYNTH-RULE-v1-threshold` | 占位版本串，用于验证版本区分与复算 |
| 比率 | `0.07 / 0.09 / 0.05 / 0.1 / 0.25 / 0.33 / 0.001 / 0.333333333333333333 / 1.234567890123456789012345678` | Decimal 字符串，覆盖小数位、循环小数、长尾精度 |
| 阈值 | `100000` 分 | 占位值，不是任何真实优惠阈值 |
| 阈值语义 | `base_cents >= threshold_cents` 触发比率，否则有效比率为 0，状态仍为 completed 并记录 `threshold_met=false` | 占位语义；真实含/不含边界与计税基数口径待确认 |
| 舍入口径 | **ROUND_HALF_UP，量化到 1 分，仅最终步一次**；负数半值远离零 | 占位且显式；测试 8 证明 `ROUND_HALF_EVEN(0.5)=0` 与之不同，故真实舍入方式必须进快照、进版本 |
| 精度 | 中间值全精度（Decimal），最终 `quantize(Decimal("1"), rounding=...)` | 不依赖全局 Decimal context（测试 8 验证 context 被改为 `ROUND_DOWN`/`ROUND_CEILING` 结果不变） |

结果快照字段：`input_snapshot`、`input_hash`（规范化 JSON 的 SHA-256）、`rule_version`、`engine_version`、`formula`、`rule_parameters`、`intermediates`（每步 `amount_cents` + 全精度 `raw_tax_cents`）、`rounding`、`threshold_met`、`effective_rate`、`final_cents`、`result_hash`。

## 15 个测试场景与结果

全部 **PASS**（Python 3.11.18，`tests/test_tax_calc_precision_synthetic.py`，15 passed）。金额单位均为分。

| # | 场景 | 合成输入 | 精确中间值 | 最终（整数分） | 结果 | 测试函数 |
| --- | --- | ---: | --- | ---: | --- | --- |
| 1 | 普通金额计算 | 12345 × 0.07 | 864.15 | 864 | PASS | `test_scenario01_normal_amount` |
| 2 | 小额金额计算 | 1 × 0.07；3 × 0.33 | 0.07；0.99 | 0；1 | PASS | `test_scenario02_small_amounts` |
| 3 | 大额金额计算 | 10¹⁵ × 0.07；1234567890123456789 × 0.001 | 70000000000000.00；1234567890123456.789 | 70000000000000；1234567890123457 | PASS（大额期望值用纯整数算术 `(n+500)//1000` 独立校验，不依赖 Decimal/float） | `test_scenario03_large_amounts` |
| 4 | 正好达到阈值 | 100000 × 0.07，阈值 100000 | `threshold_met=true`，有效比率 0.07 | 7000 | PASS | `test_scenario04_exactly_at_threshold` |
| 5 | 低于阈值 1 个最小货币单位 | 99999（阈值 100000） | `threshold_met=false`，有效比率 0 | 0（completed，非 blocked、非缺失） | PASS | `test_scenario05_one_unit_below_threshold` |
| 6 | 高于阈值 1 个最小货币单位 | 100001 × 0.07 | 7000.07 | 7000 | PASS | `test_scenario06_one_unit_above_threshold` |
| 7 | 小数边界 | 3 × `0.333333333333333333`；10 × `1.234567890123456789012345678`；7 × 0.1；3 × 0.25 | 0.999999999999999999；12.34567890123456789012345678；0.7；0.75 | 1；12；1；1 | PASS（中间值字符串逐位精确，`0.7` 不是 `0.7000000000000001`） | `test_scenario07_decimal_boundaries` |
| 8 | 舍入边界 | 4×0.1；5×0.1；6×0.1（精确半值 0.5） | 0.4；0.5；0.6 | 0；1；1 | PASS（全局 context 改 `ROUND_DOWN`/`ROUND_CEILING` 结果不变；`ROUND_HALF_EVEN(0.5)=0≠1`，证明舍入方式必须显式入快照） | `test_scenario08_rounding_boundaries` |
| 9 | 多步骤计算 | (10,10)×0.05；(1,1)×0.05；(12345,10,3)×0.05 | 0.50+0.50=1.00；0.05+0.05=0.10；617.25+0.50+0.15=617.90 | 1（逐项舍入会错成 2）；0；618 | PASS | `test_scenario09_multi_step_single_rounding` |
| 10 | 负数与退款 | -12345×0.07；-5×0.1（精确半值）；±12345 配对 | -864.15；-0.5 | -864；-1；配对和 0 | PASS（符号对称 `tax(-x) = -tax(x)`；负数半值远离零是占位口径） | `test_scenario10_negative_and_refunds` |
| 11 | 零金额输入 | 0 × 0.07 | 0 | 0（completed，`input_hash` 与缺失输入不同） | PASS | `test_scenario11_zero_amount` |
| 12 | 缺失输入 | 金额 `None`；float `12.5`/`0.001`；元字符串 `"12.34"`；小数 extra | — | blocked `missing_input`，`final_cents=None`；非法类型 `TypeError` | PASS（不置零、不吞单位混淆） | `test_scenario12_missing_input` |
| 13 | 缺失规则 | `rule=None`；比率空串 | — | blocked `missing_rule` / `missing_rule_parameter`，`final_cents=None` | PASS（缺失规则不视为零税率） | `test_scenario13_missing_rule` |
| 14 | 规则版本变化 | 同输入 12345：v1 比率 0.07 → 864.15；v2 比率 0.09 → 1111.05 | 864；1111 | 864；1111 | PASS（`input_hash`/`result_hash` 均不同；v1 重放同 hash；`engine_version` 变化亦可区分） | `test_scenario14_rule_version_change` |
| 15 | 重复计算 | 同输入同版本 × 10 次；blocked × 3 次 | 逐字节一致 | 同 `result_hash` | PASS（canonical JSON 与键序无关） | `test_scenario15_repeat_calculation` |

## 可复算与追溯检查

synthetic 快照覆盖任务要求的全部追溯项：**输入快照、规则版本、引擎版本、公式、参数、中间值、舍入口径、最终结果**，并以 `input_hash`/`result_hash`（规范化 JSON SHA-256）固定。实测：

- 同快照 + 同规则版本 + 同引擎版本重算 → `result_hash` 一致（场景 15，10 次重复逐字节相同）；
- 规则版本变化 → `input_hash`/`result_hash` 同时变化且 `rule_version` 可读，新旧结果可区分（场景 14）；
- 引擎版本变化 → 金额相同但 `result_hash` 不同，可区分（场景 14）。

与正式实现的差距（BE2-06 落地时必须补齐）：

1. 快照需增加**账务分类版本**（当前契约 `TaxCalculationRead` 只有 `data_version`，无分类版本引用）；
2. `TaxCalculationRead`/`CalculationLine` 需暴露规则键-版本配对、参数、**舍入口径**与**中间值**（P2-0.5-REVIEW P1 已记录同一缺口）；
3. `input_hash` 的规范化（canonical JSON）规则未定义，需固定排序、编码与字段集合，否则跨实现哈希不可比；
4. 规则参数需带类型/单位（`integer_cents`/`decimal_string` 等方向已在 `TemplateField.value_type` 出现），阈值含/不含边界、负数舍入方向、中间步口径必须由已确认决策给出，不得沿用本文件 fixture。

## 执行记录

- Python **3.11.18**（`server/.venv/py311-env`，符合 `AGENTS.md` 仅 3.11 执行测试的要求；主 `server/.venv` 为 3.12.5，未用于测试）。测试使用独立临时目录，未接触客户数据库或数据。
- 测试命令（见下方说明，包装层仅修正临时目录创建权限，不改任何断言或业务代码）：

  ```powershell
  server/.venv/py311-env/Scripts/python.exe -B -c "import os,sys; _m=os.mkdir; os.mkdir=lambda path, mode=0o777, **kw: _m(path, 0o777 if mode==0o700 else mode, **kw); import pytest; sys.exit(pytest.main(['-q','-p','no:cacheprovider','tests/test_tax_calc_precision_synthetic.py','tests/test_csv_service.py','tests/test_policy_template_preview.py','tests/test_mvp_csv_dedup_provenance.py','tests/test_stage4.py','--basetemp=.pytest_run_be21010']))"
  ```

- 结果：**58 passed**（约 8.7s）＝ 新增 synthetic 精度/阈值/舍入测试 **15 项** + CSV 金额解析/候选预检 24 项 + MVP 对账/CSV 去重 19 项。**新增 v0.2 正式税务计算业务测试 0 项**（引擎与规则尚不存在，不能编造）。
- Ruff（`target-version=py311`）对新增测试文件：`All checks passed!`。
- float/Decimal 对照演示（仅观察，非断言）：`12345*0.07` float 得 `864.1500000000001`、Decimal 得 `864.15`；大额 `×0.001` float 取整差 **1 分**（`…456` vs 精确 `…457`）；`Decimal("0.1")+0.2` → `TypeError`。
- 环境说明：本沙箱下 `os.mkdir(mode=0o700)` 创建的目录会立即不可访问（`tempfile`/pytest 临时目录均用 0o700；0o777 正常），故测试运行用一次性包装仅对临时目录目录权限做规避；与业务代码、断言无关。Windows 权限诊断判定 `NOT_THIS_CLASS`（该目录权限项完整、无外来包权限项），报告：`.acl-recovery/acl-report-6f3f1b19e5b144c68328ff48ef8c8fb9.jsonl`。遗留 2 个不可访问的临时目录待人工或完全权限清理：`server/.probe_m700`、`server/.pytest_tmp_be21010`（另有测试运行留下的 `server/.pytest_run_be21010`，含 6 个编号测试目录）。
- 运行时 OpenAPI 无 `/tax-calculations` 路径；`alembic` 无 `tax_calculation` 表。

## 待确认问题与继续条件

1. `DEC-002`～`004`：首发地区、经营主体、纳税人身份、申报事项与所属期定义；阈值按什么基数、什么期间判定？
2. `DEC-010`/`011`/`012`/`013`：分类确认与审批权限、政策来源/规则/表单的采信与冲突裁决、资料包发布、生产认证。谁批准规则参数（税率、阈值）？
3. **舍入口径**（必须显式确认，不得沿用本文件占位）：舍入方式（四舍五入/银行家/其他）、量化单位、负数与退款方向、中间步是否允许舍入、多次舍入的归并规则。
4. 契约补口：`TaxCalculationRead` 增加规则键-版本配对、参数、舍入口径、中间值与账务分类版本；定义 `input_hash` 的 canonical JSON 规范（P2-0.5-REVIEW P1/P2）。
5. 负数/退款入口：现有 `parse_cents`、CSV 解析与 `tax_cents >= 0` 约束拒绝负数，退款场景需在确认口径后打通。

继续条件：BE2-05/06 实现并经决策确认后，把本文件 15 个场景升级为针对正式引擎的测试（同输入同版本复算、规则/引擎版本区分、阻塞语义、快照完整性），用已确认的政策参数替换全部 synthetic fixture；在此之前，本文件的比率、阈值、舍入值一律视为占位符，**不得进入任何业务实现或对外口径**。
