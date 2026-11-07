# BE2-10-03 MVP 历史数据库升级测试

执行日期：2026-11-07。**结论：合成 MVP 历史库从 `0007_delivery` 升级到当前 head `0008_invoice_provenance` 后，旧数据、关联、ORM 查询与代表性旧 API 保持可用。** 当前仓库没有 v0.2 申报 migration、模型或运行 API，因此**不能宣称 v0.1→v0.2 兼容性已验收**；新增申报模型查询及与 Order 的独立关系仍待 BE2-01～09 实现后验证。

## 测试环境与方法

- Python **3.11.18**、SQLite、SQLAlchemy 2、Alembic、pytest。新测试位于 [test_mvp_history_upgrade.py](../server/tests/test_mvp_history_upgrade.py)，只使用 `tmp_path` 下的全新 SQLite 库和临时文件存储。工作区现有 `server/ledgercrew.db` 未被连接或修改。
- 按真实 Alembic 脚本升级空库到 `0007_delivery`，在该版本 schema 中插入合成历史记录；升级前记录**全部 18 张 MVP 业务表**的原列、完整原始行和计数。随后执行 `alembic upgrade head`，逐表用原列重新查询并与升级前逐行比较，且检查 revision、`integrity_check` 和 `foreign_key_check`。
- 运行时 ORM 查询使用当前 `app.models` 和应用的异步 SQLite Engine；HTTP 回归通过 `ASGITransport` 将当前 FastAPI 应用绑定到该隔离库。文件字节保存在临时 `LocalStorage`，用于旧下载接口实测。

## 升级前后数据对比

当前 head 为 `0008_invoice_provenance`；`0007→0008` 给 `invoice_records` 添加两个可空的来源任务 FK 列，没有改变下表原有列。下表各类均插入 **1 条**合成记录；升级前后条数均为 **1→1**，主键、所有原列值及原始 JSON 均逐行一致：

| 数据类别 | 实际表 | 前 → 后 |
| --- | --- | --- |
| Studio、Order、UploadedFile | `studios`、`orders`、`uploaded_files` | 各 1 → 1 |
| 原始/标准化流水 | `statement_imports`、`bank_transactions` | 各 1 → 1 |
| 发票及确定性对账结果 | `invoice_records`、`reconciliation_batches`、`reconciliation_matches` | 各 1 → 1 |
| 异常工单 | `exception_tickets` | 1 → 1 |
| Agent 历史与事件 | `agent_runs`、`agent_tasks`、`workflow_events` | 各 1 → 1 |
| 报告历史与审计 | `report_versions`、`audit_logs` | 各 1 → 1 |

其余四张已存在但未填充的 MVP 表（`statement_import_errors`、`exception_supplements`、`exception_decisions`、`report_review_actions`）保持 **0→0**。测试未删除或重新创建任何历史记录。额外联表核对文件→订单→Studio、流水→导入→文件、匹配→票据/流水/批次、AgentTask→AgentRun、事件→任务、报告→来源任务；`PRAGMA foreign_key_check` 无错误。当前 ORM 可查询上述 12 类有字符串主键的模型，并读取 WorkflowEvent 与 AuditLog；流水金额仍为 1000 分，报告版本仍为 1。

## MVP API 回归

升级后以合成身份调用当前旧接口，均获得预期结果：工作室、订单、文件、导入批次和异常详情；订单文件、流水、匹配、异常列表；对账批次；文件下载字节；老板查看报告列表及草稿详情。另一客户访问相应对象为 404，客户读取未发布报告为 404。测试只验证旧数据的**读取与现有权限**，未将 MVP 报告当作申报草稿，也未自动把旧 Order 转成 FilingTask。完整 MVP 写入流程仍由既有全量回归测试覆盖。

## 测试结果与问题清单

| 检查 | 实际结果 |
| --- | --- |
| 新增历史升级测试 | **3 passed**：原始行/关系、ORM 读取、旧 API 与权限。 |
| 全量后端 `pytest -q` | **127 passed，0 failed，0 skipped**，56.86 秒。 |
| 新增文件 Ruff | **通过**。 |

**尚未解决：**仓库只有 `0001`～`0008` 的 MVP migration，BE2-01～09 新增表和路由不存在；本轮不能执行“v0.2 全部 migration”、查询新增申报模型，或验证 FilingTask 与 Order 的新增 FK/业务独立性。相关业务决策 DEC-002～014 仍为 pending。未来新增 v0.2 revision 后必须在旧库副本上重跑本测试并补查新表、权限和旧数据升级；本轮没有修改 migration、业务代码、真实数据库或原有主键。
