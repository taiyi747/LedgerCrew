# LedgerCrew 实时联调与启动

本机 MVP 已接通 Next.js 客户端、sunset 老板控制台、FastAPI、独立 Worker 和真实 MiMo。原有 `docs/FRONTEND.md`、`BACKEND.md`、`AI.md` 及第二阶段计划继续保留。

## 启动

要求 Python **3.14**、Node.js **24+**。在仓库根目录：

```powershell
uv sync --project server --frozen --extra dev
cd server
# 只在不存在 .env 时复制，保留本地已有密钥。
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

第二个终端，在 `server/`：

```powershell
.venv\Scripts\python.exe -m app.live.worker
```

第三个终端，在 `web/`：

```powershell
npm ci
npm run dev
```

- 品牌首页：http://127.0.0.1:3210/
- 客户：http://127.0.0.1:3210/upload/
- 客户演示：http://127.0.0.1:3210/demo/
- 旧版页面：http://127.0.0.1:3210/workspace/
- 老板：http://127.0.0.1:3210/owner/
- 仪表盘：http://127.0.0.1:3210/owner/dashboard.html
- OpenAPI：http://127.0.0.1:8000/docs

三个进程均需运行。客户默认开发身份为 `local-customer`，老板为 `owner`，通过同源 fetch 的 `X-User-Id` 传递。仍是本机开发身份与模拟订单。客户与老板各开一个页面即可；本轮没有引入正式登录或税务申报。

`server/.env` 需要配置 `MIMO_API_KEY`、`MIMO_BASE_URL=https://api.xiaomimimo.com/v1`、`MIMO_MODEL_PRO=mimo-v2.6-pro`、`MIMO_MODEL_FLASH=mimo-v2.6-flash`。密钥缺失或调用失败时明确失败，不使用 Fake 回退。预算固定为每处理运行 64 次、每问答 6 次，包含 HTTP 重试，恢复和人工重试不清零。

## 操作

1. 客户建立工作室和账期，添加 JPG/PNG 与一份标准 CSV，发送。上传成功、CSV 实际导入后才建立处理运行。
2. 总管根据本轮实时数据库快照调用 `delegate_tasks`。专业 Agent 调用工具后返回回执，再由总管决策。
3. 老板打开作战室，选订单，点工位查看实际派单、执行和工具成果；总管工位展示业务决策摘要。
4. 异常与报告审批面板填写决定理由。可要求客户补充、保留未解决事项、确认处理或交给总管重新分析。
5. 客户在异常行提交说明或图片。新发票参与重新核对；说明凭证与文字保留为证据。文字解释不会修改原始金额或自动匹配。
6. 总管安排风险与交付 Agent 创建草稿。老板查看草稿并批准发布，客户随后能查看和下载；总管确认发布后完成运行。

合成演示材料在 `fixtures/mvp/receipt-01.png` 至 `receipt-06.png`，使用 **`statement-live.csv`**，工作室填写 **松石设计工作室**，账期 **2026-10**。预期四笔匹配、270 元差异、重复件及一笔缺票。原 `statement.csv` 保留给独立 AI CLI，字段不同，不直接上传到本机业务 API。

业务 CSV：

```csv
transaction_date,counterparty,direction,amount,description,external_id
2026-10-10,示例交易方,OUT,108.00,付款,example-001
```

金额单位元，后端 Decimal 转整数分；方向 `IN/OUT`。最多 200 行，每单一份 CSV，修正请建新单。票据最多 20 张、每张 5 MB。字段不清晰时补充新票据并关联替换原件，旧文件与历史批次继续保留。

## 运行与契约

生产工作流在 `server/app/live/`；`app/agents/` 的 MiMoRunner、独立 CLI 与离线样例继续保留。角色输入输出在 `live/contracts.py`，持久化表由迁移 `0008_live_workflow` 创建。

- 总管 Pro：实际派单、登记人工等待、确认人工发布后的完成；完整快照由受控服务在每轮调用前注入，模型必须执行动作工具取得回执。
- 票据 Flash：实际读取图片并调用 Flash 提取，代码解析金额、校验必填字段并幂等保存。可选税额/票种未知保留，不作为流水匹配必填项；低置信度或关键字段未知进入待确认。
- 核对 Pro：调用现有对账引擎产生批次，再解释实际工具结果。外部请求不能绕过派单直接对当前运行对账。
- 客服 Flash：受理、询问草稿与本订单只读问答；询问经老板确认后通过站内补充流程处理。
- 风险交付 Pro：风险摘要、真实批次与决定对应的报告草稿；无批准或发布权限。

`WorkflowRun` 保存预算、租约、检查点和人工等待；`Delegation` 保存总管决策、角色、目标、输入引用、版本和回执；`WorkflowArtifact` 保存幂等成果；`OrderMessage` 保存实际会话。现有 AgentRun/Task、报告绑定逻辑运行或输入版本。

一个 Worker，处理槽位一、问答槽位一，HTTP 模型请求共享并发上限二；票据批内并发最多二。租约 60 秒、心跳每 5 秒。人工等待与 FileCheckpointStorage 指针原子落盘后释放槽位。重启 Worker 即可领取待运行/租约过期的工作，不重复已保存票据和批次。

`input_revision` 在材料、补充和人工决定改变时递增。处理排队或运行时禁止修改输入。客户材料写入和老板决定携带预期版本，过期返回 409；旧报告不能批准或发布，退回报告必须创建新版本。已发布历史仍保留，不能用旧批准交付新内容。

新增接口（前缀 `/api/v1`）：

| 接口 | 用途 |
| --- | --- |
| `POST /orders/{id}/runs` | 幂等创建运行，202 |
| `GET /orders/{id}/runs/current` | 状态、阶段、输入版本、预算、安全错误 |
| `POST /runs/{id}/retry` | 唤醒总管，保留预算 |
| `GET/POST /orders/{id}/messages` | 持久化材料消息与问答排队 |
| `GET /orders/{id}/invoices` | 当前有效票据 |
| `GET /templates/statement.csv` | 标准流水模板 |
| `GET /owner/dashboard` | 实际订单、角色、待办与心跳 |
| `GET /owner/agents/{role}/trace` | 老板可见派单、工具成果与决策摘要 |
| `GET /owner/events/stream` | 跨订单事件续传 |

复用上传、CSV 导入、异常补充/决定、报告审核和下载接口。客户事件按字段白名单过滤，不包含老板决定内容、内部任务载荷、模型私有推理或未发布报告。老板静态资产来自 `sunset@451c88a87d196cb257ceee5d9e4c0eb3d415a291`，仅通过 FastAPI 白名单提供 `HTML/owner/`；旧原型通过独立的 `/workspace/` 路由提供历史演示，不使用真实老板端审批数据。Next 关闭代理压缩以保持 SSE 逐帧到达。

## 验证

在 `server/`：

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check app/agents app/live scripts tests/agents tests/test_live.py tests/live_support.py tests/browser_stack.py
.venv\Scripts\python.exe -m alembic check
```

在 `web/`：

```powershell
npm test
npm run typecheck
npm run build
npx playwright install chromium
npm run test:e2e
```

Playwright 启动独立临时数据库、8010 API、3211 Next 和显式测试 Worker，使用两个浏览器上下文运行上传至交付全链路。仅该测试入口注入替身模型，业务服务、数据库、工具派单、审批、SSE 和下载都真实执行；生产 Worker 不读取该替身。测试不需 API 密钥、不修改本机业务数据库。请勿将测试模式作为真实模型验收。

在三个本机服务已运行后，显式执行收费真实模型验证（仅合成材料、脚本模拟人工决定）：

```powershell
# server 目录
.venv\Scripts\python.exe -X utf8 scripts/verify_live_integration.py --simulate-synthetic-review
```

脚本检查四笔匹配、270 元差额、补充后保留差异、报告发布及各角色工具回执，脱敏结果写到 `server/data/live-verification.json`。不得对客户真实订单使用模拟审批参数。已核验记录见 [联调记录](verification/live-integration.json)。本地 `.env`、SQLite、上传材料、检查点和日志均忽略，不提交仓库。

本次本机验收：106 项基础与联调回归，加上流式请求总时限回归，共 107 项后端测试；前端 8 项业务测试、类型检查、生产构建和双浏览器主流程通过。真实 MiMo 合成订单使用 60/64 次请求完成交付，金额差异仍为 270 元，人工决定由验证脚本明确模拟。
真实客服问答另以 6/6 次请求完成，保留异常不等于自动核销，引用经本订单证据校验。脱敏记录见 [真实问答](verification/live-chat.json)。
