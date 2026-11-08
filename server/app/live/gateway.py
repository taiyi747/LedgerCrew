from __future__ import annotations

import json

from app.agents.config import Settings
from app.agents.contracts import RunIdentity
from app.agents.errors import AgentError
from app.agents.runner import MiMoRunner, RequestBudget
from app.db.types import utc_now
from app.integrations.agents.contracts import AgentInvocationResponse, contract_for
from app.live import service
from app.live.contracts import RUNNER_ROLES
from app.live.models import WorkflowRun
from app.models import Order


class BudgetStore:
    def __init__(self, sessions, run_id, lease_token):
        self.sessions, self.run_id, self.lease_token = sessions, run_id, lease_token

    async def _run(self, session):
        run = await session.get(WorkflowRun, self.run_id)
        if (
            run is None
            or run.lease_token != self.lease_token
            or run.status != "running"
            or not run.lease_expires_at
            or run.lease_expires_at <= utc_now()
        ):
            raise AgentError("运行租约已失效，拒绝写入旧执行结果。")
        return run

    async def load_artifact(self, identity, kind):
        async with self.sessions() as session:
            run = await self._run(session)
            if kind == "usage":
                return {"requests": run.requests_used, "limit": run.request_limit}
            record = await service.artifact(session, run.id, kind)
            return record.payload if record else None

    async def save_artifact(self, identity, kind, payload, idempotency_key):
        async with self.sessions() as session:
            run = await self._run(session)
            if kind == "usage":
                if payload["requests"] != run.requests_used + 1 or payload["requests"] > run.request_limit:
                    raise AgentError("请求计数冲突或已达到上限。")
                run.requests_used = payload["requests"]
                await session.commit()
                return "usage-" + str(run.requests_used)
            record = await service.save_artifact(session, run, kind, payload, idempotency_key)
            await session.commit()
            return record.id


class RealMiMoAgentGateway:
    """Real provider adapter; a runner override is explicit and test-only."""

    def __init__(self, sessions, run_id, lease_token, *, runner=None):
        self.sessions, self.run_id, self.lease_token = sessions, run_id, lease_token
        self.runner = runner or MiMoRunner(Settings.from_env())
        self.store = BudgetStore(sessions, run_id, lease_token)
        self.budget = None

    async def generate(self, role, prompt, schema, *, image=None, tools=None):
        async with self.sessions() as session:
            run = await self.store._run(session)
            order = await session.get(Order, run.order_id)
            identity = RunIdentity(order_id=run.order_id, run_id=run.id, revision=order.input_revision)
            if self.budget is None:
                self.budget = RequestBudget(self.store, identity, run.request_limit)
            else:
                self.budget.identity = identity
        return await self.runner.generate(
            RUNNER_ROLES.get(role, role), prompt, schema, self.budget, image=image, tools=tools
        )

    async def invoke(self, request):
        """Compatibility with the existing trusted backend task contract."""
        from app.models import UploadedFile
        from app.storage.local import get_storage

        started = utc_now()
        _, output_model = contract_for(request.agent_role, request.task_type, request.input_schema_version)
        role = {"material_review": "invoice_processing"}.get(request.agent_role, request.agent_role)
        image = None
        if request.task_type in {"material_review", "invoice_extraction"}:
            async with self.sessions() as session:
                file = await session.get(UploadedFile, request.input_payload["file_id"])
                if not file or file.order_id != request.order_id or file.validation_status != "valid":
                    raise AgentError("网关材料不属于当前订单或未通过格式验证。")
                image = (get_storage().read(file.storage_key), file.mime_type)
        tools = None
        if request.task_type == "reconciliation_summary":

            async def reconcile_transactions() -> str:
                """Read the backend-validated reconciliation snapshot."""
                import json

                return json.dumps(request.input_payload, ensure_ascii=False)

            tools = [reconcile_transactions]
        result = await self.generate(
            role,
            "按后端契约处理任务，仅使用提供的真实数据。不得编造金额、数量、来源或已经完成的审批。报告摘要使用定性说明，精确数字只复用输入中提供的字段。保留 accepted_unresolved 异常披露，不能说差额已消除。"
            "输出文字面向客户：不得出现 UUID、异常编号、字段名或以「分」计的金额，这些由后端明细表展示。\n"
            + json.dumps(request.input_payload, ensure_ascii=False),
            output_model,
            image=image,
            tools=tools,
        )
        return AgentInvocationResponse(
            task_id=request.task_id,
            status="succeeded",
            output_payload=result.model_dump(mode="json"),
            started_at=started,
            finished_at=utc_now(),
            provider_metadata={"provider": "mimo"},
        )
