# HTTP API 清单

业务接口统一前缀 `/api/v1`。`GET /health` 不要求身份，返回应用健康状态。运行应用后可在 `/docs` 查看交互式 OpenAPI，在 `/openapi.json` 获取精确 Schema。

开发和测试环境中，受保护接口须传 `X-User-Id`。默认 `owner` 是平台老板，其他 ID 是客户；客户对象按工作室所有者隔离，无权限对象通常返回 404。生产环境禁用该模拟身份，接入真实认证前受保护 API 返回 503。统一错误响应含 `error.code` 与 `error.message`。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST, GET | `/studios` | 创建、列出工作室 |
| GET | `/studios/{studio_id}` | 工作室详情 |
| POST, GET | `/orders` | 创建、列出模拟月度订单 |
| GET | `/orders/{order_id}` | 订单详情及服务端状态 |
| POST, GET | `/orders/{order_id}/files` | 上传一个或多个文件、列出文件 |
| POST | `/orders/{order_id}/archives` | 保存原始 ZIP 并安全解压 |
| GET | `/files/{file_id}` | 文件元数据 |
| GET | `/files/{file_id}/download` | 权限校验后的原始文件下载 |
| POST | `/orders/{order_id}/imports/csv` | 从已上传 CSV 文件导入流水 |
| GET | `/orders/{order_id}/imports` | 导入历史及行错误 |
| GET | `/imports/{import_id}` | 单次导入详情 |
| GET | `/orders/{order_id}/transactions` | 标准化流水 |
| POST | `/orders/{order_id}/reconciliation/run` | 执行确定性对账并创建批次 |
| GET | `/orders/{order_id}/reconciliation` | 最新对账批次与收支汇总 |
| GET | `/orders/{order_id}/matches` | 最新批次唯一匹配 |
| GET | `/orders/{order_id}/exceptions` | 最新批次异常工单 |
| GET | `/orders/{order_id}/events/stream` | SSE 订单事件；支持 `after_id` 或 `Last-Event-ID` |
| GET | `/exceptions/{exception_id}` | 异常详情与处理状态 |
| POST, GET | `/exceptions/{exception_id}/supplements` | 客户补充文字/图片及历史 |
| POST | `/exceptions/{exception_id}/decisions` | 老板异常决定 |
| GET | `/orders/{order_id}/reports` | 报告版本列表 |
| GET | `/reports/{report_id}` | 结构化报告 JSON |
| GET | `/reports/{report_id}/download` | 可打印 HTML |
| POST | `/reports/{report_id}/submit-review` | 提交老板审核 |
| POST | `/reports/{report_id}/approve` | 老板批准指定版本 |
| POST | `/reports/{report_id}/reject` | 老板退回审核 |
| POST | `/reports/{report_id}/publish` | 发布已批准版本 |
| GET | `/orders/{order_id}/exports/{export_type}.csv` | 下载 `invoices`、`transactions`、`matches`、`exceptions` 明细 |

创建工作室示例：`{"name":"示例工作室","business_type":"digital_services"}`。创建订单示例：`{"studio_id":"<工作室 ID>","period_start":"2026-10-01","period_end":"2026-10-31","service_scope":"monthly_records"}`。订单号、状态与模拟交易标记由后端管理，客户端不能任意改状态。

普通上传使用 multipart，字段 `files` 可重复，另传 `file_category=invoice_image|bank_statement_csv|supporting_material`。ZIP 上传用字段 `file`，同时传 `file_category` 指定条目类别。导入 CSV 用 JSON `{"file_id":"<文件 ID>"}`；可加 `column_map`。CSV 字段见 [格式文档](csv-format.md)。异常补充使用 multipart 的 `explanation`、`file`；老板决定使用 JSON，详见 [交付说明](DELIVERY.md)。

Agent 任务创建、调用和票据结果持久化目前是可信后端服务接口，**没有对客户开放 Agent 写入 HTTP 路由**；接入方法见 [Agent 接入说明](agent-integration.md)。客户只可读取自己订单已发布报告及导出；未发布版本不可见。
