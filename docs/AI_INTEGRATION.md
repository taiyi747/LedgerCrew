# 第一阶段 AI 模块接入说明

## 交付范围

本模块实现 MVP 五个角色、真实 MiMo 调用、显式工作流、人工待办、报告草稿、检查点恢复与持久请求预算。Python **3.14** 为本次实际运行和验证版本。

前后端继续负责 HTTP、身份与订单权限、正式数据库、文件存储、业务对账、Worker 租约和报告发布。`FixtureBackend` 仅供合成材料演示，不能用于客户订单。

政策研究、税务计算及申报材料按第二阶段计划推进。

## 安装与配置

在仓库根目录执行：

```powershell
uv sync --project server --extra dev --frozen --python D:\python\python.exe
```

也可创建 Python 3.14 虚拟环境，安装 `server[dev]`；可复现安装优先使用已提交的 `server/uv.lock`。

本地配置文件为 `server/.env`，Git 已忽略。用 `server/.env.example` 作为模板，配置 `MIMO_API_KEY`。其余默认配置：

| 配置 | 默认值 |
| --- | --- |
| `MIMO_BASE_URL` | `https://api.xiaomimimo.com/v1` |
| `MIMO_MODEL_PRO` | `mimo-v2.6-pro` |
| `MIMO_MODEL_FLASH` | `mimo-v2.6-flash` |
| `MIMO_TIMEOUT_SECONDS` | 60 |
| `MIMO_TRANSIENT_RETRIES` | 2 |
| `MIMO_OUTPUT_RETRIES` | 2 |
| `MIMO_MAX_REQUESTS` | 64 |
| `LEDGERCREW_DATA_DIR` | `data`，相对 CLI 的 `server/` |

Flash 用于票据和客服，Pro 用于总管、工具核对与报告。配置密钥同时用于兼容客户端及 MiMo 的 `api-key` 头；密钥不进入事件和验证记录。

普通生成优先使用原生结构化输出，接口明确拒绝 `response_format/json_schema/strict` 时转为 JSON＋Pydantic 校验。**携带工具的运行直接使用 JSON＋Pydantic，首次 `tool_choice=required`，之后由框架恢复自动选择。** 这避免 MiMo 在同时请求严格 schema 时直接生成摘要而省略工具。工具结果未实际成功返回时不进入报告。

## 后端要实现的依赖

权威类型在 `server/app/agents/contracts.py`；存储模型通过适配器转换，复用这些类型。

| 方法 | 责任 |
| --- | --- |
| `load_order(order_id) -> OrderInput` | 返回当前订单、输入版本、票据元数据、规范化流水、客户说明 |
| `read_invoice(order_id, file_id) -> bytes` | 按已授权订单读取不可变图片，支持 PNG/JPEG，最多 5 MB |
| `reconcile(order, invoices) -> ReconciliationResult` | 运行后端确定性对账；返回匹配、异常、汇总与证据 |
| `save_artifact(identity, kind, payload, idempotency_key) -> str` | 幂等保存成果与版本，返回成果标识 |
| `load_artifact(identity, kind) -> dict \| None` | 返回该逻辑运行的该类最新成果，供缓存、预算和过期待办校验 |
| `emit_event(AgentEvent)` | 按 `event_id` 幂等保存，再由后端映射为 SSE |

### 存储要求

- `identity` 包含 `order_id`、`run_id`、输入 `revision`。每次修正材料、规范化流水或客户说明，后端递增输入版本。
- 同一 `order_id/run_id` 同时只允许一个执行者，租约覆盖开始、重试和恢复；单工作流内部最多并行识别两张图片。
- `save_artifact` 的幂等键作用域为订单／运行；相同键不同内容应拒绝。写入需要事务，跨节点成果先保存后交接。
- `load_artifact` 的查找范围是整个逻辑运行，**不按当前 revision 过滤**。`usage` 预算必须跨输入版本与进程持续累计；review/report 读取后由模块校验版本。
- `usage` 由运行内锁串行更新，并在发送每个 HTTP 请求前落盘。后端执行租约防止跨进程同时更新；失败、超时、schema 兼容重试均计数。
- `invoice:<file_id>:<sha256>` 是不可变图片的提取缓存；图片变化产生新键，修正文本说明不会覆盖原始识别。
- `reconciliation:<revision>` 是当前输入版本的确定性结果。相同 revision 必须对应相同输入；新的人工修订需递增 revision。
- 成果种类还包括 `invoices`、`supervisor`、`customer_draft`、`review`、`report`、`approval`、`model_usage` 和无鉴权信息的 `wire_request`。
- `model_usage` 历史记录包含角色、模型、耗时和供应商可获得的 token 用量；`usage.requests` 包含所有实际请求尝试。

## 开始与恢复工作流

```python
from pathlib import Path
from app.agents import build_workflow, create_checkpoint_storage
from app.agents.contracts import RunIdentity, HumanReply

identity = RunIdentity(order_id="order_001", run_id="run_001", revision=1)
storage = create_checkpoint_storage(Path("data/checkpoints/order_001/run_001"))
name = "ledgercrew-order_001-run_001"
workflow = build_workflow(deps, storage, name)

# 在 Worker 中调用；HTTP 创建任务接口及时返回。
result = await workflow.run(identity)
pending = result.get_request_info_events()
checkpoint = await storage.get_latest(workflow_name=name)
# 保存 name、checkpoint.checkpoint_id、pending 的 request_id、类型、输入及报告版本。

# 收到已通过后端权限与幂等校验的人工决定后，创建新 workflow 对象即可恢复。
workflow = build_workflow(deps, storage, name)
reply = HumanReply(
    identity=pending[0].data.identity,
    request_id=pending[0].request_id,
    action="keep_flagged",
    comment="保留异常，继续生成报告。",
)
result = await workflow.run(
    checkpoint_id=checkpoint.checkpoint_id,
    responses={reply.request_id: reply},
)
```

使用 `create_checkpoint_storage` 注册本模块明确允许恢复的数据类型。不要从客户提交内容导入任意类型或接受客户提供的框架消息历史。运行恢复必须使用同一工作流名称和兼容的图结构；升级图结构前完成旧任务或为新图另建运行。

`result.get_request_info_events()` 返回框架人工待办；`event.data` 为 `ReviewRequest`，应保存其 `request_id`。框架等待后返回调用，不保持长 HTTP 请求。

| 待办类型 | 允许动作 | 后端接入行为 |
| --- | --- | --- |
| `exception` | `request_info` / `keep_flagged` | 老板审核询问草稿，决定请求补充或保留异常 |
| `customer` | `submit_information` | 先保存客户说明／新材料，递增同一运行的输入 revision，再回复原待办 |
| `delivery` | `approve_delivery` / `revise_report` | 校验老板权限、待办和报告版本；交付回复必须携带 `report_version` |

客户补充的 `HumanReply.identity` 仍对应原待办版本；`load_order` 必须返回更高 revision。模块重新读取材料与对账，文字说明不会消除已发现的金额差异。`keep_flagged` 的说明保存在本次报告上下文，后端同时保留原审批记录。

模块校验回复绑定、当前待办、当前订单版本与报告版本，因此旧检查点中的过期待办不能批准新成果。后端仍负责登录权限、单次审批幂等及发布权限。

批准后 `result.get_outputs()` 包含 `RunOutcome(status="delivery_approved")`。其报告包含权威对账金额、未解决事项、来源和说明。后端按批准的报告版本发布；AI 模块本身不发布报告、不发送外部消息。

报告和询问的自然语言不生成数字事实：报告数值保留在结构化对账结果中，询问明细由程序从工具结果渲染为人民币元，避免单位转换或号码改写。

## 业务事件

`AgentEvent` 包含运行身份、稳定 `event_id`、`agent`、`type`、`message`、`data`、`evidence_refs` 和 UTC 时间。事件类型为 `started/completed/waiting/failed/delivery_approved`。`waiting.data.review` 给出完整待办，核对工具成功事件保存确定性结果。

事件不是权限证明；后端按订单身份过滤后再发布 SSE。模型失败会记录 `failed` 并抛出异常，不以“完成”代替失败。

## 独立演示命令

下列命令在仓库根目录执行，使用真实 MiMo 和明确标注的合成材料／测试对账后端，包含模型调用费用。

```powershell
server/.venv/Scripts/python.exe -m app.agents.cli fixtures
server/.venv/Scripts/python.exe -m app.agents.cli smoke
server/.venv/Scripts/python.exe -m app.agents.cli start
server/.venv/Scripts/python.exe -m app.agents.cli status
```

按输出的待办标识依次执行：

```powershell
server/.venv/Scripts/python.exe -m app.agents.cli resume --request-id <异常待办> --action request_info --comment "请补充差额说明和凭证"
server/.venv/Scripts/python.exe -m app.agents.cli supplement --request-id <客户待办> --comment "差额原因尚未核实，票据仍待补充"
server/.venv/Scripts/python.exe -m app.agents.cli resume --request-id <新异常待办> --action keep_flagged
server/.venv/Scripts/python.exe -m app.agents.cli resume --request-id <交付待办> --action approve_delivery --report-version 1
```

每个命令创建新的 Python 进程。运行失败时使用 `retry` 从最近检查点继续；尚无检查点则从起点重试，预算不重置。重新开始整套样例可配置新的 `LEDGERCREW_DATA_DIR`，保留之前证据。CLI 使用操作系统文件锁限制同一订单同时运行；正式 Worker 使用后端租约。

## 测试

```powershell
uv run --project server --frozen --extra dev pytest server/tests -q
uv run --project server --frozen --extra dev ruff check server/app server/tests server/scripts
```

pytest 使用测试替身和 HTTP 模拟，不发送真实 API 请求，不要求密钥。`smoke` 和演示命令为显式真实调用。模型图片提取的字段不确定时必须保留人工确认；对账与报告不保证所有原始识别字段已被人类逐项核实。

完整真实验证脚本：

```powershell
server/.venv/Scripts/python.exe server/scripts/verify_live.py --simulate-human-review
```

该命令新建独立数据目录，以六个 Python 子进程执行开始、请求补充、客户回复、生成报告、批准和重复批准。模型调用真实，人工决定由测试操作者明确模拟，仅使用合成样例，不用于客户订单。验证摘要保存在该运行的 `verification.json` 中。

已提交的脱敏记录：[真实调用验证](verification/ai-live.json) · [人工待办样例](examples/ai-review.json) · [报告样例](examples/ai-report.json) · [业务事件样例](examples/ai-event.json)。
