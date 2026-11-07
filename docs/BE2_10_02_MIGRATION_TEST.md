# BE2-10-02 Alembic 空数据库迁移测试

执行日期：2026-11-07。结论：**当前仓库的空白 SQLite 数据库可连续迁移到 Alembic head，ORM 基础写入和数据库约束均通过。** 当前 head `0008_invoice_provenance` 属于 MVP；仓库尚无 v0.2 业务 migration，因此本结果不代表 v0.2 申报数据库已可初始化。

## 环境与隔离

- Python **3.11.18**；SQLite、SQLAlchemy 2.0.57、Alembic 1.20.1、pytest 9.2.0。`server/pyproject.toml` 的 `requires-python` 为 `>=3.11,<3.12`，Ruff 为 `py311`。
- 新测试：[test_empty_migration.py](../server/tests/test_empty_migration.py)。每个测试由 `tmp_path` 创建从未存在过的独立数据库，设置该测试自己的 `DATABASE_URL`，调用 Alembic `upgrade head`。未连接、升级、降级或重置 `server/ledgercrew.db`。
- `server/alembic.ini` 将脚本目录指向 `server/alembic/`；`env.py` 从 `DATABASE_URL` 转换为同步 SQLite URL并注册 `Base.metadata`。SQLite batch 迁移连接临时关闭 FK，迁移后执行 `foreign_key_check`；应用 `make_engine()` 连接启用 `PRAGMA foreign_keys=ON`。

## Revision 与执行顺序

单一 head：`0008_invoice_provenance`。八个文件的 `revision/down_revision` 连续：

`0001_initial → 0002_studios_orders_files → 0003_required_order_fields → 0004_statement_imports → 0005_reconciliation → 0006_agent_integration → 0007_delivery → 0008_invoice_provenance`。

测试动态读取 Alembic `ScriptDirectory`，要求单 head、首版本无父版本、每个后续版本引用直接前驱；从空库执行全部升级后，数据库 `alembic_version` 精确等于 head。升级未出现重复建表或重复加列错误。

## 实际数据库结构检查

升级后共有 **18 张业务表 + `alembic_version`**：

`studios`、`orders`、`uploaded_files`、`agent_runs`、`agent_tasks`、`workflow_events`、`audit_logs`、`statement_imports`、`statement_import_errors`、`bank_transactions`、`invoice_records`、`reconciliation_batches`、`reconciliation_matches`、`exception_tickets`、`exception_supplements`、`exception_decisions`、`report_versions`、`report_review_actions`。

逐表将 SQLite 反射结果与 SQLAlchemy metadata 比对：表名、字段名、可空性、主键、全部 **37 个字段级外键引用**、**24 个显式索引**及 **13 个显式唯一约束**均一致。ORM 声明的服务器默认值 `agent_tasks.attempt_count=0` 在数据库中存在且值为 0；原迁移给 `orders.is_simulated` 的服务器默认值由省略该字段的原生 INSERT 验证为 1。`PRAGMA integrity_check` 返回 `ok`，`PRAGMA foreign_key_check` 返回空结果。

应用实际异步连接的 `PRAGMA foreign_keys` 为 1；插入引用不存在订单的 `uploaded_files` 被 FK 拦截。省略 `studios.name` 被 NOT NULL 拦截；重复 `orders.order_no` 和 `uploaded_files.storage_key` 被唯一约束拦截。合成 Studio、Order、UploadedFile 用 ORM 写入后可重新查询，关联 ID、订单默认状态、金额、UTC 创建时间与文件存储键均保留。测试数据不含真实客户信息。

## 测试数量、结果与失败原因

| 命令（从 `server/` 执行） | 最终结果 |
| --- | --- |
| `python -B -m pytest -q tests/test_empty_migration.py` | **新增 3 项通过**。 |
| `python -B -m pytest -q tests/test_empty_migration.py tests/test_migration_safety.py` | **迁移专项 6 项通过**，7.48 秒。 |
| `python -B -m pytest -q` | **全量 124 项通过，0 失败、0 跳过**，52.15 秒。 |
| `ruff check tests/test_empty_migration.py` | **通过**。 |

首次编写测试时，一处 `pytest.raises` 被错误地并入 `async with`，导致 1 项**测试自身**报 `TypeError`；已改为嵌套普通 context manager 后重跑，最终无失败。没有发现迁移执行、结构、外键、唯一约束或基本读写缺陷；未修改业务代码、Alembic migration、Python 版本或依赖锁。

本测试仅覆盖**空库初始化**。旧数据升级、备份与降级的独立证据见 [BE2-10 测试报告](BE2_10_TEST_REPORT.md)及 [迁移安全测试](../server/tests/test_migration_safety.py)。若以后新增 v0.2 revision，必须重新执行本测试并增加该版本的业务表/约束验收。
