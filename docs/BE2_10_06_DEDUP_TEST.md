# BE2-10-06 平台数据去重与来源追溯测试

## 结论与范围

**v0.2 平台导入验收：BLOCKED。** 当前仓库没有 `PlatformImport`、`PlatformRecord`、`SettlementBatch`、平台导入 Service/API 或对应 Alembic migration。`contracts/API.md` 中的平台结构和操作仍是候选契约。不能把 MVP 的订单银行 CSV 导入当作已实现的平台导入，也不能声称已经满足“跨导入不重复记账”。

本次只新增合成数据回归测试 `server/tests/test_mvp_csv_dedup_provenance.py`，验证现有 `StatementImport`、`BankTransaction`、`StatementImportError` 与 `UploadedFile` 的实际边界。没有修改业务代码、数据库结构或决策状态；没有使用客户数据。

## 决策门禁与现有去重口径

- `DEC-005`（平台及导出格式、字段、外部编号）仍为 `pending`。
- `DEC-009`（资金来源、跨期、内部转账、无外部 ID 的重复检测口径及阈值）仍为 `pending`。
- 现有 MVP CSV 解析器在**单个文件内**用非空 `external_id` 检查重复。后续重复行写入 `StatementImportError`，保留行号、原因 `duplicate_external_id` 和原始行 JSON；首行写入 `BankTransaction`。数据库唯一约束作用域也是单个 `statement_import_id`。
- 对**同一个已上传文件 ID**再次请求导入，返回既有 `StatementImport`，不会重新写入银行流水或导入审计。`uploaded_file_id` 有唯一约束。
- 文件 SHA256 仅供检索与追溯，没有跨文件唯一约束。相同内容重复上传，无论文件名是否相同，都会形成新的 `UploadedFile`、`StatementImport` 和 `BankTransaction`；相同外部 ID 跨文件也不会自动识别。这是待补足的 v0.2 能力，不是已确认的去重策略。
- 无外部 ID 时，MVP 保留每个有效物理行，包括完全相同的两行；没有相似度阈值、重复判定依据或待核实状态。不能将这些行自动判为相同交易，也不能据此正式记账。

## 场景结果

| 用户场景 | 实测结果 / 当前边界 | v0.2 验收 |
| --- | --- | --- |
| 1. 同一外部 ID 重复导入 | 单文件内后续行标记 `duplicate_external_id`，原始行保留；跨文件未阻断 | **BLOCKED**，须确认平台 ID 作用域 |
| 2. 同一文件重复上传 | 同一个 `file_id` 重复导入幂等；相同文件名及字节再次上传会产生新文件及流水 | **BLOCKED**，跨上传口径未确认 |
| 3. 文件名不同但内容相同 | SHA256 相同，文件及各自流水都保留；未自动合并 | **BLOCKED**，存在跨导入重复计数风险 |
| 4. 不同批次相同外部 ID | MVP 以导入文件为约束范围，两个导入均可写入；没有平台批次模型 | **BLOCKED** |
| 5. 外部 ID 冲突 | 同文件第二行被拒并留原始证据；跨导入内容冲突无检测 | **BLOCKED** |
| 6. 缺少外部 ID | 有效行以空 ID 保存；无受控重复判定或待核实状态 | **BLOCKED**，待 DEC-009 |
| 7. 完全相同的原始行 | 无 ID 的两行均保存，行号不同；没有误删原始证据 | **BLOCKED**，不能自动记账 |
| 8. 金额相同、日期不同 | 两行分别保存并保留各自日期、行号 | 仅 MVP 保存行为已验证 |
| 9. 日期相同、交易方不同 | 两行分别保存并保留各自交易方、行号 | 仅 MVP 保存行为已验证 |
| 10. 原始与标准化关联 | `BankTransaction.statement_import_id → StatementImport.uploaded_file_id → UploadedFile`；可取原始行和原始文件 | MVP 已验证；平台记录、账户、批次关联 **BLOCKED** |
| 11. 同一记录多次请求处理 | 同 `file_id` 请求返回同一导入 ID；流水及审计各一份 | MVP 已验证；平台处理 **BLOCKED** |
| 12. 部分失败后重试 | 超出 CSV 行数上限时两次请求均无导入/流水副作用，文件仍可下载；单行错误另以 `StatementImportError` 持久化 | MVP 已验证；平台断点恢复 **BLOCKED** |

## 来源链与事务检查

测试检查了文件 SHA256、原始文件下载字节、导入 ID、原始物理行号、外部 ID、交易日期、交易方、标准化金额（整数分）、原始行 JSON 与错误原因。MVP 的 `BankTransaction` 没有平台账户字段、去重判定状态、判定依据或平台批次 ID；因此不能完整满足 v0.2 的目标来源链。

CSV 全局解析失败发生于写入导入实体之前。行数超限的两次请求后，`statement_imports`、`bank_transactions` 以及 `statement.imported` 审计数均为零，原始上传文件仍可下载。成功导入及行级错误由同一事务提交。此测试没有覆盖并发请求故障注入或平台导入事务，不能据此证明平台重试安全。

## 执行记录

- 环境：Python 3.11.18、项目锁定依赖、每个用例独立临时 SQLite 数据库；未连接开发或客户数据库。
- 命令：`server/.venv/py311-env/Scripts/python.exe -B -m ruff check tests/test_mvp_csv_dedup_provenance.py`；结果通过。
- 命令：`server/.venv/py311-env/Scripts/python.exe -B -m pytest -q tests/test_mvp_csv_dedup_provenance.py`；**4 passed**。
- 全量后端回归：`server/.venv/py311-env/Scripts/python.exe -B -m pytest -q`；**143 passed**。

## 未确认问题与后续门禁

1. DEC-005：首个平台及导出版本、每类记录外部 ID 的稳定性和作用域、是否存在跨批次复用的 ID。
2. DEC-009：相同内容文件重传和跨批次相同 ID 的处理、无 ID 记录的候选规则与阈值、人工复核动作、冲突记录是否可进入账务及其恢复流程。
3. 平台领域模块和独立来源链尚未实现；实现后需在真实平台字段契约的合成 fixture 上重跑这 12 个场景，并验证不会产生重复 `AccountingEntry`。

确认以上决策前，不添加跨文件唯一约束、不按金额/日期/交易方自动合并、不删除原始行、不把 MVP 行为提升为正式平台去重规则。
