# BE2-10 测试报告

执行日期：2026-11-07。环境：Windows、隔离的 Python **3.11.18** 虚拟环境 `server/.venv/py311-env`，SQLite 临时合成数据库。未连接真实客户数据库；未修改 `server/uv.lock`。核心依赖实测版本：FastAPI 0.162.0、Pydantic 2.14.3、SQLAlchemy 2.0.57、Alembic 1.20.1、pytest 9.2.0。`server/pyproject.toml` 要求 `>=3.11,<3.12`，Ruff 目标为 `py311`，`server/uv.lock` 限定 `==3.11.*`。

## 实际执行结果

| 检查 | 结果 | 说明 |
| --- | --- | --- |
| 全量 `python -B -m pytest -q` | **121 passed，0 failed，0 skipped**；最终复跑 50.79 秒 | 覆盖当前 MVP、开发/测试认证路由和本轮 3 个迁移/备份测试。此结果不证明未实现的 v0.2 业务。 |
| 迁移测试 `pytest -q tests/test_migration_safety.py` | **3 passed** | 空库升级与 ORM 结构比对；合成 MVP 关联数据 `0007→0008→0007→0008`；WAL 备份恢复、禁止覆盖及 manifest 篡改拒绝。包含在全量 121 项内。 |
| Python 导入检查 | **通过** | `app.main`、`app.models`、`scripts.sqlite_snapshot` 在 Python 3.11.18 可导入。项目未配置静态类型检查器，未声称完成静态类型检查。 |
| Ruff：本轮新增脚本与测试 | **通过** | `ruff check scripts/sqlite_snapshot.py tests/test_migration_safety.py`。 |
| Ruff：全仓 `app scripts tests` | **失败：119 项** | 85 项 B008、16 项 I001、8 项 UP017，其余 10 项其他规则；包括现有 MVP 和正在开发的认证代码。本轮未批量重写无关代码。上线质量门槛未满足。 |
| 当前运行 OpenAPI | **32 条路径；无 P2 申报路径** | 与候选契约标为既有的 32 条路径对齐；另有 35 个 proposed 操作（29 条新路径）仅在静态契约中。此前 29 条 MVP 路径未被移除。 |
| 工作区现有 SQLite 库只读检查 | **`0004_statement_imports`，完整性/外键通过** | `server/ledgercrew.db` 的 11 张表与 `0004` 预期相符；低于代码 head `0008`。未写入、迁移或读取业务行内容。 |

## 数据库测试的证据范围

- 空库 `alembic upgrade head` 到 `0008_invoice_provenance`，实际表集合、列、可空性、FK、显式索引和唯一约束与当前 SQLAlchemy metadata 一致；`PRAGMA integrity_check=ok`，`foreign_key_check` 为空。
- 在 `0007_delivery` 独立库插入 Studio、Order、文件、流水导入与交易、AgentTask/Run、事件、票据、对账批次与匹配、异常、报告和审计的**合成数据**。升到 `0008` 后记录计数和关联保留；降到 `0007`、再次升级均保留原有行。
- WAL 模式下使用 SQLite backup API 创建快照，验证 manifest 的 UTC 时间、revision、SHA256 及数据库完整性；恢复到全新路径，旧数据和 revision 一致；重复目标文件及篡改 manifest 均被拒绝。
- `0008` 降级会删除新增的两列。本测试中它们均为空，**不能证明已有来源引用时可无损降级**；现有 `0001`～`0007` 的删表降级也可能丢业务数据。未对真实数据库执行操作。

## 业务测试矩阵

| 要求 | 状态与原因 |
| --- | --- |
| 平台去重、批次/跨期、内部转账 | **BLOCKED**：BE2-02/03 不存在，DEC-005/009 pending。MVP CSV 和票据对账的通过结果不能套用。 |
| 政策适用、冲突、阈值、Decimal 舍入 | **BLOCKED**：BE2-05/06 不存在，DEC-011 pending，没有确认规则或参数。 |
| 申报模板导入、字段与表间关系 | **BLOCKED**：BE2-07 不存在，没有官方表单和已审模板。未造真实字段。 |
| P2 草稿审批失效、资料包发布和恢复 | **BLOCKED**：BE2-08/09 不存在，DEC-010/012/014 pending；MVP 报告审批与 Agent 检查点有测试，但只覆盖订单流程。 |
| P2 API 权限与租户隔离 | **BLOCKED**：P2 路由未挂载；当前 MVP 跨租户与生产 503 门禁测试通过，不能外推至新资源。 |
| v0.2 全链路与 v0.2 Alembic 升降级 | **BLOCKED**：BE2-01～09 未实现，没有 v0.2 revision。 |

## 修复与剩余风险

新增可重复运行的 SQLite 快照/恢复工具和 3 个迁移安全测试；测试中初版断言把 SQLAlchemy Column 对象与列名比较，已在提交前修正，最终全量无失败。没有修改既有业务逻辑、已确认决策或锁文件。剩余问题：BE2-01～09 缺失、13 项决策 pending、生产认证未配置、全仓 Ruff 119 项、v0.2 业务与迁移无法测试。**本报告不构成 v0.2 上线验收。**
