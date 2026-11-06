# LedgerCrew 后端（v0.1 开发阶段 3）

当前提供工作室、模拟订单、文件上传、安全 ZIP 解压和资金流水 CSV 导入。Agent 调用、交易对账和报告尚未实现。

## 环境与安装

使用 Python 3.11，在 `server/` 目录执行：

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
Copy-Item .env.example .env
```

默认 `DATABASE_URL=sqlite+aiosqlite:///./ledgercrew.db`，数据库文件位置相对于运行命令的当前目录。配置由环境变量或 `.env` 提供；环境变量优先。原始文件保存在 `STORAGE_ROOT` 下，API 不返回实际存储键或路径。

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

访问 `http://127.0.0.1:8000/health`，预期返回 `{"status":"ok"}`。OpenAPI 位于 `/openapi.json`，业务 API 挂载在 `/api/v1`。

## 开发身份与 API

开发和测试环境的受保护接口必须传 `X-User-Id`，它只是可替换的模拟身份。工作室 `owner_user_id` 由该身份确定，客户端不能指定其他所有者。订单和文件读取均检查工作室归属；无权限对象返回 404。**生产环境禁用这个模拟身份，受保护接口返回 503，接入真实认证前不可用于生产。**

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

创建工作室 JSON：`{"name":"示例工作室","business_type":"digital_services"}`。创建订单 JSON：`{"studio_id":"<工作室 ID>","period_start":"2026-10-01","period_end":"2026-10-31","service_scope":"monthly_records"}`。订单编号、`draft` 状态和 `is_simulated=true` 由服务端设置，客户端不能传状态。价格尚未确定，`price_cents` 在本阶段不由 API 填写。

上传使用 multipart：`file_category` 为 `invoice_image`、`bank_statement_csv` 或 `supporting_material`。普通上传字段名为 `files`，单文件也用该字段；ZIP 上传字段名为 `file`，并用 `file_category` 指定解压条目的类别。允许 JPG/JPEG、PNG 图片与 CSV；ZIP 条目不支持的格式会单独登记为 `unsupported`。图片用 Pillow 验证真实格式，CSV 做 UTF-8 文本和基本表格检查。文件结果有 `valid`、`invalid`、`unsupported` 状态；原始文件不会被覆盖。

ZIP 原包始终登记保存。坏包、路径穿越、绝对路径、符号链接、嵌套 ZIP 或超限会使原包标记为 `invalid` 并返回错误。仅允许根目录或一层文件夹中的文件；条目原始路径仅用于审计记录，实际存储键由后端生成。

CSV 默认字段、列名映射、金额规则、导入步骤和模板见 [CSV 格式说明](docs/CSV.md)。

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

## 测试

```powershell
pytest
```

测试使用临时 SQLite 数据库，并实际运行 `alembic upgrade head`；也测试从第一阶段数据升级。不需要连接开发数据库。

## 当前模型约定

- 主键使用 UUID 字符串；事件与审计日志使用递增整数，便于后续事件续传。
- 时间写入 UTC，ORM 读取为带 UTC 时区的 `datetime`。
- 金额以整数分存储；当前仅有订单价格字段。
- 原始文件存储在本地，元数据记录 SHA256、类别、校验状态和 ZIP 来源；存储键不对外暴露。
- Agent 原始输入输出和事件扩展载荷使用 JSON；身份、状态、关联、时间等使用独立列。

待确认：同一账期是否允许多个订单、订单价格策略、真实认证方式，以及 AgentRun 与 AgentTask 的最终接入语义。第一阶段旧工作室没有所有者，迁移不猜测归属，因此这些旧记录须在未来的管理流程中明确归属后才能由客户访问。
