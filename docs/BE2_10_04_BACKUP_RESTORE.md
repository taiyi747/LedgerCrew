# BE2-10-04 SQLite 备份、恢复与回滚验证

执行日期：2026-11-07。结论：**当前 MVP SQLite 库可使用官方 backup API 生成带校验元数据的一致快照，并恢复到全新路径。`0008→0007` 在发票来源字段已有值时不能无损 downgrade；必须依靠升级前快照恢复。** 仓库仍无 v0.2 业务 migration，因此本结论不覆盖未来 v0.2 的回退能力。

## 配置与实现

- 后端固定 Python 3.11、SQLite、SQLAlchemy 2、Alembic。默认数据库 URL 为 `sqlite+aiosqlite:///./ledgercrew.db`，相对运行目录；应用连接在 `app/db/session.py` 设置 `PRAGMA foreign_keys=ON`。项目未统一强制 WAL，测试显式启用 WAL 以覆盖该场景。
- [备份工具](../server/scripts/sqlite_snapshot.py) 使用 `sqlite3.Connection.backup()`，而非单独复制可能正在写入的 `.db` 文件。`backup` 只写新目标，`restore` 也只写新目标；已有路径不会被覆盖。
- 每次备份先核对源库 `PRAGMA integrity_check`、`foreign_key_check` 和唯一 Alembic revision；快照完成后再验证目标 revision，生成同名 `.manifest.json`，包含 `backup_time_utc`（UTC）、`revision`、SHA256、完整性与外键检查结果。恢复前检查备份 SQLite 内容、manifest 格式及 revision/SHA256；恢复后重查 revision、完整性和外键。
- 测试只在 `tmp_path` 下建合成库。没有对工作区现有 `server/ledgercrew.db` 执行升级、降级、备份写入或恢复覆盖；没有修改 `server/uv.lock`、Python 版本或业务 migration。

## 自动化测试结果

| 场景 | 测试和观察结果 |
| --- | --- |
| 正常备份/恢复 | 升到当前 head `0008_invoice_provenance`，插入关联的合成 MVP 数据；备份 manifest 的 UTC 时间、revision、SHA256 与实际文件吻合。恢复到全新路径后，Alembic revision、记录数量、`integrity_check=ok` 和空 `foreign_key_check` 一致。 |
| WAL 中未 checkpoint 的提交 | 显式启用 WAL，并保持旧读取事务以阻止 checkpoint；随后提交第二条审计记录。确认 WAL 文件有内容；backup API 快照和恢复库均含两条已提交审计记录。 |
| 损坏备份 | 非 SQLite 字节文件在完整性校验阶段被拒绝，未创建恢复目标。 |
| 元数据损坏 | 缺失或非法 JSON manifest、manifest revision 不匹配均被拒绝；既有安全测试还覆盖 SHA256 不匹配。 |
| 目标路径错误 | 不存在的目标目录返回错误；已有目标文件被拒绝且原字节不变；恢复前未覆盖任何现有库。 |
| 回退后再升级 | 在 `0007_delivery` 合成库写入 MVP 数据，升到 `0008` 后给发票写入两个来源任务 FK 与新审计行。保存 head 快照，降回 `0007`：旧表计数、外键和审计行保留，但新增两列被移除。再升 `0008`：两列重新出现而原值为 null。由快照恢复的新库保留两个来源任务 FK 原值，并通过完整性/外键检查。 |

新建的 [test_backup_restore.py](../server/tests/test_backup_restore.py) **3 项通过**；与现有 [迁移安全测试](../server/tests/test_migration_safety.py) 合计 **6 项通过**。本轮最终全量后端测试为 **130 passed、0 failed、0 skipped**；新增脚本与测试的 Ruff 检查通过。首次测试未发现生产迁移缺陷；新增的显式异常处理使损坏数据库和无效 manifest 返回可辨识错误。

## 操作顺序与回退边界

正式操作前确认 Python 3.11、代码提交、`DATABASE_URL` 的绝对路径、当前 revision、目标 revision、维护窗口及足够空间。先停写并记录文件存储 `STORAGE_ROOT` 的配套快照计划；数据库备份可通过如下命令完成（仅在目标库获批准后执行）：

```powershell
python scripts/sqlite_snapshot.py inspect "C:\path\to\ledgercrew.db"
python scripts/sqlite_snapshot.py backup "C:\path\to\ledgercrew.db" "C:\path\to\backups\before-upgrade.db"
python scripts/sqlite_snapshot.py inspect "C:\path\to\backups\before-upgrade.db"
```

在**独立副本**先执行 `alembic upgrade head`、数据/API 回归和必要的 downgrade 演练。真实库升级仍需负责人针对具体路径和 revision 批准。若回退不可无损，停止写入，保留故障现场和原库，用下列方式恢复到**全新路径**并验证，再切换配置；不得对真实库直接 downgrade 或覆盖：

```powershell
python scripts/sqlite_snapshot.py restore "C:\path\to\backups\before-upgrade.db" "C:\path\to\recovery\restored.db"
python scripts/sqlite_snapshot.py inspect "C:\path\to\recovery\restored.db"
```

恢复旧快照会缺少快照之后新写入的数据，必须单独核对和决定补录；数据库快照也不包含上传文件的实际字节，`STORAGE_ROOT` 需配套恢复。`0008` downgrade 会删除 `invoice_records.source_task_id` 与 `material_review_task_id`；更早 revision 的 downgrade 还会删除其新增表。**不能把这些迁移标为完全可逆。** 详细检查单见 [数据库迁移手册](DATABASE_MIGRATION.md)。

## 未解决事项

目前只有 MVP `0001`～`0008` migration，BE2-01～09 的新增申报表结构和 v0.2 rollback 尚不存在。未来每个新 revision 都需在包含真实形状的**合成数据**的副本上补做升级、回退、恢复和 API 回归，并明确其数据可逆性；本轮不推断未实现的 v0.2 可以安全上线。
