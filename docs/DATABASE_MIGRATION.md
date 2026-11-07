# SQLite 数据库迁移、备份与恢复

状态：**MVP 与生产基础设施迁移操作手册；不代表第二阶段申报功能上线。** 当前 Alembic head 为 `0016_workflow_provenance`。`0009`～`0014` 加认证、Sandbox、反馈、审核、任务恢复和模型预算；`0015` 加 Worker 租约，`0016` 加工作流来源字段。执行真实数据库升级、降级或恢复前，须由负责人批准具体数据库、目标 revision 和维护窗口。第二轮曾误触工作区默认 `server/ledgercrew.db`，详情见文末事件记录。

## 迁移前检查

1. 固定 Python 3.11，安装 `server/uv.lock` 对应依赖；核对 `server/pyproject.toml` 和 Ruff 均为 py311。记录应用提交、`DATABASE_URL` 的绝对 SQLite 路径、`alembic current` 和 `alembic heads`；确认目标 revision 有对应已审查迁移。
2. 检查磁盘空间可容纳原库、快照和升级期间 SQLite 临时文件；确定应用停写时段。WAL 模式下不能把正在写入的 `.db` 单文件复制当作唯一备份。
3. 对真实环境先在**数据库副本**上运行 upgrade、`PRAGMA integrity_check`、`PRAGMA foreign_key_check`、业务读写回归及回退演练。若旧数据和新模型不能匹配，停止发布。
4. 当前未实现完整 BE2-01～09 申报领域；不得把 `0016` 称为已上线申报版本。旧 Studio 没有所有者时不能猜测归属，须通过明确授权加入成员关系。

## 一致性备份

在 `server/` 目录使用 `scripts/sqlite_snapshot.py`。路径必须是绝对路径，目标文件与同名 manifest 必须尚不存在。工具通过 SQLite `Connection.backup()` 从源库制作一致快照，验证完整性、外键和 Alembic revision，并生成 `<备份文件>.manifest.json`，记录 UTC 时间、revision、SHA256。它不会覆盖已有文件。

```powershell
python --version
python scripts/sqlite_snapshot.py inspect "C:\path\to\ledgercrew.db"
python scripts/sqlite_snapshot.py backup "C:\path\to\ledgercrew.db" "C:\path\to\backups\ledgercrew-before-upgrade.db"
python scripts/sqlite_snapshot.py inspect "C:\path\to\backups\ledgercrew-before-upgrade.db"
```

备份可在 WAL 模式下取得一致快照；正式迁移前仍应停止应用和 Worker 写入，再确认备份 revision 与源库当前 revision 一致。将 `.db` 和 `.manifest.json` 一起保存于受控位置；原始业务文件存储 `STORAGE_ROOT` 还需单独做一致性备份，数据库快照不包含文件字节。不要把备份、manifest 或密钥提交到仓库。

## 升级与验证

本段是 **已批准迁移** 的操作顺序，不是当前 v0.2 上线指令。停写后再次 `inspect`，确认应用连接均已关闭；配置指向经核对的数据库，再运行：

```powershell
alembic current
alembic heads
alembic upgrade head
alembic current
python scripts/sqlite_snapshot.py inspect "C:\path\to\ledgercrew.db"
```

核对 `alembic_version`、表/列/FK/索引/唯一约束、`integrity_check`、`foreign_key_check`，再做权限、旧订单/文件/对账/报告查询和新增 API 的实测。应用连接在 `app/db/session.py` 设 `PRAGMA foreign_keys=ON`；Alembic 批量改表连接临时关 FK，迁移后做 `foreign_key_check`。新版服务只有在迁移与回归均通过后才可接流量。

## 回退与恢复

**不要在真实已有业务数据的库上直接 `alembic downgrade`。** `0014→0013` 会删除模型预算和遥测，`0013→0012` 若已有 cancelled/retrying/timeout 状态会与旧约束冲突；`0012`～`0009` 降级会删除审核、反馈、支付或账号数据；`0008→0007` 还会删除发票来源列。先在副本上确认；有数据转换或删列风险时停止写入并恢复升级前快照。

`0016→0015` 会删除工作流来源和报告版本字段；`0015→0014` 会删除 Worker 实例/租约。即使表当前为空，也应先做经批准的快照和副本演练。

```powershell
python scripts/sqlite_snapshot.py restore "C:\path\to\backups\ledgercrew-before-upgrade.db" "C:\path\to\recovery\ledgercrew-restored.db"
python scripts/sqlite_snapshot.py inspect "C:\path\to\recovery\ledgercrew-restored.db"
```

`restore` 先验证 manifest 与备份 SHA256，再向**全新路径**恢复并检查 SQLite 完整性、外键和 revision；不会覆盖现用库。将 `DATABASE_URL` 指向这个恢复路径，配套恢复同一时间点的 `STORAGE_ROOT`，回退到与该 revision 兼容的应用版本，先在隔离环境核对旧订单、文件下载、对账、报告和审计记录，再按维护流程切流。升级后新产生的数据不会自动存在于旧快照，必须单独评估补录或人工恢复，不能声称无损。

恢复工具还会拒绝损坏的 SQLite 文件、缺失或无效的 manifest、哈希/revision 不匹配、已有目标文件和不存在的目标目录。失败后保留原库与备份，不覆盖目标路径；若生成了不完整的新目标，先核对明确路径并由操作人逐个处理，不对目录执行批量删除。WAL 模式下已提交但尚未 checkpoint 的记录由 SQLite backup API 一并纳入快照；恢复后仍须按实际业务记录核对。

若迁移失败或备份验证失败，保留原库与失败现场，停止写入和发布；记录错误、revision、快照 manifest 及受影响数据，由负责人选择修复迁移或恢复路径。不要用 `create_all`、直接删库或覆盖原始库来处理故障。

## 自动化证据与边界

`server/tests/test_migration_safety.py` 在 Python 3.11 的独立合成库验证空库升级、ORM 结构一致性、`0007→0008→0007→0008` 的 MVP 数据保留，以及 WAL 备份/恢复、拒绝覆盖和 manifest 校验。它不证明不存在的 v0.2 migration 可回退；未来每个新增 revision 都需补同等级测试，且对真实数据的可逆性另行评估。

补充的 [BE2-10-04 备份与恢复测试](BE2_10_04_BACKUP_RESTORE.md)在 `server/tests/test_backup_restore.py` 中实测未 checkpoint 的 WAL 数据、损坏/错误路径拒绝，以及**有值的** `0008` 发票来源字段在 downgrade 后丢失、通过升级前快照恢复。该结果证明此迁移在有来源数据时不能无损 downgrade，不能替代真实环境的备份、审批和副本演练。

## 第二轮工作区默认库事件

2026-11-07 的一次迁移验证命令路径转换报错，`DATABASE_URL` 未成功赋值；PowerShell 继续执行，Alembic 将工作区默认 `server/ledgercrew.db` 从 `0004_statement_imports` 升级到 `0016_workflow_provenance`。这是超出计划的写入，不应被描述为隔离库验证。发现后只读检查：所有业务表及 Worker 表行数均为 0，`PRAGMA integrity_check=ok`，`PRAGMA foreign_key_check` 无结果。没有对该库执行降级、覆盖或删除，也没有据此声称生产库已安全迁移。随后在明确指定的新 `.pytest_tmp/workflow-migration-*.db` 上重新完成从空库升级至 `0016` 和 `alembic check`。默认库需由负责人确认保留现状或经备份/演练后恢复目标版本；在此之前不要把它作为生产数据源。
