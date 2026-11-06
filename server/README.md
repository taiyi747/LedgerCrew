# LedgerCrew 后端（第一阶段）

当前提供 FastAPI 骨架、SQLite 异步连接、SQLAlchemy 2 模型、Alembic 初始迁移和基础测试。尚未提供下单、上传、Agent 调用或业务流程接口。

## 环境与安装

后端与 AI 模块统一使用 Python 3.14。在 `server/` 目录执行：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

默认 `DATABASE_URL=sqlite+aiosqlite:///./ledgercrew.db`，数据库文件位置相对于运行命令的当前目录。配置由环境变量或 `.env` 提供；环境变量优先。生产部署需单独配置认证和安全策略，当前阶段仅开放健康检查。

需要同时安装开发工具时，可在仓库根目录执行 `uv sync --project server --frozen --extra dev`。后端配置与 MiMo 配置共用 `.env`，请保留已有密钥。AI 独立演示及后端依赖协议见 [AI 接入说明](../docs/AI_INTEGRATION.md)。

## 数据库迁移

首次启动前执行：

```powershell
alembic upgrade head
```

查看迁移版本：`alembic current`。模型变化应新增 migration，不在应用启动时自动建表。

## 启动

```powershell
uvicorn app.main:app --reload
```

访问 `http://127.0.0.1:8000/health`，预期返回 `{"status":"ok"}`。OpenAPI 位于 `/openapi.json`，后续业务 API 统一挂载在 `/api/v1`。

## 测试

```powershell
pytest
```

测试使用临时 SQLite 数据库，并实际运行 `alembic upgrade head`。不需要连接开发数据库。

## 当前模型约定

- 主键使用 UUID 字符串；事件与审计日志使用递增整数，便于后续事件续传。
- 时间写入 UTC，ORM 读取为带 UTC 时区的 `datetime`。
- 金额以整数分存储；当前仅有订单价格字段。
- 原始文件只登记元数据和不对外暴露的存储键；文件存储及安全校验在后续阶段实现。
- Agent 原始输入输出和事件扩展载荷使用 JSON；身份、状态、关联、时间等使用独立列。

待确认：客户与工作室的身份关联字段、一个账期是否允许多个订单、订单价格具体策略，以及 AgentRun 与 AgentTask 的最终接入语义。当前模型不对这些未确定的业务关系设置推断性的唯一约束。
