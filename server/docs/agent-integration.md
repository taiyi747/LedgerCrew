# Agent 接入说明（v0.1）

后端只负责结构化契约、调用边界、状态与事件持久化。本阶段不包含 Prompt、模型调用、OCR、Agent 推理或 Microsoft Agent Framework WorkflowBuilder 实现。其他开发者可以实现 `AgentGateway`，并在其可信编排代码中调用 `agent_service`。当前没有对客户开放的任务创建或调用 HTTP 接口。

## 角色、任务类型与契约

契约位于 `app/integrations/agents/contracts.py`，使用 Pydantic 2。当前只支持 `input_schema_version="1.0"`。输入和输出均拒绝未知字段。

| Agent 角色 | `task_type` | 输入 / 输出 |
| --- | --- | --- |
| `customer_reception` | `customer_reception` | `CustomerReceptionInput` / `CustomerReceptionOutput` |
| `material_review` | `material_review` | `MaterialReviewInput` / `MaterialReviewOutput` |
| `invoice_processing` | `invoice_extraction` | `InvoiceExtractionInput` / `InvoiceExtractionOutput` |
| `data_reconciliation` | `reconciliation_summary` | `ReconciliationAgentInput` / `ReconciliationAgentOutput` |
| `risk_delivery` | `risk_analysis` | `RiskAnalysisInput` / `RiskAnalysisOutput` |
| `risk_delivery` | `report_draft` | `ReportDraftInput` / `ReportDraftOutput` |

发票金额在 Agent 输出中是**原样字符串**；后端用 `Decimal` 严格解析并转换为整数分，超过两位小数直接拒绝。`ReconciliationAgentInput` 载入后端确定性对账结果；其输出只允许叙述、观察、未解决事项和证据引用，不含可覆盖金额、匹配或异常类型的字段。风险和报告草稿输出同样不能更改业务数据。Agent 输出仅存入 AgentTask/AgentRun，不会自动写原始文件、流水、审批、异常类型或已发布报告。

## 实现网关

实现 `app/integrations/agents/gateway.py` 中的 `AgentGateway` Protocol：

```python
class MyAgentGateway:
    async def invoke(self, request: AgentInvocationRequest) -> AgentInvocationResponse:
        # 调用队友提供的 Agent；将其结果映射为结构化响应。
        ...
```

请求包含 `task_id`、`run_id`、`order_id`、`agent_role`、`task_type`、`input_schema_version`、`idempotency_key`、`correlation_id` 和 `input_payload`。响应包含 `task_id`、`status`、`output_payload`、`error`、带时区的 `started_at`/`finished_at`、`provider_metadata`。网关应把幂等键和关联 ID 传递给外部执行方，并保留调用关联信息。成功响应必须有输出和完成时间；失败响应必须有错误和完成时间；暂停响应没有完成时间。

创建任务时，后端会检查输入文件属于当前订单、票据图片类别与 MIME 匹配；`invoice_extraction` 还要求该文件的最新材料审核任务结果为 `ACCEPTED` 且 `is_invoice=true`。风险输入必须与当前订单的异常工单一致；对账和报告草稿输入的金额、计数及关联 ID 必须与持久化对账批次一致。后端在写入成功结果前按任务类型验证输出，并检查 `file_id`、`exception_id`、报告 `order_id`/版本号与任务输入一致。调用异常、非法响应或非法输出会使任务和运行进入 `failed`，错误被记录，不会改写原始业务数据。终态任务再次调用 `invoke_task` 不会重新调用网关。

票据识别成功后，可信编排器调用 `app.services.reconciliation_service.persist_invoice_from_task(session, task_id)` 写入 `InvoiceRecord`，并提交当前事务。该函数只接受已成功的 `invoice_processing/invoice_extraction` 任务，再次核查材料审核结果、文件归属及金额格式；发票记录保留 `source_file_id`、`material_review_task_id`、`source_task_id`。同一识别任务重复调用返回原记录。调用方不能把未审核图片或未经校验的 Agent 字符串直接当作确定性金额。

## 创建、执行和恢复任务

```python
from app.schemas.agent import AgentTaskCreate
from app.services import agent_service

task = await agent_service.create_task(session, AgentTaskCreate(
    order_id=order_id,
    agent_role="customer_reception",
    task_type="customer_reception",
    input_schema_version="1.0",
    idempotency_key="reception:order-123:v1",
    correlation_id="request-456",
    input_payload={
        "order_id": order_id,
        "customer_message": "请整理本月账目",
        "submitted_file_ids": [],
    },
))
task = await agent_service.invoke_task(session, task.id, my_gateway)
```

`create_task` 原子性创建一个 `AgentRun`、一个 `AgentTask`、排队事件和审计记录。当前一个运行对应一个任务；同一订单内 `(order_id, idempotency_key)` 唯一。相同键、相同内容重复提交返回原任务；相同键不同内容返回 `idempotency_conflict`。运行与任务状态为 `queued`、`running`、`paused`、`succeeded`、`failed`，与订单状态独立。

编排器也可调用 `start_task`、`pause_task`、`resume_task`、`complete_task`、`fail_task` 控制状态，或使用 `save_checkpoint(session, run_id, checkpoint)` 保存 JSON 检查点。每次转换和检查点写入均有数据库事件与审计记录。`app/workers/runner.py` 仅定义 `WorkflowRunner` 适配 Protocol，未来可接 WorkflowBuilder；当前没有工作流实现。大型文件检查点或 FileCheckpointStorage 的物理存储由未来适配器处理，数据库 JSON 检查点用于必要的恢复状态和关联信息。

`FakeAgentGateway` 位于 `fake_gateway.py`，必须显式传入预设结果，可模拟成功、失败和暂停。它仅供开发与测试使用；当 `ENVIRONMENT=production` 时调用会直接报错，生产环境不会自动配置 Fake。

## 事件与 SSE

每个事件保存递增 `event_id`（数据库列 `workflow_events.id`）、订单 ID、运行 ID、任务 ID、类型、JSON 载荷和 UTC 时间。受保护的客户事件流为：

```text
GET /api/v1/orders/{order_id}/events/stream
Last-Event-ID: 42
```

也可传 `?after_id=42`；它优先于 `Last-Event-ID`。事件按 ID 升序从数据库读取，响应为标准 SSE `id`、`event`、`data` 帧；空闲时发送心跳。`?follow=false` 只读取当前已有事件后关闭，适合调试和测试。访问权限沿用订单归属校验，无权限返回 404。轮询和心跳间隔由 `SSE_POLL_SECONDS`、`SSE_HEARTBEAT_SECONDS` 控制。

## 待确认事项

- 真实 Agent 运行框架、任务调度入口和认证方式由后续集成阶段确定。当前不会自动执行排队任务；完整业务流程仅由 Fake Agent 测试验证。
- 多任务运行与外部文件检查点的生命周期需要与队友的 WorkflowBuilder/FileCheckpointStorage 实现共同确定；当前按一个运行对应一个任务持久化。
- 客户可见的 Agent 进度文案和事件保留周期尚未定义；事件 API 当前返回已授权订单的原始结构化事件。
