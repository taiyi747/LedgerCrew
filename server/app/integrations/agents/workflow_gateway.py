"""Run the repository's existing MAF graph for a persisted backend task."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.checkpoints import create_checkpoint_storage
from app.agents.config import Settings as MiMoSettings
from app.agents.contracts import HumanReply, ReportDraft, ReviewRequest, RunIdentity
from app.agents.runner import MiMoRunner, ModelRunner
from app.agents.workflow import build_workflow, validate_reply
from app.integrations.agents.contracts import AgentInvocationRequest, AgentInvocationResponse
from app.integrations.agents.gateway import AgentGateway
from app.integrations.agents.workflow_backend import DatabaseWorkflowBackend
from app.models import AgentRun, AgentTask, ReportVersion
from app.services import report_service
from app.storage.base import Storage


class FullWorkflowGateway:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], storage: Storage,
                 checkpoint_root: Path, settings: MiMoSettings,
                 runner: ModelRunner | None = None) -> None:
        self.sessions = sessions
        self.storage = storage
        self.checkpoint_root = checkpoint_root
        self.settings = settings
        self.runner = runner or MiMoRunner(settings)

    async def invoke(self, request: AgentInvocationRequest) -> AgentInvocationResponse:
        if request.task_type != "full_workflow" or request.agent_role != "supervisor":
            raise ValueError("Full workflow task contract is required")
        async with self.sessions() as db:
            task = await db.get(AgentTask, request.task_id)
            if (task is None or task.status != "running" or task.order_id != request.order_id
                    or task.run_id != request.run_id or task.input_data != request.input_payload):
                raise ValueError("Workflow task is not the current running task")
            run = await db.get(AgentRun, task.run_id)
            saved = dict(run.checkpoint_data or {})
        identity = RunIdentity(order_id=request.order_id, run_id=request.run_id,
                               revision=request.input_payload["revision"])
        backend = DatabaseWorkflowBackend(self.sessions, self.storage, request.task_id)
        path = self.checkpoint_root / request.order_id / request.task_id
        checkpoint_storage = create_checkpoint_storage(path)
        name = "ledgercrew-backend-" + request.task_id
        workflow = build_workflow(backend, checkpoint_storage, name, runner=self.runner,
                                  max_requests=self.settings.max_requests)
        started = datetime.now(UTC)
        if saved.get("checkpoint_id"):
            current = await checkpoint_storage.get_latest(workflow_name=name)
            if current is None or current.checkpoint_id != saved["checkpoint_id"]:
                raise ValueError("Workflow checkpoint is missing or has changed")
            if not saved.get("reply"):
                return self._paused(request, started, saved)
            review = ReviewRequest.model_validate(saved["review_request"])
            reply = HumanReply.model_validate(saved["reply"])
            validate_reply(review, reply)
            result = await workflow.run(
                checkpoint_id=current.checkpoint_id, responses={review.request_id: reply})
        else:
            result = await workflow.run(identity)
        checkpoint = await checkpoint_storage.get_latest(workflow_name=name)
        pending = result.get_request_info_events()
        outputs = result.get_outputs()
        if len(pending) == 1 and not outputs:
            review = ReviewRequest.model_validate(pending[0].data)
            report_id = None
            if review.kind == "delivery":
                raw_report = await backend.load_artifact(identity, "report")
                if raw_report is None:
                    raise ValueError("Delivery review has no persisted report")
                async with self.sessions() as db:
                    report = await report_service.create_from_workflow(
                        db, request.task_id, ReportDraft.model_validate(raw_report))
                    if report.status == "draft":
                        await report_service.submit_workflow_review(db, report.id)
                    report_id = report.id
            if checkpoint is None:
                raise ValueError("Workflow pause has no checkpoint")
            saved = {"checkpoint_id": checkpoint.checkpoint_id,
                     "review_request": review.model_dump(mode="json"),
                     "report_id": report_id, "reply": None}
            async with self.sessions() as db:
                run = await db.get(AgentRun, request.run_id)
                run.checkpoint_data = saved
                await db.commit()
            return self._paused(request, started, saved)
        if len(outputs) != 1 or pending:
            raise ValueError("Workflow ended without a single approved result")
        outcome = outputs[0]
        if outcome.status != "delivery_approved" or not saved.get("report_id"):
            raise ValueError("Workflow approval does not match a report")
        async with self.sessions() as db:
            report = await db.get(ReportVersion, saved["report_id"])
            if report is None or report.workflow_task_id != request.task_id:
                raise ValueError("Workflow report identity differs")
        return AgentInvocationResponse(
            task_id=request.task_id, status="succeeded",
            output_payload={"order_id": request.order_id, "report_id": report.id,
                            "report_version": report.version,
                            "approval_request_id": outcome.approval_request_id},
            started_at=started, finished_at=datetime.now(UTC),
            provider_metadata={"provider": "mimo", "workflow": "maf-v1",
                               "checkpoint_id": checkpoint.checkpoint_id if checkpoint else None})

    @staticmethod
    def _paused(request: AgentInvocationRequest, started: datetime,
                checkpoint: dict) -> AgentInvocationResponse:
        return AgentInvocationResponse(
            task_id=request.task_id, status="paused", started_at=started,
            provider_metadata={"workflow": "maf-v1", "checkpoint_id": checkpoint["checkpoint_id"],
                               "review_kind": checkpoint["review_request"]["kind"],
                               "report_id": checkpoint.get("report_id")})


class RoutedAgentGateway:
    def __init__(self, single_task: AgentGateway, full_workflow: AgentGateway) -> None:
        self.single_task = single_task
        self.full_workflow = full_workflow

    async def invoke(self, request: AgentInvocationRequest) -> AgentInvocationResponse:
        if request.task_type == "full_workflow":
            return await self.full_workflow.invoke(request)
        return await self.single_task.invoke(request)
