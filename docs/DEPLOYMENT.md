# 后端部署与启用边界

状态：**仅描述当前 MVP 的可验证启动流程；v0.2 不能部署启用。** 依据 [BE2-10 审查](BE2_10_AUDIT_REPORT.md)，申报领域与正式政策、表单、资料包均无运行实现。生产身份服务仍待 DEC-013，受保护接口在 `ENVIRONMENT=production` 下返回 503；因此当前后端也不能直接作为真实客户生产服务。

工作区现有 `server/ledgercrew.db` 经只读检查停在 `0004_statement_imports`，代码当前 head 为 `0008_invoice_provenance`。该库不能跳过备份、副本迁移与回归直接用于完整当前应用；本轮未对它执行迁移。

## 环境准备

在 `server/` 使用 Python 3.11，确认 `python --version`、`requires-python >=3.11,<3.12`、Ruff `py311` 与锁文件 `==3.11.*`。在受控环境按 `server/README.md` 安装锁定依赖，配置 `server/.env.example` 所列环境变量；`.env`、数据库与密钥不得提交。使用独立 SQLite 数据文件和独立 `STORAGE_ROOT`，两者均纳入备份。生产不得使用开发模拟身份、默认演示账号或 `FakeAgentGateway`。

## 当前 MVP 启动顺序

1. 确认应用提交和目标 Alembic revision。停写后按 [迁移手册](DATABASE_MIGRATION.md) 用 SQLite backup API 做快照并核验 manifest。
2. 在数据库副本验证 `alembic upgrade head`、`integrity_check`、`foreign_key_check` 和 MVP API 回归；取得负责人对真实目标库的操作批准。
3. 维护窗口中对已批准目标执行迁移，验证 revision、数据与文件存储，再启动 `uvicorn app.main:app` 和适用 Worker。`/health` 与 `/openapi.json` 仅是存活/契约检查，不能替代权限和端到端验收。
4. 若生产身份服务尚未确认并接入，保持受保护 API 的 503 门禁，不接入真实客户流量。

## v0.2 分阶段启用门槛

逐项完成 DEC-002～014 中受影响决策、BE2-01～09 的实现/迁移/测试/文档、政策和模板官方来源审核、权限及生产认证、跨租户与全链路测试、资料包发布与回退演练后，才可启用已确认的范围。任何不支持组合、未审核规则/模板或未解决 blocker 均不得进入正式计算和交付。当前没有此类功能开关或支持范围服务，不能宣称已具备逐步启用能力。
