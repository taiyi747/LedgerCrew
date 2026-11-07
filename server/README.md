# LedgerCrew 后端（v0.1 开发阶段 6）

当前已接通客户页、老板作战室与 `app/live/` 的总管委派工作流。总管实际调用派单工具，专业 Agent 调用现有业务服务完成识别、对账和草稿；后台 Worker 持久化预算、租约及检查点。完整启动和新增接口见 [实时联调说明](../docs/LIVE_INTEGRATION.md)。`app/agents/` 的独立 CLI 保留。

## 环境与安装

后端与 AI 模块统一使用 Python 3.14。在 `server/` 目录执行：

```powershell
python -m venv .venv
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
uvicorn app.main:app --host 127.0.0.1 --port 8000
# 另一个终端同样在 server/ 启动：
python -m app.live.worker
```

访问 `http://127.0.0.1:8000/health`，预期返回 `{"status":"ok"}`。OpenAPI 位于 `/openapi.json`，业务 API 挂载在 `/api/v1`。

## 开发身份与 API

开发和测试环境的受保护接口必须传 `X-User-Id`，它只是可替换的模拟身份。`DEV_OWNER_USER_IDS`（默认 `["owner"]`）指定平台老板，其他身份为客户。工作室 `owner_user_id` 是客户归属 ID，由创建身份确定；无权限对象返回 404。客户只能读取自己订单的已发布报告。**生产环境禁用模拟身份，受保护接口返回 503，接入真实认证前不可用于生产。**

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

CSV 默认字段、列名映射、金额规则、导入步骤和模板见 [CSV 格式说明](docs/CSV.md)。

票据写入契约、确定性匹配与异常规则、收支汇总口径见 [对账说明](docs/RECONCILIATION.md)。本阶段没有票据识别或 Agent 实现；未来集成方通过 `InvoiceRecordCreate` 和 `persist_invoice` 服务写入已验证的票据字段。对账只匹配两个方向均唯一的候选；每次运行保留一个新批次，查询接口返回最新批次。

五个 Agent 角色的 Pydantic 契约、`AgentGateway` 接入方法、任务状态、Fake 与 SSE 用法见 [Agent 接入说明](docs/agent-integration.md)。`app/integrations/agents/` 提供后端集成边界，真实工作流实现与依赖协议见 [AI 模块接入说明](../docs/AI_INTEGRATION.md)。`FakeAgentGateway` 必须显式传入预设结果，仅供开发和测试，生产环境调用会报错。任务创建和调用是可信后端服务接口，不对客户开放 HTTP 写入入口。

客户补充、老板决定、报告版本、审批、HTML 与 CSV 导出口径见 [交付说明](docs/DELIVERY.md)。报告草稿由已校验的 `report_draft` 任务输出创建，财务数字仍取自确定性对账批次；客户只能在发布后查看。

下列限制是 **MVP 初始配置**，可通过 `.env` 调整：

| 设置 | 默认值 |
| --- | ---: |
| `MAX_UPLOAD_FILES` | 每次普通上传 20 个 |
| `MAX_IMAGE_BYTES` | 5 MiB |
| `MAX_CSV_BYTES` | 2 MiB |
| `MAX_ARCHIVE_BYTES` | 25 MiB |
| `MAX_ARCHIVE_FILES` | 30 个文件 |
| `MAX_ARCHIVE_ENTRY_BYTES` | 5 MiB |
| `MAX_ARCHIVE_TOTAL_BYTES` | 50 MiB |
| `MAX_ARCHIVE_RATIO` | 100:1 |
| `CSV_MAX_ROWS` | 200 行 |
| `SSE_POLL_SECONDS` | 1 秒 |
| `SSE_HEARTBEAT_SECONDS` | 15 秒 |

## 测试

```powershell
pytest
```

测试使用临时 SQLite 数据库，并实际运行 `alembic upgrade head`；也测试从第一阶段数据升级。不需要连接开发数据库。

## 当前模型约定

- 主键使用 UUID 字符串；事件与审计日志使用递增整数，便于后续事件续传。
- 时间写入 UTC，ORM 读取为带 UTC 时区的 `datetime`。
- 金额以整数分存储；CSV 流水、票据、匹配差异、异常和收支汇总均不使用浮点数。
- 原始文件存储在本地，元数据记录 SHA256、类别、校验状态和 ZIP 来源；存储键不对外暴露。
- Agent 原始输入输出和事件扩展载荷使用 JSON；身份、状态、关联、时间等使用独立列。
- Agent 任务有订单内唯一幂等键；运行和任务状态分别持久化，并保留 JSON 检查点、事件与审计记录。

待确认：同一账期是否允许多个订单、订单价格策略、真实认证方式，以及 AgentRun 与 AgentTask 的最终接入语义。第一阶段旧工作室没有所有者，迁移不猜测归属，因此这些旧记录须在未来的管理流程中明确归属后才能由客户访问。
