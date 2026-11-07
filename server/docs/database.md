# 数据库与迁移

数据库默认是 `sqlite+aiosqlite:///./ledgercrew.db`，路径相对于运行命令的目录。所有配置通过环境变量或 `.env` 提供，例子见 `../.env.example`。模型使用 SQLAlchemy 2 `Mapped` / `mapped_column`，异步 Session 按请求创建；UTC 时间由自定义类型写入和读取。金额统一保存为整数分。应用启动不执行 `create_all`。

在 `server/` 目录运行：

```powershell
alembic upgrade head
alembic current
```

模型变化应新增 `alembic/versions` 中的 revision。当前 head 为 `0008_invoice_provenance`，为发票增加可追溯的审核与识别任务外键，并对识别任务 ID 设置唯一索引。迁移测试覆盖从空数据库升级及第一阶段已有记录升级。

## 主要表

| 表 | 主要关系与数据 |
| --- | --- |
| `studios`, `orders` | 工作室归属、账期、模拟订单、服务范围和订单状态；订单号唯一 |
| `uploaded_files` | 原始文件元数据、SHA256、校验状态、ZIP 原包/条目来源；存储键唯一 |
| `statement_imports`, `statement_import_errors`, `bank_transactions` | CSV 导入批次、行错误、原始行 JSON 与规范化交易；同一导入的行号/非空外部 ID 唯一 |
| `agent_runs`, `agent_tasks` | 输入输出 JSON、状态、幂等键、时间、错误与检查点；订单内幂等键唯一 |
| `workflow_events`, `audit_logs` | 可续读事件、操作者和关键操作审计 |
| `invoice_records` | 原文件、审核任务、识别任务、票面字段和整数分金额；识别任务 ID 唯一 |
| `reconciliation_batches`, `reconciliation_matches`, `exception_tickets` | 批次汇总、唯一票据/流水配对、独立异常工单；批次号在订单内唯一 |
| `exception_supplements`, `exception_decisions` | 客户独立补充及老板决定，不覆盖原始数据 |
| `report_versions`, `report_review_actions` | 报告版本、内容哈希、批次快照、审核/批准/发布历史 |

SQLite 连接启用外键约束；测试执行 `PRAGMA foreign_key_check`。原始文件和原始 CSV 行不会被 Agent 输出覆盖。JSON 只用于 Agent 原始输入输出、行原始数据、证据、事件等可变结构；归属、状态、金额、关联和时间是独立列。

## 版本与一致性

对账再次运行创建新批次，旧批次和工单保留。报告按订单递增版本，审批绑定报告 ID、版本与内容哈希；内容或异常状态变化会使待审报告失效，需创建新版本。新版本发布后旧已发布版本标记为 `superseded`。对账匹配的 `(batch_id, invoice_id)` 与 `(batch_id, transaction_id)` 唯一，避免同一批次重复配对。

当前跨批次异常决定继承规则尚待确认，服务不自动迁移旧工单的处理结果。
