"""Bridge a persisted backend Agent task to the existing MAF MiMo model runner."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import select
from sqlalchemy import text as sql_text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.config import Settings as MiMoSettings
from app.agents.contracts import RunIdentity
from app.agents.errors import RequestBudgetExceeded
from app.agents.runner import MiMoRunner, ModelRunner, RequestBudget
from app.integrations.agents.contracts import AgentInvocationRequest, AgentInvocationResponse, contract_for
from app.models import AgentModelArtifact, AgentTask, UploadedFile
from app.storage.base import Storage


class TaskModelArtifacts:
    """Save budget reservations before network requests, independent of task transaction."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], task_id: str) -> None:
        self.sessions = sessions
        self.task_id = task_id

    async def reserve_request(self, limit: int) -> str:
        """SQLite write lock serializes reservations across processes and budget instances."""
        async with self.sessions() as db:
            await db.execute(sql_text("BEGIN IMMEDIATE"))
            latest = await db.scalar(select(AgentModelArtifact).where(
                AgentModelArtifact.task_id == self.task_id, AgentModelArtifact.kind == "usage")
                .order_by(AgentModelArtifact.id.desc()).limit(1))
            count = int(latest.payload["requests"]) if latest else 0
            if count >= limit:
                await db.rollback()
                raise RequestBudgetExceeded(f"本次运行已达到 {limit} 次模型请求上限，请人工处理。")
            next_count = count + 1
            item = AgentModelArtifact(
                task_id=self.task_id, kind="usage", idempotency_key=f"usage:{next_count}",
                payload={"requests": next_count, "limit": limit, "state": "reserved"})
            db.add(item)
            await db.flush()
            reservation_id = str(item.id)
            await db.commit()
            return reservation_id

    async def settle_request(self, identity: RunIdentity, reservation_id: str, status: str,
                             http_status: int | None, usage: dict[str, int] | None) -> None:
        """First settlement wins; missing provider usage remains explicitly unknown."""
        payload = {"reservation_id": reservation_id, "status": status,
                   "http_status": http_status, "usage": usage,
                   "usage_status": "known" if usage else "unknown"}
        async with self.sessions() as db:
            key = f"settlement:{reservation_id}"
            existing = await db.scalar(select(AgentModelArtifact.id).where(
                AgentModelArtifact.task_id == self.task_id,
                AgentModelArtifact.idempotency_key == key))
            if existing is not None:
                return
            db.add(AgentModelArtifact(task_id=self.task_id, kind="model_settlement",
                                      idempotency_key=key, payload=payload))
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()  # Another worker's first settlement is authoritative.

    async def save_artifact(self, identity: RunIdentity, kind: str,
                            payload: dict[str, Any], idempotency_key: str) -> str:
        async with self.sessions() as db:
            existing = await db.scalar(select(AgentModelArtifact).where(
                AgentModelArtifact.task_id == self.task_id,
                AgentModelArtifact.idempotency_key == idempotency_key))
            if existing is not None:
                if existing.kind != kind or existing.payload != payload:
                    raise ValueError("Model artifact idempotency conflict")
                return str(existing.id)
            artifact = AgentModelArtifact(task_id=self.task_id, kind=kind,
                                          idempotency_key=idempotency_key, payload=payload)
            db.add(artifact)
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                existing = await db.scalar(select(AgentModelArtifact).where(
                    AgentModelArtifact.task_id == self.task_id,
                    AgentModelArtifact.idempotency_key == idempotency_key))
                if existing is None or existing.kind != kind or existing.payload != payload:
                    raise ValueError("Model artifact idempotency conflict") from None
                return str(existing.id)
            return str(artifact.id)

    async def load_artifact(self, identity: RunIdentity, kind: str) -> dict[str, Any] | None:
        async with self.sessions() as db:
            item = await db.scalar(select(AgentModelArtifact).where(
                AgentModelArtifact.task_id == self.task_id, AgentModelArtifact.kind == kind)
                .order_by(AgentModelArtifact.id.desc()).limit(1))
            return item.payload if item else None


class MiMoAgentGateway:
    """One contract-validated task per call; full multi-agent workflow remains separate."""

    _ROLES: ClassVar[dict[str, str]] = {
        "customer_reception": "customer_service",
        "material_review": "invoice",
        "invoice_extraction": "invoice",
        "reconciliation_summary": "delivery",
        "risk_analysis": "delivery",
        "report_draft": "delivery",
    }

    def __init__(self, sessions: async_sessionmaker[AsyncSession], storage: Storage,
                 settings: MiMoSettings, runner: ModelRunner | None = None) -> None:
        self.sessions = sessions
        self.storage = storage
        self.settings = settings
        self.runner = runner or MiMoRunner(settings)

    async def invoke(self, request: AgentInvocationRequest) -> AgentInvocationResponse:
        input_model, output_model = contract_for(
            request.agent_role, request.task_type, request.input_schema_version)
        validated_input = input_model.model_validate(request.input_payload)
        async with self.sessions() as db:
            task = await db.get(AgentTask, request.task_id)
            if (task is None or task.status != "running" or task.run_id != request.run_id
                    or task.order_id != request.order_id or task.task_type != request.task_type
                    or task.agent_name != request.agent_role or task.input_data != request.input_payload):
                raise ValueError("Agent task does not match persisted running request")
            attempt = task.attempt_count
            image = None
            if request.task_type in {"material_review", "invoice_extraction"}:
                source = await db.get(UploadedFile, validated_input.file_id)
                if (source is None or source.order_id != request.order_id
                        or source.validation_status != "valid"
                        or source.mime_type not in {"image/png", "image/jpeg"}):
                    raise ValueError("Agent image source is invalid")
                data = self.storage.read(source.storage_key)
                if hashlib.sha256(data).hexdigest() != source.sha256:
                    raise ValueError("Agent image checksum mismatch")
                image = (data, source.mime_type)
        identity = RunIdentity(order_id=request.order_id, run_id=request.run_id, revision=max(1, attempt))
        artifacts = TaskModelArtifacts(self.sessions, request.task_id)
        budget = RequestBudget(artifacts, identity, self.settings.max_requests)
        prompt = (
            "根据下列已校验的业务输入完成当前任务。未知信息留空，不编造事实。"
            "金额、统计和证据引用仅使用输入中提供的数据。只返回要求的 JSON。\n"
            + json.dumps(validated_input.model_dump(mode="json"), ensure_ascii=False)
        )
        started = datetime.now(UTC)
        output = await self.runner.generate(
            self._ROLES[request.task_type], prompt, output_model, budget, image=image)
        usage = await artifacts.load_artifact(identity, "model_usage") or {}
        metadata = {
            "provider": "mimo", "model": usage.get("model"), "usage": usage.get("usage"),
            "usage_status": usage.get("usage_status", "unknown"),
            "elapsed_ms": usage.get("elapsed_ms"), "attempt": attempt,
        }
        return AgentInvocationResponse(
            task_id=request.task_id, status="succeeded", output_payload=output.model_dump(mode="json"),
            started_at=started, finished_at=datetime.now(UTC), provider_metadata=metadata)
