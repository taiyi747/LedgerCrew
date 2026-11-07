# 后端部署与启用边界

状态：**代码已有本地认证、Sandbox 支付、完整 MAF 后端工作流及 Worker 心跳/租约，但仍不能接入真实客户。** 真实 MiMo 服务缺凭证未联调，`/health/ready` 返回 503；正式支付商、结算对账、申报领域与政策/表单/资料包均未上线。参考 [生产升级报告](PRODUCTION_UPGRADE_REPORT_2026-11-07.md)与 [当前 API](API.md)。

**红线：未经开发者（负责人）批准，不允许对任何生产数据库执行迁移、写入、恢复或其他操作。** 本文所有涉及真实数据库的步骤都必须先在副本上演练并取得书面批准。

代码 head 现为 `0016_workflow_provenance`。第二轮验证命令曾误将工作区默认 `server/ledgercrew.db` 从 `0004` 升到 `0016`；只读核查显示所有业务表为空、完整性正常，尚未回退。详情见 [数据库迁移手册](DATABASE_MIGRATION.md)。不要把该默认库直接作为生产数据源；对任何既有库先只读检查、备份并在副本演练。

本文 12 项上线要点的分布：本文覆盖 1–7、12；[回退手册](ROLLBACK.md) 覆盖 8–11（数据库恢复、应用回滚、版本兼容性、故障处理）。

## 1. Python 3.11 环境要求

- `server/` 后端固定 Python **3.11**（DEC-001，`requires-python = ">=3.11,<3.12"`，Ruff `target-version = "py311"`，`server/uv.lock` 限定 `==3.11.*`）。不得用 3.12+ 专属语法或运行时 API；测试只在 3.11 执行，其他版本的运行结果不作为验收依据。
- 部署前确认解释器版本：`python --version` 必须输出 `3.11.x`。实测环境为 Python 3.11.18（`server/.venv/py311-env`）。注意工作区根 `server/.venv` 顶层解释器可能是 3.12，**不能**用于安装、运行或测试 `server/`。
- AI Agent 相关依赖同样须在 3.11 可安装、可运行；不能满足时隔离到独立服务，不得提升 `server/` 的 Python 版本。

## 2. 依赖安装

1. 在 `server/` 下以 Python 3.11 创建/使用虚拟环境。
2. 按 `server/README.md` 用 `uv` 安装 `server/uv.lock` 锁定的依赖（`uv sync`），或以等价方式严格按锁文件安装；不得静默升级 FastAPI、SQLAlchemy、Alembic、Pydantic 等主版本。
3. 测试依赖来自 `pyproject.toml` 的 `test`/`dev` extra（pytest、pytest-asyncio、ruff）。
4. 安装后自检：`python -c "import app.main"`、`python -m pytest --version`；核心依赖实测版本见 [BE2-10 测试报告](BE2_10_TEST_REPORT.md)。

## 3. 环境变量配置

- 以 `server/.env.example` 为模板生成 `server/.env`；`.env`、数据库文件、`STORAGE_ROOT` 内容和任何密钥**不得提交**仓库（`.gitignore` 已排除）。
- 关键变量：`ENVIRONMENT`（`development|test|production`）、`DATABASE_URL`、`STORAGE_ROOT`、上传/ZIP 安全上限（含 `MAX_UPLOAD_REQUEST_BYTES`、`MAX_ORDER_ARCHIVE_BYTES`、`MAX_ORDER_EXTRACTED_BYTES`）、`CSV_COLUMN_MAP`、SSE 参数与单进程容量限制（`SSE_MAX_CONNECTIONS`、`API_RATE_LIMIT_REQUESTS`、`API_RATE_LIMIT_WINDOW_SECONDS`）、`MIMO_API_KEY`。本地认证配置为 `AUTH_SESSION_TTL_SECONDS`、`AUTH_MAX_FAILED_ATTEMPTS`、`AUTH_LOCK_SECONDS`；任务恢复为 `WORKER_MAX_ATTEMPTS`、`WORKER_TIMEOUT_SECONDS`。收费仅在显式配置 `SERVICE_PRICES_CENTS` JSON 与 `SERVICE_CURRENCY` 时生效；Sandbox 回调需 `PAYMENT_SANDBOX_WEBHOOK_SECRET`（至少 32 字符）。
- `MIMO_API_KEY` 等密钥只放在部署环境的密钥管理或本地 `.env` 中，`SecretStr` 仅在内存中使用；日志不输出凭据、税号、文件内容等敏感值（当前后端仅在未处理异常时记录 `logger.exception`）。
- **生产必须设置 `ENVIRONMENT=production` 并使用 HTTPS**：受保护接口只接受服务端 Cookie 会话，修改请求需 CSRF 头；开发模拟身份（`X-User-Id`）与 `FakeAgentGateway` 均不可用于生产。数据库升级后，用 `python scripts/create_user.py <username> --role owner` 显式开通首个管理员；后续客户可用 `--studio-id` 授权现有 Studio。密码通过终端提示输入。
- 生产数据库建议使用独立 SQLite 文件（或将后端迁至独立数据库实例）与独立 `STORAGE_ROOT`，两者均纳入备份范围。

## 4. 数据库备份

1. 停写或在维护窗口内，用 `python scripts/sqlite_snapshot.py backup <库路径> <备份目录>` 生成快照。工具使用 SQLite backup API，在 WAL 模式下取得一致快照，并生成 `.manifest.json`（UTC 时间、Alembic revision、SHA256）。
2. 核验 manifest 与数据库完整性（`integrity_check`、`foreign_key_check`），备份 `STORAGE_ROOT` 同一时间点副本，异地保存。
3. 备份必须在任何 `alembic upgrade`/`downgrade` **之前**完成并验证可用；`alembic downgrade` 不是用户数据备份。

## 5. Alembic 升级

1. 确认应用提交与目标 revision（当前 head：`0016_workflow_provenance`，`0001`～`0016` 单 head 线性链；`0015` 加 Worker 租约，`0016` 加工作流来源，不等于第二阶段申报功能）。
2. **先在数据库副本**上执行 `alembic upgrade head`，核对表/列/索引/唯一约束与 SQLAlchemy metadata 一致，并跑 MVP API 回归（[数据库迁移手册](DATABASE_MIGRATION.md)、[迁移测试](BE2_10_02_MIGRATION_TEST.md)、[历史升级测试](BE2_10_03_MVP_UPGRADE_TEST.md)）。
3. 取得负责人对真实目标库的操作批准后，才在维护窗口对已批准目标执行迁移；迁移后验证 revision、`integrity_check`、`foreign_key_check`、旧数据行与文件存储。
4. 危险边界：`0008→0007` downgrade 在发票来源列有值时丢失来源关联；更早 downgrade 含删表。生产回退一律优先用升级前快照恢复（见 [ROLLBACK.md](ROLLBACK.md)）。

## 6. 后端启动

1. 迁移与备份核验完成后启动：`uvicorn app.main:app`（在 `server/` 下、Python 3.11 环境）。
2. 在隔离环境按 `server/README.md` 运行 `uv run --project . python -m scripts.run_agent_tasks`；SQLite 默认部署一个进程，多进程竞争只做过隔离测试。生产不得启用 `FakeAgentGateway`；真实 MiMo 联调入口见 [联调说明](LIVE_INTEGRATION.md)。
3. 启动后确认 `/health/live`、`/health/ready` 与 `/openapi.json`；第二轮新增 3 个工作流操作，无 P2 申报路径。`/health/ready` 在真实外部模型尚未验证时应为 503，不可绕过。

## 7. 健康检查

- `GET /health` 和 `/health/live`：仅进程存活。`GET /health/ready`：脱敏返回数据库迁移、队列计数、Worker/缓存/外部 AI 和业务服务状态；缺常驻 Worker 时返回 503。`GET /openapi.json`：核对部署路由。
- 健康检查不能替代登录、跨租户、支付、Worker 与真实 MiMo 端到端验收。生产环境须验证伪造 `X-User-Id` 被 401 拒绝、Cookie/CSRF 生效；未通过前不接入真实客户流量。

## 8–11. 数据库恢复、应用回滚、版本兼容性、故障处理

见 [ROLLBACK.md](ROLLBACK.md)：数据库恢复（`scripts/sqlite_snapshot.py restore`，拒绝覆盖并校验 manifest/完整性/revision）、应用回滚顺序、前后版本 schema 兼容性验证、故障处理与现场保留原则。

## 12. 新功能逐步启用方式

- 逐项完成 DEC-002～014 中受影响决策、BE2-01～09 的实现/迁移/测试/文档、政策和模板官方来源审核、权限及生产认证、跨租户与全链路测试、资料包发布与回退演练后，才可启用**已确认范围**的功能。
- 任何不支持组合、未审核规则/模板或未解决 blocker 均不得进入正式计算和交付；启用需按 Studio/范围灰度并可独立关闭，出现异常即回退到上一步。
- 当前没有此类功能开关或支持范围服务（`supported-scopes` 等 P2 接口未实现、未挂载），**不能宣称已具备逐步启用能力**；v0.2 启用的前提条件详见 [V2 验收清单](V2_ACCEPTANCE_CHECKLIST.md)。
