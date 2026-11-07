# 真实环境联调边界（2026-11-07）

> 以下“已有代码和已验证范围”是第一轮历史记录；第二轮现状与联调入口见文末。

## 已有代码和已验证范围

- 独立 `server/app/agents/` 使用 Microsoft Agent Framework 和 MiMo 的真实调用代码，具有超时、有限重试、模型/耗时/Token 用量记录及合成样例测试。后端 `MiMoAgentGateway` 已接到该 MiMoRunner，并在测试中通过本地模拟 HTTP 响应验证单任务调用及预算持久化。`scripts/run_agent_tasks.py` 可顺序执行队列，但没有完成真实服务联调、持久心跳或完整多 Agent 工作流接入；任务入队和 `rerun` 本身不表示模型已经执行。
- `server/app/services/payment_service.py` 仅实现 `PaymentProvider` 接口和 Sandbox。HMAC 回调、幂等、取消、失败、部分/全额退款都是本地模拟状态，未扣款、未退款，也未与真实结算账单核对。
- 生产本地认证代码在隔离 SQLite 测试库经过登录、会话、过期、CSRF、角色和跨租户测试；未做公网反向代理、浏览器和多实例部署验证。

## 人工配置和联调入口

1. 先在**数据库副本**执行 `alembic upgrade head`、`alembic check`、备份恢复与回归。正式数据库操作需按 [部署说明](DEPLOYMENT.md) 审批。生产 HTTPS 配置完成后设置 `ENVIRONMENT=production`、`DATABASE_URL`、`STORAGE_ROOT`，运行 `python scripts/create_user.py <username> --role owner` 开通首个管理员。
2. 只有确认价格和币种后才设置 `SERVICE_PRICES_CENTS`、`SERVICE_CURRENCY`；Sandbox 回调密钥 `PAYMENT_SANDBOX_WEBHOOK_SECRET` 至少 32 字符，存入密钥管理。未指定真实支付供应商时不得设置“真实支付已启用”标识。
3. 真实 MiMo 验证需 `MIMO_API_KEY`、`MIMO_BASE_URL`、`MIMO_MODEL_PRO`、`MIMO_MODEL_FLASH`，显式运行 `server/scripts/verify_live.py --simulate-human-review` 的合成样例；这只验证独立完整工作流。后端单任务可用 `python scripts/run_agent_tasks.py --once` 在隔离测试数据库中执行。真实服务与 Worker 端到端联调仍未完成，不能解除 readiness 阻断。
4. `python scripts/recover_tasks.py --retry` 扫描超时任务并入队有限重试；运行 `python scripts/run_agent_tasks.py` 可单进程顺序消费。SQLite 下不得部署多个执行进程；没有持久心跳或跨进程租约。恢复日志、`agent_task_history` 和 `agent_model_artifacts` 应人工检查。

## 尚未通过的真实环境验收

真实客户数据隔离与浏览器 Cookie/CSRF、反向代理 HTTPS、真实模型供应商调用成本和错误处理、后端完整工作流、Worker 多进程租约与吞吐、支付供应商签名与退款、真实结算对账、SQLite 压力与备份恢复演练，均未在本轮代码测试中获得生产验证。`/health/ready` 持续 503 是预期状态。

## 第二轮：真实 MiMo 后端联调入口

后端 MiMo 调用适配、模型预算原子预留/幂等结算、完整 MAF 业务工作流、Worker 心跳与租约已由隔离数据库测试覆盖；真实供应商请求**尚未运行**，当前环境没有 `MIMO_API_KEY`。测试 Gateway 的成功不能作为真实服务证明。支付仍限 Sandbox。

在独立测试环境安装 Python 3.11 和项目依赖，设置真实 `MIMO_API_KEY`、`MIMO_BASE_URL`、`MIMO_MODEL_PRO`、`MIMO_MODEL_FLASH`，并确认出站网络与账单预算。由 `server/` 执行：

```powershell
$env:LEDGERCREW_ENABLE_LIVE_MIMO = '1'
uv run --project . python -m scripts.verify_backend_mimo --run-live
```

入口同时要求开关和 `--run-live`，缺密钥或占位密钥会拒绝运行。它创建 `server/data/live-backend/` 下独立的合成 SQLite 数据库，运行迁移、建立合成订单和真实后端任务，经 Worker 调用 MiMo，并校验任务成功、预算计数和模型结算工件。输出仅含任务 ID、状态、模型、耗时、请求数、用量是否已知、HTTP 状态和测试库路径；不得上传客户内容或密钥。请保存脱敏输出、外部账单/响应状态及数据库工件供验收，不要把测试库或凭证提交仓库。该入口只测单任务真实链路；完整工作流真实模型与人工审核仍须在受控环境另行验收。

Worker 常驻入口为 `uv run --project . python -m scripts.run_agent_tasks`，单次为 `--once`；先在数据库副本完成 `0015`、`0016` 迁移。`/health/ready` 把有密钥但未验证外部服务标记为 `configured_unverified` 并保持 503。生产启用前还需长期 Worker 心跳、检查点目录与业务文件的同步备份、HTTPS/认证和异常恢复演练。原文中“无租约/完整工作流”描述已被第二轮代码取代，但并不表示生产真实服务验收完成。

## 第三阶段任务一：真实 Gateway 探测结果（2026-11-07）

**状态：代码完成、真实联调未完成（缺 `MIMO_API_KEY`）。** 完整证据与 12 项交付见 [真实 MiMo Gateway 联调报告](MIMO_GATEWAY_ACCEPTANCE_2026-11-07.md)。

已用真实服务完成的**非计费**验证（共 4 个 HTTP 请求，均被 401 拒绝）：

- 连通性与 TLS：`GET https://api.xiaomimimo.com/v1/models`（`verify=True` 强证书校验）两次均通（562ms/531ms），服务端 `MiFE/3.4.34`，无凭证返回 `401 {"error":{code,message,param,type}}`。
- 失败路径（真实全链路）：新增受双开关（`LEDGERCREW_ENABLE_LIVE_MIMO=1` + `--run-live`）保护的 `python -m scripts.probe_live_gateway --run-live`，经 `run_once`（Worker 认领/租约）→ `MiMoAgentGateway` → `MiMoRunner` → 真实 HTTP 发出请求，使用哨兵无效凭证验证 401 被分类为任务 `failed`（不伪装成功）、预算预留与结算真实落库（`usage_status=unknown`，不虚构 Token）。探测使用独立新库 `server/data/live-failure-probe/`，**不触碰 `server/ledgercrew.db`**。
- 健康检查（隔离 0016 库实测）：`/health/live` 200；`/health/ready` 503（`database ok`、`worker unavailable`、`external_ai unconfigured`），未放宽任何就绪条件。

凭证缺失清单：真实 `MIMO_API_KEY`（经 `server/.env` 或密钥管理提供，勿粘贴到聊天）、模型调用权限确认、账单预算确认。凭证就位后按上文 `verify_backend_mimo` 与 `verify_live.py` 顺序执行成功链路联调，并补 HTTP 200/请求 ID/真实 Token 用量/结算与账单核对证据。

模型选择补充（同日）：指定模型为 `server/.env.example` 的 `MIMO_MODEL_PRO=mimo-v2.6-pro`，经 `risk_analysis → delivery` 角色路由验证**实际请求体 `model=mimo-v2.6-pro`**（持久化 `wire_request` 工件比对，`model_matches_config=true`），确认模型标识由配置驱动而非默认值或 Mock。**安全发现**：`server/.env.example` 的 `MIMO_API_KEY` 条目是用户有意修改写入的真实凭证（HEAD 原为占位值）。探测阶段未使用；经用户确认后作为本轮真实联调凭证经环境变量注入使用（不回显、不入文档）。该值位于 Git 跟踪文件，建议迁移至 `server/.env`（gitignore）或密钥管理并轮换。

## 真实联调完成记录（2026-11-07 晚，凭证就位后）

用户确认 `server/.env.example` 中的密钥为有意提供的真实凭证后，成功链路真实联调**已完成**（A–J 全部满足，详见 [联调报告](MIMO_GATEWAY_ACCEPTANCE_2026-11-07.md)）：

- `verify_backend_mimo --run-live`：单任务真实成功（`mimo-v2.6-flash`，HTTP 200，11.47s，Token 297/331/628，预算预留/结算齐全，任务 succeeded）。
- `probe_live_gateway --run-live --task-type risk_analysis`（真实凭证模式）：指定模型 `mimo-v2.6-pro` 真实成功（HTTP 200，8.75s，Token 375/348/723，`model_matches_config=true`，输出过 Pydantic Schema 校验）。
- `verify_live.py --simulate-human-review`：完整 MAF 五节点工作流真实模型 14 次调用全部 200，检查点暂停/恢复、人工审核（显式模拟）、报告 v1 交付；**重复审批重放零新增模型请求**。
- 累计 23 次真实 HTTP：16 次计费模型调用（全 200）+ 7 次非计费探测（无凭证 401）。零虚构 Token（成功 `known` 为供应商原值，失败显式 `unknown`）。
- 遗留：供应商账单核对、Readiness 真实服务证明（当前仍 503 `configured_unverified`）、常驻 Worker/故障演练、凭证迁移 `server/.env` 并轮换。
