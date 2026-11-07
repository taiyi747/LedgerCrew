# LedgerCrew 后端（v0.1 阶段 7 交付检查）

当前提供工作室、模拟订单、文件上传、安全 ZIP 解压、资金流水 CSV 导入、确定性票据对账、Agent 集成契约、异常处理、报告审批与交付，并新增本地生产账号、Sandbox 支付、客户反馈、Agent 结果审核和有上限的任务重试/超时恢复。后端任务通过既有 MiMoRunner 执行单任务或完整 MAF 工作流；Worker 有持久身份、心跳、租约和异常回收。真实外部 MiMo 服务尚无凭证验证，`/health/ready` 因此返回 503。

## 项目结构

`app/api/v1` 提供 HTTP 路由，`app/services` 处理业务规则，`app/repositories` 访问数据，`app/models` 与 `app/schemas` 分别定义数据库和 API/Agent 数据结构，`app/integrations/agents` 定义后端网关与 Fake，`app/agents` 放置独立 MiMo 工作流，`app/storage` 隔离本地文件存储，`alembic/versions` 保存迁移，`tests` 包含单元、接口和端到端测试。详细边界见 [架构说明](docs/architecture.md)。

## 环境与安装

后端固定使用 Python 3.11。Agent 依赖须先在 3.11 验证；如不兼容，应隔离而非升级后端。在 `server/` 目录执行：

已有其他 Python 版本的 `.venv` 时，不要覆盖它；先创建独立的 3.11 环境并验证版本。

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

默认 `DATABASE_URL=sqlite+aiosqlite:///./ledgercrew.db`，数据库文件位置相对于运行命令的当前目录。配置由环境变量或 `.env` 提供；环境变量优先。原始文件保存在 `STORAGE_ROOT` 下，API 不返回实际存储键或路径。

需要同时安装开发工具时，可在仓库根目录执行 `uv sync --project server --frozen --extra dev`。后端配置与 MiMo 配置共用 `.env`，请保留已有密钥。AI 独立演示及后端依赖协议见 [AI 接入说明](../docs/AI_INTEGRATION.md)。

## 数据库迁移

首次启动或更新代码后执行：

```powershell
alembic upgrade head
```

查看迁移版本：`alembic current`。模型变化应新增 migration，不在应用启动时自动建表。

## 启动

```powershell
uvicorn app.main:app --reload
```

访问 `http://127.0.0.1:8000/health/live`，进程存活时返回 `{"status":"ok"}`；`/health/ready` 会检查数据库迁移和任务队列，并如实报告 Worker 心跳/外部 AI 尚未联调（503）。OpenAPI 位于 `/openapi.json`，业务 API 挂载在 `/api/v1`，完整清单见 [API 说明](../docs/API.md)。

## 开发身份与 API

开发和测试环境可使用 `X-User-Id` 模拟身份，或开发令牌。`DEV_OWNER_USER_IDS`（默认 `["owner"]`）指定模拟老板。**生产环境仅接受本地用户名/密码签发的服务端 Cookie 会话，忽略 `X-User-Id` 和 Authorization；修改请求需 `X-CSRF-Token`。** 客户通过显式 Studio 成员关系访问数据，无权限对象返回 404。账号开通：先 `alembic upgrade head`，再在 `server/` 执行 `python scripts/create_user.py <username> [--role owner|customer] [--studio-id <现有Studio>]`；密码从终端安全提示输入，不能写进命令行或配置文件。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST / GET | `/api/v1/studios` | 创建、列出自己的工作室 |
| GET | `/api/v1/studios/{studio_id}` | 工作室详情 |
| POST / GET | `/api/v1/orders` | 创建、列出自己的模拟订单 |
| GET | `/api/v1/orders/{order_id}` | 订单详情 |
| POST / GET | `/api/v1/orders/{order_id}/files` | 上传一个或多个文件、列出订单文件 |
| POST | `/api/v1/orders/{order_id}/archives` | 上传并解压 ZIP |
| GET | `/api/v1/files/{file_id}` | 文件元数据 |
| GET | `/api/v1/files/{file_id}/download` | 有权限的原始文件下载 |
| POST | `/api/v1/orders/{order_id}/imports/csv` | 以已上传 CSV 文件 ID 导入流水 |
| GET | `/api/v1/orders/{order_id}/transactions` | 查询标准化交易 |
| GET | `/api/v1/orders/{order_id}/imports` | 查询导入记录及行错误 |
| GET | `/api/v1/imports/{import_id}` | 查询单次导入结果 |
| POST | `/api/v1/orders/{order_id}/reconciliation/run` | 运行确定性对账并创建新批次 |
| GET | `/api/v1/orders/{order_id}/reconciliation` | 查询最新对账批次和收支汇总 |
| GET | `/api/v1/orders/{order_id}/matches` | 查询最新批次的唯一匹配 |
| GET | `/api/v1/orders/{order_id}/exceptions` | 查询最新批次的异常工单 |
| GET | `/api/v1/orders/{order_id}/events/stream` | 订单事件 SSE；支持 `Last-Event-ID` 或 `after_id` 续读 |
| GET | `/api/v1/exceptions/{exception_id}` | 查询异常工单与处理状态 |
| POST / GET | `/api/v1/exceptions/{exception_id}/supplements` | 客户提交文字或证据图片、查询补充历史 |
| POST | `/api/v1/exceptions/{exception_id}/decisions` | 老板处理异常 |
| GET | `/api/v1/orders/{order_id}/reports` | 查询可访问的报告版本 |
| GET | `/api/v1/reports/{report_id}` | 查询报告 JSON |
| GET | `/api/v1/reports/{report_id}/download` | 下载可打印 HTML |
| POST | `/api/v1/reports/{report_id}/submit-review`、`approve`、`reject`、`publish` | 老板审核与发布 |
| GET | `/api/v1/orders/{order_id}/exports/{export_type}.csv` | 发票、流水、匹配、异常 CSV |

创建工作室 JSON：`{"name":"示例工作室","business_type":"digital_services"}`。创建订单 JSON：`{"studio_id":"<工作室 ID>","period_start":"2026-10-01","period_end":"2026-10-31","service_scope":"monthly_records"}`。订单编号、`draft` 状态和 `is_simulated=true` 由服务端设置，客户端不能传状态。价格尚未确定，`price_cents` 在本阶段不由 API 填写。

上传使用 multipart：`file_category` 为 `invoice_image`、`bank_statement_csv` 或 `supporting_material`。普通上传字段名为 `files`，单文件也用该字段；ZIP 上传字段名为 `file`，并用 `file_category` 指定解压条目的类别。允许 JPG/JPEG、PNG 图片与 CSV；ZIP 条目不支持的格式会单独登记为 `unsupported`。图片用 Pillow 验证真实格式，CSV 做 UTF-8 文本和基本表格检查。文件结果有 `valid`、`invalid`、`unsupported` 状态；原始文件不会被覆盖。

ZIP 原包始终登记保存。坏包、路径穿越、绝对路径、符号链接、嵌套 ZIP 或超限会使原包标记为 `invalid` 并返回错误。仅允许根目录或一层文件夹中的文件；条目原始路径仅用于审计记录，实际存储键由后端生成。

CSV 默认字段、列名映射、金额规则、导入步骤和模板见 [CSV 格式说明](docs/csv-format.md)。

票据写入契约、确定性匹配与异常规则、收支汇总口径见 [对账说明](docs/RECONCILIATION.md)。后端与真实票据识别 Agent 尚未联调；可信编排器需先保存 `material_review` 的 `ACCEPTED` 结果，再创建 `invoice_extraction` 任务，最后调用 `persist_invoice_from_task`。发票记录保留审核任务与识别任务 ID。对账只匹配两个方向均唯一的候选；每次运行保留一个新批次，查询接口返回最新批次。

五个 Agent 角色的 Pydantic 契约、`AgentGateway` 接入方法、任务状态、Fake 与 SSE 用法见 [Agent 接入说明](docs/agent-integration.md)。`MiMoAgentGateway` 和 `FullWorkflowGateway` 共用现有 MiMoRunner；预算、用量状态和非内容元数据持久化至 `agent_model_artifacts`。在 `server/` 下使用 `uv run --project . python -m scripts.run_agent_tasks --once` 执行一个队列任务；持续运行去掉 `--once`。SQLite 默认单 Worker 部署，多进程竞争仅在隔离测试验证。`FakeAgentGateway` 只供开发测试，生产调用会报错。完整工作流可通过认证 API 创建，见 [API](../docs/API.md)。

客户补充、老板决定、报告版本、审批、HTML 与 CSV 导出口径见 [交付说明](docs/DELIVERY.md)。报告草稿由已校验的 `report_draft` 任务输出创建，财务数字仍取自确定性对账批次；客户只能在发布后查看。

下列限制是 **MVP 初始配置**，可通过 `.env` 调整：

| 设置 | 默认值 |
| --- | ---: |
| `MAX_UPLOAD_FILES` | 每次普通上传 20 个 |
| `MAX_UPLOAD_REQUEST_BYTES` | 每次普通上传累计 50 MiB |
| `MAX_IMAGE_BYTES` | 5 MiB |
| `MAX_CSV_BYTES` | 2 MiB |
| `MAX_ARCHIVE_BYTES` | 25 MiB |
| `MAX_ARCHIVE_FILES` | 30 个文件 |
| `MAX_ARCHIVE_ENTRY_BYTES` | 5 MiB |
| `MAX_ARCHIVE_TOTAL_BYTES` | 50 MiB |
| `MAX_ARCHIVE_RATIO` | 100:1 |
| `MAX_ORDER_ARCHIVE_BYTES` | 每订单 ZIP 原包累计 100 MiB |
| `MAX_ORDER_EXTRACTED_BYTES` | 每订单 ZIP 解压文件累计 200 MiB |
| `CSV_MAX_ROWS` | 200 行 |
| `SSE_POLL_SECONDS` | 1 秒 |
| `SSE_HEARTBEAT_SECONDS` | 15 秒 |
| `API_RATE_LIMIT_REQUESTS` / `API_RATE_LIMIT_WINDOW_SECONDS` | 单进程同一客户端地址 1000 次 / 60 秒 |
| `SSE_MAX_CONNECTIONS` | 单进程同时 20 条 SSE |

认证和 Sandbox 支付配置：`AUTH_SESSION_TTL_SECONDS`、`AUTH_MAX_FAILED_ATTEMPTS`、`AUTH_LOCK_SECONDS`、`SERVICE_PRICES_CENTS`（JSON 字典，无默认价格）、`SERVICE_CURRENCY`（无默认币种）、`PAYMENT_SANDBOX_WEBHOOK_SECRET`（至少 32 字符）。Worker 配置：`WORKER_MAX_ATTEMPTS`、`WORKER_TIMEOUT_SECONDS`、`WORKER_LEASE_SECONDS`、`WORKER_HEARTBEAT_SECONDS`。缺少价格/币种时支付意图拒绝创建；缺少回调密钥时回调返回 503。所有订单仍标记 `is_simulated=true`。

## 测试

```powershell
pytest
```

测试必须在 Python 3.11 执行，使用临时 SQLite 数据库，并实际运行 `alembic upgrade head`；也测试从第一阶段数据升级。不需要连接开发数据库。阶段 7 端到端测试以 Fake Agent 走通客户创建到报告发布及 CSV 下载，并检查材料审核门禁、权限、原始数据、事务回滚与外键。

## 当前模型约定

- 主键使用 UUID 字符串；事件与审计日志使用递增整数，便于后续事件续传。
- 时间写入 UTC，ORM 读取为带 UTC 时区的 `datetime`。
- 金额以整数分存储；CSV 流水、票据、匹配差异、异常和收支汇总均不使用浮点数。
- 原始文件存储在本地，元数据记录 SHA256、类别、校验状态和 ZIP 来源；存储键不对外暴露。
- Agent 原始输入输出和事件扩展载荷使用 JSON；身份、状态、关联、时间等使用独立列。
- Agent 任务有订单内唯一幂等键；运行和任务状态分别持久化，并保留 JSON 检查点、事件与审计记录。

## 尚未完成与待确认

- 完整 MAF 工作流、Worker 心跳/租约已由隔离数据库测试覆盖；真实 MiMo 模型联调、跨存储恢复和多进程压力验收尚未完成。Fake 只用于本地和测试。
- 第二阶段后端 Python 已锁定为 3.11；新业务仅按仓库根目录 `AGENTS.md` 和 `docs/P2_DECISIONS.md` 中 confirmed 的决策实施。MVP 模拟身份规则继续有效，不能自动作为 P2 审批或发布规则。
- 生产本地认证代码已接入但尚未完成真实部署验证；支付仅为 Sandbox，不会真实扣款或退款。PDF、外部通知与电子签署未实现；真实 Agent Gateway 和常驻 Worker 仍需生产环境联调。
- 同一账期是否允许多个订单、订单价格策略、跨批次异常处理结果沿用、客户可见的事件文案与保留周期需确认。
- 第一阶段旧工作室没有所有者，迁移不猜测归属；需要后续管理流程明确归属后客户才能访问。
