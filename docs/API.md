# LedgerCrew 运行中 API（2026-11-07）

基址 `/api/v1`；当前 OpenAPI 实测 **49 条路径、57 个操作**，字段 Schema 以运行时 `/openapi.json` 为准。第一轮基线为 46 条路径、54 个操作，第二轮新增 3 个工作流操作。[第二阶段候选契约](../contracts/API.md) 的申报接口未挂载。原 MVP 接口及详细字段见 [后端 API 说明](../server/docs/api.md)。

## 身份、权限和错误

生产环境通过 `POST /auth/login` 使用用户名/密码登录；服务端设置 `lc_session`（HttpOnly、Secure、SameSite=Lax）和 `lc_csrf`（Secure、SameSite=Lax）。修改请求应带 `X-CSRF-Token`，值等于 `lc_csrf` Cookie。生产环境只认可服务端 Cookie，忽略 `X-User-Id` 和 Authorization。开发/测试环境保留旧模拟身份供回归，禁止用于生产。`owner` 为平台管理员；普通用户只能访问明确授权的 Studio 及其订单、文件、报告、支付和反馈。跨租户对象返回 404。

错误格式为 `{"error":{"code":"<code>","message":"<safe message>"}}`。通用状态：401 未登录或回调签名无效，403 角色/CSRF，404 不存在或无租户权限，409 状态/幂等冲突，413 容量超限，422 参数校验，429 API/SSE 容量限制，503 配置或依赖不可用。金额单位为整数分，时间为 UTC。

## 路由与请求/响应

表中 ID 均是路径参数；GET 列表返回数组，单资源返回对应对象。除登录、健康检查和签名回调外，均需登录；生产环境的 POST 还需 CSRF 头。

| 方法 | 路径（省略 `/api/v1`） | 参数/主体 → 返回 | 权限 |
| --- | --- | --- | --- |
| POST | `/auth/login` | `username` 或兼容 `email`、`password` → 用户；开发态另有凭据 | 公开 |
| GET, POST | `/auth/me`, `/auth/logout` | 当前用户；退出返回 `logged_out` | 登录 |
| POST, GET | `/studios` | POST `name`,`business_type` → Studio；GET 列表 | 登录/本租户 |
| GET | `/studios/{studio_id}` | Studio | 本租户 |
| POST, GET | `/orders` | POST `studio_id`,`period_start`,`period_end`,`service_scope` → Order；GET 列表 | 本租户 |
| GET | `/orders/{order_id}` | Order | 本租户 |
| POST, GET | `/orders/{order_id}/files` | POST multipart `file_category`,重复 `files` → FileBatch；GET 列表 | 本租户 |
| POST | `/orders/{order_id}/archives` | multipart `file_category`,`file` ZIP → Archive | 本租户 |
| GET | `/files/{file_id}`, `/files/{file_id}/download` | 元数据；原始二进制 | 本租户 |
| POST | `/orders/{order_id}/imports/csv` | JSON `file_id`、可选 `column_map` → Import | 本租户 |
| GET | `/orders/{order_id}/imports`, `/imports/{import_id}`, `/orders/{order_id}/transactions` | 导入列表/详情、流水列表 | 本租户 |
| POST, GET | `/orders/{order_id}/reconciliation/run`, `/orders/{order_id}/reconciliation` | 新批次；最新批次 | 本租户 |
| GET | `/orders/{order_id}/matches`, `/orders/{order_id}/exceptions` | 匹配、异常列表 | 本租户 |
| GET | `/orders/{order_id}/events/stream` | `after_id`/`follow` 或 `Last-Event-ID` → SSE | 本租户 |
| GET | `/exceptions/{exception_id}` | 异常详情 | 本租户 |
| POST, GET | `/exceptions/{exception_id}/supplements` | POST multipart `explanation`/图片 `file` → 补充/历史 | 本租户 |
| POST | `/exceptions/{exception_id}/decisions` | `decision`,`reason`,`target_version` 等 → 决定 | owner |
| GET | `/orders/{order_id}/reports`, `/reports/{report_id}`, `/reports/{report_id}/download` | 版本列表、报告 JSON、HTML | 本租户；客户仅已发布 |
| POST | `/reports/{report_id}/submit-review`, `/approve`, `/reject`, `/publish` | 驳回要求 `reason` → 报告版本 | owner |
| GET | `/orders/{order_id}/exports/{export_type}.csv` | `invoices`/`transactions`/`matches`/`exceptions` → CSV | 本租户；客户需已发布报告 |
| POST, GET | `/orders/{order_id}/payments` | POST `Idempotency-Key` → Sandbox PaymentIntent；GET 列表 | 本租户 |
| POST | `/payments/sandbox/webhook` | 原始 JSON、`X-Sandbox-Signature` HMAC-SHA256 → PaymentIntent | 签名；不需登录 |
| POST, GET | `/studios/{studio_id}/feedback` | POST `category`,`message`、可选 `order_id`/`run_id` → Feedback；GET 列表 | 本租户 |
| GET | `/feedback/{feedback_id}`, `/feedback/{feedback_id}/actions` | 反馈详情、处理历史 | 本租户 |
| POST | `/feedback/{feedback_id}/actions` | `action`,`note` → Feedback | owner |
| GET, POST | `/agent-tasks/{task_id}/reviews` | POST `decision`,`note`、纠错时 `revised_output` → 审核/历史 | owner |
| POST | `/agent-tasks/{task_id}/rerun` | `Idempotency-Key` → 新 queued 任务 | owner |
| GET | `/orders/{order_id}/agent-reviews/stats` | 确认/纠错/驳回计数、已审任务数 | owner |
| GET | `/agent-tasks/{task_id}`, `/agent-tasks/{task_id}/history` | 任务详情/状态历史 | owner |
| POST | `/agent-tasks/{task_id}/cancel`, `/agent-tasks/{task_id}/retry` | 更新后的任务 | owner |
| POST | `/orders/{order_id}/workflows` | `Idempotency-Key` → full_workflow 任务，状态 queued | 本租户 |
| GET | `/agent-tasks/{task_id}/workflow-review` | 当前暂停的结构化审核请求、关联报告 ID | owner 且本租户 |
| POST | `/agent-tasks/{task_id}/workflow-reply` | `action`,`comment`、可选 `report_version` → retrying 任务 | owner 且本租户 |
| GET | `/health`, `/health/live`, `/health/ready` | 存活；依赖状态与队列计数 | 公开 |

## 示例和业务错误

生产登录：`POST /api/v1/auth/login`，`{"username":"alice","password":"<password>"}` → `{"user":{"user_id":"<uuid>","username":"alice"}}`，原始会话凭据仅在 Cookie 中。后续修改请求带 `X-CSRF-Token: <lc_csrf cookie value>`。

创建订单：`POST /api/v1/orders`，`{"studio_id":"<uuid>","period_start":"2026-10-01","period_end":"2026-10-31","service_scope":"monthly_records"}` → 包含 `id`,`order_no`,`status:"draft"`,`is_simulated:true` 的既有 OrderRead。价格未配置时创建支付意图返回 409 `pricing_unconfigured`。

Sandbox 支付：`POST /api/v1/orders/<id>/payments`，头 `Idempotency-Key: checkout-001` → `{"id":"<uuid>","order_id":"<uuid>","provider":"sandbox","amount_cents":2599,"currency":"CNY","status":"pending","refunded_cents":0,"created_at":"2026-11-07T00:00:00Z"}`。示例金额没有代码默认值，必须显式设置 `SERVICE_PRICES_CENTS` 与 `SERVICE_CURRENCY`。回调体为 `{"event_id":"evt-1","intent_id":"<uuid>","event_type":"succeeded","amount_cents":2599}`；签名是配置密钥对**原始请求字节**的 HMAC-SHA256 十六进制值。重复事件幂等返回同一结果；不同内容复用事件 ID 返回 409 `payment_event_conflict`。部分退款使用 `event_type:"refunded"` 和本次退款金额。

反馈：`POST /api/v1/studios/<id>/feedback`，`{"category":"question","message":"请解释这笔订单","order_id":"<uuid>"}` → 状态 `open`。老板 `POST /api/v1/feedback/<id>/actions` 提交 `{"action":"resolved","note":"已解释"}`；跨租户关联返回 404。

Agent 纠错：`POST /api/v1/agent-tasks/<id>/reviews`，`{"decision":"corrected","note":"修正文字","revised_output":{...}}` → 含版本、原输出、修订输出、审核人和时间；不符合原任务输出 Schema 返回 422，已生成下游记录返回 409 `result_already_used`。`rerun` 只入队，不表示模型已执行。

工作流创建要求已就绪的月度订单、有效的票据图片和流水，服务端记录输入快照指纹；重复幂等键返回同一任务。Worker 先认领租约再执行既有 MAF 工作流，遇异常或报告交付审核时进入 paused。读取 `workflow-review` 返回 `request.kind`、`allowed_actions`、`evidence_refs` 和可选报告版本；回复示例 `{"action":"keep_flagged","comment":"保留异常"}` 或交付阶段 `{"action":"approve_delivery","report_version":1}`。动作必须在当前请求允许范围内。直接调用普通报告 `/approve`、`/reject` 审核工作流报告会返回 409 `workflow_reply_required`。任务历史和报告版本可通过原有查询路由追踪。客户补件后的新输入修订尚未实现。

当前仅有 Sandbox 支付，无真实扣款或结算对账；后端完整工作流和 Worker 租约已通过隔离数据库测试，真实 MiMo 服务缺凭证未联调，故 `/health/ready` 返回 503。`/health` 仅表示 API 进程存活。

第三阶段任务一（2026-11-07）：API 面未变化（仍 49 条路径、57 个操作）。新增受双开关保护的诊断入口 `python -m scripts.probe_live_gateway --run-live`（本地证据采集，不注册路由、不暴露密钥）。**真实 MiMo 联调已完成**：单任务（`mimo-v2.6-flash` 与指定模型 `mimo-v2.6-pro`）及完整工作流 14 次真实调用全部 HTTP 200，响应过 Schema 校验、Token 用量为供应商真实值、预算预留/结算落库、401 失败不伪装成功、重复重放零重复计费。`/health/ready` 维持 503（`external_ai: configured_unverified`），待 Readiness 真实服务证明后才可 200。详见 [真实 MiMo Gateway 联调报告](MIMO_GATEWAY_ACCEPTANCE_2026-11-07.md)。
