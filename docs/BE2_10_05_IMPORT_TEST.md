# BE2-10-05 政策规则与申报模板导入预检

执行日期：2026-11-07。状态：**partially_completed（通用候选 JSON 校验与 dry_run 预检完成；正式导入阻塞）**。本报告不代表存在可供正式税务计算的已审核政策或申报模板。

## 代码与决策检查

`server/app/`、`server/alembic/versions/` 中没有 PolicySource、PolicyRule、FormTemplate、TaxReturnDraft 的运行模型、迁移、规则审核 Service 或导入 API；当前 head 仍为 MVP 的 `0008_invoice_provenance`。[决策登记表](P2_DECISIONS.md)中 DEC-002～004、011 均为 pending。候选 [API 契约](../contracts/API.md)和 `contracts/schemas.py` 尚未冻结，不能直接作为生产规则或官方表单。故本轮**没有建表、挂载导入路由、写入正式规则或实现批准/计算**。

## 已实现的通用预检

[policy_template_preview.py](../server/app/services/policy_template_preview.py) 是纯函数式预检，不访问数据库。`PolicyRuleCandidate` 和 `FormTemplateCandidate` 用 Pydantic 2 严格解析 JSON：检查来源 UUID 与来源哈希、身份/版本/适用元数据、日期区间、候选审核状态、模板字段类型，以及声明的 SHA256 是否等于规范化 JSON 的哈希。规范化时排除 `content_hash` 本身，排序 JSON 键；空白/顺序不同但内容相同的请求得到同一哈希。

调用方可传入**已知来源 ID→来源哈希**与**已有身份→内容哈希**的只读索引，`preview_policy_rule` / `preview_form_template` 返回 `new`、`duplicate` 或 `version_conflict`。规则预检身份为 `(source_id, rule_code, rule_version)`，模板预检身份为 `(template_id, template_version)`；这仅是 dry_run 比较键，**不是数据库业务唯一约束**。同一身份/版本但不同内容返回冲突，不覆盖原值。来源不存在、来源哈希变化、内容哈希不符会拒绝预检。导入入口只接受显式 `review_status="candidate"`，不能由 JSON 自报 `approved`。

来源索引和已有版本索引目前由调用方提供，尚无可信持久化 Repository；预检结果不能自动转成“官方来源已验证”“正式规则已批准”或“模板可申报”。地区、主体、身份、申报事项代码在测试中均为 `SYNTHETIC_*`，不代表支持范围。

## 可直接读取的 synthetic JSON

- [规则示例](../contracts/examples/synthetic_policy_rule_import.json)：`SYNTHETIC_RULE`、`synthetic-v1`、虚构来源 UUID、`review_status=candidate`，参数仅含 `synthetic_key=example_only`，**没有税率或政策内容**。
- [模板示例](../contracts/examples/synthetic_form_template_import.json)：`SYNTHETIC_TEMPLATE`、单个 `SYNTHETIC_FIELD` 文本占位字段，**不是实际申报字段或官方表单**。

两份文件是完整可解析 JSON，SHA256 已按预检算法生成，并由自动化测试直接读取验证。示意调用：

```python
from pathlib import Path
from app.services.policy_template_preview import preview_policy_rule

preview = preview_policy_rule(
    Path("../contracts/examples/synthetic_policy_rule_import.json").read_bytes(),
    known_sources={"00000000-0000-4000-8000-000000000901": "a" * 64},
    existing={},
)
assert preview.outcome == "new"  # dry_run only; no database write
```

## 测试结果与边界

| 验收项 | 结果 |
| --- | --- |
| 正常结构校验与 dry_run | **通过**，规则和模板均返回 `new`，索引未改变。 |
| 重复请求、JSON 键顺序变化 | **通过（预检）**，给定同一已有索引返回 `duplicate`；尚未证明持久化幂等。 |
| 相同身份/版本不同内容 | **通过（身份冲突）**，返回 `version_conflict`，不覆盖已有哈希。适用范围重叠等**语义冲突**仍待 DEC-011。 |
| 缺必填元数据、空白版本、非法日期/字段类型、错误内容哈希 | **通过**，均被拒绝。 |
| 来源不存在或来源版本哈希不符 | **通过（调用方索引）**，均被拒绝；来源 Repository/官方性审核仍未实现。 |
| 未审核规则使用 | **仅验证候选入口不能自报 approved**；正式计算服务不存在，计算门禁 **BLOCKED**。 |
| 正式导入、事务失败回滚、历史规则/模板查询 | **BLOCKED**：没有持久化模型、Alembic migration、审核 Service 或导入 API。 |

新增 [test_policy_template_preview.py](../server/tests/test_policy_template_preview.py) **9 passed**；Python 3.11.18 全量后端测试 **139 passed，0 failed，0 skipped**（57.50 秒）；新增模块与测试的 Ruff 检查通过。未修改 Python 版本、`server/uv.lock`、MVP 业务代码或决策状态。

## 完成正式导入前所需条件

先完成 BE2-05/07 的模型、Alembic migration、来源快照与版本 Repository，并由 DEC-011 确认官方来源采信、审核角色/动作、规则与模板适用及冲突裁决；DEC-002～004 确认首发范围。之后将预检连接到受权事务式 `validate/dry_run/import/preview/conflict` 流程，补正式导入幂等、历史查询、失败回滚和未审核数据不得进入确定性计算的测试。不能将本轮的 synthetic 字段或预检身份键升格为业务规则。
