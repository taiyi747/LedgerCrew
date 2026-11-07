# 应用与数据库回退

状态：**现有 MVP 的恢复原则；v0.2 无迁移可回退。** 任何真实数据库回退都需要负责人批准、维护窗口和经校验备份。不要把 `alembic downgrade` 当作用户数据备份。

1. 停止入口流量、API 和 Worker 写入，记录当前提交、Alembic revision、错误、数据库及文件存储路径；保留失败现场。
2. 核对升级前由 `scripts/sqlite_snapshot.py backup` 生成的 `.db` 与 `.manifest.json`。工具使用 SQLite backup API，在 WAL 模式下取得一致快照并记录 UTC 时间、revision 与 SHA256。配套核对 `STORAGE_ROOT` 的同一时间点备份。
3. 若只是应用代码回退，先确认旧应用能读取当前 schema；不能假设前后版本兼容。先在隔离副本启动旧应用并回归旧订单、文件、对账、报告和审计。
4. 若数据库 schema 或数据需要回退，优先使用 `python scripts/sqlite_snapshot.py restore <备份库> <全新恢复路径>`。恢复工具拒绝覆盖，并验证 manifest、数据库完整性、外键及 revision。将配置指向恢复路径与相应文件存储副本，核对旧业务后才切流。
5. 升级后写入的数据不会自动进入旧快照；记录差异、暂停相关操作，由负责人决定人工补录。不得静默删除原始文件、历史报告或审计。

`0008_invoice_provenance` 的 downgrade 删除发票来源任务外键列；有值时会丢失该来源关联。更早 revision 的 downgrade 含删表。自动化只验证了**无新增列数据**时 `0008→0007→0008` 的合成数据演练，不能声称真实库完全可逆。详细步骤及验证见 [数据库迁移手册](DATABASE_MIGRATION.md)。
